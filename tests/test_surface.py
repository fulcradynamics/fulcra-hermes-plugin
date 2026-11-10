"""The public surface: explicit setup, native tools and read-only registration."""
import argparse
import unittest
from unittest.mock import Mock, patch

from test_updates import Context, State, load_plugin


class SurfaceTests(unittest.TestCase):
    def test_mesh_resolves_state_only_when_called(self):
        plugin = load_plugin()
        ctx = Context()
        del ctx.state
        with patch.object(plugin.mesh, 'make_handler') as factory:
            plugin.register(ctx)
            factory.assert_not_called()
            args = {'local_agent': 'helper'}
            for state in (State(), State()):
                ctx.state = state
                result = ctx.tools['fulcra_receive_agent_messages'](args, session_id='session')
                factory.assert_called_with(state)
                factory.return_value.assert_called_with(args, session_id='session')
                self.assertIs(result, factory.return_value.return_value)

    def test_registration_keeps_tools_and_skills_without_model_interception(self):
        plugin = load_plugin()
        ctx = Context()
        ctx.register_middleware = Mock()
        ctx.register_skill = Mock()
        before = ctx.config.copy()
        plugin.register(ctx)
        self.assertEqual(ctx.config, before)
        self.assertEqual(ctx.state.values, {})
        ctx.register_middleware.assert_not_called()
        self.assertEqual(set(ctx.tools), set(plugin.tools.TOOL_SCHEMAS) |
                         {'fulcra_receive_agent_messages', 'fulcra_configure_updates'})
        self.assertEqual({call.args[0] for call in ctx.register_skill.call_args_list},
                         {'context'})

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

    def test_setup_views_are_read_only(self):
        setup = load_plugin().plugin_setup.Setup(Context())
        with patch.object(setup.ctx.state, 'set') as write:
            for command in ('', 'setup', 'status', 'help', 'setup --help'):
                self.assertIn('Fulcra settings', setup.command(command))
            parser = argparse.ArgumentParser()
            setup.cli_setup(parser)
            setup.cli(parser.parse_args(['status']))
            write.assert_not_called()
        self.assertEqual(setup.ctx.config, {})
