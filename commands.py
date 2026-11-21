"""The /fulcra command (chat) and `hermes fulcra` (terminal): connect Fulcra and set up what's new."""
import argparse
import json
import shlex
import subprocess
import sys

from . import mcp_api, whats_new

USAGE = '''/fulcra connect [--url URL]   add the Fulcra MCP server to Hermes (asks Hermes to sign in to it)
/fulcra status                 show the connection and what's new settings
/fulcra setup [options]        change what's new settings, e.g. --whats-new on --agent-name NAME'''


SIGN_IN = (f'Sign in: in Hermes Desktop, open Capabilities > MCP servers and sign in to {mcp_api.SERVER}; or in a '
           f'terminal on the machine running Hermes, run `hermes mcp login {mcp_api.SERVER}`. Then run /reload-mcp '
           'or start a new chat.')


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse would otherwise exit the host process.
        raise ValueError(message)


def arguments(parser):
    parser.add_argument('action', nargs='?', choices=('setup', 'status', 'connect'), default=None)
    parser.add_argument('--url', default=argparse.SUPPRESS, metavar='URL',
                        help=f'connect: the Fulcra MCP server (default {mcp_api.DEFAULT_URL})')
    for key, spec in whats_new.SETTINGS.items():
        options = {'dest': key, 'default': argparse.SUPPRESS, 'help': 'setup: ' + spec['description']}
        if spec['type'] == 'boolean':
            options['choices'] = ('on', 'off')
        elif spec['type'] == 'integer':
            options.update(type=int, metavar='SECONDS')
        elif spec['type'] == 'array':
            options.update(nargs='*', metavar='VALUE')
        else:
            options['metavar'] = 'NAME'
        parser.add_argument('--' + key, **options)


class Commands:
    def __init__(self, ctx):
        self.ctx = ctx

    def chat(self, raw_args=''):
        parser = Parser(prog='/fulcra', add_help=False, usage=USAGE)
        arguments(parser)
        parser.add_argument('-h', '--help', action='store_true')
        try:
            args = vars(parser.parse_args(shlex.split(raw_args)))
            if args.pop('help'):
                return parser.format_help()
            action = args.get('action')
            text = self.run(args)
            if (action or 'status') == 'status' and mcp_api.configured():
                # In chat, Hermes has connected its MCP servers, so this shows whether Fulcra answers.
                text = text.replace('\n', '\n' + self.answering() + '\n', 1)
            if action == 'connect':
                text += '\n\n' + SIGN_IN
            return text
        except ValueError as exc:
            return 'Error: ' + str(exc)

    def cli(self, args):
        values = {k: v for k, v in vars(args).items() if k in whats_new.SETTINGS or k in ('action', 'url')}
        try:
            print(self.run(dict(values)))
        except ValueError as exc:
            print('Error: ' + str(exc))
            return 1
        if values.get('action') == 'connect':
            return self.sign_in()
        return 0

    def sign_in(self):
        """Offer Hermes's own sign-in for the server; it runs only if the user says yes."""
        command = f'hermes mcp login {mcp_api.SERVER}'
        if not sys.stdin.isatty():
            print(f'To sign in, run: {command}')
            return 0
        answer = input('Sign in to Fulcra in your browser now? [Y/n] ').strip().lower()
        if answer not in ('', 'y', 'yes'):
            print(f'Sign in later with: {command}')
            return 0
        done = subprocess.run([sys.executable, '-m', 'hermes_cli.main', 'mcp', 'login', mcp_api.SERVER], check=False)
        if done.returncode == 0:
            print('Signed in. New Hermes sessions can use Fulcra; in a chat that is already open, run /reload-mcp.')
        return done.returncode

    def run(self, args):
        action = args.pop('action', None) or ('setup' if set(args) & set(whats_new.SETTINGS) else 'status')
        if action == 'connect':
            if set(args) - {'url'}:
                raise ValueError('connect takes only --url')
            return self.connect(args.get('url', mcp_api.DEFAULT_URL))
        if 'url' in args:
            raise ValueError('--url is for connect')
        if action == 'status' and args:
            raise ValueError('status takes no settings; use setup')
        return self.setup(args) if action == 'setup' else self.status()

    def answering(self):
        found = mcp_api.probe(self.ctx)
        return {'connected': f'  Fulcra answers ({found["seconds"]} s).',
                'not_connected': '  Not connected yet: sign in (see /fulcra connect), then run /reload-mcp or start a new chat.',
                'not_allowed': '  The plugin may not use the fulcra server: run /fulcra connect to allow it.',
                }.get(found['state'], f'  Fulcra answered with an error; you may need to sign in again. {found.get("detail", "")}')

    def connect(self, url):
        if not url.startswith('https://') and not url.startswith('http://127.0.0.1') and not url.startswith('http://localhost'):
            raise ValueError('the server URL must use https')
        current, plugin_id = mcp_api.configured(), self.ctx.plugin_id
        if current == url and mcp_api.allowed(plugin_id):
            return f'Fulcra is already added to Hermes ({mcp_api.SERVER}: {url}).'
        mcp_api.connect(url, plugin_id)
        before = f' (replacing {current})' if current and current != url else ''
        return (f'Added the Fulcra MCP server to Hermes as {mcp_api.SERVER}: {url}{before}, and let the Fulcra plugin '
                f'use it for what\'s new and the Desktop page (plugins.entries.{plugin_id}.mcp_allowlist). '
                f'Remove the server with `hermes mcp remove {mcp_api.SERVER}`.')

    def setup(self, args):
        changes = {k: v == 'on' if whats_new.SETTINGS[k]['type'] == 'boolean' else v for k, v in args.items()}
        with whats_new._lock(self.ctx):
            values = {key: self.ctx.get_config(key, spec['default']) for key, spec in whats_new.SETTINGS.items()}
            whats_new.validate({**values, **changes})
            for key, value in changes.items():
                self.ctx.set_config(key, value)
        return self.status()

    def status(self):
        url = mcp_api.configured()
        lines = [f'Fulcra MCP server: {url}' if url else
                 'Fulcra MCP server: not added. Add it with /fulcra connect (hermes fulcra connect in a terminal).']
        lines += ["What's new (this profile; trusted chats only):"]
        lines += [f'  {key} = {json.dumps(self.ctx.get_config(key, spec["default"]))}'
                  for key, spec in whats_new.SETTINGS.items()]
        lines.append('Change with /fulcra setup --whats-new on --agent-name NAME; see /fulcra --help.')
        return '\n'.join(lines)


def register(ctx):
    commands = Commands(ctx)
    ctx.register_command('fulcra', commands.chat, description="Connect Fulcra and set up what's new",
                         args_hint='[connect|status|setup] [options]')
    ctx.register_cli_command(name='fulcra', help="Connect Fulcra and set up what's new",
                             setup_fn=arguments, handler_fn=commands.cli)
