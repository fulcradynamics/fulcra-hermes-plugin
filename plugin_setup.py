"""Native settings plus explicit, noninteractive slash/CLI frontends."""
import argparse
import json
import re
import shlex

from . import mesh_updates, settings, updates, workspace

SETTINGS = {**workspace.SETTINGS, **updates.SETTINGS, **mesh_updates.SETTINGS}

FEATURES = ('workspace_context_enabled', 'updates_enabled', 'mesh_messages_enabled', 'mesh_invites_enabled')
GROUPS = (
    ('Features', FEATURES),
    ('Workspace', ('workspace_name', 'workspace_role')),
    ('Shared checks', ('update_interval',)),
    ('Mesh', ('mesh_agent',)),
    ('Update filters', ('updates_data_types', 'updates_include_files',
                        'updates_file_prefixes', 'updates_ignore_prefixes')),
)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        """Return parsing errors without exiting the host."""
        raise ValueError(message)


def arguments(parser):
    """Add the shared slash and native CLI settings arguments."""
    parser.add_argument('action', nargs='?', choices=('setup', 'status', 'help'), default='setup')
    for title, keys in GROUPS:
        group = parser.add_argument_group(title)
        for key in keys:
            spec = SETTINGS[key]
            options = {'dest': key, 'default': argparse.SUPPRESS, 'help': spec['description']}
            if spec['type'] == 'boolean':
                options['choices'] = ('on', 'off')
            elif spec['type'] == 'integer':
                options.update(type=int, metavar='SECONDS')
            elif spec['type'] == 'array':
                options.update(nargs='*', metavar='VALUE')
                options['help'] += ' Supply values to replace; no values clears the list.'
            else:
                options['metavar'] = 'NAME'
            group.add_argument('--' + settings.NAMES[key], **options)
    parser.add_argument_group('Upgrade').add_argument(
        '--migrate', action='store_true', default=argparse.SUPPRESS,
        help='Copy saved legacy choices to the new setting names; preserve explicit new values.')


class Setup:
    def __init__(self, ctx):
        """Bind setup to the active profile's plugin context."""
        self.ctx = ctx

    def command(self, raw_args=''):
        """Handle explicit slash setup without prompts or host exits."""
        action = raw_args.strip().split(maxsplit=1)[0] if raw_args.strip() else ''

        # argparse's default help/error paths exit the host, including gateways.
        parser = Parser(prog='/fulcra', add_help=False, allow_abbrev=False)
        arguments(parser)
        parser.add_argument('-h', '--help', action='store_true')
        try:
            args = vars(parser.parse_args(shlex.split(raw_args)))
            if args.pop('help'):
                return parser.format_help() + '\n' + self.status()
            return self.apply(args)
        except (ValueError, OSError) as exc:
            return 'Error: ' + str(exc) if action in ('setup', 'status', 'help', '') else 'Error: invalid choice.'

    def cli_setup(self, parser):
        """Register native CLI arguments using the shared schema."""
        arguments(parser)

    def cli(self, args):
        """Apply explicit native CLI choices and print their readback."""
        # Only our namespace keys, not Hermes's global parser options.
        values = {k: v for k, v in vars(args).items() if k in SETTINGS or k in ('action', 'migrate')}
        try:
            text = self.apply(values)
        except (ValueError, OSError) as exc:
            text = 'Error: ' + str(exc)
        print(text)
        return text

    def apply(self, args):
        """Validate proposed settings and write only explicitly supplied choices."""
        action = args.pop('action', 'setup')
        if action != 'setup' and args:
            raise ValueError('Only setup accepts settings flags')
        migrate = args.pop('migrate', False)
        if not args and not migrate:
            return self.status()
        changes = {k: (v == 'on' if SETTINGS[k]['type'] == 'boolean' else v) for k, v in args.items()}
        with updates._lock(self.ctx):
            if migrate:
                changes = {**settings.legacy(self.ctx), **changes}
            current = {k: settings.get(self.ctx, k, spec['default']) for k, spec in SETTINGS.items()}
            merged = {**current, **changes}
            # Validate the complete proposed configuration before the first config write.
            updates._validate_settings({k: merged[k] for k in updates.SETTINGS})
            for key in ('workspace_name', 'workspace_role'):
                if not isinstance(merged[key], str) or not re.fullmatch(workspace.SEGMENT, merged[key]):
                    raise ValueError(settings.NAMES[key] + ' must be a single alphanumeric, hyphen or underscore segment (1–64 characters)')
            mesh_updates.validate(merged)
            for key in FEATURES:
                if type(merged[key]) is not bool:
                    raise ValueError(settings.NAMES[key] + ' must be boolean')
            for key, value in changes.items():
                self.ctx.set_config(settings.NAMES[key], value)
            if changes:
                mesh_updates.sync(self.ctx)
                updates._control(self.ctx, updates._settings(self.ctx))
            return self.status()

    def status(self):
        """Show current grouped values and available setup controls."""
        lines = ['Fulcra settings (active profile; trusted chats only):']
        if settings.legacy(self.ctx):
            lines.append('Legacy settings are active. Run /fulcra setup --migrate before using the native settings form.')
        for group, keys in GROUPS:
            lines.append(group + ':')
            for key in keys:
                value = settings.get(self.ctx, key, SETTINGS[key]['default'])
                lines.append('  ' + settings.NAMES[key] + ' = ' + json.dumps(value, ensure_ascii=True))
        lines += ['Use Desktop Capabilities → Plugins, /fulcra setup --help, or hermes fulcra setup --help.',
                  'Choose --workspace on/off --updates on/off --interval 900 --mesh-messages on/off',
                  '       --mesh-invites on/off --mesh-agent NAME. Omitted choices are preserved.',
                  'Checks are turn-triggered; notices arrive on a later turn, never while idle.',
                  'No automatic accept/share/reply/send. Workspace loads on a new session first turn.']
        return '\n'.join(lines)


def register(ctx):
    """Register explicit setup frontends without persistent writes."""
    setup = Setup(ctx)
    ctx.register_command('fulcra', setup.command, description='Fulcra setup, settings and status',
                         args_hint='[setup|status|help] [options]')
    ctx.register_cli_command(name='fulcra', help='Fulcra setup and status',
                             setup_fn=setup.cli_setup, handler_fn=setup.cli)
