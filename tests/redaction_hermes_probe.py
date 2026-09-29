"""Offline acceptance of PLAT-480 against real Hermes dispatch and parsers."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS


def deny_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
        raise RuntimeError('Network forbidden in PLAT-480 probe')


sys.addaudithook(deny_network)
sys.dont_write_bytecode = True
from hermes_cli.middleware import run_llm_execution_middleware
from hermes_cli.plugins import PluginContext, get_plugin_manager
from hermes_cli.plugins_manifest import PluginManifest
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from gateway.session_context import set_session_vars, clear_session_vars
from agent.transports import get_transport
from agent.turn_truncation import normalize_response_for_agent
from agent.turn_api_call import perform_api_call

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
        self.assertIn('1 phrases', self.setup.command('redact synthetic-private-word'))
        self.request = {'messages': [{'role': 'user', 'content': 'synthetic-private-word'}]}

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
        self.assertIn('Redaction off', self.setup.command('unredact'))
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
        self.assertIn('concrete session ID unavailable', self.setup.command('redact another-private-word'))
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
            self.assertIn('1 phrases', self.setup.command('redact other-profile-private --profile'))
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
