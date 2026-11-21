"""Fulcra through the hosted Fulcra MCP server, which Hermes connects and signs in to.

The plugin holds no credentials: its hooks and Desktop backend call the server's tools with ctx.call_mcp,
Hermes's own MCP client. Hermes allows that only for servers in plugins.entries.<plugin>.mcp_allowlist,
which connect() sets when the user asks to connect Fulcra.
"""
import json
import time
from datetime import timedelta

SERVER = 'fulcra'  # The plugin registers no toolset named fulcra; one would hide the server's tools.
PREFIX = f'mcp__{SERVER}__'
DEFAULT_URL = 'https://mcp.fulcradynamics.com/mcp'
# Tools only MCP App panels use (visibility ["app"]) or that open one. Hermes shows no panels, but would
# offer these to the model; the server already hides open_agent_contacts* from hosts without MCP Apps.
# scripts/check-tools.py compares this list with the server's.
APP_ONLY = ['end_agent_contact', 'get_contact_preferences', 'get_fulcra_settings', 'get_message_check_status',
            'open_file_manager', 'prepare_agent_invitation', 'prepare_standing_agent_invitation',
            'search_agent_contacts', 'send_agent_contact_message', 'set_contact_identifier', 'set_contact_preferences',
            'set_contact_status', 'start_file_upload', 'update_fulcra_settings', 'upload_file_chunk']
TRUNCATED = '(showing the first'  # get_records caps long ranges and says so.


class MCPError(RuntimeError):
    pass


class Truncated(MCPError):
    """Hermes cut a result short (call_mcp keeps about 64 KB)."""


class MCPApi:
    """The Fulcra reads what's new needs, through the MCP server's tools."""

    def __init__(self, ctx):
        self.ctx = ctx

    def text(self, tool, **args):
        """What the tool returned: its text, or its structured content when it has no text."""
        out = self.ctx.call_mcp(SERVER, tool, {k: v for k, v in args.items() if v is not None}, timeout=60)
        if not out.get('ok'):
            raise MCPError(f'{tool}: {str(out.get("error", out))[:200]}')
        if out.get('truncated'):
            raise Truncated(tool)
        return out['result']

    def call(self, tool, **args):
        return parse(tool, self.text(tool, **args))[1]

    def shares(self):
        return self.call('list_shares', direction='incoming')

    def data_updates(self, start, end):
        return self.call('get_data_updates', start_time=start.isoformat(), end_time=end.isoformat())

    def records(self, data_type, start, end, owner):
        """Every record in [start, end], halving the window while the server or Hermes caps it."""
        try:
            text = self.text('get_records', data_type=data_type, start_time=start.isoformat(),
                             end_time=end.isoformat(), fulcra_userid=owner)
            heading, rows = parse('get_records', text)
        except Truncated:
            if end - start <= timedelta(seconds=2):
                raise
            heading, rows = TRUNCATED, []
        if TRUNCATED in heading and end - start > timedelta(seconds=2):
            middle = start + (end - start) / 2
            return self.records(data_type, start, middle, owner) + self.records(data_type, middle, end, owner)
        return rows


def parse(tool, text):
    """(heading, data): Fulcra tools answer with a one-line heading followed by JSON, or with JSON alone."""
    if not isinstance(text, str):
        return '', text
    start = min((i for i in (text.find('{'), text.find('[')) if i >= 0), default=-1)
    if start < 0:
        raise MCPError(f'{tool}: {text[:200]}')
    return text[:start], json.JSONDecoder().raw_decode(text, start)[0]


def probe(ctx):
    """Whether Fulcra answers here: {'state': connected | not_connected | not_allowed | error, 'seconds', 'detail'?}.

    not_connected: this process hasn't connected the server yet (Hermes connects MCP servers when a session
    starts, and a server added before sign-in waits for its next retry). Shows no account details.
    """
    started = time.monotonic()
    try:
        out = ctx.call_mcp(SERVER, 'get_user_info', {}, timeout=30)
    except PermissionError:
        out = {'ok': False, 'state': 'not_allowed', 'error': f'{SERVER} is not in the plugin\'s mcp_allowlist'}
    except Exception as exc:
        out = {'ok': False, 'error': type(exc).__name__}
    result = {'seconds': round(time.monotonic() - started, 2)}
    if out.get('ok'):
        return {'state': 'connected', **result}
    error = str(out.get('error', out))
    state = out.get('state') or ('not_connected' if 'not connected' in error or 'reconnect' in error else 'error')
    return {'state': state, 'detail': error[:200], **result}


def server_entry(url=DEFAULT_URL):
    return {'url': url, 'auth': 'oauth', 'tools': {'exclude': APP_ONLY}}


def configured():
    """The URL of this profile's Fulcra MCP server, or None."""
    from hermes_cli.config import load_config_readonly
    server = (load_config_readonly().get('mcp_servers') or {}).get(SERVER)
    return server.get('url') if isinstance(server, dict) else None


def allowed(plugin_id):
    from hermes_cli.config import load_config_readonly
    entry = ((load_config_readonly().get('plugins') or {}).get('entries') or {}).get(plugin_id) or {}
    return SERVER in (entry.get('mcp_allowlist') or [])


def connect(url, plugin_id):
    """Add the Fulcra MCP server (Hermes signs in to it with OAuth) and let this plugin call it.

    Only on the user's request: /fulcra connect or the Desktop page's Connect. Other servers, grants and
    settings are kept.
    """
    from hermes_cli.config import load_config, save_config
    config = load_config()
    config.setdefault('mcp_servers', {})[SERVER] = server_entry(url)
    entry = config.setdefault('plugins', {}).setdefault('entries', {}).setdefault(plugin_id, {})
    allowlist = [name for name in entry.get('mcp_allowlist') or [] if name != SERVER]
    entry['mcp_allowlist'] = allowlist + [SERVER]
    save_config(config)
