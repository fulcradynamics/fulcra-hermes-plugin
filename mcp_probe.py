"""Spike: call the hosted Fulcra MCP server's tools from hooks through ctx.dispatch_tool.

Records each call's outcome (never its content) in plugin state under 'mcp-probe', from the
pre_llm_call hook (in the turn) and from a post_llm_call background thread (as what's new runs).
"""
import contextvars
import json
import threading
import time
from datetime import datetime, timedelta, timezone

KEY = 'mcp-probe'
CALLS = {
    'mcp__fulcra_context__get_user_info': lambda: {},
    'mcp__fulcra_context__get_data_updates': lambda: {
        'start_time': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        'end_time': datetime.now(timezone.utc).isoformat()},
}


def _probe(ctx, where):
    results = {}
    for name, args in CALLS.items():
        started = time.time()
        try:
            out = ctx.dispatch_tool(name, args())
            try:
                parsed = json.loads(out)
                shape = sorted(parsed)[:8] if isinstance(parsed, dict) else type(parsed).__name__
            except (TypeError, ValueError):
                shape = 'text'
            results[name] = {'ok': 'error' not in str(out)[:200].lower(), 'shape': shape,
                             'head': str(out)[:80] if 'error' in str(out)[:200].lower() else None,
                             'seconds': round(time.time() - started, 2)}
        except Exception as exc:
            results[name] = {'ok': False, 'exception': type(exc).__name__, 'message': str(exc)[:160]}
    state = ctx.state.get(KEY, {})
    state[where] = {'at': datetime.now(timezone.utc).isoformat(), 'results': results}
    ctx.state.set(KEY, state)


def register(ctx):
    def pre(**kwargs):
        _probe(ctx, 'pre_llm_call')

    def post(**kwargs):
        threading.Thread(target=contextvars.copy_context().run, args=(_probe, ctx, 'post_llm_call_thread'),
                         daemon=True).start()

    ctx.register_hook('pre_llm_call', pre)
    ctx.register_hook('post_llm_call', post)
