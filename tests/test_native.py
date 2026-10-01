"""Native boundary contracts; no production requests."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
pkg = types.ModuleType('native_plugin')
pkg.__path__ = [str(ROOT)]
sys.modules['native_plugin'] = pkg


class NativeTests(unittest.TestCase):
    def test_runtime_has_no_process_or_heavy_imports(self):
        import ast
        banned = {'subprocess', 'uv', 'pandas', 'numpy', 'pyarrow', 'dateparser', 'click'}
        files = [*ROOT.glob('*.py'), *ROOT.joinpath('_vendor').glob('*.py')]
        for path in files:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({n.name.split('.')[0] for n in node.names} & banned, path)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], banned, path)
                elif isinstance(node, ast.Call):
                    self.assertNotIn(ast.unparse(node.func), {'os.system', 'os.popen', 'eval', 'exec', '__import__'}, path)

    def test_native_catalog_without_process(self):
        from native_plugin import tools
        self.assertTrue(hasattr(tools, 'client'), 'native client factory missing')
        with patch.object(tools, 'client') as factory:
            factory.return_value.v1_catalog.return_value = [{'id': 'HeartRate'}]
            self.assertEqual(tools.fulcra_data_catalog({}), '[{"id": "HeartRate"}]')
            factory.return_value.v1_catalog.assert_called_once_with()

    def test_auth_pending_and_private_compatible_credentials(self):
        import io
        import json
        import tempfile
        from datetime import datetime, timedelta
        from urllib.error import HTTPError
        from native_plugin import client as auth
        from native_plugin._vendor.credentials import FulcraCredentials
        with tempfile.TemporaryDirectory() as root, patch.object(auth, 'credential_path', return_value=Path(root) / 'credentials.json'), patch.object(auth.Client, '_open') as request:
            request.side_effect = HTTPError('https://fixture', 403, 'denied', {}, io.BytesIO(b'{"error":"authorization_pending"}'))
            self.assertEqual(auth.auth_finish('private')['status'], 'pending')
            self.assertEqual(request.call_count, 1)
            self.assertFalse((Path(root) / 'credentials.json').exists())
            request.side_effect = None
            request.return_value.read.return_value = b'{"access_token":"secret", "refresh_token":"refresh", "expires_in":3600}'
            self.assertEqual(auth.auth_finish('private'), {'status': 'authorized'})
            saved = Path(root) / 'credentials.json'
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
            self.assertEqual(FulcraCredentials.from_json(saved.read_text()).refresh_token, 'refresh')

    def test_selector_replacement_never_inherits_all_data(self):
        from native_plugin import tools
        with patch.object(tools, 'client') as factory:
            factory.return_value.update_datashare.return_value = {}
            share = '11111111-1111-4111-8111-111111111111'
            result = tools.fulcra_update_share({'share_id': share, 'files': ['/private'], 'data_types': []})
            self.assertFalse(result.startswith('Error'), result)
            factory.return_value.update_datashare.assert_called_once_with(share, fulcra_data_types=['file:/private'], share_all_data=False)

    def test_transport_value_errors_withhold_sensitive_text(self):
        from native_plugin import tools
        with patch.object(tools, 'client') as factory:
            factory.return_value.v1_catalog.side_effect = ValueError('signed-url private-token')
            result = tools.fulcra_data_catalog({})
            self.assertTrue(result.startswith('Error:'))
            self.assertNotIn('private-token', result)

    def test_write_error_does_not_repeat_or_expose_payload(self):
        from native_plugin import tools
        with patch.object(tools, 'client') as factory:
            factory.return_value.create_datashare.side_effect = TimeoutError('private token')
            result = tools.fulcra_file_share({'name': 'x', 'path': '/x', 'user_ids': ['11111111-1111-4111-8111-111111111111']})
            self.assertIn('uncertain', result)
            self.assertNotIn('private token', result)
            self.assertEqual(factory.return_value.create_datashare.call_count, 1)


if __name__ == '__main__':
    unittest.main()
