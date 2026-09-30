"""Differential checks against the pinned, read-only upstream checkout.

Set FULCRA_UPSTREAM to run; pandas is an import-only sentinel and cannot be used.
No CLI helpers or extraction generator participate in the expected results.
"""
import base64
from datetime import datetime, timedelta, timezone
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch, Mock
from test_tools import load_tools

PIN = '66949bac42920c841facd567a02d6d6c4e01e824'
ID = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


@unittest.skipUnless(os.environ.get('FULCRA_UPSTREAM'), 'set FULCRA_UPSTREAM for pinned upstream parity')
class ParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(os.environ['FULCRA_UPSTREAM'])
        assert subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip() == PIN
        package = types.ModuleType('fulcra_api')
        package.__path__ = [str(path / 'fulcra_api')]
        pandas = types.ModuleType('pandas')
        pandas.DataFrame = object  # Only unused annotations need it, no pandas operations permitted.
        with patch.dict(sys.modules, {'fulcra_api': package, 'pandas': pandas}):
            cls.up = importlib.import_module('fulcra_api.core')
            cls.up_records = importlib.import_module('fulcra_api.records')
        load_tools()
        cls.vendor = importlib.import_module('tool_fixture_plugin._vendor.core')
        cls.native = importlib.import_module('tool_fixture_plugin.client')
        cls.records = importlib.import_module('tool_fixture_plugin._vendor.records')

    def clients(self):
        claims = base64.urlsafe_b64encode(json.dumps({'fulcradynamics.com/userid': ID}).encode()).decode()
        return [module.FulcraAPI(oidc_audience='http://127.0.0.1:9', access_token='x.' + claims + '.x', access_token_expiration=datetime.now() + timedelta(hours=1)) for module in (self.up, self.vendor)]

    def test_wire_methods_match_upstream(self):
        cases = [
            ('v1_catalog', (), {'category': 'event', 'fulcra_userid': OTHER}),
            ('v1_catalog_schema', ('MomentAnnotation', 'v1alpha1', OTHER), {}),
            ('data_updates', ('2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'), {}),
            ('create_annotation', ('scale', 'Mood', 'desc', []), {'scale_labels': ['a', 'b', 'c', 'd', 'e']}),
            ('record_data_type', ('MomentAnnotation', [{'note': 'é\n'}], 'v1alpha1'), {}),
            ('create_datashare', ('Named', ['file:/notes', 'HeartRate'], [OTHER]), {'allowed_group_ids': [ID]}),
            ('update_datashare', (ID,), {'allowed_group_ids': [], 'time_end': None, 'share_all_data': False}),
            ('delete_datashare', (ID,), {}), ('delete_dataset_permission', (ID,), {}),
            ('list_shared_data_types', (OTHER, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'), {}),
            ('get_datashares', (), {}), ('get_shared_datasets', (), {}),
            ('list_files', ('/notes',), {'fulcra_userid': OTHER}),
            ('restore_file', (ID,), {}), ('delete_file', (ID,), {}),
        ]
        for method, args, kwargs in cases:
            with self.subTest(method=method):
                observed = []
                for api in self.clients():
                    requests = []
                    def opened(req):
                        requests.append((req.full_url, req.method, req.data, dict(req.headers)))
                        return io.BytesIO(b'{}')
                    api._open = opened
                    with patch.object(self.up.urllib.request, 'urlopen', side_effect=opened), patch('socket.socket.connect', side_effect=AssertionError('Parity must be offline')):
                        value = getattr(api, method)(*args, **kwargs)
                    observed.append((value, requests))
                self.assertEqual(*observed)

    def test_annotation_tag_resolution_matches(self):
        observed = []
        for api in self.clients():
            calls = []
            def request(path, **kwargs):
                calls.append((path, kwargs))
                if path == '/user/v1alpha1/tag' and not kwargs:
                    return b'[{"name":"existing", "id":"known"}]'
                return b'{"id":"created"}'
            api.fulcra_api = request
            result = api.create_annotation('moment', 'Note', '', ['existing', 'new'])
            observed.append((result, calls))
        self.assertEqual(*observed)

    def test_catalog_ambiguity_and_owner_resolution(self):
        entries = [{'id': 'HeartRate', 'api_version': v, 'fulcra_userid': owner} for v in ('v0', 'v1') for owner in (ID, OTHER)]
        results = []
        for api in self.clients():
            api.v1_catalog = Mock(return_value=entries)
            results.append(api.resolve_data_type('HeartRate', 'v1'))
        self.assertEqual(*results)
        self.assertEqual(results[0], [entries[2]])

    def test_records_dispatch_and_scope_match(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)
        for version in ('v0', 'v1alpha1', 'v1'):
            for owner in (ID, OTHER):
                for grouped in (False, True):
                    observed = []
                    for module, record_module, api in zip((self.up, self.vendor), (self.up_records, self.records), self.clients()):
                        calls = []
                        def request(path, **kwargs):
                            calls.append((path, kwargs))
                            return b'{"value":1}\n' if path == '/data/v1/records' else b'[{"value":1}]'
                        api.fulcra_api = request
                        source = api.group_participant(ID, OTHER) if grouped else api
                        entry = {'id': 'HeartRate', 'api_version': version, 'fulcra_userid': owner, 'record_spec': {'type': 'metric'}}
                        try:
                            result = record_module.get_records(source, entry, start, end)
                        except ValueError as exc:
                            result = str(exc)
                        observed.append((result, calls))
                    self.assertEqual(*observed, (version, owner, grouped))
        self.assertEqual(self.records.build_v1_promql('HeartRate', latest=True), self.up_records.build_v1_promql('HeartRate', latest=True))

    def test_device_and_token_wire_parity(self):
        observed = []
        for api in self.clients():
            calls = []
            def opened(req):
                calls.append((req.full_url, req.method, req.data, dict(req.headers)))
                value = ({'device_code': 'device', 'verification_uri_complete': 'https://fixture/verify',
                          'user_code': 'human', 'expires_in': 3600, 'interval': 5}
                         if req.full_url.endswith('/code') else
                         {'access_token': 'access', 'refresh_token': 'refresh', 'id_token': 'identity', 'expires_in': 3600})
                return Mock(status=200, read=Mock(return_value=json.dumps(value).encode()))
            api.oidc._open = opened
            with patch.object(self.up.urllib.request, 'urlopen', side_effect=opened), patch('socket.socket.connect', side_effect=AssertionError('Parity must be offline')):
                device = api.oidc.get_device_code()
                creds = api.oidc.get_token('urn:ietf:params:oauth:grant-type:device_code', {'device_code': 'device'})
            observed.append((device, creds.access_token, creds.refresh_token, creds.id_token, calls))
        self.assertEqual(*observed)

    def test_extraction_reproducible(self):
        import ast
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('vendor_extraction', root / 'scripts/vendor.py')
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        upstream = Path(os.environ['FULCRA_UPSTREAM'])
        for name in ('core', 'oidc', 'credentials', 'records'):
            expected = generator.extract((upstream / 'fulcra_api' / (name + '.py')).read_text(), name)
            actual = (root / '_vendor' / (name + '.py')).read_text()
            self.assertEqual(ast.dump(ast.parse(actual)), ast.dump(ast.parse(expected)), name)
        self.assertEqual((root / '_vendor/LICENSE').read_bytes(), (upstream / 'LICENSE').read_bytes())

    def test_credentials_roundtrip_and_refresh_preservation(self):
        stamp = datetime(2026, 1, 1)
        observed = []
        for api in self.clients():
            credential = type(api.fulcra_credentials)
            api.fulcra_credentials = credential(access_token='old', access_token_expiration=stamp, refresh_token='retain')
            api.oidc.refresh_credentials = Mock(return_value=credential(access_token='new', access_token_expiration=stamp))
            callback = Mock()
            api.refresh_callback = callback
            self.assertTrue(api.refresh_access_token())
            callback.assert_called_once_with(api.fulcra_credentials)
            text = api.fulcra_credentials.to_json()
            self.assertEqual(credential.from_json(text).refresh_token, 'retain')
            observed.append(text)
        self.assertEqual(*observed)
