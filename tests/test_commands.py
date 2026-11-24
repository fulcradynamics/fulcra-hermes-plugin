"""/fulcra and `hermes fulcra`: never change Hermes's config, show the commands still needed, set what's new."""
import argparse
import io
import unittest
from contextlib import redirect_stdout

from plugin import Context, Fulcra, HermesConfig, load

ADD = 'hermes mcp add fulcra --url https://mcp.fulcradynamics.com/mcp --auth oauth --connect-timeout 300'
GRANT = "hermes config set plugins.entries.fulcra.mcp_allowlist '[\"fulcra\"]'"
SERVER = {'mcp_servers': {'fulcra': {'url': 'https://mcp.fulcradynamics.com/mcp', 'auth': 'oauth'}}}
GRANTED = {'plugins': {'entries': {'fulcra': {'mcp_allowlist': ['fulcra']}}}}


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load()
        self.config = HermesConfig().install(self)
        self.ctx = Context(Fulcra())
        self.plugin.register(self.ctx)
        self.chat = self.ctx.commands['fulcra']

    def cli(self, *argv):
        parser = argparse.ArgumentParser()
        self.ctx.commands['cli fulcra']['setup_fn'](parser)
        out = io.StringIO()
        with redirect_stdout(out):
            code = self.ctx.commands['cli fulcra']['handler_fn'](parser.parse_args(argv))
        return code, out.getvalue()

    def test_connect_shows_only_the_commands_still_needed_and_changes_nothing(self):
        text = self.chat('connect')
        self.assertIn(ADD, text)
        self.assertIn(GRANT, text)
        self.assertIn('Capabilities > Connectors > Add your own', text)
        self.assertEqual(self.config.data, {})
        self.config.data = dict(SERVER)
        text = self.chat('connect')
        self.assertNotIn('hermes mcp add', text)
        self.assertIn(GRANT, text)
        self.config.data = {**SERVER, **GRANTED}
        self.assertIn('hermes mcp login fulcra', self.chat('connect'))
        self.assertEqual(self.config.data, {**SERVER, **GRANTED})

    def test_connect_url_and_errors(self):
        self.assertIn('--url https://mcp.devfulcra.com/mcp', self.chat('connect --url https://mcp.devfulcra.com/mcp'))
        self.assertTrue(self.chat('connect --url http://example.com/mcp').startswith('Error:'))
        self.assertTrue(self.chat('connect --interval 300').startswith('Error:'))
        self.assertTrue(self.chat('status --url https://x').startswith('Error:'))

    def test_status_says_what_is_missing_and_whether_fulcra_answers(self):
        self.assertIn('not added', self.chat('status'))
        self.config.data = dict(SERVER)
        self.ctx.allowed = False
        self.assertIn('may not use it yet', self.chat('status'))
        self.config.data = {**SERVER, **GRANTED}
        self.ctx.allowed = True
        self.assertIn('Fulcra answers', self.chat('status'))
        self.ctx.fulcra = None
        self.assertIn('Not connected yet', self.chat(''))
        self.ctx.fulcra = Fulcra()
        self.ctx.fulcra.fail = 'get_user_info'
        self.assertIn('answered with an error', self.chat('status'))

    def test_settings_imply_setup_and_are_validated(self):
        self.assertIn('whats-new = true', self.chat('--whats-new on'))  # No agent name needed.
        status = self.chat('--whats-new on --agent-name helper --interval 120')
        self.assertIn('whats-new = true', status)
        self.assertEqual(self.ctx.config, {'whats-new': True, 'agent-name': 'helper', 'interval': 120})
        self.assertTrue(self.chat('status --interval 300').startswith('Error:'))
        self.assertTrue(self.chat('--bogus').startswith('Error:'))
        self.assertTrue(self.chat('--mode everything').startswith('Error:'))
        self.assertIn('mode = "reply"', self.chat('--mode reply'))
        self.assertEqual(self.ctx.config['mode'], 'reply')
        self.assertIn('/fulcra connect', self.chat('--help'))

    def test_terminal(self):
        code, out = self.cli('connect')
        self.assertEqual(code, 0)
        self.assertIn(ADD, out)
        code, out = self.cli('setup', '--whats-new', 'on', '--agent-name', 'helper')
        self.assertEqual(code, 0)
        self.assertIn('agent-name = "helper"', out)
        self.assertNotIn('Fulcra answers', out)  # The terminal has no MCP connection to test.
        self.assertEqual(self.cli('setup', '--interval', '5')[0], 1)
        self.assertEqual(self.config.data, {})


if __name__ == '__main__':
    unittest.main()
