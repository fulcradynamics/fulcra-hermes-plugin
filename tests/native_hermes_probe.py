"""Register the plugin and exercise its tools in a disposable, offline Hermes.

Usage: python tests/native_hermes_probe.py HERMES_PYTHON HERMES_SOURCE [--doctor | --validate]
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types


def child(source, probe):
    def deny(event, args):
        if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
            raise RuntimeError('Probe network forbidden')
    sys.addaudithook(deny)
    sys.path[:0] = [source, str(Path(__file__).parent)]
    bootstrap = types.ModuleType('hermes_bootstrap')
    bootstrap._happy_eyeballs_create_connection = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline'))
    sys.modules['hermes_bootstrap'] = bootstrap
    if probe == 'validate':
        from hermes_cli.plugins_cmd_catalog import cmd_validate
        cmd_validate(str(Path(__file__).resolve().parents[1]))
        return
    if probe == 'doctor':
        from hermes_cli.plugins_cmd import cmd_plugin_doctor
        raise SystemExit(cmd_plugin_doctor(str(Path(__file__).resolve().parents[1]), ci=True))
    import importlib.util
    import json
    from unittest.mock import patch
    from hermes_cli.plugins import PluginContext, get_plugin_manager
    from hermes_cli.plugins_manifest import PluginManifest
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from tools.registry import registry
    from plugin import CHANNEL_FIELDS, accounts
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('fulcra_plugin', root / '__init__.py', submodule_search_locations=[str(root)])
    plugin = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = plugin
    spec.loader.exec_module(plugin)
    alex, sura = '00000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-00000000000b'
    for name in ('a', 'b', 'a'):
        home = Path(os.environ['HERMES_HOME']) / name
        home.mkdir(exist_ok=True)
        token = set_hermes_home_override(home)
        try:
            manager = get_plugin_manager()
            manager._discovered = True
            context = PluginContext(PluginManifest(name='fulcra', path=str(root)), manager)
            before = sorted(home.rglob('*'))
            plugin.register(context)
            assert sorted(home.rglob('*')) == before
            call = lambda tool, **args: registry.get_entry(tool, scope=manager.scope_key).handler(args)
            signed_out = call('fulcra_data_catalog')
            assert 'not signed in' in signed_out and 'fulcra_auth_device' in signed_out, signed_out
            assert plugin.whats_new.Setup(context).command('status').startswith("Fulcra what's new")
            (a, b), act, stop = accounts(plugin, alex, sura)
            try:
                invite = json.loads(call('fulcra_create_agent_invitation', inviter_name='Alex', recipient_name='Sura'))
                act(b)
                channel = json.loads(call('fulcra_create_data_type', base_type='event', name='Sura with Alex',
                                          description='Agent contact channel', fields=CHANNEL_FIELDS))['id']
                call('fulcra_create_share', name='connect-our-agents', data_types=[channel], files=[], user_ids=[alex])
                assert json.loads(call('fulcra_send_agent_message', connection=channel, sender='Sura',
                                       body='Hello', topic=invite['topic']))['status'] == 'posted'
                act(a)
                assert json.loads(call('fulcra_match_agent_invitations'))['results'][0]['status'] == 'matched'
                assert json.loads(call('fulcra_send_agent_message', connection=sura, sender='Alex', body='Hi'))['status'] == 'posted'
                act(b)
                inbox = json.loads(call('fulcra_receive_agent_messages', agent_name='Sura'))
                assert [m['body'] for m in inbox['messages']] == ['Hi'], inbox
            finally:
                stop()
        finally:
            reset_hermes_home_override(token)
    print('Native registration and invite/accept/match/send/receive through the registry A→B→A: PASS')


def main():
    if os.environ.get('FULCRA_PROBE_CHILD'):
        child(sys.argv[1], sys.argv[2])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('python')
    parser.add_argument('source')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--doctor', action='store_true')
    mode.add_argument('--validate', action='store_true')
    args = parser.parse_args()
    probes = ('native',)
    if args.validate:
        probes = ('validate',)
    elif args.doctor:
        probes = ('doctor',)
    for probe in probes:
        with tempfile.TemporaryDirectory(prefix='fulcra-native-', dir=os.environ['TMPDIR']) as directory:
            root = Path(directory)
            home = root / 'home'
            home.mkdir()
            profile = home / '.hermes'
            profile.mkdir()
            env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'HERMES_HOME': str(profile),
                   'TMPDIR': str(root), 'XDG_CONFIG_HOME': str(root / 'config'), 'XDG_CACHE_HOME': str(root / 'cache'),
                   'PYTHONDONTWRITEBYTECODE': '1', 'HF_HUB_OFFLINE': '1', 'FULCRA_PROBE_CHILD': '1'}
            bootstrap = 'import runpy,sys; sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")'
            subprocess.run([args.python, '-I', '-B', '-c', bootstrap, str(Path(__file__).resolve()), args.source, probe],
                           env=env, cwd=root, check=True, timeout=180)


if __name__ == '__main__':
    main()
