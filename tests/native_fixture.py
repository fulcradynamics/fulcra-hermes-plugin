"""Scripted read fixtures for offline hook and receive tests.

Native wire/payload parity is tested separately in test_native and test_parity.
"""
import json


class FileStore:
    """User files that automatic hooks must leave untouched."""
    def __init__(self):
        self.files = {}
        self.calls = []

    def __call__(self, argv, timeout):
        self.calls.append((argv, timeout))
        raise AssertionError('Automatic hooks must not access user file contents')


def install(plugin):
    tools = plugin.tools
    def unavailable(*args, **kwargs):
        raise AssertionError('Unmocked fixture')
    tools.fixture_call = unavailable
    tools.client = lambda **kwargs: FixtureClient(plugin, kwargs.get('timeout'))
    # Record dispatch is covered separately by native and lifecycle tests.
    tools.records = lambda api, kind, start, end, user_id=None: api.records(kind, start, end, user_id)
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

    def get_shared_datasets(self):
        return self.rows(['share', 'list-incoming'])

    def records(self, kind, start, end, owner):
        argv = ['get-records', kind, start.isoformat(), end.isoformat()]
        if owner:
            argv += ['--user-id', owner]
        return self.rows(argv)

    def data_updates(self, start, end):
        return json.loads(self.call(['data-updates', start, end]))
