"""/fulcra and `hermes fulcra`: connecting Fulcra only when asked, and what's new settings."""
import argparse
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from plugin import Context, Fulcra, HermesConfig, load


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load()
        self.config = HermesConfig().install(self)
        self.ctx = Context(Fulcra())
        self.plugin.register(self.ctx)
        self.chat = self.ctx.commands['fulcra']

    def cli(self, *argv, tty=False, answer=''):
        parser = argparse.ArgumentParser()
        self.ctx.commands['cli fulcra']['setup_fn'](parser)
        out = io.StringIO()
        with redirect_stdout(out), patch('sys.stdin') as stdin, patch('builtins.input', return_value=answer):
            stdin.isatty.return_value = tty
            code = self.ctx.commands['cli fulcra']['handler_fn'](parser.parse_args(argv))
        return code, out.getvalue()

    def test_nothing_is_added_until_the_user_connects(self):
        status = self.chat('')
        self.assertIn('not added', status)
        self.chat('setup --whats-new on --agent-name helper')
        self.assertEqual(self.config.data, {})

    def test_connect_adds_the_server_with_oauth_and_without_panel_tools(self):
        text = self.chat('connect')
        server = self.config.data['mcp_servers']['fulcra']
        self.assertEqual(server['url'], 'https://mcp.fulcradynamics.com/mcp')
        self.assertEqual(server['auth'], 'oauth')
        self.assertIn('open_file_manager', server['tools']['exclude'])
        self.assertIn('hermes mcp login fulcra', text)
        self.assertIn('already added', self.chat('connect'))
        self.assertIn('replacing', self.chat('connect --url https://mcp.devfulcra.com/mcp'))
        self.assertEqual(self.config.data['mcp_servers']['fulcra']['url'], 'https://mcp.devfulcra.com/mcp')

    def test_connect_keeps_other_servers_and_rejects_plain_http(self):
        self.config.data = {'mcp_servers': {'linear': {'url': 'https://mcp.linear.app/mcp'}}, 'model': 'x'}
        self.assertTrue(self.chat('connect --url http://example.com/mcp').startswith('Error:'))
        self.chat('connect')
        self.assertEqual(set(self.config.data['mcp_servers']), {'linear', 'fulcra'})
        self.assertEqual(self.config.data['model'], 'x')

    def test_status_in_chat_says_whether_fulcra_answers(self):
        self.chat('connect')
        self.assertIn('Fulcra answers', self.chat('status'))
        self.ctx.fulcra = None
        self.assertIn('Not connected in this chat', self.chat('status'))
        self.ctx.fulcra = Fulcra()
        self.ctx.fulcra.fail = 'get_user_info'
        self.assertIn('answered with an error', self.chat('status'))

    def test_settings_imply_setup_and_are_validated(self):
        self.assertTrue(self.chat('--whats-new on').startswith('Error:'))
        status = self.chat('--whats-new on --agent-name helper --interval 120')
        self.assertIn('whats-new = true', status)
        self.assertEqual(self.ctx.config, {'whats-new': True, 'agent-name': 'helper', 'interval': 120})
        self.assertTrue(self.chat('status --interval 300').startswith('Error:'))
        self.assertTrue(self.chat('connect --interval 300').startswith('Error:'))
        self.assertTrue(self.chat('--bogus').startswith('Error:'))
        self.assertIn('/fulcra connect', self.chat('--help'))

    def test_terminal_connect_offers_hermes_sign_in(self):
        code, out = self.cli('connect')
        self.assertEqual(code, 0)
        self.assertIn('To sign in, run: hermes mcp login fulcra', out)
        with patch.object(self.plugin.commands.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.cli('connect', tty=True, answer='n')
            run.assert_not_called()
            code, out = self.cli('connect', tty=True, answer='')
        self.assertEqual(code, 0)
        self.assertEqual(run.call_args.args[0][1:], ['-m', 'hermes_cli.main', 'mcp', 'login', 'fulcra'])
        self.assertIn('Start a new Hermes session', out)

    def test_terminal_setup_and_errors(self):
        code, out = self.cli('setup', '--whats-new', 'on', '--agent-name', 'helper')
        self.assertEqual(code, 0)
        self.assertIn('agent-name = "helper"', out)
        self.assertEqual(self.cli('setup', '--whats-new', 'on', '--agent-name', ' ')[0], 1)


if __name__ == '__main__':
    unittest.main()
