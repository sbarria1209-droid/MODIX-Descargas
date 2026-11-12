"""Señalización WebRTC y respaldo H.264; no decodifica vídeo en Render."""
import asyncio, json, secrets, time, contextlib
from aiohttp import web, WSMsgType
from relay9 import Hub, equal

MAGIC=b'MXH1'
class MediaPeer:
    def __init__(self,ws):
        self.ws=ws;self.queue=asyncio.Queue(40);self.direct=False;self.wait_key=True

class MediaHub(Hub):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.rtc_owner=None;self.rtc_peers={};self.media_time=0
    async def revoke_peers(self):
        await super().revoke_peers()
        sockets=[p.ws for p in self.rtc_peers.values()]
        if self.rtc_owner:sockets.append(self.rtc_owner)
        for ws in sockets:await ws.close(code=1008,message=b'Acceso revocado')
        self.rtc_peers.clear();self.rtc_owner=None
    async def get(self,request):
        if request.path=='/health':
            return await self.response(request,{'service':'MODIX-HTTPS','protocol':7,'implementation':10,'websocket':True,'webrtc_signaling':True,'h264_relay':True,'ready':len(self.owner)>=32})
        return await super().get(request)
    async def owner_message(self,data):
        ws=self.rtc_owner
        if ws and not ws.closed:
            with contextlib.suppress(ConnectionError,asyncio.TimeoutError):await asyncio.wait_for(ws.send_json(data),2)
    async def audience(self):await self.owner_message({'type':'audience','fallback':sum(not p.direct for p in self.rtc_peers.values())})
    def broadcast(self,kind,data):
        obs=bool((self.state or {}).get('obs',{}).get('active'))
        for queue in list(self.peers.values()):
            if kind=='frame' and obs and queue.get('no_jpeg'):continue
            queue[kind]=data;queue['wake'].set()
    async def rtc_publish(self,request):
        if not equal(self.token(request),self.owner):return await self.response(request,{'error':'Acceso denegado'},403)
        generation=request.headers.get('X-Modix-Session')
        if not self.viewer or generation!=self.session:return await self.response(request,{'error':'Sesion cambiada'},409)
        ws=web.WebSocketResponse(heartbeat=10,max_msg_size=1100000,compress=False);await ws.prepare(request)
        if self.rtc_owner:await self.rtc_owner.close(code=1008,message=b'Canal sustituido')
        self.rtc_owner=ws
        for peer_id,peer in self.rtc_peers.items():
            peer.direct=False;peer.wait_key=True;await self.owner_message({'type':'join','peer':peer_id})
        await self.audience()
        try:
            async for message in ws:
                if self.session!=generation:break
                if message.type==WSMsgType.BINARY:
                    payload=message.data
                    if len(payload)<17 or not payload.startswith(MAGIC):raise ValueError('Video invalido')
                    self.media_time=time.time();key=bool(payload[16])
                    for peer in list(self.rtc_peers.values()):
                        if peer.direct:continue
                        if peer.queue.full():
                            while not peer.queue.empty():peer.queue.get_nowait()
                            peer.wait_key=True
                        if peer.wait_key and not key:continue
                        peer.wait_key=False;peer.queue.put_nowait(payload)
                elif message.type==WSMsgType.TEXT:
                    data=json.loads(message.data);peer=self.rtc_peers.get(data.get('peer'))
                    if data.get('type')=='offer' and peer and isinstance(data.get('sdp'),str) and len(data['sdp'])<100000:
                        await peer.ws.send_json({'type':'offer','sdp':data['sdp']})
                elif message.type==WSMsgType.ERROR:break
        except (ValueError,KeyError,TypeError):await ws.close(code=1008,message=b'Datos invalidos')
        finally:
            if self.rtc_owner is ws:
                self.rtc_owner=None
                for peer in self.rtc_peers.values():
                    peer.direct=False;peer.wait_key=True
                    with contextlib.suppress(ConnectionError):await peer.ws.send_json({'type':'publisher_offline'})
        return ws
    async def rtc_view(self,request):
        token=self.token(request)
        if not equal(token,self.viewer):return await self.response(request,{'error':'Acceso denegado'},403)
        if len(self.rtc_peers)>=4:return await self.response(request,{'error':'Maximo cuatro visores OBS'},429)
        ws=web.WebSocketResponse(heartbeat=10,max_msg_size=110000,compress=False);await ws.prepare(request)
        peer_id=secrets.token_urlsafe(16);peer=MediaPeer(ws);self.rtc_peers[peer_id]=peer;generation=self.session;self.viewed=time.time()
        await ws.send_json({'type':'hello','peer':peer_id});await self.owner_message({'type':'join','peer':peer_id});await self.audience()
        async def send():
            while not ws.closed:
                if generation!=self.session or not equal(token,self.viewer) or time.time()-self.updated>15:
                    await ws.close(code=1008,message=b'Principal desconectada');return
                self.viewed=time.time()
                try:payload=await asyncio.wait_for(peer.queue.get(),1)
                except asyncio.TimeoutError:continue
                if peer.direct:continue
                if not self.spend(len(payload)):await ws.close(code=1008,message=b'Limite de transferencia');return
                try:await asyncio.wait_for(ws.send_bytes(payload),2)
                except (asyncio.TimeoutError,ConnectionError):await ws.close();return
        sender=asyncio.create_task(send())
        try:
            async for message in ws:
                if generation!=self.session:break
                if message.type==WSMsgType.TEXT:
                    data=json.loads(message.data);kind=data.get('type')
                    if kind=='answer' and isinstance(data.get('sdp'),str) and len(data['sdp'])<100000:
                        await self.owner_message({'type':'answer','peer':peer_id,'sdp':data['sdp']})
                    elif kind=='direct':
                        peer.direct=data.get('active') is True;peer.wait_key=True
                        await self.owner_message({'type':'direct','peer':peer_id,'active':peer.direct})
                        await self.audience()
                    elif kind=='retry':await self.owner_message({'type':'join','peer':peer_id})
                elif message.type==WSMsgType.ERROR:break
        except (ValueError,TypeError):pass
        finally:
            self.rtc_peers.pop(peer_id,None);sender.cancel();await asyncio.gather(sender,return_exceptions=True)
            await self.owner_message({'type':'leave','peer':peer_id})
            await self.audience()
        return ws

def create_app(owner=None,limit=None):
    import os
    hub=MediaHub(owner if owner is not None else os.environ.get('MODIX_OWNER_TOKEN',''),limit if limit is not None else int(os.environ.get('MODIX_OUTPUT_LIMIT','1000000000')))
    app=web.Application(client_max_size=16*1024*1024);app['hub']=hub
    app.router.add_get('/rtc/publish',hub.rtc_publish);app.router.add_get('/rtc/view',hub.rtc_view)
    app.router.add_get('/publish/stream',hub.publisher);app.router.add_get('/stream',hub.viewer_stream)
    app.router.add_get('/{path:.*}',hub.get);app.router.add_post('/{path:.*}',hub.post);return app

def main():
    import os
    app=create_app()
    if len(app['hub'].owner)<32:raise SystemExit('Falta MODIX_OWNER_TOKEN')
    web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT','10000')),access_log=None,print=None)
if __name__=='__main__':main()
