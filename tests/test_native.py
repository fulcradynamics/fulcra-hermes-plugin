"""Runtime boundaries: no credentials, no heavy imports, processes only for the user's own sign-in."""
import ast
import asyncio
import importlib.util
import sys
import unittest
from unittest.mock import patch

from plugin import ROOT, Context, Fulcra, HermesConfig, load


class NativeTests(unittest.TestCase):
    def test_runtime_has_no_heavy_imports_processes_or_config_writes(self):
        banned = {'pandas', 'numpy', 'pyarrow', 'dateparser', 'click', 'requests', 'httpx', 'urllib', 'jsonschema'}
        for path in [*ROOT.glob('*.py'), *ROOT.glob('dashboard/*.py')]:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = ({n.name.split('.')[0] for n in node.names} if isinstance(node, ast.Import) else
                         {(node.module or '').split('.')[0]} if isinstance(node, ast.ImportFrom) else set())
                self.assertFalse(names & (banned | {'subprocess'}), path)
                if isinstance(node, ast.Call):
                    self.assertNotIn(ast.unparse(node.func), {'os.system', 'os.popen', 'eval', 'exec', '__import__'}, path)
            self.assertNotIn('save_config', path.read_text(), path)

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

    def test_status_and_ping(self):
        status = self.run_async(self.api.status())
        self.assertEqual((status['url'], status['allowed'], len(status['commands'])), (None, False, 2))
        self.assertEqual(self.run_async(self.api.ping()), {'state': 'not_configured'})
        self.config.data = {'mcp_servers': {'fulcra': {'url': 'https://mcp.fulcradynamics.com/mcp'}},
                            'plugins': {'entries': {'fulcra': {'mcp_allowlist': ['fulcra']}}}}
        status = self.run_async(self.api.status())
        self.assertEqual((status['allowed'], status['commands']), (True, []))
        self.assertEqual(self.run_async(self.api.ping())['state'], 'connected')
        self.ctx.fulcra = None
        self.assertEqual(self.run_async(self.api.ping())['state'], 'not_connected')
        self.ctx.allowed = False
        self.assertEqual(self.run_async(self.api.ping())['state'], 'not_allowed')
        self.assertFalse(hasattr(self.api, 'connect'))

    def test_unloaded_plugin_is_a_clear_error(self):
        from fastapi import HTTPException
        with patch.object(self.plugin.mcp_api, '_FULCRA_CTX', None), self.assertRaises(HTTPException) as caught:
            self.run_async(self.api.status())
        self.assertEqual(caught.exception.status_code, 503)


if __name__ == '__main__':
    unittest.main()
