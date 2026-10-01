"""Adapt retained workflow fixtures to native clients, never a runtime transport.

The old scripted transcripts remain useful for cursor/consent/failure regressions.
Native wire/payload parity is tested separately in test_native and test_parity.
"""
import json
from pathlib import Path
import tempfile


def install(plugin):
    tools = plugin.tools
    def unavailable(*args, **kwargs):
        raise AssertionError('Unmocked fixture')
    tools.fixture_call = unavailable
    tools.client = lambda **kwargs: FixtureClient(plugin, kwargs.get('timeout'))
    # Exercise the workflow, with record dispatch covered separately by native tests.
    tools.records = lambda api, kind, start, end, user_id=None: api.records(kind, start, end, user_id)
    tools.record = lambda api, kind, rows: api.record(kind, rows)
    return plugin


class FixtureClient:
    def __init__(self, plugin, timeout):
        self.plugin, self.timeout = plugin, timeout

    def call(self, argv):
        if self.timeout is None:
            return self.plugin.tools.fixture_call(argv)
        return self.plugin.tools.fixture_call(argv, timeout=self.timeout)

    def rows(self, argv):
        return [json.loads(line) for line in self.call(argv).splitlines() if line.strip()]

    def get_user_info(self):
        return json.loads(self.call(['user-info']))

    def v1_catalog(self, data_type):
        return self.rows(['catalog', '--data-type', data_type])

    def create_annotation(self, kind, name, description, tags):
        assert kind == 'moment' and tags == []
        return json.loads(self.call(['data-type', 'create', 'MomentAnnotation', name, '--description', description]))

    def get_datashares(self):
        return self.rows(['share', 'list-outgoing'])

    def get_shared_datasets(self):
        return self.rows(['share', 'list-incoming'])

    def create_datashare(self, name, types, users, *, share_all_data, allowed_group_ids):
        assert share_all_data is False and allowed_group_ids == [] and len(types) == len(users) == 1
        return json.loads(self.call(['share', 'create', '--name', name, '--data-type', types[0], '--user-id', users[0]]))

    def record(self, kind, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'records'
            path.write_text('\n'.join(map(json.dumps, rows)))
            path.chmod(0o600)
            return self.call(['record', kind, '--file', str(path)])

    def records(self, kind, start, end, owner):
        argv = ['get-records', kind, start.isoformat(), end.isoformat()]
        if owner:
            argv += ['--user-id', owner]
        return self.rows(argv)

    def data_updates(self, start, end):
        return json.loads(self.call(['data-updates', start, end]))

    def read_file(self, remote):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'download'
            try:
                self.call(['file', 'download', remote, str(path)])
            except RuntimeError as exc:
                if str(exc) == f'Fulcra CLI exited with status 1: Error: File not found in Fulcra: {remote}':
                    from importlib import import_module
                    raise import_module(self.plugin.__name__ + '.client').MissingFile(remote) from None
                raise
            return path.read_bytes()

    def write_file(self, remote, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'upload'
            path.write_bytes(data)
            path.chmod(0o600)
            return self.call(['file', 'upload', str(path), remote])
