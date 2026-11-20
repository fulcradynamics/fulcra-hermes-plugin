"""Fulcra calls through the hosted Fulcra MCP server, which Hermes connects to and signs in to.

Hooks can't hold credentials, so they call the server's tools through ctx.dispatch_tool, the same
tools the model uses.
"""
import json

SERVER = 'fulcra-context'  # Not 'fulcra': Hermes aliases a server's toolset by its name, which would hide its tools.
TOOL_PREFIX = 'mcp__fulcra_context__'
DEFAULT_URL = 'https://mcp.fulcradynamics.com/mcp'


class MCPApi:
    """The Fulcra calls what's new makes, answered by the MCP server's tools."""

    def __init__(self, ctx):
        self.ctx = ctx

    def _call(self, tool, **args):
        out = self.ctx.dispatch_tool(TOOL_PREFIX + tool, {k: v for k, v in args.items() if v is not None})
        result = json.loads(out)
        if 'result' not in result:
            raise RuntimeError(f'{tool} failed: {str(result.get("error", out))[:200]}')
        # Results are a short description followed by JSON.
        text = result['result']
        start = min((i for i in (text.find('{'), text.find('[')) if i >= 0), default=-1)
        if start < 0:
            raise RuntimeError(f'{tool} returned no data: {text[:200]}')
        return json.JSONDecoder().raw_decode(text, start)[0]

    def get_fulcra_userid(self):
        return self._call('list_shares', direction='incoming')['own_fulcra_userid']

    def get_shared_datasets(self):
        incoming = self._call('list_shares', direction='incoming')['incoming']
        return [dict(share, fulcra_data_types=share['file_paths'] + share['file_history_paths'] + share['data_types'])
                for share in incoming]

    def data_updates(self, start, end):
        return self._call('get_data_updates', start_time=start.isoformat(), end_time=end.isoformat())

    def mcp_records(self, data_type, start, end, user_id=None):
        return self._call('get_records', data_type=data_type, start_time=start.isoformat(),
                          end_time=end.isoformat(), fulcra_userid=user_id)


def configured():
    from hermes_cli.config import load_config_readonly
    return SERVER in (load_config_readonly().get('mcp_servers') or {})


def connect(url=DEFAULT_URL):
    """Add the Fulcra MCP server to this profile's Hermes config; Hermes signs in with OAuth."""
    from hermes_cli.config import load_config, save_config
    config = load_config()
    config.setdefault('mcp_servers', {})[SERVER] = {'url': url, 'auth': 'oauth'}
    save_config(config)
