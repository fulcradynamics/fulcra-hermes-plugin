"""Two synthetic accounts connect and message only through the plugin's tools."""
import json
import unittest

from plugin import CHANNEL_FIELDS, State, accounts, load

ALEX = '00000000-0000-4000-8000-00000000000a'
SURA = '00000000-0000-4000-8000-00000000000b'
RIO = '00000000-0000-4000-8000-00000000000c'


class MessagingTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load()
        self.tools = self.plugin.tools
        (self.alex, self.sura, self.rio), self.act, stop = accounts(self.plugin, ALEX, SURA, RIO)
        self.addCleanup(stop)

    def call(self, account, tool, **args):
        self.act(account)
        handler = getattr(self.tools, tool, None) or self.plugin.messages.tool(account.state)
        result = handler(args)
        self.assertFalse(result.startswith("Error"), (tool, result))
        return json.loads(result)

    def accept(self, account, inviter, topic, sender):
        """The accept steps in the connect-our-agents skill."""
        channel = self.call(account, 'fulcra_create_data_type', base_type='event', name='Sura with Alex',
                            description='Agent contact channel\nContact label: "Alex\'s agent"', fields=CHANNEL_FIELDS)['id']
        self.call(account, 'fulcra_create_share', name='connect-our-agents: Sura with Alex',
                  data_types=[channel], files=[], user_ids=[inviter])
        posted = self.call(account, 'fulcra_send_agent_message', connection=channel, sender=sender,
                           body='Hi, this is Sura\'s agent.', topic=topic)
        self.assertEqual(posted['status'], 'posted')
        return channel

    def test_invite_accept_match_send_receive_and_ack(self):
        invite = self.call(self.alex, 'fulcra_create_agent_invitation', inviter_name='Alex', recipient_name='Sura')
        self.assertEqual(invite['status'], 'prepared')
        self.assertFalse(self.alex.shares)
        self.accept(self.sura, ALEX, invite['topic'], "Sura's Hermes")

        matched = self.call(self.alex, 'fulcra_match_agent_invitations')
        self.assertEqual([r['status'] for r in matched['results']], ['matched'])
        self.assertEqual(self.alex.shares[0]['fulcra_data_types'], [invite['data_type']])

        sent = self.call(self.alex, 'fulcra_send_agent_message', connection=SURA, sender="Alex's Hermes",
                         body='Dinner Friday?', recipients=["Sura's Hermes"])
        self.assertEqual(sent['status'], 'posted')
        self.sura.state = State()
        inbox = self.call(self.sura, 'fulcra_receive_agent_messages', agent_name="Sura's Hermes")
        self.assertEqual([m['body'] for m in inbox['messages']], ['Dinner Friday?'])
        self.assertEqual(self.call(self.sura, 'fulcra_receive_agent_messages', agent_name="Sura's Hermes")['messages'], [])
        other = self.call(self.sura, 'fulcra_receive_agent_messages', agent_name='someone else', since='2020-01-01T00:00:00+00:00')
        self.assertEqual(other['messages'], [])

        ack = self.call(self.sura, 'fulcra_send_agent_message', connection=ALEX, sender="Sura's Hermes", body='ack',
                        ack=sent['mid'], target_peer_userid=ALEX)
        self.assertEqual((ack['status'], ack['record']['kind'], ack['record']['in_reply_to']), ('posted', 'ack', sent['mid']))

    def test_standing_invitation_gives_each_responder_an_outbox(self):
        standing = self.call(self.alex, 'fulcra_standing_agent_invitation', inviter_name='Alex')
        self.assertTrue(standing['topic'].startswith('open_invitation '))
        self.assertEqual(self.call(self.alex, 'fulcra_standing_agent_invitation')['code'], standing['code'])
        for account in (self.sura, self.rio):
            self.accept(account, ALEX, standing['topic'], 'Agent')
        results = self.call(self.alex, 'fulcra_match_agent_invitations')['results']
        self.assertEqual(sorted(r['peer_userid'] for r in results if r['status'] == 'matched'), [SURA, RIO])
        outboxes = [s['fulcra_data_types'][0] for s in self.alex.shares]
        self.assertEqual(len(set(outboxes)), 2)
        self.assertNotIn(standing['data_type'], outboxes)

    def test_send_needs_an_existing_connection(self):
        self.act(self.alex)
        result = self.tools.fulcra_send_agent_message({'connection': SURA, 'sender': 'a', 'body': 'hi'})
        self.assertTrue(result.startswith('Error:'), result)
        self.assertEqual(self.alex.rows, {})


if __name__ == '__main__':
    unittest.main()
