"""Persisted public-wire fixtures: separate owners, catalogs, grants and records."""
import json
import re
import importlib
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import jsonschema
from test_tools import load_tools
from test_contacts import OWN, PEER, OTHER


class Account:
    def __init__(self, path, owner, fields):
        self.path, self.owner, self.fields = path, owner, fields
        self.after_update = self.after_share = None

    def load(self):
        return json.loads(self.path.read_text())

    def save(self, state):
        self.path.write_text(json.dumps(state))

    def get_fulcra_userid(self):
        return self.owner

    def get_user_info(self):
        return {'userid': self.owner}

    def get_datashares(self):
        return self.load()[self.owner]['shares']

    def get_shared_datasets(self):
        return [dict(s, sharing_fulcra_userid=owner, grant_type='user')
                for owner, data in self.load().items() if owner != self.owner
                for s in data['shares']
                if self.owner in [p['allowed_fulcra_userid'] for p in s['permissions']]]

    def v1_catalog(self, data_type=None, fulcra_userid=None):
        owner = fulcra_userid or self.owner
        entries = self.load()[owner]['catalog'].values()
        if owner != self.owner:
            allowed = {t for s in self.get_shared_datasets() if s['sharing_fulcra_userid'] == owner
                       for t in s['fulcra_data_types']}
            entries = [e for e in entries if e['id'] in allowed]
        return [e for e in entries if data_type is None or e['id'] == data_type]

    def resolve_data_type(self, data_type, api_version=None, fulcra_userid=None):
        return self.v1_catalog(data_type, fulcra_userid)

    def v1_catalog_schema(self, data_type, version, fulcra_userid=None):
        entry, = self.v1_catalog(data_type, fulcra_userid)
        return json.loads(entry['record_spec']['schema'])

    def create_data_type(self, base, body):
        state = self.load()
        channel = base + '/' + str(uuid4())
        state[self.owner]['catalog'][channel] = dict(body, id=channel, fulcra_userid=self.owner,
            api_version='v1', recordable=True, record_spec={**body['record_spec'], 'type': 'event'})
        state[self.owner]['rows'][channel] = []
        self.save(state)
        return {'id': channel}

    def update_data_type(self, base, uid, changes):
        state = self.load()
        state[self.owner]['catalog'][base + '/' + uid].update(changes)
        self.save(state)
        if self.after_update:
            self.after_update(changes)

    def create_datashare(self, **args):
        state = self.load()
        state[self.owner]['shares'].append(dict(id=str(uuid4()),
            fulcra_data_types=args['fulcra_data_types'], share_all_data=args['share_all_data'],
            permissions=[{'allowed_fulcra_userid': p} for p in args['allowed_user_ids']],
            group_permissions=args.get('allowed_group_ids') or [],
            time_start=args.get('time_start'), time_end=args.get('time_end')))
        self.save(state)
        if self.after_share:
            self.after_share()

    def validate_records(self, channel, rows, version):
        schema = self.v1_catalog_schema(channel, version)
        for row in rows:
            jsonschema.validate({k: v for k, v in row.items() if k != 'id'}, {'type': 'object', **schema})
        return []

    def record_data_type(self, channel, rows, version):
        self.validate_records(channel, rows, version)
        state = self.load()
        state[self.owner]['rows'][channel].extend(dict(r, start_time='2026-01-01T00:00:00Z') for r in rows)
        self.save(state)

    def fulcra_v1_records(self, query, fulcra_userid=None):
        channel = re.search(r'__name__="([^"]+)"', query)[1]
        owner = fulcra_userid or self.owner
        if not self.v1_catalog(channel, owner):
            raise PermissionError()
        return '\n'.join(json.dumps(r) for r in self.load()[owner]['rows'][channel])


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tools = load_tools()
        self.c, self.i = self.tools.contacts, self.tools.invitations
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'accounts.json'
        self.path.write_text(json.dumps({p: dict(catalog={}, shares=[], rows={}) for p in (OWN, PEER, OTHER)}))
        self.a, self.b, self.third = [self.account(p) for p in (OWN, PEER, OTHER)]

    def account(self, owner):
        return Account(self.path, owner, self.c.connections.CHANNEL_FIELDS)

    def prepared(self):
        invite = self.c.create_invitation(self.a, 'Alice', 'Bob')
        self.assertEqual(invite['status'], 'prepared')
        accepted = self.i.accept(self.b, OWN, invite['topic'], 'Bob', 'Hello')
        self.assertEqual(accepted['status'], 'introduction_posted')
        return invite, accepted

    def withdraw(self):
        state = self.a.load()
        state[PEER]['shares'] = []
        self.a.save(state)

    def details(self, channel):
        return self.c.metadata(self.a.v1_catalog(channel)[0]['description'])

    def test_persisted_two_account_lifecycle_and_multiparty(self):
        invite, accepted = self.prepared()
        # Fresh clients discover persisted state, not pre-populated mock grants.
        a, b = self.account(OWN), self.account(PEER)
        result = self.i.match(a)
        self.assertEqual(result['results'][0]['status'], 'matched')
        for api, peer, channel in ((a, PEER, invite['data_type']), (b, OWN, accepted['data_type'])):
            sent = self.c.send(api, channel, 'helper', 'Reply', reply_to=accepted['mid'])
            self.assertEqual(sent['status'], 'posted')
            receiver = self.account(peer)
            rows = self.i.history(receiver, api.owner, channel)
            self.assertIn(sent['mid'], [r['id'] for r in rows])
            mesh = importlib.import_module(self.tools.__package__ + '.mesh')
            from test_mesh import State
            with patch.object(self.tools, 'client', return_value=receiver):
                receive = mesh.make_handler(State())
                messages = json.loads(receive({'local_agent': 'helper', 'incoming_channel': channel}))['messages']
                self.assertIn(sent['mid'], [m['envelope']['mid'] for m in messages])
                self.assertTrue(all(m['origin_userid'] == api.owner for m in messages))
                self.assertEqual(json.loads(receive({'local_agent': 'helper'}))['messages'], [])
        channel = invite['data_type']
        a.create_datashare(fulcra_data_types=[channel], allowed_user_ids=[OTHER], share_all_data=False)
        sent = self.c.send(a, channel, 'helper', 'All', expected_peer_userids=[PEER, OTHER], target_peer_userid=PEER)
        self.assertEqual(sent['status'], 'posted')
        self.assertEqual(self.c.send(a, PEER, 'helper', 'Ambiguous multiparty')['status'], 'rejected')
        second = self.c.create_invitation(a, 'Alice', 'Bob', PEER)
        self.assertTrue(second['shared'])
        self.assertEqual(self.c.send(a, PEER, 'helper', 'Ambiguous route')['status'], 'rejected')

    def test_independent_broad_policy_does_not_establish_or_block_audience(self):
        invite, _ = self.prepared()
        self.a.create_datashare(fulcra_data_types=[], allowed_user_ids=[OTHER], share_all_data=True)
        self.assertEqual(self.i.match(self.a)['results'][0]['status'], 'matched')
        self.assertEqual(self.c.send(self.a, invite['data_type'], 'helper', 'Hello')['status'], 'posted')
        self.assertEqual(self.c.audience(self.a, OWN, invite['data_type']), {PEER})

    def test_evidence_rechecked_before_consumption_after_consumption_and_after_grant(self):
        for boundary in ('before', 'consumed', 'grant'):
            with self.subTest(boundary=boundary):
                self.setUp()
                invite, _ = self.prepared()
                if boundary == 'before':
                    original = self.a.get_datashares
                    def outgoing():
                        self.withdraw()
                        return original()
                    self.a.get_datashares = outgoing
                elif boundary == 'consumed':
                    self.a.after_update = lambda changes: self.withdraw() if 'consumed' in changes.get('description', '') else None
                else:
                    self.a.after_share = self.withdraw
                result = self.i.match(self.a)
                self.assertNotEqual(result['results'][0]['status'], 'matched')
                self.assertEqual(len(self.a.load()[OWN]['shares']), int(boundary == 'grant'))
                self.assertNotEqual(self.details(invite['data_type'])['invitation']['state'], 'completed')
                self.a.after_update = self.a.after_share = None
                self.i.match(self.account(OWN))
                self.assertEqual(len(self.a.load()[OWN]['shares']), int(boundary == 'grant'))

    def test_accept_selected_channel_ignores_independent_broad_policy(self):
        channel = self.b.create_data_type('Event', dict(name='Response', description='Context',
            record_spec={'schema': json.dumps(self.c.connections.CHANNEL_FIELDS)}))['id']
        self.b.create_datashare(fulcra_data_types=[], allowed_user_ids=[OTHER], share_all_data=True)
        result = self.i.accept(self.b, OWN, 'handshake ' + 'a' * 32, 'helper', 'Hi', response_channel=channel)
        self.assertEqual(result['status'], 'introduction_posted')
        self.assertEqual(self.c.audience(self.b, PEER, channel), {OWN})

    def test_incompatible_event_and_template_are_not_handshake_history(self):
        self.prepared()
        channel = self.third.create_data_type('Event', dict(name='Log', description='',
            record_spec={'schema': json.dumps({'properties': {'kind': {'type': 'string'}}})}))['id']
        self.third.create_datashare(fulcra_data_types=[channel], allowed_user_ids=[OWN], share_all_data=False)
        self.third.record_data_type(channel, [{'id': str(uuid4()), 'kind': 'message'}], 'v1')
        template = self.third.create_data_type('Event', dict(name='connect-our-agents-standing-invitation',
            description='', record_spec={'schema': json.dumps(self.c.connections.CHANNEL_FIELDS)}))['id']
        self.third.create_datashare(fulcra_data_types=[template], allowed_user_ids=[OWN], share_all_data=False)
        state = self.a.load()
        state[OTHER]['rows'][template] = [{'kind': 'message'}]  # Must never interpret template history.
        self.a.save(state)
        self.assertEqual(self.i.match(self.a)['results'][0]['status'], 'matched')

    def test_duplicate_responders_and_ambiguous_first_time_do_not_match(self):
        invite, accepted = self.prepared()
        self.i.accept(self.third, OWN, invite['topic'], 'Third', 'Hi')
        self.assertFalse(any(r['status'] == 'matched' for r in self.i.match(self.a)['results']))
        state = self.a.load()
        state[OTHER]['shares'] = []
        state[PEER]['rows'][accepted['data_type']].append(dict(state[PEER]['rows'][accepted['data_type']][0], id=str(uuid4())))
        self.a.save(state)
        self.assertFalse(any(r['status'] == 'matched' for r in self.i.match(self.a)['results']))
        self.assertEqual(self.a.get_datashares(), [])

    def test_consumed_reconciles_existing_grant_but_never_recreates(self):
        invite, _ = self.prepared()
        update = self.a.update_data_type
        def fail_completion(base, uid, changes):
            if 'completed' in changes.get('description', ''):
                raise TimeoutError()
            update(base, uid, changes)
        self.a.update_data_type = fail_completion
        self.i.match(self.a)
        self.assertEqual(self.details(invite['data_type'])['invitation']['state'], 'consumed')
        self.assertEqual(len(self.a.get_datashares()), 1)
        self.assertEqual(self.i.match(self.account(OWN))['results'][0]['status'], 'matched')
        self.assertEqual(len(self.a.get_datashares()), 1)
        state = self.a.load()
        state[OWN]['shares'] = []
        details = self.details(invite['data_type'])
        details['invitation']['state'] = 'consumed'
        state[OWN]['catalog'][invite['data_type']]['description'] = 'Connection details: ' + json.dumps(details)
        self.a.save(state)
        result = self.i.match(self.account(OWN))
        self.assertNotEqual(result['results'][0]['status'], 'matched')
        self.assertEqual(self.a.get_datashares(), [])

    def test_status_tool_is_agent_registered(self):
        self.assertIn('fulcra_set_contact_status', self.tools.TOOL_SCHEMAS)

    def test_schema_wire_plumbing_nullable_fields_and_optional_extensions(self):
        invite, _ = self.prepared()
        state = self.a.load()
        for owner in (OWN, PEER):
            for entry in state[owner]['catalog'].values():
                schema = json.loads(entry['record_spec']['schema'])
                schema['properties'].update(id={'type': 'string'}, start_time={'type': 'string'},
                                            sources={'type': 'array'}, tags={'type': 'array'})
                schema['required'] += ['id', 'start_time', 'sources', 'tags']
                schema['properties']['topic'] = {'anyOf': [schema['properties']['topic'], {'type': 'null'}], 'title': 'Topic'}
                schema['properties']['optional_extension'] = {'type': 'string'}
                entry['record_spec']['schema'] = json.dumps(schema)
        self.a.save(state)
        self.assertEqual(self.i.match(self.a)['results'][0]['status'], 'matched')
        self.assertEqual(self.details(invite['data_type'])['invitation']['state'], 'completed')

    def test_status_set_and_message_reply_clear_but_ack_retains(self):
        invite, accepted = self.prepared()
        self.i.match(self.a)
        channel = invite['data_type']
        for kind in ('ack', 'message', 'reply'):
            result = self.c.set_status(self.a, channel, PEER, True, 'Decision needed')
            self.assertTrue(result['verified'])
            args = {kind if kind == 'ack' else 'reply_to': accepted['mid']} if kind != 'message' else {}
            sent = self.c.send(self.a, channel, 'helper', 'Hello', **args)
            self.assertEqual(sent['status'], 'posted')
            description = self.a.v1_catalog(channel)[0]['description']
            self.assertEqual('Contact status:' in description, kind == 'ack')
            self.assertIn('Connection details:', description)

    def test_public_schema_and_metadata_wire_roundtrip(self):
        # Public connection-schema.json contract, not an MCP private helper import.
        contract = json.loads(Path(__file__).with_name('fixtures').joinpath('connection-schema.json').read_text())
        invite, accepted = self.prepared()
        for api, channel in ((self.a, invite['data_type']), (self.b, accepted['data_type'])):
            schema = api.v1_catalog_schema(channel, 'v1')
            wire_fields = json.loads(json.dumps(schema['properties']),
                                     object_hook=lambda value: {k: v for k, v in value.items() if k != 'description'})
            self.assertEqual(wire_fields, contract['fields'])
            self.assertEqual(sorted(schema['required']), contract['required_fields'])
        self.i.match(self.a)
        details = self.details(invite['data_type'])
        self.assertEqual(details['peers'], [{'fulcra_userid': PEER, 'data_type': accepted['data_type']}])
        self.assertEqual(details['invitation'], dict(code=invite['code'], prefix='handshake', state='completed',
                                                   peer_userid=PEER, incoming_data_type=accepted['data_type']))

    def test_changed_first_message_and_malformed_compatible_history_fail_closed(self):
        invite, accepted = self.prepared()
        def change(changes):
            if 'consumed' in changes.get('description', ''):
                state = self.a.load()
                state[PEER]['rows'][accepted['data_type']][0]['topic'] = 'chat'
                self.a.save(state)
        self.a.after_update = change
        self.assertNotEqual(self.i.match(self.a)['results'][0]['status'], 'matched')
        self.assertEqual(self.a.get_datashares(), [])
        self.assertEqual(self.details(invite['data_type'])['invitation']['state'], 'consumed')
        state = self.a.load()
        del state[PEER]['rows'][accepted['data_type']][0]['start_time']
        self.a.save(state)
        self.assertEqual(self.i.match(self.a)['status'], 'unavailable')
        self.assertEqual(self.a.get_datashares(), [])

    def test_standing_uncertain_creation_is_reserved_not_recreated(self):
        template = self.standing_template()
        self.i.accept(self.b, OWN, 'open_invitation ' + 'a' * 32, 'helper', 'Hi')
        create = self.a.create_data_type
        def fail_readback(base, body):
            create(base, body)
            raise TimeoutError()
        self.a.create_data_type = fail_readback
        self.assertEqual(self.i.match(self.a)['results'][0]['status'], 'uncertain')
        self.assertEqual(self.details(template)['invitation']['responses'][PEER]['state'], 'creating')
        self.assertEqual(len(self.a.v1_catalog()), 2)
        self.assertEqual(self.i.match(self.account(OWN))['results'][0]['status'], 'uncertain')
        self.assertEqual(len(self.a.v1_catalog()), 2)
        self.assertEqual(self.a.get_datashares(), [])

    def test_standing_consumed_reconciles_and_withdrawal_prevents_grant(self):
        template = self.standing_template()
        self.i.accept(self.b, OWN, 'open_invitation ' + 'a' * 32, 'helper', 'Hi')
        update = self.a.update_data_type
        def fail_completion(base, uid, changes):
            if 'completed' in changes.get('description', ''):
                raise TimeoutError()
            update(base, uid, changes)
        self.a.update_data_type = fail_completion
        self.assertEqual(self.i.match(self.a)['results'][0]['status'], 'uncertain')
        self.assertEqual(self.details(template)['invitation']['responses'][PEER]['state'], 'consumed')
        self.assertEqual(self.i.match(self.account(OWN))['results'][0]['status'], 'matched')
        self.assertEqual(len(self.a.get_datashares()), 1)
        self.i.accept(self.third, OWN, 'open_invitation ' + 'a' * 32, 'helper', 'Hi')
        def withdraw_third(changes):
            details = self.c.metadata(changes.get('description', ''))
            if details.get('invitation', {}).get('responses', {}).get(OTHER, {}).get('state') == 'consumed':
                state = self.a.load()
                state[OTHER]['shares'] = []
                self.a.save(state)
        self.a.update_data_type = update
        self.a.after_update = withdraw_third
        self.assertEqual(self.i.match(self.a)['results'][0]['status'], 'uncertain')
        self.assertEqual(len(self.a.get_datashares()), 1)
        self.i.match(self.account(OWN))
        self.assertEqual(len(self.a.get_datashares()), 1)

    def test_status_clear_failure_preserves_posted_and_bracketed_metadata(self):
        invite, _ = self.prepared()
        self.i.match(self.a)
        channel = invite['data_type']
        assessment = dict(attention=True, reason='Decision needed', assessed_at='2026-01-01T00:00:00Z')
        description = self.a.v1_catalog(channel)[0]['description'] + '\n'
        self.a.update_data_type('Event', channel.split('/')[1], {'description': description + '[contact_status: ' + json.dumps(assessment) + ']Suffix'})
        update = self.a.update_data_type
        def denied(*args):
            raise PermissionError()
        self.a.update_data_type = denied
        sent = self.c.send(self.a, channel, 'helper', 'Hi')
        self.assertEqual(sent['status'], 'posted')
        self.assertFalse(sent['status_cleared'])
        self.a.update_data_type = update
        recovered = self.c.send(self.a, channel, 'helper', 'Hi', record_id=sent['mid'])
        self.assertTrue(recovered['status_cleared'])
        self.assertEqual(self.a.v1_catalog(channel)[0]['description'], description + 'Suffix')
        self.assertEqual(len(self.a.load()[OWN]['rows'][channel]), 1)

    def standing_template(self):
        return self.a.create_data_type('Event', dict(name='connect-our-agents-standing-invitation',
            description='Contact label: "Open invitation"\nConnection details: ' + json.dumps(dict(version=1,
                invitation=dict(code='a' * 32, prefix='open_invitation', state='prepared', responses={}))),
            record_spec={'schema': json.dumps(self.c.connections.CHANNEL_FIELDS)}))['id']

    def test_standing_template_fans_out(self):
        template = self.standing_template()
        for api in (self.b, self.third):
            self.assertEqual(self.i.accept(api, OWN, 'open_invitation ' + 'a' * 32, 'helper', 'Hi')['status'], 'introduction_posted')
        result = self.i.match(self.a)
        self.assertEqual([r['status'] for r in result['results']], ['matched', 'matched'])
        responses = self.details(template)['invitation']['responses']
        self.assertEqual(set(responses), {PEER, OTHER})
        self.assertEqual(len({r['data_type'] for r in responses.values()}), 2)
        for peer, binding in responses.items():
            self.assertEqual(binding['state'], 'completed')
            self.assertEqual(self.c.audience(self.a, OWN, binding['data_type']), {peer})
            self.assertNotEqual(binding['data_type'], template)
            self.assertEqual(self.details(binding['data_type'])['peers'][0]['fulcra_userid'], peer)
        self.assertEqual(self.i.match(self.account(OWN))['results'], [])
        self.assertFalse(any(s['fulcra_data_types'] == [template] for s in self.a.get_datashares()))
