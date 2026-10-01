"""One public settings vocabulary across setup and native settings."""
import argparse
import unittest

from test_updates import Context, load_plugin


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load_plugin()
        self.ctx = Context()
        self.setup = self.plugin.plugin_setup.Setup(self.ctx)

    def test_setup_writes_flag_names_and_runtime_reads_them(self):
        result = self.setup.command('setup --workspace off --updates on --interval 120 '
                                    '--mesh-agent helper --mesh-messages on --mesh-invites off')
        self.assertNotIn('Error:', result)
        self.assertIs(self.ctx.get_config('updates'), True)
        self.assertEqual(self.ctx.get_config('interval'), 120)
        self.assertIs(self.ctx.get_config('workspace'), False)
        self.assertIs(self.plugin.updates._settings(self.ctx)['updates_enabled'], True)
        self.assertIs(self.plugin.mesh_updates.sync(self.ctx)['settings']['mesh_messages_enabled'], True)
        self.assertIn('  mesh-messages = true', result)
        self.assertLess(result.index('Features:'), result.index('Workspace:'))
        self.assertNotIn('updates_enabled', result)

    def test_filters_use_same_cli_and_slash_flags_and_clear_explicitly(self):
        parser = argparse.ArgumentParser()
        self.setup.cli_setup(parser)
        flags = ['setup', '--updates-data-types', 'Steps', 'HeartRate',
                 '--updates-file-prefixes', '/workspace/', '/notes/',
                 '--updates-ignore-prefixes', '/notes/private/', '--updates-include-files', 'off']
        result = self.setup.cli(parser.parse_args(flags))
        self.assertNotIn('Error:', result)
        self.assertEqual(self.ctx.get_config('updates-data-types'), ['Steps', 'HeartRate'])
        self.assertIs(self.ctx.get_config('updates-include-files'), False)
        self.assertEqual(self.plugin.updates._settings(self.ctx)['updates_file_prefixes'],
                         ['/workspace/', '/notes/'])
        result = self.setup.command('setup --updates-data-types --updates-include-files on')
        self.assertNotIn('Error:', result)
        self.assertEqual(self.ctx.get_config('updates-data-types'), [])
        self.assertEqual(self.ctx.get_config('updates-ignore-prefixes'), ['/notes/private/'])
        before = self.ctx.config.copy()
        self.assertTrue(self.setup.command('setup --updates-data-types ""').startswith('Error:'))
        self.assertEqual(self.ctx.config, before)
        help_text = parser.format_help()
        self.assertLess(help_text.index('Features:'), help_text.index('Update filters:'))

    def test_explicit_migration_preserves_choices_and_new_values_win(self):
        for key, value in {'updates_enabled': True, 'update_interval': 120,
                           'workspace_context_enabled': False, 'updates_data_types': ['Steps']}.items():
            self.ctx.set_config(key, value)
        self.ctx.set_config('updates', False)
        before = self.ctx.config.copy()
        self.assertIn('  interval = 120', self.setup.command('status'))
        self.assertEqual(self.ctx.config, before)
        self.assertIs(self.plugin.updates._settings(self.ctx)['updates_enabled'], False)
        result = self.setup.command('setup --migrate')
        self.assertNotIn('Error:', result)
        self.assertEqual(self.ctx.get_config('interval'), 120)
        self.assertIs(self.ctx.get_config('updates'), False)
        self.assertEqual(self.ctx.get_config('updates-data-types'), ['Steps'])
        self.assertIsNone(self.ctx.get_config('mesh-messages'))
        self.assertNotIn('Error:', self.setup.command('setup --updates-data-types'))
        self.assertEqual(self.plugin.updates._settings(self.ctx)['updates_data_types'], [])
        result = self.plugin.updates.Updates(self.ctx).configure({'updates_enabled': True})
        self.assertNotIn('Error:', result)
        self.assertIs(self.ctx.get_config('updates'), True)
        token = self.ctx.state.profile.set('b')
        try:
            self.assertIs(self.plugin.updates._settings(self.ctx)['updates_enabled'], False)
        finally:
            self.ctx.state.profile.reset(token)
