"""Real Hermes registration/state probe; run with Hermes's Python, no network."""
import json
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugins import PluginContext, PluginManager
from hermes_cli.plugins_manifest import PluginManifest
from tools.registry import registry
from test_mesh import load_plugin, OWN, PEER, CHANNEL, MID

plugin = load_plugin()
manifest = PluginManifest(name='context', path=str(Path(__file__).resolve().parents[1]), source='project')
account = OWN
calls = []


def cli(argv):
    calls.append(argv)
    if argv == ['user-info']:
        return json.dumps({'userid': account, 'intercom_token': 'must-not-persist'})
    if argv == ['share', 'list-incoming']:
        return json.dumps({'sharing_fulcra_userid': PEER, 'fulcra_data_types': [CHANNEL],
                           'share_all_data': False, 'grant_type': 'group'})
    if argv[0] == 'get-records':
        return json.dumps(dict(id=MID, sender='peer', recipients=['ours'],
                               kind='message', priority='P2', topic='probe', body='fixture'))
    raise AssertionError(argv)


with tempfile.TemporaryDirectory(prefix='mesh-hermes-probe-') as root, \
        patch.object(plugin.tools, 'fixture_call', side_effect=cli), \
        patch.object(socket.socket, 'connect', side_effect=AssertionError('No networking')):
    homes = [Path(root) / name for name in ('a', 'b')]
    for home in homes:
        home.mkdir()

    for iteration, index in enumerate((0, 1, 0)):
        token = set_hermes_home_override(homes[index])
        try:
            manager = PluginManager()
            ctx = PluginContext(manifest, manager)
            plugin.register(ctx)
            entry = registry.get_entry('fulcra_receive_agent_messages', scope=manager.scope_key)
            assert entry is not None
            handler = entry.handler
            received = json.loads(handler({'local_agent': 'ours'}))
            assert len(received['messages']) == (0 if iteration == 2 else 1)
            assert received['windows'][0]['grant_type'] == 'group'
            if received['messages']:
                assert received['messages'][0]['origin_userid'] == PEER
            saved = json.loads(ctx.state.path.read_text())
            for text in ('must-not-persist', 'fixture'):
                assert text not in json.dumps(saved)
            assert ctx.state.path.stat().st_mode & 0o777 == 0o600
            assert PluginContext(manifest, manager).state.get(plugin.mesh.STATE_KEY) == saved[plugin.mesh.STATE_KEY]
            assert not (homes[index] / 'fulcra-output').exists(), 'Small responses must remain inline'
        finally:
            reset_hermes_home_override(token)

    assert not any(c[0] in ('record', 'data-type') or c[:2] == ['share', 'create'] for c in calls)
    assert 'fulcra_api' not in sys.modules
print('Real Hermes PluginContext + ctx.state: PASS (A→B→A Event receive, group provenance, dedup, private metadata, inline-only small responses; network blocked)')
