"""Event receive workflows with synthetic accounts; no network."""
import copy
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
OWN = '11111111-1111-4111-8111-111111111111'
PEER = '22222222-2222-4222-8222-222222222222'
CHANNEL = 'Event/33333333-3333-4333-8333-333333333333'
SHARE = '44444444-4444-4444-8444-444444444444'
MID = '55555555-5555-4555-8555-555555555555'


def load_plugin():
    spec = importlib.util.spec_from_file_location('mesh_fixture_plugin', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from native_fixture import install
    return install(module)


class State:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return copy.deepcopy(self.data.get(key, default))

    def set(self, key, value):
        self.data[key] = copy.deepcopy(value)


class MeshTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load_plugin()
        self.mesh = self.plugin.mesh
        self.state = State()
        self.handler = self.mesh.make_handler(self.state)
        self.own = OWN
        self.incoming = [dict(datashare_id=SHARE, sharing_fulcra_userid=PEER,
                             fulcra_data_types=[CHANNEL], share_all_data=False, grant_type='group')]
        self.env = dict(id=MID, sender='peer', recipients=['ours'], kind='message',
                        priority='P2', topic='chat', body='hello')
        self.records = [self.env]
        self.calls = []
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        constants = types.ModuleType('hermes_constants')
        constants.get_hermes_home = lambda: Path(temp.name)
        for stub in (patch.dict(sys.modules, {'hermes_constants': constants}),
                     patch.object(self.plugin.tools, 'fixture_call', side_effect=self.cli)):
            stub.start()
            self.addCleanup(stub.stop)

    def cli(self, argv):
        self.calls.append(argv)
        if argv == ['user-info']:
            return json.dumps({'userid': self.own})
        if argv == ['share', 'list-incoming']:
            return '\n'.join(map(json.dumps, self.incoming))
        if argv[0] == 'get-records':
            return '\n'.join(map(json.dumps, self.records))
        raise AssertionError(argv)

    def call(self, **kwargs):
        return self.handler(dict(local_agent='ours', **kwargs))

    def test_receive_filters_proven_origin_and_durable_dedup(self):
        self.records += [dict(self.env, recipients=['other']), dict(self.env, kind='invalid'), {}]
        self.incoming += [dict(self.incoming[0], share_all_data=True),
                          dict(self.incoming[0], fulcra_data_types=[CHANNEL, 'HeartRate'])]
        result = json.loads(self.call())
        message = result['messages'][0]
        self.assertEqual(message['origin_userid'], PEER)
        self.assertEqual(message['grant_type'], 'group')
        self.assertEqual(message['envelope']['mid'], MID)
        self.assertTrue(result['untrusted_peer_content'])
        self.assertEqual(result['ignored_records'], 3)
        self.assertEqual(result['ignored_shares'], 2)
        self.handler = self.mesh.make_handler(self.state)
        self.assertEqual(json.loads(self.call())['messages'], [])
        read = [c for c in self.calls if c[0] == 'get-records'][-1]
        self.assertEqual(read[-2:], ['--user-id', PEER])
        self.assertEqual(datetime.fromisoformat(read[2]),
                         datetime.fromisoformat(result['windows'][0]['until']) - self.mesh.OVERLAP)
        before = len(self.calls)
        self.call(incoming_channel='Event/' + MID)
        self.assertFalse(any(c[0] == 'get-records' for c in self.calls[before:]))

    def test_failed_read_and_artifact_failure_do_not_consume_messages(self):
        self.records = [dict(self.env, id=str(uuid4()), body='é' * 4000) for _ in range(3)]
        with patch.object(self.plugin.tools, 'records', side_effect=RuntimeError('read failed')):
            self.assertIn('Error', self.call())
        self.assertEqual(self.state.data, {})
        with patch.object(sys.modules[self.plugin.__name__ + '.output'], '_save_output', side_effect=OSError('full')):
            self.assertIn('Error', self.call())
        self.assertEqual(self.state.data, {})
        output = self.call()
        path = Path(output.split('Complete UTF-8 text: ', 1)[1].splitlines()[0])
        self.assertEqual(json.loads(path.read_text())['messages'][0]['envelope']['body'], 'é' * 4000)
        self.assertEqual(json.loads(self.call())['messages'], [])

    def test_account_agent_separation_and_bounded_cursor(self):
        self.call()
        self.own = PEER
        self.assertEqual(json.loads(self.call())['messages'], [])
        self.own = OWN
        self.assertEqual(json.loads(self.call())['messages'], [])
        self.assertEqual(json.loads(self.handler({'local_agent': 'other'}))['messages'], [])
        self.records = [dict(self.env, id=str(uuid4())) for _ in range(self.mesh.DEDUP_LIMIT + 2)]
        self.call(since='2026-01-01T00:00:00Z')
        cursor = next(iter(self.state.data[self.mesh.STATE_KEY]['receives'].values()))
        self.assertEqual(len(cursor['mids']), self.mesh.DEDUP_LIMIT)
        before = copy.deepcopy(self.state.data)
        with patch.object(self.mesh, '_userid', side_effect=[OWN, PEER]):
            self.assertIn('account changed', self.call())
        self.assertEqual(self.state.data, before)
