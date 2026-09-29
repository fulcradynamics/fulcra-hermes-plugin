"""Literal redaction contracts; no credentials or provider access."""
import unittest
from test_updates import Context, load_plugin
from redaction_review_contracts import RedactionReviewContracts


class RedactionTests(RedactionReviewContracts, unittest.TestCase):
    def setUp(self):
        self.plugin = load_plugin()
        self.ctx = Context()
        self.guard = self.plugin.redaction.Redaction(self.ctx)
        self.dispatch = self.guard.execute

    def test_commands_stable_ids_isolation_and_generic_errors(self):
        command = lambda text: self.guard.command(text, session_id='A')
        result = command('redact add Leif Meyer = user name, Hermes')
        self.assertIn('2 phrases', result)
        self.assertNotIn('Leif', result)
        rules = self.guard.rules('A')
        self.assertEqual(rules['entries'], [['Leif Meyer', '{REDACTED-user name}'], ['Hermes', '{REDACTED-2}']])
        self.assertEqual(self.guard.rules('B')['entries'], [])
        self.assertTrue(command('redact add Another = user name').startswith('Error:'))
        self.assertNotIn('Another', command('redact add Another = user name'))
        command('redact off')
        self.assertFalse(self.guard.rules('A')['enabled'])
        command('redact on')
        command('redact add Third')
        self.assertEqual(self.guard.rules('A')['entries'][-1][1], '{REDACTED-3}')
        self.assertEqual(self.ctx.config, {})
        self.assertIn('--profile', self.guard.command('redact add secret'))

    def test_dispatch_profile_rules_and_toggle(self):
        self.plugin.register(self.ctx)
        self.assertIn('llm_execution', self.ctx.middleware)
        setup = self.plugin.plugin_setup.Setup(self.ctx)
        self.assertIn('invalid choice', setup.command('raw'))
        self.assertIn('1 phrases', setup.command('redact add secret --profile'))
        self.assertEqual(self.guard.rules('A')['entries'], self.guard.rules('B')['entries'])
        token = self.ctx.state.profile.set('b')
        self.assertEqual(self.guard.rules('A')['entries'], [])
        self.ctx.state.profile.reset(token)
        self.assertEqual(len(self.guard.rules('A')['entries']), 1)
        self.assertIn('Redaction off', setup.command('redact off --profile'))
        self.assertFalse(self.guard.rules('A')['enabled'])
        self.assertNotIn('restore', self.guard.load()['profile'])

    def test_unknown_shapes_missing_identity_and_tool_only(self):
        from types import SimpleNamespace as NS
        self.guard.command('redact add private', session_id='A')
        sent = []
        for request, session in [({'messages': [{'role': 'user', 'content': 'private'}], 'mystery': 'x'}, 'A'),
                                 ({'messages': [{'role': 'user', 'content': 'private'}]}, '')]:
            response = self.guard.execute(request, sent.append, session_id=session)
            self.assertEqual(sent, [])
            self.assertIn('Local Fulcra', response.choices[0].message.content)
        call = NS(id='private-id', function=NS(name='private-tool', arguments='{"value":"{REDACTED-1}"}'))
        def provider(request):
            return NS(choices=[NS(message=NS(content=None, tool_calls=[call]))])
        request = {'messages': [{'role': 'user', 'content': 'private'}]}
        response = self.guard.execute(request, provider, session_id='A')
        self.assertEqual(response.choices[0].message.tool_calls[0].function.arguments, call.function.arguments)
        self.assertIn('1 substitutions', response.choices[0].message.content)
        self.guard.command('redact off', session_id='A')
        response = self.guard.execute(request, lambda r: NS(choices=[NS(message=NS(content='{REDACTED-1}', tool_calls=[]))]), session_id='A')
        self.assertIn('{REDACTED-1}', response.choices[0].message.content)
        self.assertNotIn('private', response.choices[0].message.content)

    def test_collisions_opaque_data_and_stable_prefix(self):
        import copy
        self.assertTrue(self.guard.command('redact add secret = secret', session_id='A').startswith('Error:'))
        self.guard.command('redact add secret', session_id='A')
        payload = self.plugin.redaction.redact_request
        request = {'messages': [{'role': 'user', 'content': 'secret'},
                               {'role': 'assistant', 'content': None, 'tool_calls': [
                                   {'id': 'call-1', 'type': 'function', 'function': {'name': 'lookup', 'arguments': '{"q":"secret"}'}}]},
                               {'role': 'tool', 'tool_call_id': 'call-1', 'content': 'secret'}]}
        rules = self.guard.rules('A')['entries']
        first, count = payload(request, rules)
        self.assertEqual(count, 3)
        self.assertEqual(first['messages'][1]['tool_calls'][0]['id'], 'call-1')
        self.assertEqual(first['messages'][1]['tool_calls'][0]['function']['name'], 'lookup')
        extended = copy.deepcopy(request)
        extended['messages'].append({'role': 'user', 'content': 'next'})
        second, _ = payload(extended, rules)
        self.assertEqual(first['messages'], second['messages'][:-1])
        for message in ({'role': 'user', 'content': '{REDACTED-1}'},
                        {'role': 'user', 'content': 'safe', 'future_payload': 'unknown'},
                        {'role': 'user', 'content': [{'type': 'unknown', 'text': 'secret'}]},
                        {'role': 'assistant', 'content': [{'type': 'thinking', 'thinking': 'safe', 'signature': 'opaque'},
                                                          {'type': 'text', 'text': 'secret'}]}):
            before = copy.deepcopy(message)
            with self.assertRaises(ValueError):
                payload({'messages': [message]}, rules)
            self.assertEqual(message, before)

    def test_execution_round_trip_history_and_fail_closed(self):
        from types import SimpleNamespace as NS
        import copy
        self.guard.command('redact add Leif, Leif Meyer = user name', session_id='A')
        request = {'messages': [{'role': 'user', 'content': 'Leif Meyer and Leif; leif'},
                                {'role': 'assistant', 'content': 'Leif Meyer'}]}
        original = copy.deepcopy(request)
        sent = []
        def provider(payload):
            sent.append(payload)
            return NS(choices=[NS(message=NS(content='{REDACTED-user name}', tool_calls=[]))])
        result = self.guard.execute(request, provider, session_id='A', api_mode='chat_completions')
        self.assertEqual(request, original)
        self.assertNotIn('Leif', str(sent))
        self.assertIn('leif', str(sent))
        self.assertIn('Leif Meyer', result.choices[0].message.content)
        self.assertIn('3 substitutions', result.choices[0].message.content)
        self.assertEqual(len(sent), 1)
        sent.clear()
        result = self.guard.execute({'messages': object()}, provider, session_id='A')
        self.assertEqual(sent, [])
        self.assertIn('Local Fulcra', result.choices[0].message.content)
        self.assertEqual(result.usage.total_tokens, 0)
        self.assertEqual(result.choices[0].message.tool_calls, [])
        def broken(payload):
            sent.append(payload)
            raise RuntimeError('provider boundary')
        with self.assertRaisesRegex(RuntimeError, 'provider boundary'):
            self.guard.execute(request, broken, session_id='A')
        self.assertEqual(len(sent), 1)
        for malformed in (NS(content=[NS(type='future_payload', text='private')]),
                          NS(output=[NS(type='future_payload')])):
            result = self.guard.execute(request, lambda r: malformed, session_id='A')
            self.assertIn('response withheld', result.choices[0].message.content)


if __name__ == '__main__':
    unittest.main()
