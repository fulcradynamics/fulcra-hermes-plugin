"""Runtime boundaries: no credentials, no heavy imports, processes only for the user's own sign-in."""
import ast
import asyncio
import importlib.util
import sys
import unittest
from unittest.mock import patch

from plugin import ROOT, Context, Fulcra, HermesConfig, load


class NativeTests(unittest.TestCase):
    def test_runtime_has_no_heavy_imports_and_starts_a_process_only_to_sign_in(self):
        banned = {'pandas', 'numpy', 'pyarrow', 'dateparser', 'click', 'requests', 'httpx', 'urllib', 'jsonschema'}
        for path in [*ROOT.glob('*.py'), *ROOT.glob('dashboard/*.py')]:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = ({n.name.split('.')[0] for n in node.names} if isinstance(node, ast.Import) else
                         {(node.module or '').split('.')[0]} if isinstance(node, ast.ImportFrom) else set())
                self.assertFalse(names & banned, path)
                if 'subprocess' in names:
                    self.assertEqual(path.name, 'commands.py')
                if isinstance(node, ast.Call):
                    self.assertNotIn(ast.unparse(node.func), {'os.system', 'os.popen', 'eval', 'exec', '__import__'}, path)
        source = (ROOT / 'commands.py').read_text()
        self.assertEqual(source.count('subprocess.run('), 1)
        self.assertIn("if answer not in ('', 'y', 'yes')", source)

    def test_no_credentials_or_fulcra_config(self):
        for path in [*ROOT.glob('*.py'), *ROOT.glob('dashboard/*.py'), *ROOT.glob('desktop/*.js')]:
            text = path.read_text()
            for word in ('credentials.json', '.config/fulcra', 'access_token', 'refresh_token', 'mcp-tokens'):
                self.assertNotIn(word, text, path)


@unittest.skipUnless(importlib.util.find_spec('fastapi'), 'fastapi is not installed')
class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load()
        self.config = HermesConfig().install(self)
        self.ctx = Context(Fulcra())
        self.plugin.register(self.ctx)
        spec = importlib.util.spec_from_file_location('fulcra_dashboard_api', ROOT / 'dashboard/plugin_api.py')
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)

    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def test_status_connect_and_ping(self):
        self.assertEqual(self.run_async(self.api.status())['url'], None)
        self.assertEqual(self.run_async(self.api.ping()), {'state': 'not_configured'})
        self.run_async(self.api.connect({}))
        self.assertEqual(self.config.data['mcp_servers']['fulcra']['auth'], 'oauth')
        self.assertTrue(self.run_async(self.api.status())['allowed'])
        self.assertEqual(self.run_async(self.api.ping())['state'], 'connected')
        self.ctx.fulcra = None
        self.assertEqual(self.run_async(self.api.ping())['state'], 'not_connected')

    def test_connect_requires_https(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            self.run_async(self.api.connect({'url': 'http://example.com/mcp'}))

    def test_unloaded_plugin_is_a_clear_error(self):
        from fastapi import HTTPException
        with patch.object(self.plugin.mcp_api, '_FULCRA_CTX', None), self.assertRaises(HTTPException) as caught:
            self.run_async(self.api.status())
        self.assertEqual(caught.exception.status_code, 503)


if __name__ == '__main__':
    unittest.main()
