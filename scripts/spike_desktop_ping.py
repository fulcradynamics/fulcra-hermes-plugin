"""POST the Agents I Know page's /ping before and after a chat session exists, as Desktop would."""
import asyncio
import json
import sys
import urllib.request

import websockets

PORT, TOKEN = int(sys.argv[1]), open(sys.argv[2]).read().strip()


def ping(stage):
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}/api/plugins/fulcra/ping', data=b'', method='POST',
                                 headers={'X-Hermes-Session-Token': TOKEN})
    print(f'{stage:<28}', json.load(urllib.request.urlopen(req, timeout=60)), flush=True)


async def main():
    ping('before any session')
    async with websockets.connect(f'ws://127.0.0.1:{PORT}/api/ws?token={TOKEN}', max_size=None) as ws:
        await ws.send(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'session.create', 'params': {}}))
        while json.loads(await asyncio.wait_for(ws.recv(), 60)).get('id') != 1:
            pass
        await asyncio.sleep(10)
        ping('after session.create')


asyncio.run(main())
