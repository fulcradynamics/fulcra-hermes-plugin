"""What the plugin registers and what its manifest and skills promise."""
import re
import unittest
from unittest.mock import Mock

from plugin import ROOT, Context, load


class SurfaceTests(unittest.TestCase):
    def test_registration_matches_the_manifest_without_side_effects(self):
        plugin, ctx = load(), Context()
        ctx.state.set = Mock()
        plugin.register(ctx)
        manifest = (ROOT / 'plugin.yaml').read_text()
        listed = lambda key: re.findall(r'- (\S+)', re.search(rf'^{key}:\n((?:  - .*\n)+)', manifest, re.M)[1])
        self.assertEqual(sorted(ctx.tools), sorted(listed('provides_tools')))
        self.assertEqual(sorted(ctx.hooks), sorted(listed('provides_hooks')))
        self.assertEqual(set(ctx.commands), {'fulcra', 'cli fulcra'})
        self.assertEqual(ctx.config, {})
        ctx.state.set.assert_not_called()
        self.assertEqual(sorted(ctx.skills), sorted(p.parent.name for p in (ROOT / 'skills').glob('*/SKILL.md')))

    def test_settings_match_the_manifest(self):
        manifest = (ROOT / 'plugin.yaml').read_text().split('config_schema:')[1]
        self.assertEqual(re.findall(r'^  (\S+):$', manifest, re.M), list(load().whats_new.SETTINGS))

    def test_skills_name_only_real_tools_and_skills(self):
        ctx = Context()
        load().register(ctx)
        for path in (ROOT / 'skills').rglob('*.md'):
            text = path.read_text()
            with self.subTest(path=path.relative_to(ROOT)):
                fields = {'fulcra_userid', 'fulcra_data_types'}
                self.assertLessEqual(set(re.findall(r'\bfulcra_[a-z_]+', text)) - fields, set(ctx.tools))
                self.assertLessEqual(set(re.findall(r'`fulcra:([a-z-]+)`', text)), set(ctx.skills))
                for link in re.findall(r'\]\(((?!https?:)[^)#]+)', text):
                    self.assertTrue((path.parent / link).exists(), link)


if __name__ == '__main__':
    unittest.main()
