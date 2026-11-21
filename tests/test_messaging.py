"""Reading contacts' channels: which shares are channels and which records are messages for this agent."""
import unittest

from plugin import ALEX, CHANNEL, SURA, load

messages = load().messages


def share(**changes):
    return {'sharing_fulcra_userid': SURA, 'share_all_data': False, 'file_paths': [], 'file_history_paths': [],
            'data_types': [CHANNEL], **changes}


class MessagingTests(unittest.TestCase):
    def test_a_channel_is_one_event_type_shared_alone_by_someone_else(self):
        self.assertEqual(messages.channels([share(), share()], ALEX), [(SURA, CHANNEL)])
        for other in (share(sharing_fulcra_userid=ALEX), share(share_all_data=True), share(file_paths=['/a']),
                      share(data_types=[CHANNEL, 'Event/00000000-0000-4000-8000-0000000000c2']),
                      share(data_types=['HeartRate'])):
            with self.subTest(other=other):
                self.assertEqual(messages.channels([other], ALEX), [])

    def test_messages_must_fit_the_channel_fields(self):
        ok = {'id': 'r1', 'sender': 'sura', 'kind': 'message', 'body': 'hi', 'topic': None}
        self.assertEqual(messages._message(ok, 'helper')['body'], 'hi')
        for bad in ({'kind': 'shout'}, {'body': ''}, {'body': 'x' * 4001}, {'sender': 5},
                    {'in_reply_to': 'not-a-uuid'}, {'recipients': []}, {'artifacts': [{'version': '1'}]}):
            with self.subTest(bad=bad):
                self.assertIsNone(messages._message({**ok, **bad}, 'helper'))
        self.assertIsNone(messages._message({'id': 'r2', 'sender': 'sura', 'kind': 'message'}, 'helper'))

    def test_recipients_pick_the_agent(self):
        row = {'id': 'r1', 'sender': 'sura', 'kind': 'message', 'body': 'hi'}
        self.assertIsNotNone(messages._message({**row, 'recipients': ['helper']}, 'helper'))
        self.assertIsNotNone(messages._message({**row, 'recipients': ['all']}, 'helper'))
        self.assertIsNone(messages._message({**row, 'recipients': ['other']}, 'helper'))

    def test_timestamps_need_a_time_zone(self):
        self.assertEqual(messages.timestamp('2026-11-21T10:00:00Z').utcoffset().total_seconds(), 0)
        with self.assertRaises(ValueError):
            messages.timestamp('2026-11-21T10:00:00')


if __name__ == '__main__':
    unittest.main()
