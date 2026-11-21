"""Probe the plugin route at each stage of a Desktop-like session on `hermes serve`."""
import asyncio
import json
import sys
import urllib.request

import websockets

PORT = int(sys.argv[1])
TOKEN = open(sys.argv[2]).read().strip()
BASE = f'http://127.0.0.1:{PORT}'


def probe(stage):
    req = urllib.request.Request(BASE + '/api/plugins/fulcra/probe', headers={'X-Hermes-Session-Token': TOKEN})
    data = json.load(urllib.request.urlopen(req, timeout=120))
    d = data['ctx_dispatch'] or {}
    print(f"{stage:<34} process={data['process']} tools={data['fulcra_context_tools']} "
          f"dispatch_ok={d.get('ok')} {d.get('error') or d.get('exception') or ''}"[:220], flush=True)


async def rpc(ws, rid, method, params):
    await ws.send(json.dumps({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params}))
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
        if msg.get('id') == rid:
            return msg


async def main():
    probe('1. serve started, no session')
    async with websockets.connect(f'ws://127.0.0.1:{PORT}/api/ws?token={TOKEN}', max_size=None) as ws:
        created = await rpc(ws, 1, 'session.create', {})
        sid = created.get('result', {}).get('session_id')
        print('session.create:', 'ok' if sid else created.get('error'), flush=True)
        await asyncio.sleep(10)
        probe('2. session created (lazy), +10s')
        submitted = await rpc(ws, 2, 'prompt.submit', {'session_id': sid, 'text': 'Say hi.'})
        print('prompt.submit:', 'ok' if 'result' in submitted else submitted.get('error'), flush=True)
        done = False
        for _ in range(60):
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
            except asyncio.TimeoutError:
                continue
            if msg.get('method') == 'event' and msg.get('params', {}).get('type') == 'message.complete':
                done = True
                break
        print('turn complete:', done, flush=True)
        probe('3. after one chat turn')
    probe('4. websocket closed')


asyncio.run(main())
