"""Backend for the Fulcra page in Hermes Desktop.

Reads this profile's config and reaches Fulcra only through the plugin's ctx.call_mcp, on the MCP connection
and sign-in Hermes made. Never changes config or handles credentials: the page shows the Hermes commands
still needed. Once Fulcra answers, the page runs the Agents I Know app and passes its tool calls here.
"""
import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

router = APIRouter()
APP = Path(__file__).resolve().parent.parent / 'desktop' / 'agents-i-know.html'
# Raised with any change to these routes. Hermes keeps a running backend's routes when the plugin is
# reinstalled or updated, so the page compares this to tell the user to restart Hermes.
API_VERSION = 2


def _plugin():
    # register() stores the plugin's ctx on its mcp_api module; Hermes loads this file separately, by path.
    module = next((m for m in list(sys.modules.values()) if getattr(m, '_FULCRA_CTX', None) is not None), None)
    if module is None:
        raise HTTPException(503, 'The Fulcra plugin is not loaded in this Hermes backend. Enable it and restart.')
    return module


@router.get('/status')
async def status():
    mcp_api = _plugin()
    plugin_id = mcp_api._FULCRA_CTX.plugin_id
    return {'api': API_VERSION, 'server': mcp_api.SERVER, 'url': mcp_api.configured(), 'allowed': mcp_api.allowed(plugin_id),
            'commands': [{'purpose': purpose, 'command': command}
                         for purpose, command in mcp_api.setup_commands(plugin_id)]}


@router.post('/ping')
async def ping():
    mcp_api = _plugin()
    if not mcp_api.configured():
        return {'state': 'not_configured'}
    return await asyncio.to_thread(mcp_api.probe, mcp_api._FULCRA_CTX)


@router.get('/app')
async def app():
    return {'html': APP.read_text(encoding='utf-8')}


@router.post('/call')
async def call(name: str = Body(), arguments: dict = Body(default_factory=dict)):
    mcp_api = _plugin()
    if name not in mcp_api.APP_TOOLS:
        raise HTTPException(403, f'Agents I Know does not call {name}.')
    return await asyncio.to_thread(mcp_api.app_call, mcp_api._FULCRA_CTX, name, arguments)
