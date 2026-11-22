#!/usr/bin/env python3
"""Drive a `hermes serve` backend the way the Desktop Agents I Know page does.

    desktop_backend_check.py PORT TOKEN_FILE

Prints one line per step (no tokens or account details): GET /api/plugins/fulcra/status, then POST /ping
before and after a session.create over the gateway WebSocket (Hermes connects MCP servers when a session
starts). Needs the `websockets` package (Hermes's Python has it).
"""
import argparse
import asyncio
import json
import urllib.request

import websockets


def rest(port, token, path, body=None):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/api/plugins/fulcra{path}',
                                     method='GET' if body is None else 'POST',
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={'X-Hermes-Session-Token': token, 'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(request, timeout=60))


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('port', type=int)
    parser.add_argument('token_file')
    args = parser.parse_args()
    port, token = args.port, open(args.token_file).read().strip()
    print('status:', rest(port, token, '/status'), flush=True)
    print('ping before a session:', rest(port, token, '/ping', {}), flush=True)
    async with websockets.connect(f'ws://127.0.0.1:{port}/api/ws?token={token}', max_size=None) as ws:
        await ws.send(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'session.create', 'params': {}}))
        while json.loads(await asyncio.wait_for(ws.recv(), 120)).get('id') != 1:
            pass
        ping = {}
        for _ in range(15):  # MCP discovery runs in the background after the session starts.
            await asyncio.sleep(2)
            ping = rest(port, token, '/ping', {})
            if ping.get('state') != 'not_connected':
                break
        print('ping after session.create:', ping, flush=True)


asyncio.run(main())
