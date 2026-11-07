"""Native current-channel behavior, with no network or credentials."""
import copy
import json
import unittest
from unittest.mock import Mock, patch

from test_tools import load_tools
from test_updates import load_plugin

OWN = '11111111-1111-4111-8111-111111111111'
PEER = '22222222-2222-4222-8222-222222222222'
OTHER = '33333333-3333-4333-8333-333333333333'
CHANNEL = 'Event/44444444-4444-4444-8444-444444444444'
MID = '55555555-5555-4555-8555-555555555555'


class ContactsTests(unittest.TestCase):
    def setUp(self):
        self.tools = load_tools()
        self.api = Mock()
        self.entry = dict(id=CHANNEL, fulcra_userid=OWN, api_version='v1',
                          recordable=True, description='Existing context', name='Contact',
                          record_spec={'type': 'event'})
        self.api.get_fulcra_userid.return_value = OWN
        self.api.v1_catalog.side_effect = lambda **kw: [copy.deepcopy(self.entry)]
        self.api.resolve_data_type.side_effect = lambda *a, **kw: [copy.deepcopy(self.entry)]
        self.share = dict(id=OTHER, fulcra_data_types=[CHANNEL], share_all_data=False,
                          permissions=[{'allowed_fulcra_userid': PEER}], group_permissions=[])
        self.api.get_datashares.side_effect = lambda: [copy.deepcopy(self.share)]
        self.api.validate_records.return_value = []
        self.api.v1_catalog_schema.return_value = copy.deepcopy(self.tools.contacts.connections.CHANNEL_FIELDS)
        self.rows = []
        self.api.fulcra_v1_records.side_effect = lambda *a, **kw: '\n'.join(json.dumps(r) for r in self.rows)
        self.api.record_data_type.side_effect = lambda channel, rows, version: self.rows.extend(copy.deepcopy(rows)) or {}
        self.api.update_data_type.side_effect = lambda base, uid, changes: self.entry.update(changes) or {}
        self.factory = patch.object(self.tools, 'client', return_value=self.api)
        self.factory.start()
        self.addCleanup(self.factory.stop)

    def call(self, tool, **args):
        return json.loads(getattr(self.tools, 'fulcra_' + tool)(args))

    def test_generic_event_records_keep_exact_channel_without_annotation_sources(self):
        self.api.resolve_data_type.return_value = [self.entry]
        self.api.resolve_data_type.side_effect = None
        self.tools.record(self.api, CHANNEL, [{'id': MID, 'body': 'Hello'}])
        self.api.record_data_type.assert_called_once_with(CHANNEL, [{'id': MID, 'body': 'Hello'}], 'v1')
        self.api.record_data_type.reset_mock()
        self.tools.record(self.api, CHANNEL, [{'record_id': MID}], deletion=True)
        self.api.record_data_type.assert_called_once_with('DeletedRecord', [{'record_id': MID, 'data_type': CHANNEL}], 'v1')

    def test_metadata_preserves_schema_and_rejects_stale_or_unowned(self):
        result = self.call('update_data_type', data_type=CHANNEL, description='New context', expected_description='Existing context')
        self.assertTrue(result['verified'])
        self.api.update_data_type.assert_called_once_with('Event', CHANNEL.split('/')[1], {'description': 'New context'})
        self.api.update_data_type.reset_mock()
        self.assertEqual(self.call('update_data_type', data_type=CHANNEL, name='New', expected_description='stale')['status'], 'rejected')
        self.entry['fulcra_userid'] = PEER
        self.assertEqual(self.call('update_data_type', data_type=CHANNEL, name='New')['status'], 'rejected')
        self.api.update_data_type.assert_not_called()

    def test_metadata_failed_readback_is_uncertain(self):
        self.api.update_data_type.side_effect = None
        result = self.call('update_data_type', data_type=CHANNEL, name='Changed')
        self.assertFalse(result['verified'])
        self.assertEqual(result['status'], 'uncertain')

    def test_send_current_protocol_exact_payload_and_no_sharing(self):
        result = self.call('send_agent_message', connection=CHANNEL, sender='helper', body='Hello', record_id=MID,
                           reply_to=OTHER, artifacts=[{'path': '/shared/plan.txt'}])
        self.assertEqual(result['status'], 'posted')
        self.assertFalse(result['peer_acknowledged'])
        self.assertEqual(self.rows[0], dict(id=MID, sender='helper', body='Hello', kind='reply',
                         in_reply_to=OTHER, topic='chat', priority='P2', artifacts=[{'path': '/shared/plan.txt'}]))
        self.api.create_datashare.assert_not_called()

    def test_send_rejects_audience_changes_malformed_ids_and_payload_conflicts(self):
        args = dict(connection=CHANNEL, sender='helper', body='Hello', record_id=MID)
        self.share['permissions'].append({'allowed_fulcra_userid': OTHER})
        self.assertEqual(self.call('send_agent_message', **args)['status'], 'rejected')
        self.assertEqual(self.call('send_agent_message', **args, expected_peer_userids=[PEER])['status'], 'rejected')
        self.share['permissions'].pop()
        self.assertEqual(self.call('send_agent_message', **{**args, 'record_id': MID.replace('-', '')})['status'], 'rejected')
        self.rows.append(dict(id=MID, sender='helper', body='different', kind='message', topic='chat', priority='P2'))
        self.assertEqual(self.call('send_agent_message', **args)['status'], 'rejected')
        self.api.record_data_type.assert_not_called()

    def test_send_uncertain_write_never_retries(self):
        self.api.record_data_type.side_effect = TimeoutError('private server detail')
        result = self.call('send_agent_message', connection=PEER, sender='helper', body='Hello', record_id=MID)
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(result['mid'], MID)
        self.assertNotIn('private server detail', json.dumps(result))
        self.api.record_data_type.assert_called_once()

    def test_invitation_persists_code_before_optional_narrow_share(self):
        def create(base, body):
            self.entry.update(body)
            return {'id': CHANNEL}
        self.api.create_data_type.side_effect = create
        self.api.get_datashares.side_effect = None
        self.api.get_datashares.return_value = []
        result = self.call('create_agent_invitation', inviter_name='Alice', recipient_name='Bob')
        self.assertTrue(result['prepared'])
        self.assertFalse(result['sent'])
        self.assertFalse(result['connected'])
        self.assertRegex(result['topic'], r'^handshake [0-9a-f]{32}$')
        self.assertIn(result['code'], self.entry['description'])
        self.assertIn(result['topic'], result['invitation_text'])
        self.api.create_datashare.assert_not_called()
        self.api.record_data_type.assert_not_called()

    def test_accept_reserves_before_sharing_and_never_reposts_prior_attempt(self):
        catalog = []
        self.api.v1_catalog.side_effect = lambda **kw: [copy.deepcopy(self.entry)] if kw.get('data_type') else copy.deepcopy(catalog)
        def create(base, body):
            self.entry.update(body)
            self.entry['record_spec']['type'] = 'event'
            catalog.append(self.entry)
            return {'id': CHANNEL}
        self.api.create_data_type.side_effect = create
        args = dict(inviter_userid=PEER, topic='handshake ' + 'a' * 32, sender='helper', introduction='Hello')
        first = self.call('accept_agent_invitation', **args)
        self.assertEqual(first['status'], 'introduction_posted')
        self.assertFalse(first['connected'])
        self.assertEqual(self.rows[0]['topic'], args['topic'])
        self.api.create_data_type.assert_called_once()
        self.api.create_datashare.assert_called_once()
        self.api.record_data_type.assert_called_once()
        second = self.call('accept_agent_invitation', **args)
        self.assertEqual(second['status'], 'recovery_required')
        self.api.create_data_type.assert_called_once()
        self.api.create_datashare.assert_called_once()
        self.api.record_data_type.assert_called_once()

    def test_match_requires_first_message_code_and_consumes_before_grant(self):
        code = 'a' * 32
        details = {'version': 1, 'invitation': {'code': code, 'prefix': 'handshake', 'state': 'prepared'}}
        self.entry['description'] = 'Agent channel[agent_connection: ' + json.dumps(details) + ']Preserved text'
        incoming = 'Event/' + OTHER
        self.api.get_shared_datasets.return_value = [dict(grant_type='user', sharing_fulcra_userid=PEER,
            share_all_data=False, fulcra_data_types=[incoming])]
        self.rows[:] = [dict(id=MID, sender='peer', body='Hi', kind='message', topic='handshake ' + code,
                            start_time='2026-01-01T00:00:00Z')]
        self.api.get_datashares.side_effect = None
        self.api.get_datashares.return_value = []
        def share(**kwargs):
            self.assertIn('consumed', self.entry['description'])
            self.api.get_datashares.return_value = [self.share]
            return {}
        self.api.create_datashare.side_effect = share
        self.api.resolve_data_type.side_effect = lambda *a, **kw: [dict(self.entry, id=incoming, fulcra_userid=PEER)]
        later = copy.deepcopy(self.rows[0])
        later['start_time'] = '2026-01-02T00:00:00Z'
        self.rows[0]['topic'] = 'not the invitation'
        self.rows.append(later)
        self.assertEqual(self.call('match_agent_invitations')['results'], [])
        self.api.create_datashare.assert_not_called()
        self.rows.pop(0)
        result = self.call('match_agent_invitations')
        self.assertEqual(result['results'][0]['status'], 'matched')
        self.assertIn('completed', self.entry['description'])
        self.assertIn('Agent channel', self.entry['description'])
        self.assertIn('Preserved text', self.entry['description'])
        self.api.create_datashare.assert_called_once()
        self.call('match_agent_invitations')
        self.api.create_datashare.assert_called_once()
        # A failed grant consumes the code and must not be replayed on re-entry.
        self.entry['description'] = 'Agent channel\nConnection details: ' + json.dumps(details)
        self.api.get_datashares.return_value = []
        self.api.create_datashare.reset_mock()
        self.api.create_datashare.side_effect = TimeoutError('private detail')
        self.assertEqual(self.call('match_agent_invitations')['status'], 'uncertain')
        self.assertIn('consumed', self.entry['description'])
        self.call('match_agent_invitations')
        self.api.create_datashare.assert_called_once()

    def test_known_recipient_invitation_share_failure_preserves_recovery_id(self):
        def create(base, body):
            self.entry.update(body)
            return {'id': CHANNEL}
        self.api.create_data_type.side_effect = create
        self.api.create_datashare.side_effect = TimeoutError('private server detail')
        result = self.call('create_agent_invitation', inviter_name='Alice', recipient_name='Bob', recipient_userid=PEER)
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(result['data_type'], CHANNEL)
        self.assertFalse(result['retryable'])
        self.assertNotIn('private server detail', json.dumps(result))
        self.api.create_data_type.assert_called_once()
        self.api.create_datashare.assert_called_once()
        fields = self.api.create_datashare.call_args.kwargs
        self.assertEqual(fields['fulcra_data_types'], [CHANNEL])
        self.assertEqual(fields['allowed_user_ids'], [PEER])
        self.assertEqual(fields['allowed_group_ids'], [])
        self.assertIs(fields['share_all_data'], False)

    def test_send_requires_narrow_non_group_grant_and_denial_is_not_retried(self):
        args = dict(connection=CHANNEL, sender='helper', body='Hello', record_id=MID)
        for change in ({'share_all_data': True}, {'group_permissions': [{'group_id': OTHER}]}):
            with self.subTest(change=change):
                with patch.dict(self.share, change):
                    self.assertEqual(self.call('send_agent_message', **args)['status'], 'rejected')
        self.api.record_data_type.assert_not_called()
        from urllib.error import HTTPError
        self.api.record_data_type.side_effect = HTTPError('https://private', 403, 'denied', {}, None)
        result = self.call('send_agent_message', **args)
        self.assertFalse(result['retryable'])
        self.api.record_data_type.assert_called_once()

    def test_event_messages_are_received_as_untrusted_with_shared_owner(self):
        plugin = load_plugin()
        api = Mock()
        api.get_user_info.return_value = {'userid': OWN}
        share = dict(sharing_fulcra_userid=PEER, id=OTHER, grant_type='user',
                     fulcra_data_types=[CHANNEL], share_all_data=False)
        api.get_shared_datasets.return_value = [share]
        rows = [{'id': MID, 'sender': 'peer helper', 'body': 'Hello', 'kind': 'message'},
                {'id': OTHER, 'sender': 'peer helper', 'body': 'Elsewhere', 'kind': 'message', 'recipients': ['someone else']}]
        with patch.object(plugin.tools, 'records', return_value=rows):
            result = plugin.mesh._receive({'local_agent': 'helper'}, OWN, {}, api=lambda: api)
        self.assertEqual(len(result['messages']), 1)
        self.assertEqual(result['messages'][0]['origin_userid'], PEER)
        self.assertEqual(result['messages'][0]['envelope']['mid'], MID)
        self.assertTrue(result['untrusted_peer_content'])
        self.assertEqual(plugin.mesh_updates._candidates([share], OWN), [share])
