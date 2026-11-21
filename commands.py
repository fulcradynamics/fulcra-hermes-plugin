"""The /fulcra command (chat) and `hermes fulcra` (terminal): what Fulcra needs, and what's new settings.

The plugin never changes Hermes's config or signs in itself: `connect` prints the Hermes commands still
needed, and the user (or the agent, with their approval) runs them.
"""
import argparse
import json
import shlex

from . import mcp_api, whats_new

USAGE = '''/fulcra connect [--url URL]   show the Hermes commands that connect Fulcra
/fulcra status                 show the connection and what's new settings
/fulcra setup [options]        change what's new settings, e.g. --whats-new on --agent-name NAME'''
RELOAD = ('After signing in, start a new chat, or run /reload-mcp in an open one. A running gateway or Desktop '
          'may need a restart to pick up the sign-in.')
DESKTOP = 'In Hermes Desktop you can instead add the server and sign in under Capabilities > MCP servers.'


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
            return self.run(args, chat=True)
        except ValueError as exc:
            return 'Error: ' + str(exc)

    def cli(self, args):
        values = {k: v for k, v in vars(args).items() if k in whats_new.SETTINGS or k in ('action', 'url')}
        try:
            print(self.run(values, chat=False))
        except ValueError as exc:
            print('Error: ' + str(exc))
            return 1
        return 0

    def run(self, args, chat):
        action = args.pop('action', None) or ('setup' if set(args) & set(whats_new.SETTINGS) else 'status')
        if action == 'connect':
            if set(args) - {'url'}:
                raise ValueError('connect takes only --url')
            url = args.get('url', mcp_api.DEFAULT_URL)
            if not url.startswith('https://'):
                raise ValueError('the server URL must use https')
            return self.connect(url)
        if 'url' in args:
            raise ValueError('--url is for connect')
        if action == 'status' and args:
            raise ValueError('status takes no settings; use setup')
        if action == 'setup':
            self.setup(args)
        return self.status(chat)

    def connect(self, url):
        steps = mcp_api.setup_commands(self.ctx.plugin_id, url)
        if not steps:
            return (f'Fulcra is added to Hermes ({mcp_api.configured()}) and the plugin may use it. If its tools are '
                    f'missing, sign in again with `hermes mcp login {mcp_api.SERVER}`. {RELOAD}')
        lines = ['To connect Fulcra, run in a terminal on the machine running Hermes:', '']
        for n, (purpose, command) in enumerate(steps, 1):
            lines += [f'{n}. {purpose}:', f'   {command}']
        lines += ['', RELOAD, DESKTOP]
        return '\n'.join(lines)

    def setup(self, args):
        changes = {k: v == 'on' if whats_new.SETTINGS[k]['type'] == 'boolean' else v for k, v in args.items()}
        with whats_new._lock(self.ctx):
            values = {key: self.ctx.get_config(key, spec['default']) for key, spec in whats_new.SETTINGS.items()}
            whats_new.validate({**values, **changes})
            for key, value in changes.items():
                self.ctx.set_config(key, value)

    def status(self, chat):
        url, allowed = mcp_api.configured(), mcp_api.allowed(self.ctx.plugin_id)
        if not url:
            lines = ['Fulcra MCP server: not added. /fulcra connect shows how to add it.']
        else:
            lines = [f'Fulcra MCP server: {url}']
            if not allowed:
                lines.append("  The plugin may not use it yet (what's new and the Desktop page need that); "
                             '/fulcra connect shows the command.')
            elif chat:
                # In chat, Hermes has connected its MCP servers, so this shows whether Fulcra answers.
                lines.append(self.answering())
        lines += ["What's new (this profile; trusted chats only):"]
        lines += [f'  {key} = {json.dumps(self.ctx.get_config(key, spec["default"]))}'
                  for key, spec in whats_new.SETTINGS.items()]
        lines.append('Change with /fulcra setup --whats-new on --agent-name NAME; see /fulcra --help.')
        return '\n'.join(lines)

    def answering(self):
        found = mcp_api.probe(self.ctx)
        return {'connected': f'  Fulcra answers ({found["seconds"]} s).',
                'not_connected': (f'  Not connected yet. If you haven\'t signed in, run `hermes mcp login '
                                  f'{mcp_api.SERVER}`; then run /reload-mcp or start a new chat.'),
                'not_allowed': '  The plugin may not use the fulcra server yet; /fulcra connect shows the command.',
                }.get(found['state'], f'  Fulcra answered with an error; you may need to sign in again '
                                      f'(`hermes mcp login {mcp_api.SERVER}`). {found.get("detail", "")}')


def register(ctx):
    commands = Commands(ctx)
    ctx.register_command('fulcra', commands.chat, description="Connect Fulcra and set up what's new",
                         args_hint='[connect|status|setup] [options]')
    ctx.register_cli_command(name='fulcra', help="Connect Fulcra and set up what's new",
                             setup_fn=arguments, handler_fn=commands.cli)
