"""Backend for the Fulcra page in Hermes Desktop.

Reaches Fulcra only through the plugin's ctx.dispatch_tool, on the MCP connection and sign-in Hermes made;
never handles credentials. Sign-in itself goes through Hermes's own gateway RPC from desktop/plugin.js.
"""
import asyncio
import sys

from fastapi import APIRouter, Body, HTTPException

router = APIRouter()


def _plugin():
    # register() stores the plugin's ctx on its mcp_api module; Hermes loads this file separately, by path.
    module = next((m for m in list(sys.modules.values()) if getattr(m, '_FULCRA_CTX', None) is not None), None)
    if module is None:
        raise HTTPException(503, 'The Fulcra plugin is not loaded in this Hermes backend. Enable it and restart.')
    return module


@router.get('/status')
async def status():
    mcp_api = _plugin()
    return {'server': mcp_api.SERVER, 'url': mcp_api.configured(), 'default_url': mcp_api.DEFAULT_URL}


@router.post('/connect')
async def connect(body: dict = Body(default={})):
    """Add the Fulcra MCP server; the page asks the user first."""
    mcp_api = _plugin()
    url = body.get('url') or mcp_api.DEFAULT_URL
    if not isinstance(url, str) or not url.startswith('https://'):
        raise HTTPException(400, 'The server URL must use https.')
    await asyncio.to_thread(mcp_api.connect, url)
    return {'server': mcp_api.SERVER, 'url': url}


@router.post('/ping')
async def ping():
    mcp_api = _plugin()
    if not mcp_api.configured():
        return {'state': 'not_configured'}
    return await asyncio.to_thread(mcp_api.probe, mcp_api._FULCRA_CTX)
