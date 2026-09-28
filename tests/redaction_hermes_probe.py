"""PLAT-480 required safety contract; intentionally fails on unsupported Hermes.

Run via run_redaction_probe.py, not unittest discovery. No real provider is used.
"""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


def deny_network(event, args):
    """Block network access, including imports, without replacing core functions."""
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
        raise RuntimeError('Network forbidden in PLAT-480 probe')


sys.addaudithook(deny_network)
sys.dont_write_bytecode = True

from hermes_cli.middleware import apply_llm_request_middleware, run_llm_execution_middleware
from hermes_cli.plugins import PluginContext, get_plugin_manager
from hermes_cli.plugins_manifest import PluginManifest


class RedactionContract(unittest.TestCase):
    def setUp(self):
        # Fresh profile per test: no discovery of installed plugins or shared registry.
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        home = Path(os.environ['HERMES_HOME']) / self._testMethodName
        home.mkdir()
        token = set_hermes_home_override(home)
        self.addCleanup(reset_hermes_home_override, token)
        manager = get_plugin_manager()
        manager._discovered = True  # Test harness only; do not load profile plugins.
        self.ctx = PluginContext(PluginManifest(name='redaction-probe', path=str(home)), manager)
        self.request = {'messages': [{'role': 'user', 'content': 'synthetic-private-word'}]}

    def test_request_failure_must_not_send_original(self):
        invoked = []
        def rewrite_request(**kwargs):
            invoked.append(True)
            raise ValueError('synthetic redaction failure')

        self.ctx.register_middleware('llm_request', rewrite_request)
        sent = []
        result = apply_llm_request_middleware(self.request, session_id='session-A')
        run_llm_execution_middleware(result.payload, lambda request: sent.append(request))
        self.assertEqual(invoked, [True], 'Probe did not invoke the target middleware')
        self.assertEqual(sent, [], 'BLOCKER: request failure forwarded original private user text')

    def test_execution_failure_must_not_send_original(self):
        invoked = []
        def wrap_llm_call(**kwargs):
            invoked.append(True)
            raise ValueError('synthetic execution redaction failure')

        self.ctx.register_middleware('llm_execution', wrap_llm_call)
        sent = []
        run_llm_execution_middleware(self.request, lambda request: sent.append(request))
        self.assertEqual(invoked, [True], 'Probe did not invoke the target middleware')
        self.assertEqual(sent, [], 'BLOCKER: execution failure forwarded original private user text')

    def test_restoration_must_precede_stream_delivery(self):
        from agent.turn_api_call import perform_api_call

        emitted = []
        def stream(request, on_first_delta):
            emitted.append('{REDACTED-1}')
            return {'content': '{REDACTED-1}'}

        def restore(request, next_call, **kwargs):
            response = next_call(request)
            response['content'] = response['content'].replace('{REDACTED-1}', 'synthetic-private-word')
            return response

        self.ctx.register_middleware('llm_execution', restore)
        agent = SimpleNamespace(
            base_url='', provider='probe', model='probe', api_mode='chat_completions',
            session_id='session-A', platform='cli', _has_stream_consumers=lambda: True,
            _interruptible_streaming_api_call=stream, _has_pending_redirect=lambda: False,
        )
        verdict = perform_api_call(
            agent, api_kwargs=self.request, _original_api_kwargs=self.request,
            _llm_middleware_trace=[], _moa_prepared_request=None, _retry=None,
            thinking_spinner=None, retry_count=0, api_call_count=0, api_request_id='request-A',
            effective_task_id='task-A', turn_id='turn-A', interrupted=False,
        )
        self.assertEqual(verdict.response['content'], 'synthetic-private-word')
        self.assertEqual(emitted, ['synthetic-private-word'],
                         'BLOCKER: streamed text was delivered before execution middleware restored it')


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RedactionContract))
    # Distinguish an unmet contract from an import/runtime failure in the launcher.
    verdict = 'ERROR' if result.errors else 'PASS' if result.wasSuccessful() else 'BLOCKED'
    Path(os.environ['PLAT480_RECEIPT']).write_text(verdict)
