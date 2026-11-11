"""Vendored code against the pinned upstream checkouts.

Set FULCRA_API_PYTHON and FULCRA_CONTEXT_MCP to checkouts at the pins in scripts/vendor.py.
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
from unittest.mock import Mock, patch

from plugin import ROOT, load

ID = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
CHECKOUTS = {'fulcra_api': os.environ.get('FULCRA_API_PYTHON'), 'fulcra_mcp': os.environ.get('FULCRA_CONTEXT_MCP')}


@unittest.skipUnless(all(CHECKOUTS.values()), 'set FULCRA_API_PYTHON and FULCRA_CONTEXT_MCP')
class VendorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('vendor_script', ROOT / 'scripts/vendor.py')
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)
        cls.checkouts = {k: Path(v) for k, v in CHECKOUTS.items()}
        for package, path in cls.checkouts.items():
            head = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
            assert head == cls.script.PINS[package], f'{package} checkout is not at the pin'
        upstream = types.ModuleType('fulcra_api')
        upstream.__version__ = 'unknown'
        upstream.__path__ = [str(cls.checkouts['fulcra_api'] / 'fulcra_api')]
        with patch.dict(sys.modules, {'fulcra_api': upstream}):
            cls.up = importlib.import_module('fulcra_api.core')
            cls.up_records = importlib.import_module('fulcra_api.records')
        load()
        cls.vendor = importlib.import_module('fulcra_plugin._vendor.fulcra_api.core')
        cls.records = importlib.import_module('fulcra_plugin._vendor.fulcra_api.records')

    def test_vendored_files_are_exactly_the_reachable_extraction(self):
        expected = self.script.extract(self.checkouts)
        actual = {str(p.relative_to(ROOT / '_vendor')): p.read_bytes()
                  for package in self.script.PINS for p in (ROOT / '_vendor' / package).rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts}
        self.assertEqual(sorted(actual), sorted(expected))
        for path, data in expected.items():
            self.assertEqual(actual[path], data, path)

    def clients(self):
        claims = base64.urlsafe_b64encode(json.dumps({'fulcradynamics.com/userid': ID}).encode()).decode()
        return [module.FulcraAPI(oidc_audience='http://127.0.0.1:9', access_token='x.' + claims + '.x',
                                 access_token_expiration=datetime.now() + timedelta(hours=1))
                for module in (self.up, self.vendor)]

    def test_requests_match_upstream(self):
        cases = [
            ('v1_catalog', (), {'category': 'event', 'fulcra_userid': OTHER}),
            ('create_data_type', ('Event', {'name': 'Contact', 'description': 'test'}), {}),
            ('update_data_type', ('Event', ID, {'description': 'updated'}), {}),
            ('v1_catalog_schema', ('MomentAnnotation', 'v1alpha1', OTHER), {}),
            ('data_updates', ('2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'), {}),
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
                    def opened(req, **kwargs):
                        requests.append((req.full_url, req.method, req.data, dict(req.headers)))
                        return io.BytesIO(b'{}')
                    api._open = opened
                    with patch.object(self.up.urllib.request, 'urlopen', side_effect=opened), \
                            patch('socket.socket.connect', side_effect=AssertionError('offline only')):
                        observed.append((getattr(api, method)(*args, **kwargs), requests))
                self.assertEqual(*observed)

    def test_record_reads_match_upstream(self):
        start, end = datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc)
        for version in ('v0', 'v1alpha1', 'v1'):
            for owner in (ID, OTHER):
                observed = []
                for records, api in zip((self.up_records, self.records), self.clients()):
                    calls = []
                    def request(path, **kwargs):
                        calls.append((path, kwargs))
                        return b'{"value":1}\n' if path == '/data/v1/records' else b'[{"value":1}]'
                    api.fulcra_api = request
                    entry = {'id': 'HeartRate', 'api_version': version, 'fulcra_userid': owner, 'record_spec': {'type': 'metric'}}
                    observed.append((records.get_records(api, entry, start, end), calls))
                self.assertEqual(*observed, (version, owner))

    def test_sign_in_and_refresh_match_upstream(self):
        observed = []
        for api in self.clients():
            calls = []
            def opened(req, **kwargs):
                calls.append((req.full_url, req.method, req.data))
                value = ({'device_code': 'device', 'verification_uri_complete': 'https://fixture/verify',
                          'user_code': 'human', 'expires_in': 3600, 'interval': 5}
                         if req.full_url.endswith('/code') else
                         {'access_token': 'access', 'refresh_token': 'refresh', 'id_token': 'identity', 'expires_in': 3600})
                return Mock(status=200, read=Mock(return_value=json.dumps(value).encode()))
            api.oidc._open = opened
            with patch.object(self.up.urllib.request, 'urlopen', side_effect=opened):
                device = api.oidc.get_device_code()
                creds = api.oidc.get_token('urn:ietf:params:oauth:grant-type:device_code', {'device_code': 'device'})
            credential = type(api.fulcra_credentials)
            api.fulcra_credentials = credential(access_token='old', access_token_expiration=datetime(2026, 1, 1),
                                                refresh_token='retain')
            api.oidc.refresh_credentials = Mock(return_value=credential(access_token='new', access_token_expiration=datetime(2026, 1, 1)))
            api.refresh_callback = Mock()
            api.refresh_access_token()
            observed.append((device, creds.refresh_token, calls, api.fulcra_credentials.to_json()))
        self.assertEqual(*observed)


if __name__ == '__main__':
    unittest.main()
