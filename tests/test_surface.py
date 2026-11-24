"""What the plugin registers and what its manifest and skills promise."""
import json
import re
import unittest
from unittest.mock import Mock

from plugin import ROOT, Context, load


class SurfaceTests(unittest.TestCase):
    def test_registration_matches_the_manifest_without_side_effects(self):
        plugin, ctx = load(), Context()
        ctx.state.set = Mock()
        ctx.call_mcp = Mock()
        plugin.register(ctx)
        manifest = (ROOT / 'plugin.yaml').read_text()
        block = lambda key: re.search(rf'^{key}:\n((?:  - .*\n)+)', manifest, re.M)
        listed = lambda key: re.findall(r'- (\S+)', block(key)[1]) if block(key) else []
        # Fulcra's tools come from its MCP server; a plugin toolset named fulcra would hide them.
        self.assertEqual(ctx.tools, {})
        self.assertNotIn('provides_tools', manifest)
        self.assertEqual(sorted(ctx.hooks), sorted(listed('provides_hooks')))
        self.assertEqual(set(ctx.commands), {'fulcra', 'cli fulcra'})
        self.assertEqual(ctx.config, {})
        ctx.state.set.assert_not_called()
        ctx.call_mcp.assert_not_called()
        self.assertEqual(sorted(ctx.skills), sorted(p.parent.name for p in (ROOT / 'skills').glob('*/SKILL.md')))

    def test_settings_match_the_manifest(self):
        manifest = (ROOT / 'plugin.yaml').read_text().split('config_schema:')[1]
        self.assertEqual(re.findall(r'^  (\S+):$', manifest, re.M), list(load().whats_new.SETTINGS))

    def test_skills_name_only_offered_tools_and_real_skills(self):
        ctx = Context()
        load().register(ctx)
        panel_only = {'open_file_manager', 'send_agent_contact_message', 'end_agent_contact', 'set_contact_status',
                      'search_agent_contacts', 'start_file_upload', 'upload_file_chunk'}
        for path in (ROOT / 'skills').rglob('*.md'):
            text = path.read_text()
            with self.subTest(path=path.relative_to(ROOT)):
                called = set(re.findall(r'`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\(', text))
                called |= set(re.findall(r'mcp__fulcra__([a-z_]+)', text))
                self.assertFalse(called & panel_only, 'skills call tools only MCP App panels use')
                self.assertNotRegex(text, r'\bfulcra_(?!userid|data_types)[a-z_]+\(', 'old plugin tool names')
                self.assertLessEqual(set(re.findall(r'`fulcra:([a-z-]+)`', text)), set(ctx.skills))
                for link in re.findall(r'\]\(((?!https?:)[^)#]+)', text):
                    self.assertTrue((path.parent / link).exists(), link)

    def test_desktop_and_dashboard_halves_are_declared(self):
        manifest = json.loads((ROOT / 'dashboard/manifest.json').read_text())
        self.assertEqual((manifest['name'], manifest['api']), ('fulcra', 'plugin_api.py'))
        script = (ROOT / 'desktop/plugin.js').read_text()
        imports = set(re.findall(r"from '([^']+)'", script))
        self.assertLessEqual(imports, {'@hermes/plugin-sdk', 'react', 'react/jsx-runtime'})
        self.assertNotIn('window.hermesDesktop', script)
        self.assertNotRegex(script, r'\beval\(|new Function')
        self.assertIn("name: 'fulcra-agents-i-know'", script)


if __name__ == '__main__':
    unittest.main()
