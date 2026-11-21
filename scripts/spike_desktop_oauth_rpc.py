"""Sign in to a configured MCP server through the gateway JSON-RPC Desktop uses (mcp.servers.oauth.*)."""
import asyncio
import json
import sys

import websockets

PORT, TOKEN, NAME, URL_FILE = int(sys.argv[1]), open(sys.argv[2]).read().strip(), sys.argv[3], sys.argv[4]


async def rpc(ws, rid, method, params):
    await ws.send(json.dumps({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params}))
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
        if msg.get('id') == rid:
            return msg


async def main():
    async with websockets.connect(f'ws://127.0.0.1:{PORT}/api/ws?token={TOKEN}', max_size=None) as ws:
        status = await rpc(ws, 1, 'mcp.servers.status', {'name': NAME})
        print('status before:', json.dumps(status.get('result', status.get('error')))[:300], flush=True)
        started = await rpc(ws, 2, 'mcp.servers.oauth.start', {'name': NAME})
        result = started.get('result') or {}
        if not result.get('auth_url'):
            print('oauth.start failed:', started.get('error'), flush=True)
            return
        open(URL_FILE, 'w').write(result['auth_url'])
        print('oauth.start: flow', result.get('flow'), '- auth URL written', flush=True)
        for i in range(90):
            polled = (await rpc(ws, 10 + i, 'mcp.servers.oauth.poll',
                                {'name': NAME, 'session_id': result['session_id']})).get('result') or {}
            if polled.get('status') != 'pending':
                print('poll:', polled.get('status'), str(polled.get('error') or '')[:200], flush=True)
                break
            await asyncio.sleep(2)
        status = await rpc(ws, 200, 'mcp.servers.status', {'name': NAME})
        print('status after:', json.dumps(status.get('result', status.get('error')))[:300], flush=True)


asyncio.run(main())
