"""Runtime boundaries: no credentials, no heavy imports, processes only for the user's own sign-in."""
import ast
import asyncio
import hashlib
import importlib.util
import json
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
        self.assertIn(f"const API_VERSION = {status['api']} ", (ROOT / 'desktop/plugin.js').read_text())
        self.assertEqual(self.run_async(self.api.ping()), {'state': 'not_configured'})
        self.config.data = {'mcp_servers': {'fulcra': {'url': 'https://mcp.fulcradynamics.com/hermes/mcp'}},
                            'plugins': {'entries': {'fulcra': {'mcp_allowlist': ['fulcra']}}}}
        status = self.run_async(self.api.status())
        self.assertEqual((status['allowed'], status['commands']), (True, []))
        self.assertEqual(self.run_async(self.api.ping())['state'], 'connected')
        self.ctx.fulcra = None
        self.assertEqual(self.run_async(self.api.ping())['state'], 'not_connected')
        self.ctx.allowed = False
        self.assertEqual(self.run_async(self.api.ping())['state'], 'not_allowed')
        self.assertFalse(hasattr(self.api, 'connect'))

    def test_the_app_and_its_tool_calls(self):
        provenance = json.loads((ROOT / 'provenance.json').read_text())['app']
        html = self.run_async(self.api.app())['html']
        self.assertEqual(hashlib.sha256(html.encode()).hexdigest(), provenance['sha256'])
        self.config.data = {'plugins': {'entries': {'fulcra': {'mcp_allowlist': ['fulcra']}}}}
        call = lambda name, **args: self.run_async(self.api.call(name, args))

        shares = call('list_shares', direction='both')  # Text the app parses.
        self.assertEqual(shares['content'][0]['text'][:8], 'Shares: ')
        self.assertNotIn('structuredContent', shares)
        self.ctx.fulcra.answer = lambda tool, args: {'result': json.dumps({'status': 'prepared'})}
        # Hermes drops structuredContent the text repeats as JSON; the app reads structuredContent.
        self.assertEqual(call('prepare_standing_agent_invitation')['structuredContent'], {'status': 'prepared'})
        self.ctx.fulcra.answer = lambda tool, args: {'result': 'x' * 70000}
        self.assertIn('64 KB', call('get_records')['content'][0]['text'])
        self.ctx.fulcra = None
        self.assertEqual(call('get_records'), {'isError': True, 'content': [
            {'type': 'text', 'text': "MCP server 'fulcra' is not connected"}]})

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            call('delete_records')  # Not one the app calls.
        self.assertEqual(caught.exception.status_code, 403)

    def test_unloaded_plugin_is_a_clear_error(self):
        from fastapi import HTTPException
        with patch.object(self.plugin.mcp_api, '_FULCRA_CTX', None), self.assertRaises(HTTPException) as caught:
            self.run_async(self.api.status())
        self.assertEqual(caught.exception.status_code, 503)


if __name__ == '__main__':
    unittest.main()
