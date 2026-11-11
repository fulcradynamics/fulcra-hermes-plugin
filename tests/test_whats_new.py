"""What's new: opt-in, turn-triggered notices of messages, contact channels and changes."""
import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from plugin import Context, accounts, load

ALEX = '00000000-0000-4000-8000-00000000000a'
SURA = '00000000-0000-4000-8000-00000000000b'
CHANNEL_FIELDS = {'properties': {'sender': {'type': 'string'}, 'kind': {'type': 'string'}, 'body': {'type': 'string'}}}


class WhatsNewTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load()
        self.whats_new = self.plugin.whats_new
        self.ctx = Context()
        self.plugin.register(self.ctx)
        (self.alex, self.sura), self.act, stop = accounts(self.plugin, ALEX, SURA)
        self.addCleanup(stop)
        # Run checks inline instead of in a background thread.
        thread = patch.object(self.whats_new.threading, 'Thread',
                              side_effect=lambda target, args, **kwargs: type('T', (), {'start': lambda s: target(*args)})())
        thread.start()
        self.addCleanup(thread.stop)

    def turn(self, session='chat'):
        notice = self.ctx.hooks['pre_llm_call'](session_id=session)
        self.ctx.hooks['post_llm_call'](session_id=session)
        return notice

    def due(self):
        state = self.ctx.state.values['whats-new']
        state['last_attempt'] -= 10_000
        state['started'] = (datetime.fromisoformat(state['started']) - timedelta(minutes=10)).isoformat()
        if 'cursor' in state:
            state['cursor'] = (datetime.fromisoformat(state['cursor']) - timedelta(minutes=10)).isoformat()

    def test_off_by_default_and_setup_requires_an_agent_name(self):
        self.assertIsNone(self.turn())
        self.assertTrue(self.ctx.commands['fulcra']('setup --whats-new on').startswith('Error:'))
        status = self.ctx.commands['fulcra']('setup --whats-new on --agent-name helper --interval 120')
        self.assertIn('whats-new = true', status)
        self.assertEqual(self.ctx.config, {'whats-new': True, 'agent-name': 'helper', 'interval': 120})
        self.assertTrue(self.ctx.commands['fulcra']('status --interval 5').startswith('Error:'))

    def test_notices_new_messages_contact_channels_and_changes_once(self):
        self.ctx.commands['fulcra']('setup --whats-new on --agent-name helper --ignore-prefixes /private/')
        self.act(self.alex)
        self.turn()  # Starts the profile's clock; nothing is due yet.
        self.due()
        self.turn()  # First check: existing channels and older changes are not new.
        self.assertEqual(self.ctx.state.values['whats-new']['pending'], [])

        channel = self.sura.create_data_type('Event', {'name': 'Sura with Alex', 'description': 'x',
                                                       'record_spec': {'schema': json.dumps(CHANNEL_FIELDS)}})['id']
        self.sura.create_datashare('connect-our-agents', [channel], [ALEX])
        self.sura.record_data_type(channel, [{'id': '00000000-0000-4000-8000-000000000001', 'sender': 'sura',
                                              'kind': 'message', 'body': 'Draft is ready'}], 'v1')
        self.sura.record_data_type(channel, [{'id': '00000000-0000-4000-8000-000000000002', 'sender': 'sura',
                                              'kind': 'message', 'body': 'Not for you', 'recipients': ['other']}], 'v1')
        notes = self.alex.create_data_type('Event', {'name': 'Notes', 'description': 'x'})['id']
        self.alex.record_data_type(notes, [{'id': '00000000-0000-4000-8000-000000000003'}], 'v1')
        stamp = datetime.now(timezone.utc).isoformat()
        self.alex.files.append({'id': 'f1', 'full_name': '/work/report.md', 'state': 'uploaded', 'uploaded_at': stamp})
        self.alex.files.append({'id': 'f2', 'full_name': '/private/x', 'state': 'uploaded', 'uploaded_at': stamp})
        self.due()
        with patch.object(self.whats_new, 'LAG', timedelta(0)):
            self.turn()

        notice = self.turn()['context']
        items = [json.loads(line) for line in notice.splitlines()[1:]]
        self.assertEqual(sorted(i['kind'] for i in items), ['contact_channel', 'data', 'file', 'message'])
        self.assertEqual(next(i for i in items if i['kind'] == 'message')['preview'], 'Draft is ready')
        self.assertEqual(next(i for i in items if i['kind'] == 'file')['path'], '/work/report.md')
        self.assertIn('UNTRUSTED', notice)
        self.assertIsNone(self.turn())

    def test_own_writes_and_cron_sessions_are_not_reported(self):
        self.ctx.commands['fulcra']('setup --whats-new on --agent-name helper')
        self.turn()
        self.ctx.hooks['post_tool_call'](session_id='chat', tool_name='fulcra_record',
                                          args={'data_type': 'Event/x'}, result='{"upload_id": "u"}')
        state = self.ctx.state.values['whats-new']
        self.assertGreater(state['known']['type:Event/x'], time.time())
        self.assertFalse(self.whats_new._selected({'kind': 'data', 'data_type': 'Event/x'}, state['settings'],
                                                  state['known'], time.time()))
        state['pending'] = [{'kind': 'data', 'data_type': 'Event/y', 'records': 1}]
        self.assertIsNone(self.ctx.hooks['pre_llm_call'](session_id='job', platform='cron'))
        self.assertEqual(len(self.ctx.state.values['whats-new']['pending']), 1)


if __name__ == '__main__':
    unittest.main()
