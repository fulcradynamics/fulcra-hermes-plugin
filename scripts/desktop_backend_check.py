#!/usr/bin/env python3
"""Drive a `hermes serve` backend the way the Desktop Agents I Know page does.

    desktop_backend_check.py PORT TOKEN_FILE [--connect URL] [--sign-in AUTH_URL_FILE]

Each step prints one line (no tokens or account details):
1. GET /api/plugins/fulcra/status, and mcp.servers.status over the gateway WebSocket.
2. --connect: POST /connect with URL (what the page's Connect button does).
3. --sign-in: mcp.servers.oauth.start, writing the auth URL to AUTH_URL_FILE for a browser to open, then
   mcp.servers.oauth.poll until it finishes (what the page's Sign in button does).
4. POST /ping before and after session.create (Hermes connects MCP servers when a session starts).

Needs the `websockets` package (Hermes's Python has it).
"""
import argparse
import asyncio
import json
import urllib.request

import websockets


def rest(port, token, path, body=None):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/api/plugins/fulcra{path}', method='GET' if body is None else 'POST',
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={'X-Hermes-Session-Token': token, 'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(request, timeout=60))


async def rpc(ws, rid, method, params):
    await ws.send(json.dumps({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params}))
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), 120))
        if message.get('id') == rid:
            return message.get('result', {'error': message.get('error')})


def fulcra_row(status):
    row = next((s for s in status.get('servers', []) if s.get('name') == 'fulcra'), None)
    return row and {k: row.get(k) for k in ('status', 'connected', 'tools', 'needs_auth')}


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('port', type=int)
    parser.add_argument('token_file')
    parser.add_argument('--connect', metavar='URL')
    parser.add_argument('--sign-in', metavar='AUTH_URL_FILE')
    args = parser.parse_args()
    port, token = args.port, open(args.token_file).read().strip()
    print('status:', rest(port, token, '/status'), flush=True)
    async with websockets.connect(f'ws://127.0.0.1:{port}/api/ws?token={token}', max_size=None) as ws:
        print('mcp.servers.status:', fulcra_row(await rpc(ws, 1, 'mcp.servers.status', {})), flush=True)
        if args.connect:
            print('connect:', rest(port, token, '/connect', {'url': args.connect}), flush=True)
        if args.sign_in:
            flow = await rpc(ws, 2, 'mcp.servers.oauth.start', {'name': 'fulcra'})
            if not flow.get('auth_url'):
                print('oauth.start failed:', flow, flush=True)
                return
            open(args.sign_in, 'w').write(flow['auth_url'])
            print('oauth.start: auth URL written; open it in a browser', flush=True)
            for i in range(150):
                polled = await rpc(ws, 10 + i, 'mcp.servers.oauth.poll', {'name': 'fulcra', 'session_id': flow['session_id']})
                if polled.get('status') != 'pending':
                    print('oauth.poll:', polled.get('status'), str(polled.get('error') or '')[:200], flush=True)
                    break
                await asyncio.sleep(2)
        print('ping before a session:', rest(port, token, '/ping', {}), flush=True)
        await rpc(ws, 500, "session.create", {})
        ping = {}
        for _ in range(15):  # MCP discovery runs in the background after the session starts.
            await asyncio.sleep(2)
            ping = rest(port, token, '/ping', {})
            if ping.get('state') != 'not_connected':
                break
        print('ping after session.create:', ping, flush=True)
        print('mcp.servers.status:', fulcra_row(await rpc(ws, 501, 'mcp.servers.status', {})), flush=True)


asyncio.run(main())
