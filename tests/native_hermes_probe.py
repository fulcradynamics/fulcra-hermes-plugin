"""Run native registration and existing hook probes in disposable offline Hermes.

Usage: python tests/native_hermes_probe.py HERMES_PYTHON HERMES_SOURCE [--doctor | --validate]
"""
import argparse
import os
from pathlib import Path
import runpy
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
    if probe != 'native':
        sys.argv = [probe, source]
        runpy.run_path(str(Path(__file__).with_name(probe)), run_name='__main__')
        return
    import importlib.util
    from unittest.mock import patch
    from hermes_cli.plugins import PluginContext, get_plugin_manager
    from hermes_cli.plugins_manifest import PluginManifest
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from tools.registry import registry
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('native_runtime_plugin', root / '__init__.py', submodule_search_locations=[str(root)])
    plugin = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = plugin
    spec.loader.exec_module(plugin)
    for name in ('a', 'b', 'a'):
        home = Path(os.environ['HERMES_HOME']) / name
        home.mkdir(exist_ok=True)
        token = set_hermes_home_override(home)
        try:
            manager = get_plugin_manager()
            manager._discovered = True
            context = PluginContext(PluginManifest(name='context', path=str(root)), manager)
            before = sorted(home.rglob('*'))
            plugin.register(context)
            assert sorted(home.rglob('*')) == before
            assert context.get_config('workspace_context_enabled', False) is False
            entry = registry.get_entry('fulcra_data_catalog', scope=manager.scope_key)
            signed_out = entry.handler({})
            assert 'not signed in' in signed_out, signed_out
            assert 'fulcra_auth' in signed_out and 'fulcra_auth_device' in signed_out
            with patch.object(plugin.tools, 'client') as factory:
                factory.return_value.v1_catalog.return_value = [{'id': 'fixture'}]
                assert entry.handler({}) == '[{"id": "fixture"}]'
                factory.return_value.v1_catalog.assert_called_once_with()
            assert plugin.plugin_setup.Setup(context).command('status').startswith('Fulcra settings')
        finally:
            reset_hermes_home_override(token)
    print('Native tool registration A→B→A: PASS')


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
    probes = ('native', 'hermes_updates_probe.py', 'mesh_hermes_probe.py')
    if args.validate:
        probes = ('validate',)
    elif args.doctor:
        probes = ('doctor',)
    for probe in probes:
        with tempfile.TemporaryDirectory(prefix='plat510-', dir=os.environ['TMPDIR']) as directory:
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
