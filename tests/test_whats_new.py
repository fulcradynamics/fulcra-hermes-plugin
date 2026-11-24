"""What's new: opt-in, turn-triggered notices of messages, contact channels and changes, through MCP tools."""
import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from plugin import CHANNEL, SURA, Context, Fulcra, load


class WhatsNewTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load()
        self.whats_new = self.plugin.whats_new
        self.fulcra = Fulcra()
        self.ctx = Context(self.fulcra)
        self.plugin.register(self.ctx)
        # Run checks inline instead of in a background thread.
        thread = patch.object(self.whats_new.threading, 'Thread',
                              side_effect=lambda target, args, **kwargs: type('T', (), {'start': lambda s: target(*args)})())
        thread.start()
        self.addCleanup(thread.stop)
        lag = patch.object(self.whats_new, 'LAG', timedelta(0))
        lag.start()
        self.addCleanup(lag.stop)

    def setup(self, *args):
        values = {'whats-new': True, 'agent-name': 'helper', 'interval': 60}
        for key, value in values.items():
            self.ctx.set_config(key, value)
        for key, value in zip(args[::2], args[1::2]):
            self.ctx.set_config(key, value)

    def turn(self, session='chat', **kwargs):
        notice = self.ctx.hooks['pre_llm_call'](session_id=session, **kwargs)
        self.ctx.hooks['post_llm_call'](session_id=session)
        return notice

    def due(self):
        """Move the clock: the next reply starts a check, and the saved window began a minute ago."""
        state = self.ctx.state.values['whats-new']
        state['last_attempt'] -= 10_000
        earlier = lambda value: (datetime.fromisoformat(value) - timedelta(minutes=1)).isoformat()
        state['started'] = earlier(state['started'])
        if 'cursor' in state:
            state['cursor'] = earlier(state['cursor'])
        for cursor in state.get('cursors', {}).values():
            cursor['until'] = earlier(cursor['until'])

    def test_off_by_default(self):
        self.assertIsNone(self.turn())
        self.assertEqual(self.fulcra.calls, [])

    def test_first_check_runs_after_the_first_reply_and_only_sets_the_starting_point(self):
        self.fulcra.share_channel()
        self.fulcra.post(CHANNEL, '00000000-0000-4000-8000-000000000001', sender='sura', kind='message', body='Old')
        self.setup()
        self.turn()
        self.assertIn('list_shares', [tool for tool, _ in self.fulcra.calls])
        self.assertEqual(self.ctx.state.values['whats-new']['pending'], [])

    def test_without_an_agent_name_addressed_messages_arrive_with_their_recipients(self):
        self.setup('agent-name', '')
        self.turn()
        self.fulcra.share_channel()
        self.fulcra.post(CHANNEL, '00000000-0000-4000-8000-000000000001', sender='sura', kind='message',
                         body='For someone', recipients=['other'])
        self.due()
        self.turn()
        items = [json.loads(line) for line in self.turn()['context'].splitlines()[1:]]
        self.assertIn(['other'], [item.get('recipients') for item in items if item['kind'] == 'message'])

    def test_messages_up_to_the_last_one_the_user_answered_are_not_new(self):
        outbox = 'Event/00000000-0000-4000-8000-0000000000d1'
        ids = [f'00000000-0000-4000-8000-00000000001{i}' for i in range(4)]
        at = lambda minutes: (datetime.now(timezone.utc) - timedelta(seconds=minutes * 6)).isoformat()
        self.setup()
        self.turn()
        self.fulcra.share_channel()
        self.fulcra.share_outbox(outbox=outbox)
        for i, minutes in enumerate((4, 3, 2)):
            self.fulcra.post(CHANNEL, ids[i], sender='sura', kind='message', body=f'm{i}', start_time=at(minutes))
        # Read in the panel: it acknowledged the middle one, so the first two are read.
        self.fulcra.post(outbox, ids[3], sender='helper', kind='ack', body='ack', in_reply_to=ids[1])
        self.due()
        self.turn()
        items = [json.loads(line) for line in self.turn()['context'].splitlines()[1:]]
        self.assertEqual([i['id'] for i in items if i['kind'] == 'message'], [ids[2]])

    def test_a_waiting_notice_is_dropped_once_the_user_answers_it(self):
        outbox = 'Event/00000000-0000-4000-8000-0000000000d1'
        message, reply = '00000000-0000-4000-8000-000000000021', '00000000-0000-4000-8000-000000000022'
        self.setup()
        self.turn()
        self.fulcra.share_channel()
        self.fulcra.share_outbox(outbox=outbox)
        self.fulcra.post(CHANNEL, message, sender='sura', kind='message', body='Dinner?')
        self.due()
        self.turn('other')  # This check queues the notice for the next turn.
        self.assertEqual([i['id'] for i in self.ctx.state.values['whats-new']['pending'] if i['kind'] == 'message'],
                         [message])
        self.fulcra.post(outbox, reply, sender='helper', kind='reply', body='Pies', in_reply_to=message)
        self.due()
        self.ctx.hooks['post_llm_call'](session_id='other')  # The next check, before any turn shows it.
        self.assertNotIn(message, [i.get('id') for i in self.ctx.state.values['whats-new']['pending']])

    def test_notices_new_messages_contact_channels_and_changes_once(self):
        self.setup('ignore-prefixes', ['/private/'])
        self.turn()  # First check: existing channels and older changes are not new.

        self.fulcra.share_channel()
        self.fulcra.post(CHANNEL, '00000000-0000-4000-8000-000000000001', sender='sura', kind='message',
                         body='Draft is ready')
        self.fulcra.post(CHANNEL, '00000000-0000-4000-8000-000000000002', sender='sura', kind='message',
                         body='Not for you', recipients=['other'])
        self.fulcra.post(CHANNEL, '00000000-0000-4000-8000-000000000003', sender='sura', kind='shout', body='Bad')
        stamp = datetime.now(timezone.utc).isoformat()
        self.fulcra.updates = {'data_types': {'Event/notes': 2, 'Event/empty': 0, 'FileChange': 2}, 'file_changes': [
            {'id': 'f1', 'full_name': '/work/report.md', 'state': 'uploaded', 'uploaded_at': stamp},
            {'id': 'f2', 'full_name': '/private/x', 'state': 'uploaded', 'uploaded_at': stamp}]}
        self.due()
        self.turn()

        notice = self.turn()['context']
        items = [json.loads(line) for line in notice.splitlines()[1:]]
        self.assertEqual(sorted(i['kind'] for i in items), ['contact_channel', 'data', 'file', 'message'])
        self.assertEqual(next(i for i in items if i['kind'] == 'message')['preview'], 'Draft is ready')
        self.assertEqual(next(i for i in items if i['kind'] == 'file')['path'], '/work/report.md')
        self.assertEqual([i['data_type'] for i in items if i['kind'] == 'data'], ['Event/notes'])
        self.assertEqual(next(i for i in items if i['kind'] == 'contact_channel')['owner'], SURA)
        self.assertIn('UNTRUSTED', notice)
        self.assertIsNone(self.turn())

    def test_reads_every_message_when_the_server_caps_records(self):
        self.setup()
        self.fulcra.share_channel()
        self.turn()
        for n in range(7):
            self.fulcra.post(CHANNEL, f'00000000-0000-4000-8000-00000000001{n}', sender='sura', kind='message',
                             body=f'm{n}')
        # Spread the records over the window so halving it can split them.
        for n, row in enumerate(self.fulcra.rows[CHANNEL]):
            row['start_time'] = (datetime.now(timezone.utc) - timedelta(seconds=50 - 7 * n)).isoformat()
        self.due()
        self.turn()
        previews = [json.loads(line)['preview'] for line in self.turn()['context'].splitlines()[1:]]
        self.assertEqual(sorted(previews), [f'm{n}' for n in range(7)])

    def test_reads_every_message_when_hermes_truncates_a_result(self):
        self.setup()
        self.fulcra.share_channel()
        self.turn()
        self.ctx.CAP = 900
        self.fulcra.MAX_RECORDS = 100
        for n in range(6):
            row = self.fulcra.post(CHANNEL, f'00000000-0000-4000-8000-00000000002{n}', sender='sura',
                                   kind='message', body=f'm{n} ' + 'x' * 200)
            row['start_time'] = (datetime.now(timezone.utc) - timedelta(seconds=50 - 8 * n)).isoformat()
        self.due()
        self.turn()
        previews = [json.loads(line)['preview'][:2] for line in self.turn()['context'].splitlines()[1:]]
        self.assertEqual(sorted(previews), [f'm{n}' for n in range(6)])

    def test_without_the_grant_checks_fail_quietly(self):
        self.ctx.allowed = False
        self.setup()
        with self.assertLogs(self.whats_new.LOG, 'WARNING') as logs:
            self.turn()
        self.assertIn('PermissionError', ''.join(logs.output))

    def test_own_successful_writes_are_not_reported(self):
        self.setup()
        self.turn()
        written = self.ctx.hooks['post_tool_call']
        written(session_id='chat', tool_name='mcp__fulcra__write_file', args={'path': 'work/a.md'},
                result=json.dumps({'result': 'Wrote /work/a.md'}))
        written(session_id='chat', tool_name='mcp__fulcra__record_data', args={'data_type': 'Event/x'},
                result=json.dumps({'error': 'MCP call failed'}))
        written(session_id='chat', tool_name='mcp__fulcra__send_agent_message', args={},
                result=json.dumps({'result': json.dumps({'status': 'posted', 'outbox': 'Event/mine'})}))
        written(session_id='chat', tool_name='mcp__fulcra__send_agent_message', args={},
                result=json.dumps({'result': json.dumps({'status': 'rejected', 'outbox': 'Event/other'})}))
        known = self.ctx.state.values['whats-new']['known']
        self.assertEqual(set(known), {'path:/work/a.md', 'type:Event/mine'})
        self.assertGreater(known['path:/work/a.md'], time.time())
        settings = self.ctx.state.values['whats-new']['settings']
        self.assertFalse(self.whats_new._selected({'kind': 'file', 'path': '/work/a.md'}, settings, known, time.time()))

    def test_cron_and_subagent_turns_get_no_notices(self):
        self.setup()
        self.turn()
        state = self.ctx.state.values['whats-new']
        state['pending'] = [{'kind': 'data', 'data_type': 'Event/y', 'records': 1}]
        self.assertIsNone(self.ctx.hooks['pre_llm_call'](session_id='job', platform='cron'))
        self.assertIsNone(self.ctx.hooks['pre_llm_call'](session_id='sub', parent_session_id='chat'))
        self.assertEqual(len(self.ctx.state.values['whats-new']['pending']), 1)

    def test_a_failed_check_keeps_the_cursor_and_logs_no_details(self):
        self.setup()
        self.turn()
        before = dict(self.ctx.state.values['whats-new'])
        self.fulcra.fail = 'get_data_updates'
        self.due()
        cursor = self.ctx.state.values['whats-new']['cursor']
        with self.assertLogs(self.whats_new.LOG, 'WARNING') as logs:
            self.turn()
        self.assertEqual(self.ctx.state.values['whats-new']['cursor'], cursor)
        self.assertNotIn('unavailable', ''.join(logs.output))
        self.assertEqual(before['account'], self.ctx.state.values['whats-new']['account'])

    def test_not_connected_is_a_quiet_failure(self):
        self.ctx.fulcra = None
        self.setup()
        with self.assertLogs(self.whats_new.LOG, 'WARNING'):
            self.turn()
        self.assertIsNone(self.turn())


if __name__ == '__main__':
    unittest.main()
