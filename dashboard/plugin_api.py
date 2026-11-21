"""Spike: can a backend route reach the Fulcra MCP tools Hermes already connected? Reports outcomes only, never data."""
import asyncio
import json
import os
import sys
import time

from fastapi import APIRouter

router = APIRouter()
TOOL = 'mcp__fulcra__list_shares'


def _outcome(fn):
    started = time.monotonic()
    try:
        out = fn()
        parsed = json.loads(out) if isinstance(out, str) else out
        ok = isinstance(parsed, dict) and 'result' in parsed and 'own_fulcra_userid' in str(parsed['result'])
        return {'ok': ok, 'error': None if ok else str(parsed)[:200], 'seconds': round(time.monotonic() - started, 2)}
    except Exception as exc:
        return {'ok': False, 'exception': f'{type(exc).__name__}: {exc}'[:300],
                'seconds': round(time.monotonic() - started, 2)}


def _probe():
    from tools.registry import registry
    ctxs = [m._FULCRA_CTX for m in list(sys.modules.values()) if getattr(m, '_FULCRA_CTX', None) is not None]
    return {
        'pid': os.getpid(),
        'process': os.path.basename(sys.argv[0]),
        'fulcra_context_tools': len([n for n in registry.get_all_tool_names() if n.startswith('mcp__fulcra__')]),
        'ctx_found': len(ctxs),
        'ctx_dispatch': _outcome(lambda: ctxs[0].dispatch_tool(TOOL, {'direction': 'incoming'})) if ctxs else None,
    }


@router.get('/probe')
async def probe():
    return await asyncio.to_thread(_probe)
