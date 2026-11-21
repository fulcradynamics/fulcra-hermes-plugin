"""Backend for the Desktop Agents I Know page (proof of concept).

Calls the Fulcra MCP server's tools through the plugin's own ctx.dispatch_tool, using the connection
and sign-in Hermes already made. Never handles credentials.
"""
import asyncio
import json
import sys
import time

from fastapi import APIRouter

router = APIRouter()
SERVER = 'fulcra'
PING_TOOL = f'mcp__{SERVER}__get_user_info'


def _ctx():
    # register() stores the plugin's ctx on its mcp_api module; this route file is loaded separately by path.
    return next((m._FULCRA_CTX for m in list(sys.modules.values())
                 if getattr(m, '_FULCRA_CTX', None) is not None), None)


def _configured():
    from hermes_cli.config import load_config_readonly
    return SERVER in (load_config_readonly().get('mcp_servers') or {})


def _ping():
    if not _configured():
        return {'state': 'not_configured'}
    ctx = _ctx()
    if ctx is None:
        return {'state': 'error', 'detail': 'The Fulcra plugin is not loaded in this backend.'}
    started = time.monotonic()
    out = json.loads(ctx.dispatch_tool(PING_TOOL, {}))
    seconds = round(time.monotonic() - started, 2)
    if 'result' not in out:
        error = str(out.get('error', out))
        state = 'not_connected' if error.startswith('Unknown tool') else 'error'
        return {'state': state, 'detail': error[:200], 'tool': PING_TOOL, 'seconds': seconds}
    return {'state': 'connected', 'tool': PING_TOOL, 'seconds': seconds}


@router.post('/ping')
async def ping():
    return await asyncio.to_thread(_ping)
