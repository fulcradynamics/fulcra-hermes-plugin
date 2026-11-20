"""Spike: can a backend route reach the Fulcra MCP server's tools? Reports outcomes only, never data."""
import asyncio
import json
import os
import sys
import time

from fastapi import APIRouter

router = APIRouter()
TOOL = 'mcp__fulcra_context__list_shares'


def _outcome(fn):
    started = time.monotonic()
    try:
        out = fn()
        parsed = json.loads(out) if isinstance(out, str) else out
        ok = isinstance(parsed, dict) and 'result' in parsed and 'own_fulcra_userid' in str(parsed['result'])
        return {'ok': ok, 'keys': sorted(parsed) if isinstance(parsed, dict) else type(parsed).__name__,
                'error': None if ok else str(parsed)[:200], 'seconds': round(time.monotonic() - started, 2)}
    except Exception as exc:
        return {'ok': False, 'exception': f'{type(exc).__name__}: {exc}'[:300],
                'seconds': round(time.monotonic() - started, 2)}


def _probe():
    from tools.registry import registry
    entry = registry.get_entry(TOOL)
    mcp_names = [n for n in registry.get_all_tool_names() if n.startswith('mcp__fulcra_context__')] \
        if hasattr(registry, 'get_all_tool_names') else None
    ctxs = [m._FULCRA_CTX for m in list(sys.modules.values()) if getattr(m, '_FULCRA_CTX', None) is not None]
    return {
        'pid': os.getpid(),
        'process': ' '.join(sys.argv[:4])[:160],
        'registered': entry is not None,
        'fulcra_context_tools': len(mcp_names) if mcp_names is not None else 'unknown',
        'registry_dispatch': _outcome(lambda: registry.dispatch(TOOL, {'direction': 'incoming'})),
        'registered_scoped': _scoped_entry(registry),
        'registry_dispatch_scoped': _outcome(lambda: registry.dispatch(TOOL, {'direction': 'incoming'},
                                                                       scope=_scope())),
        'ctx_found': len(ctxs),
        'ctx_dispatch': _outcome(lambda: ctxs[0].dispatch_tool(TOOL, {'direction': 'incoming'})) if ctxs else None,
    }


def _scope():
    from hermes_cli.plugins import get_plugin_manager
    return get_plugin_manager().scope_key


def _scoped_entry(registry):
    try:
        return registry.get_entry(TOOL, scope=_scope()) is not None
    except Exception as exc:
        return f'{type(exc).__name__}: {exc}'[:200]


@router.get('/probe')
async def probe():
    return await asyncio.to_thread(_probe)
