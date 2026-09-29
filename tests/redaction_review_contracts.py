"""Shared regressions exercised locally and through real Hermes dispatch."""
import copy
import json
from types import SimpleNamespace as NS


class RedactionReviewContracts:
    def fresh_rules(self):
        self.ctx.state.set(self.plugin.redaction.KEY, {
            'next': 1, 'profile': self.plugin.redaction.empty_scope(), 'sessions': {}})

    def call_boundary(self, request, session='A', mode='chat_completions', refused=False):
        sent = []
        before = copy.deepcopy(request)
        def provider(payload):
            sent.append(payload)
            return NS(choices=[NS(message=NS(content='safe', tool_calls=[]), finish_reason='stop')])
        response = self.dispatch(request, provider, session_id=session, api_mode=mode)
        self.assertEqual(request, before)
        self.assertEqual(len(sent), 0 if refused else 1)
        if refused:
            self.assertIn('no provider call', response.choices[0].message.content)
            self.assertEqual(response.usage.total_tokens, 0)
        return sent

    def test_review_unknown_placeholders_all_text_locations(self):
        self.fresh_rules()
        self.guard.command('redact secret', session_id='A')
        for token in ('{REDACTED-secret}', '{REDACTED-unknown}', '{REDACTED-}'):
            requests = [
                {'messages': [{'role': role, 'content': token}]}
                for role in ('user', 'assistant', 'tool', 'system', 'developer')]
            requests += [
                {'messages': [{'role': 'user', 'content': 'safe'}], field: token}
                for field in ('instructions', 'system')]
            requests += [
                {'messages': [{'role': 'assistant', 'content': None, 'tool_calls': [
                    {'id': 'call-1', 'type': 'function', 'function': {
                        'name': 'lookup', 'arguments': json.dumps({'q': token})}}]}]},
                {'messages': [{'role': 'assistant', 'content': [
                    {'type': 'tool_use', 'id': 'call-1', 'name': 'lookup', 'input': {'q': token}}]}]},
                {'input': [{'type': 'function_call', 'name': 'lookup', 'call_id': 'call-1',
                            'arguments': json.dumps({'q': token})}]},
                {'input': [{'type': 'function_call_output', 'call_id': 'call-1', 'output': token}]},
                {'messages': [{'role': 'assistant', 'content': 'safe', 'reasoning_content': token}]},
            ]
            for request in requests:
                with self.subTest(token=token, request=request):
                    self.call_boundary(request, refused=True)
        for request in (
            {'messages': [{'role': 'assistant', 'content': '{REDACTED-1} secret'}]},
            {'messages': [{'role': 'tool', 'content': '{REDACTED-1}'}], 'instructions': '{REDACTED-1}'},
            {'input': [{'type': 'function_call', 'name': 'lookup', 'call_id': 'call-1',
                        'arguments': json.dumps({'q': '{REDACTED-1}'})}]},
        ):
            sent = self.call_boundary(request)
            self.assertNotIn('secret', str(sent))
            self.assertIn('{REDACTED-1}', str(sent))
        self.guard.command('redact on', session_id='B')
        self.call_boundary({'messages': [{'role': 'tool', 'content': '{REDACTED-1}'}]},
                           session='B', refused=True)  # A's token is not B's replay.

    def test_bare_unredact_stops_outbound_and_restoration(self):
        for profile in (False, True):
            with self.subTest(profile=profile):
                self.fresh_rules()
                suffix = ' --profile' if profile else ''
                self.guard.command('redact secret' + suffix, session_id='A')
                request = {'messages': [{'role': 'user', 'content': 'secret'}]}
                self.assertNotIn('secret', str(self.call_boundary(request)))
                result = self.guard.command('unredact' + suffix, session_id='A')
                self.assertEqual(self.call_boundary(request)[0], request)
                self.assertIn('Redaction off', result)
                response = NS(choices=[NS(message=NS(content='{REDACTED-1}', tool_calls=[]))])
                self.assertIs(self.dispatch(request, lambda _: response, session_id='A'), response)
                self.guard.command('redact on' + suffix, session_id='A')
                self.assertNotIn('secret', str(self.call_boundary(request)))
                restored = self.dispatch(request, lambda _: response, session_id='A')
                self.assertIn('secret', restored.choices[0].message.content)
                before = self.guard.load()
                for command in ('unredact on', 'unredact off'):
                    self.assertTrue(self.guard.command(command + suffix, session_id='A').startswith('Error:'))
                    self.assertEqual(self.guard.load(), before)

    def test_review_status_is_read_only_and_inherits_profile(self):
        self.fresh_rules()
        before = self.guard.load()
        for command in ('redact', 'redact status', 'redact help', 'redact status --profile'):
            self.guard.command(command, session_id='A')
            self.assertEqual(self.guard.load(), before)
        self.guard.command('redact secret --profile')
        request = {'messages': [{'role': 'user', 'content': 'secret'}]}
        sent = self.call_boundary(request)
        self.assertNotIn('secret', str(sent))
        self.assertNotIn('A', self.guard.load()['sessions'])
        # The tri-state representation also keeps an inherited scope live.
        data = self.guard.load()
        data['sessions']['A'] = {'enabled': None, 'entries': []}
        self.ctx.state.set(self.plugin.redaction.KEY, data)
        self.guard.command('redact status', session_id='A')
        self.assertEqual(self.guard.load(), data)
        self.guard.command('redact off --profile')
        self.assertFalse(self.guard.rules('A')['enabled'])
        self.guard.command('redact on --profile')
        self.assertTrue(self.guard.rules('A')['enabled'])
        self.guard.command('redact off', session_id='A')
        self.assertEqual(self.call_boundary(request)[0], request)
        data = self.guard.load()
        data['profile']['enabled'] = None
        self.ctx.state.set(self.plugin.redaction.KEY, data)
        self.call_boundary(request, refused=True)

    def test_review_unknown_session_requires_outbound_consent(self):
        self.fresh_rules()
        self.guard.command('redact secret', session_id='A')
        request = {'messages': [{'role': 'user', 'content': 'secret'}]}
        for profile in (False, True):
            if profile:
                self.guard.command('redact shared --profile')
            for session in ('rotated', 'B'):
                with self.subTest(profile=profile, session=session):
                    self.call_boundary(request, session=session, refused=True)
                    before = self.guard.load()
                    for command in ('redact status', 'redact', 'redact help'):
                        self.guard.command(command, session_id=session)
                        self.assertEqual(self.guard.load(), before)
                        self.call_boundary(request, session=session, refused=True)
        self.guard.command('unredact', session_id='rotated')
        self.assertEqual(self.call_boundary(request, session='rotated')[0], request)
        self.guard.command('redact on', session_id='B')
        sent = self.call_boundary({'messages': [{'role': 'user', 'content': 'secret shared'}]}, session='B')
        self.assertIn('secret', str(sent))  # Explicitly new boundary; never copy A's rules.
        self.assertNotIn('shared', str(sent))
        self.assertEqual(self.guard.load()['sessions']['B']['entries'], [])
        self.guard.command('redact separate', session_id='C')
        sent = self.call_boundary({'messages': [{'role': 'user', 'content': 'secret separate'}]}, session='C')
        self.assertIn('secret', str(sent))
        self.assertNotIn('separate', str(sent))
        self.assertNotIn('secret', str(self.call_boundary(request, session='A')))
        self.guard.command('redact off', session_id='A')
        self.guard.command('redact off', session_id='C')
        self.call_boundary(request, session='new-with-no-enabled-session-rules')

    def test_review_sdk_overrides_refused(self):
        self.fresh_rules()
        phrase = 'private"value\\path'
        self.guard.command('redact ' + phrase, session_id='A')
        override = [{'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'call-1', 'type': 'function', 'function': {
                'name': 'lookup', 'arguments': json.dumps({'q': phrase})}}]}]
        self.call_boundary({'messages': [{'role': 'user', 'content': 'safe'}],
                            'extra_body': {'messages': override}}, refused=True)

    def test_review_placeholder_boundary_overlap_refused(self):
        self.fresh_rules()
        self.assertIn('2 phrases', self.guard.command(
            'redact seed = account, account}12345', session_id='A'))
        self.call_boundary({'messages': [{'role': 'tool',
                            'content': '{REDACTED-account}12345'}]}, refused=True)

    def test_review_structured_output_refused_text_allowed(self):
        self.fresh_rules()
        phrase = 'private"value\\path'
        self.guard.command('redact ' + phrase, session_id='A')
        for kind in ('json_object', 'json_schema'):
            schema = {'type': 'object', 'properties': {'value': {'type': 'string'}},
                      'required': ['value'], 'additionalProperties': False}
            chat_format = {'type': kind}
            responses_format = {'type': kind}
            if kind == 'json_schema':
                chat_format['json_schema'] = {'name': 'result', 'strict': True, 'schema': schema}
                responses_format.update(name='result', strict=True, schema=schema)
            for mode, option in (
                ('chat_completions', {'response_format': chat_format}),
                ('codex_responses', {'text': {'format': responses_format}}),
                ('chat_completions', {'extra_body': {'response_format': chat_format}}),
                ('codex_responses', {'extra_body': {'text': {'format': responses_format}}}),
            ):
                with self.subTest(kind=kind, mode=mode, option=option):
                    key = 'input' if mode == 'codex_responses' else 'messages'
                    request = {key: [{'role': 'user', 'content': phrase}], **option}
                    self.call_boundary(request, mode=mode, refused=True)
        for option in ({'response_format': {'type': 'text'}}, {'text': {'format': {'type': 'text'}}}):
            sent = self.call_boundary({'messages': [{'role': 'user', 'content': phrase}], **option})
            self.assertNotIn(phrase, str(sent))
            self.assertIn('{REDACTED-1}', str(sent))
        self.guard.command('redact off', session_id='A')
        request = {'messages': [{'role': 'user', 'content': phrase}], 'response_format': {'type': 'json_object'}}
        self.assertEqual(self.call_boundary(request)[0], request)
