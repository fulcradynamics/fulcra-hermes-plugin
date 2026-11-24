"""Load the plugin offline with a fake Hermes context whose dispatch_tool answers like the Fulcra MCP server."""
import copy
import importlib.util
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALEX = '00000000-0000-4000-8000-00000000000a'
SURA = '00000000-0000-4000-8000-00000000000b'
CHANNEL = 'Event/00000000-0000-4000-8000-0000000000c1'


def load():
    if 'fulcra_plugin' not in sys.modules:
        spec = importlib.util.spec_from_file_location('fulcra_plugin', ROOT / '__init__.py',
                                                      submodule_search_locations=[str(ROOT)])
        module = importlib.util.module_from_spec(spec)
        sys.modules['fulcra_plugin'] = module
        spec.loader.exec_module(module)
    return sys.modules['fulcra_plugin']


class HermesConfig:
    """Stands in for hermes_cli.config: one profile's config.yaml in memory."""

    def __init__(self):
        self.data = {}
        self.module = types.ModuleType('hermes_cli.config')
        vars(self.module).update(load_config=lambda: copy.deepcopy(self.data),
                                 load_config_readonly=lambda: copy.deepcopy(self.data),
                                 save_config=lambda config: setattr(self, 'data', copy.deepcopy(config)))

    def install(self, test):
        package = sys.modules.get('hermes_cli') or types.ModuleType('hermes_cli')
        previous = {name: sys.modules.get(name) for name in ('hermes_cli', 'hermes_cli.config')}
        sys.modules['hermes_cli'], sys.modules['hermes_cli.config'] = package, self.module
        vars(package)['config'] = self.module

        def restore():
            for name, module in previous.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
        test.addCleanup(restore)
        return self


class State:
    def __init__(self):
        self.values, self.path = {}, Path('/profile/plugin-state')

    def get(self, key, default=None):
        return copy.deepcopy(self.values.get(key, default))

    def set(self, key, value):
        self.values[key] = copy.deepcopy(value)


class Fulcra:
    """A synthetic Fulcra backend, seen through the MCP server's tools, for one signed-in account."""

    MAX_RECORDS = 3  # The real server caps get_records too (at a larger number).

    def __init__(self, own=ALEX):
        self.own = own
        self.incoming = []  # list_shares incoming entries
        self.outgoing = []  # list_shares outgoing entries
        self.rows = {}  # data type -> records (each with start_time)
        self.updates = {'data_types': {}, 'file_changes': []}
        self.calls = []
        self.fail: str | None = None  # a tool name whose calls fail

    def share_channel(self, owner=SURA, channel=CHANNEL):
        self.incoming.append({'grant_id': 'g-' + channel, 'sharing_fulcra_userid': owner, 'share_all_data': False,
                              'file_paths': [], 'file_history_paths': [], 'data_types': [channel]})

    def share_outbox(self, peer=SURA, outbox=None):
        """Your own channel to peer, shared with them."""
        self.outgoing.append({'datashare_id': 's-' + outbox, 'share_all_data': False, 'file_paths': [],
                              'file_history_paths': [], 'data_types': [outbox], 'with_user_ids': [peer]})

    def post(self, channel, record_id, **fields):
        row = {'id': record_id, 'start_time': datetime.now(timezone.utc).isoformat(), **fields}
        self.rows.setdefault(channel, []).append(row)
        return row

    def answer(self, tool, args):
        self.calls.append((tool, args))
        if tool == self.fail:
            return {'error': f"MCP call failed: {tool} is unavailable"}
        if tool == 'get_user_info':
            return {'result': json.dumps({'fulcra_userid': self.own})}
        if tool == 'list_shares':
            return {'result': 'Shares: ' + json.dumps({'own_fulcra_userid': self.own, 'outgoing': self.outgoing, 'incoming': self.incoming})}
        if tool == 'get_data_updates':
            return {'result': 'Updates: ' + json.dumps(self.updates)}
        if tool == 'get_records':
            start, end = (datetime.fromisoformat(args[k]) for k in ('start_time', 'end_time'))
            rows = [r for r in self.rows.get(args['data_type'], [])
                    if start <= datetime.fromisoformat(r['start_time']) <= end]
            heading = f"Records for {args['data_type']} from {args['start_time']} to {args['end_time']}"
            if len(rows) > self.MAX_RECORDS:
                heading += f' (showing the first {self.MAX_RECORDS} of {len(rows)}; narrow the time range)'
                rows = rows[:self.MAX_RECORDS]
            return {'result': heading + ': ' + json.dumps(rows)}
        return {'error': f'Unknown tool: mcp__fulcra__{tool}'}


class Context:
    plugin_id = 'fulcra'
    CAP = 65536  # call_mcp truncates longer results

    def __init__(self, fulcra=None, allowed=True):
        self.config, self.state = {}, State()
        self.tools, self.hooks, self.commands, self.skills = {}, {}, {}, {}
        self.fulcra = fulcra  # None: Hermes hasn't connected the Fulcra MCP server here
        self.allowed = allowed  # whether fulcra is in this plugin's mcp_allowlist

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def set_config(self, key, value):
        self.config[key] = value

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        self.tools[name] = handler

    def register_hook(self, name, handler):
        self.hooks[name] = handler

    def register_command(self, name, handler, **kwargs):
        self.commands[name] = handler

    def register_cli_command(self, name, **kwargs):
        self.commands['cli ' + name] = kwargs

    def register_skill(self, name, path):
        self.skills[name] = path

    def call_mcp(self, server, tool, arguments=None, timeout=30):
        """Like Hermes's ctx.call_mcp: allowlisted servers only, an {ok, result|error} envelope, a size cap."""
        if server != 'fulcra' or not self.allowed:
            raise PermissionError(f'Plugin {self.plugin_id!r} is not allowed to call MCP server {server!r}.')
        if self.fulcra is None:
            return {'ok': False, 'error': f"MCP server '{server}' is not connected"}
        out = self.fulcra.answer(tool, dict(arguments or {}))
        if 'error' in out:
            return {'ok': False, 'error': out['error']}
        if len(out['result']) > self.CAP:
            return {'ok': True, 'result': out['result'][:self.CAP] + '… [truncated]', 'truncated': True}
        return {'ok': True, 'result': out['result']}
