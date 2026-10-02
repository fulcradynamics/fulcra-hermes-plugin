"""The small public surface: explicit setup, retained tools, no interception."""
import argparse
import unittest
from unittest.mock import Mock, patch

from test_updates import Context, load_plugin


class SurfaceTests(unittest.TestCase):
    def test_registration_keeps_tools_and_skills_without_model_interception(self):
        plugin = load_plugin()
        ctx = Context()
        ctx.register_middleware = Mock()
        ctx.register_skill = Mock()
        plugin.register(ctx)
        ctx.register_middleware.assert_not_called()
        self.assertEqual(set(ctx.tools), set(plugin.tools.TOOL_SCHEMAS) |
                         {'fulcra_mesh', 'fulcra_configure_updates'})
        self.assertEqual({call.args[0] for call in ctx.register_skill.call_args_list},
                         {'context', 'workspace'})

    def test_setup_registers_only_explicit_frontends(self):
        plugin = load_plugin()
        ctx = Context()
        ctx.register_hook = Mock()
        ctx.register_command = Mock()
        ctx.register_cli_command = Mock()
        plugin.plugin_setup.register(ctx)
        ctx.register_hook.assert_not_called()
        ctx.register_command.assert_called_once()
        ctx.register_cli_command.assert_called_once()
        self.assertEqual(ctx.config, {})
        self.assertEqual(ctx.state.values, {})

    def test_setup_views_do_not_persist_discovery_state(self):
        setup = load_plugin().plugin_setup.Setup(Context())
        with patch.object(setup.ctx.state, 'set') as write:
            for command in ('', 'setup', 'status', 'help', 'setup --help'):
                self.assertNotIn('redact', setup.command(command))
            parser = argparse.ArgumentParser()
            setup.cli_setup(parser)
            setup.cli(parser.parse_args(['status']))
            write.assert_not_called()
        self.assertEqual(setup.ctx.config, {})

    def test_removed_redact_command_is_rejected_without_state_changes(self):
        ctx = Context()
        setup = load_plugin().plugin_setup.Setup(ctx)
        self.assertTrue(setup.command('redact help --profile').startswith('Error:'))
        self.assertEqual(ctx.state.values, {})
        self.assertEqual(ctx.config, {})
