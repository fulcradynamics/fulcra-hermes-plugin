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
        result = self.setup.command('setup --updates on --interval 120 '
                                    '--mesh-agent helper --mesh-messages on --mesh-invites off')
        self.assertNotIn('Error:', result)
        self.assertIs(self.ctx.get_config('updates'), True)
        self.assertEqual(self.ctx.get_config('interval'), 120)
        self.assertIs(self.plugin.updates._settings(self.ctx)['updates_enabled'], True)
        self.assertIs(self.plugin.mesh_updates.sync(self.ctx)['settings']['mesh_messages_enabled'], True)
        self.assertIn('  mesh-messages = true', result)
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

    def test_only_public_settings_control_runtime_without_status_writes(self):
        self.ctx.set_config('updates_enabled', True)
        self.ctx.set_config('update_interval', 120)
        before = self.ctx.config.copy()
        self.assertIn('  interval = 900', self.setup.command('status'))
        self.assertEqual(self.ctx.config, before)
        self.assertIs(self.plugin.updates._settings(self.ctx)['updates_enabled'], False)
        self.assertNotIn('Error:', self.setup.command('setup --updates on --interval 120'))
        self.assertIs(self.plugin.updates._settings(self.ctx)['updates_enabled'], True)
        token = self.ctx.state.profile.set('b')
        try:
            self.assertIs(self.plugin.updates._settings(self.ctx)['updates_enabled'], False)
        finally:
            self.ctx.state.profile.reset(token)
