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
        files = [*ROOT.glob('*.py'), *ROOT.joinpath('_vendor').rglob('*.py')]
        for path in files:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({n.name.split('.')[0] for n in node.names} & banned, path)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], banned, path)
                elif isinstance(node, ast.Call):
                    self.assertNotIn(ast.unparse(node.func), {'os.system', 'os.popen', 'eval', 'exec', '__import__'}, path)

    def test_auth_pending_and_private_compatible_credentials(self):
        import io
        import json
        import tempfile
        from datetime import datetime, timedelta
        from urllib.error import HTTPError
        from native_plugin import client as auth
        from native_plugin._vendor.fulcra_api.credentials import FulcraCredentials
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


if __name__ == '__main__':
    unittest.main()
