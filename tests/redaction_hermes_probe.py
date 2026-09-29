"""Offline acceptance of PLAT-480 against real Hermes dispatch and parsers."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS


def deny_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
        raise RuntimeError('Network forbidden in PLAT-480 probe')


sys.addaudithook(deny_network)
sys.dont_write_bytecode = True
# CLI/gateway imports otherwise activate package provisioning even without main().
# This harness already has its interpreter; only bootstrap is stubbed, not dispatch.
sys.modules['hermes_bootstrap'] = ModuleType('hermes_bootstrap')
def forbidden_connect(*args, **kwargs):
    raise RuntimeError('Network forbidden in PLAT-480 probe')
sys.modules['hermes_bootstrap']._happy_eyeballs_create_connection = forbidden_connect
from hermes_cli.middleware import run_llm_execution_middleware
from hermes_cli.plugins import PluginContext, get_plugin_manager
from hermes_cli.plugins_manifest import PluginManifest
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from gateway.session_context import set_session_vars, clear_session_vars
from agent.transports import get_transport
from agent.turn_truncation import normalize_response_for_agent
from agent.turn_api_call import perform_api_call
from hermes_state import SessionDB

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from redaction_review_contracts import RedactionReviewContracts
spec = importlib.util.spec_from_file_location('fulcra_probe', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
assert spec and spec.loader
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)
MODES = ('chat_completions', 'anthropic_messages', 'codex_responses', 'bedrock_converse')


class RedactionContract(RedactionReviewContracts, unittest.TestCase):
    def setUp(self):
        self.home = Path(os.environ['HERMES_HOME']) / self._testMethodName
        self.home.mkdir()
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        manager = get_plugin_manager()
        manager._discovered = True  # Harness only: never discover installed plugins.
        self.ctx = PluginContext(PluginManifest(name='redaction-probe', path=str(ROOT)), manager)
        plugin.plugin_setup.register(self.ctx)
        self.setup = plugin.plugin_setup.Setup(self.ctx)
        self.guard = plugin.redaction.Redaction(self.ctx)
        self.plugin = plugin
        self.dispatch = run_llm_execution_middleware
        self.tokens = set_session_vars(session_id='session-A', source='cli')
        self.addCleanup(clear_session_vars, self.tokens)
        self.assertIn('1 phrases', self.setup.command('redact add synthetic-private-word'))
        self.request = {'messages': [{'role': 'user', 'content': 'synthetic-private-word'}]}

    def test_cli_slash_list_is_display_only(self):
        import cli
        from unittest.mock import Mock, patch
        from hermes_cli.plugins import get_plugin_command_handler
        from run_agent import AIAgent
        history = [{'role': 'user', 'content': 'existing history'}]
        shell = object.__new__(cli.HermesCLI)
        shell.config = {}
        shell.session_id = 'session-A'
        shell.conversation_history = history.copy()
        shell.agent = NS(conversation_history=history.copy(), run_conversation=Mock(side_effect=AssertionError('model invoked')))
        before = self.guard.load()
        with patch.object(cli, '_ensure_skill_commands', return_value={}), \
             patch.object(cli, 'get_skill_bundles', return_value={}), \
             patch.object(cli, '_cprint') as display, \
             patch.object(AIAgent, 'run_conversation', side_effect=AssertionError('model invoked')) as model, \
             patch.object(SessionDB, 'append_message', side_effect=AssertionError('history append')) as append, \
             patch.object(SessionDB, 'append_messages_batch', side_effect=AssertionError('history append')) as batch, \
             patch.object(PluginContext, 'inject_message', side_effect=AssertionError('injection')) as inject:
            self.assertTrue(shell.process_command('/fulcra redact list'))
            text = str(display.call_args)
            self.assertIn('synthetic-private-word', text)
            self.assertIn('{REDACTED-1}', text)
            model.assert_not_called()
            append.assert_not_called()
            batch.assert_not_called()
            inject.assert_not_called()
        self.assertEqual(shell.conversation_history, history)
        self.assertEqual(shell.agent.conversation_history, history)
        shell.agent.run_conversation.assert_not_called()
        self.assertEqual(self.guard.load(), before)
        self.assertIsNone(get_plugin_command_handler('redact'))
        self.assertIsNone(get_plugin_command_handler('unredact'))
        self.assertNotIn('synthetic-private-word', self.setup.command('unredact synthetic-private-word'))

    def test_tui_command_dispatch_list_is_display_only(self):
        from unittest.mock import patch
        from tui_gateway import server
        from run_agent import AIAgent
        self.setup.command('redact add shared-private --profile')
        clear_session_vars(self.tokens)
        self.tokens = set_session_vars(session_id='', source='tui')
        history = [{'role': 'user', 'content': 'existing history'}]
        session = {'session_key': 'agent:tui:probe', 'cwd': '', 'profile_home': str(self.home),
                   'history': history.copy(), 'agent': NS(session_id='session-A', conversation_history=history.copy())}
        before = self.guard.load()
        with patch.object(server, '_sessions', {'sid': session}), \
             patch.object(AIAgent, 'run_conversation', side_effect=AssertionError('model invoked')) as model, \
             patch.object(SessionDB, 'append_message', side_effect=AssertionError('history append')) as append, \
             patch.object(SessionDB, 'append_messages_batch', side_effect=AssertionError('history append')) as batch, \
             patch.object(PluginContext, 'inject_message', side_effect=AssertionError('injection')) as inject:
            result = server._methods['command.dispatch']('list', {
                'name': 'fulcra', 'arg': 'redact list --profile', 'session_id': 'sid'})['result']
            self.assertEqual(set(result), {'type', 'output'})
            self.assertEqual(result['type'], 'plugin')
            self.assertIn('shared-private', result['output'])
            self.assertNotIn('synthetic-private-word', result['output'])
            result = server._methods['command.dispatch']('session-list', {
                'name': 'fulcra', 'arg': 'redact list', 'session_id': 'sid'})['result']
            self.assertIn('synthetic-private-word', result['output'])
            self.assertIn('Inherited profile', result['output'])
            self.assertIn('shared-private', result['output'])
            slash = server._methods['slash.exec']('slash-list', {
                'command': '/fulcra redact list', 'session_id': 'sid'})['result']
            self.assertEqual(set(slash), {'output'})
            self.assertIn('synthetic-private-word', slash['output'])
            model.assert_not_called()
            append.assert_not_called()
            batch.assert_not_called()
            inject.assert_not_called()
        self.assertEqual(session['history'], history)
        self.assertEqual(session['agent'].conversation_history, history)
        self.assertEqual(self.guard.load(), before)

    def test_gateway_list_route_is_display_only(self):
        import asyncio
        from unittest.mock import patch
        from gateway.run import GatewayRunner
        from gateway.config import GatewayConfig, Platform
        from gateway.session import SessionSource
        from gateway.platforms.event import MessageEvent
        from run_agent import AIAgent
        self.setup.command('redact add shared-private --profile')
        runner = object.__new__(GatewayRunner)
        runner.config = GatewayConfig()
        runner._draining = False
        source = SessionSource(platform=Platform.TELEGRAM, chat_id='probe', user_id='probe', chat_type='dm')
        before = self.guard.load()
        with patch.object(AIAgent, 'run_conversation', side_effect=AssertionError('model invoked')) as model, \
             patch.object(SessionDB, 'append_message', side_effect=AssertionError('history append')) as append, \
             patch.object(SessionDB, 'append_messages_batch', side_effect=AssertionError('history append')) as batch, \
             patch.object(PluginContext, 'inject_message', side_effect=AssertionError('injection')) as inject:
            for suffix in (' --profile', ''):
                event = MessageEvent(text='/fulcra redact list' + suffix, source=source, message_id='probe')
                handled, output, command = asyncio.run(runner._hm_dispatch_quick_and_plugin_commands(event, source, 'fulcra'))
                self.assertTrue(handled)
                self.assertEqual(command, 'fulcra')
                if suffix:
                    self.assertIn('shared-private', output)
                    self.assertNotIn('synthetic-private-word', output)
                else:
                    self.assertIn('concrete session ID unavailable', output)
            model.assert_not_called()
            append.assert_not_called()
            batch.assert_not_called()
            inject.assert_not_called()
        self.assertEqual(self.guard.load(), before)

    def parse(self, response, mode):
        transport = get_transport(mode)
        self.assertTrue(transport.validate_response(response), mode)
        agent = NS(api_mode=mode, _get_transport=lambda: transport, _is_anthropic_oauth=False)
        return normalize_response_for_agent(agent, response)

    def test_request_and_state_failures_short_circuit_all_parsers(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                sent = []
                response = run_llm_execution_middleware({'messages': object()}, sent.append,
                                                        session_id='session-A', api_mode=mode)
                self.assertEqual(sent, [])
                parsed = self.parse(response, mode)
                self.assertIn('Local Fulcra privacy refusal', parsed.content)
                self.assertFalse(parsed.tool_calls)
                self.assertEqual(response.usage.total_tokens, 0)
        self.ctx.state.set(plugin.redaction.KEY, {'broken': True})
        sent = []
        response = run_llm_execution_middleware(self.request, sent.append, session_id='session-A')
        self.assertEqual(sent, [])
        self.assertIn('no provider call', self.parse(response, 'chat_completions').content)

    def test_real_call_roundtrip_and_stream_limit(self):
        sent, emitted = [], []
        def stream(request, on_first_delta):
            sent.append(request)
            self.assertNotIn('synthetic-private-word', str(request))
            emitted.append('{REDACTED-1}')
            return NS(choices=[NS(message=NS(content='{REDACTED-1}', tool_calls=[]), finish_reason='stop')])
        agent = NS(base_url='', provider='probe', model='probe', api_mode='chat_completions',
                   session_id='session-A', platform='cli', _has_stream_consumers=lambda: True,
                   _interruptible_streaming_api_call=stream, _has_pending_redirect=lambda: False)
        result = perform_api_call(agent, api_kwargs=self.request, _original_api_kwargs=self.request,
                                  _llm_middleware_trace=[], _moa_prepared_request=None, _retry=None,
                                  thinking_spinner=None, retry_count=0, api_call_count=0,
                                  api_request_id='r', effective_task_id='t', turn_id='turn', interrupted=False)
        self.assertEqual(len(sent), 1)
        self.assertEqual(emitted, ['{REDACTED-1}'])
        self.assertIn('synthetic-private-word', self.parse(result.response, 'chat_completions').content)
        self.assertEqual(self.request['messages'][0]['content'], 'synthetic-private-word')
        self.assertIn('Redaction off', self.setup.command('redact off'))
        raw_response = NS(choices=[NS(message=NS(content='{REDACTED-1}', tool_calls=[]))])
        def raw_provider(request):
            self.assertEqual(request, self.request)
            return raw_response
        self.assertIs(run_llm_execution_middleware(self.request, raw_provider, session_id='session-A'),
                      raw_response)

    def test_real_transport_requests_and_completed_responses(self):
        from openai.types.chat import ChatCompletion

        responses = {
            'chat_completions': ChatCompletion(id='probe', object='chat.completion', created=0, model='probe',
                choices=[{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{REDACTED-1}'}}]),
            'anthropic_messages': NS(id='probe', type='message', role='assistant', model='probe',
                content=[NS(type='text', text='{REDACTED-1}')], stop_reason='end_turn',
                usage=NS(input_tokens=0, output_tokens=0)),
            'codex_responses': NS(status='completed', output=[NS(type='message', role='assistant', status='completed',
                content=[NS(type='output_text', text='{REDACTED-1}')])]),
            'bedrock_converse': {'output': {'message': {'role': 'assistant', 'content': [{'text': '{REDACTED-1}'}]}},
                                'stopReason': 'end_turn', 'usage': {'inputTokens': 0, 'outputTokens': 0}},
        }
        for mode in MODES:
            with self.subTest(mode=mode):
                transport = get_transport(mode)
                request = transport.build_kwargs('probe', self.request['messages'], max_tokens=512)
                sent = []
                def provider(payload):
                    sent.append(payload)
                    return responses[mode]
                response = run_llm_execution_middleware(request, provider, session_id='session-A', api_mode=mode)
                self.assertEqual(len(sent), 1, (mode, request))
                self.assertNotIn('synthetic-private-word', str(sent))
                self.assertIn('literal substitutions', str(sent))
                self.assertIn('synthetic-private-word', self.parse(response, mode).content)

    def test_profiles_sessions_and_key_only_command(self):
        clear_session_vars(self.tokens)
        self.tokens = set_session_vars(session_key='agent:main:telegram:123', source='telegram')
        self.assertIn('concrete session ID unavailable', self.setup.command('redact add another-private-word'))
        self.assertEqual(self.guard.rules('session-B')['entries'], [])
        self.assertEqual(len(self.guard.rules('session-A')['entries']), 1)
        def wire(text):
            sent = []
            def provider(request):
                sent.append(request)
                return NS(choices=[NS(message=NS(content='{REDACTED-1}', tool_calls=[]), finish_reason='stop')])
            response = run_llm_execution_middleware({'messages': [{'role': 'user', 'content': text}]},
                                                    provider, session_id='session-A')
            self.assertEqual(len(sent), 1)
            self.assertNotIn(text, str(sent))
            self.assertIn(text, self.parse(response, 'chat_completions').content)
        wire('synthetic-private-word')
        home_b = self.home / 'profile-B'
        home_b.mkdir()
        token = set_hermes_home_override(home_b)
        try:
            manager_b = get_plugin_manager()
            manager_b._discovered = True
            ctx_b = PluginContext(PluginManifest(name='redaction-probe', path=str(ROOT)), manager_b)
            plugin.plugin_setup.register(ctx_b)
            self.assertEqual(self.guard.rules('session-A')['entries'], [])
            self.assertIn('1 phrases', self.setup.command('redact add other-profile-private --profile'))
            self.assertEqual(self.guard.rules('session-A')['entries'][0][0], 'other-profile-private')
            wire('other-profile-private')
        finally:
            reset_hermes_home_override(token)
        self.assertEqual(self.guard.rules('session-A')['entries'][0][0], 'synthetic-private-word')
        wire('synthetic-private-word')
        self.assertEqual(self.guard.rules('session-B')['entries'], [])

    def test_downstream_error_once_and_restoration_failure(self):
        calls = []
        def broken(request):
            calls.append(request)
            raise RuntimeError('provider-boundary')
        with self.assertRaisesRegex(RuntimeError, 'provider-boundary'):
            run_llm_execution_middleware(self.request, broken, session_id='session-A')
        self.assertEqual(len(calls), 1)
        def malformed(request):
            calls.append(request)
            return object()
        response = run_llm_execution_middleware(self.request, malformed, session_id='session-A')
        self.assertEqual(len(calls), 2)
        self.assertIn('response withheld', self.parse(response, 'chat_completions').content)


if __name__ == '__main__':
    if os.environ.get('PLAT480_DOCTOR'):
        os.chdir(ROOT)
        # The command implementation, not main(): main's PM startup may try to
        # provision even with an already-provisioned interpreter and fresh HOME.
        from hermes_cli.plugins_cmd import cmd_plugin_doctor
        cmd_plugin_doctor('.', ci=True)
        verdict = 'PASS'
    else:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RedactionContract))
        verdict = 'ERROR' if result.errors else 'PASS' if result.wasSuccessful() else 'BLOCKED'
    Path(os.environ['PLAT480_RECEIPT']).write_text(verdict)
