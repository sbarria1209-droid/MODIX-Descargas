"""Puente HTTP compatible y WebSocket de última imagen; visores de solo lectura."""
import asyncio,os,json,time,secrets,gzip,hashlib,contextlib
from aiohttp import web,WSMsgType

def equal(a,b):return bool(a and b) and secrets.compare_digest(str(a),str(b))
class Hub:
    def __init__(self,owner,limit=1000000000):
        self.owner=owner;self.viewer='';self.session='';self.updated=0.;self.camera_time=0.;self.state=None;self.model=None;self.model_encoded=None;self.jpeg=None;self.serial=0;self.viewed=0.;self.limit=limit;self.output=0;self.month=time.strftime('%Y-%m');self.peers={};self.publishers=set()
    def spend(self,count):
        month=time.strftime('%Y-%m')
        if month!=self.month:self.month=month;self.output=0
        if self.output+count>self.limit:return False
        self.output+=count;return True
    def token(self,request):
        auth=request.headers.get('Authorization','');return auth[7:] if auth.startswith('Bearer ') else ''
    async def revoke_peers(self):
        for peer in list(self.peers):await peer.close(code=1008,message=b'Acceso cerrado o sustituido')
        for peer in list(self.publishers):await peer.close(code=1008,message=b'Sesion sustituida')
    def broadcast(self,kind,data):
        for queue in list(self.peers.values()):
            queue[kind]=data;queue['wake'].set()
    async def response(self,request,data,status=200,kind='application/json',compress=False,etag=None):
        body=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode();headers={'Cache-Control':'private, no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'}
        if compress and len(body)>1000 and 'gzip' in request.headers.get('Accept-Encoding',''):body=await asyncio.to_thread(gzip.compress,body,compresslevel=1);headers['Content-Encoding']='gzip'
        if etag:headers['ETag']=etag
        if not self.spend(len(body)):body=b'{"error":"Limite gratuito de transferencia alcanzado"}';status=429;headers.pop('Content-Encoding',None)
        return web.Response(status=status,body=body,content_type=kind,headers=headers)
    async def get(self,request):
        path=request.path;token=self.token(request);now=time.time()
        if path=='/health':return await self.response(request,{'service':'MODIX-HTTPS','protocol':7,'implementation':9,'websocket':True,'ready':len(self.owner)>=32})
        if path=='/':return await self.response(request,b'MODIX: usa el cliente de escritorio.','200' if False else 200,'text/plain')
        if path=='/publish/status' and equal(token,self.owner):return await self.response(request,{'viewing':bool(self.peers) or now-self.viewed<7,'active':bool(self.viewer),'session':self.session,'stream_viewers':len(self.peers)})
        if not equal(token,self.viewer):return await self.response(request,{'error':'Acceso cerrado o clave incorrecta'},403)
        if now-self.updated>15:return await self.response(request,{'error':'Principal sin datos recientes'},503)
        self.viewed=now
        if path=='/api/live':return await self.response(request,self.state or {},compress=True)
        if path=='/api/layers':
            body=self.model_encoded
            if body is None:return await self.response(request,{'gcode':self.model},compress=True)
            if not self.spend(len(body)):return await self.response(request,{'error':'Limite gratuito de transferencia alcanzado'},429)
            return web.Response(body=body,content_type='application/json',headers={'Content-Encoding':'gzip','Cache-Control':'private, no-store'})
        if path=='/camera.jpg':
            if not self.jpeg or now-self.camera_time>5:return await self.response(request,{'error':'Cámara sin imagen reciente'},404)
            etag='"'+str(self.serial)+'"'
            if request.headers.get('If-None-Match')==etag:return await self.response(request,b'',304,etag=etag)
            return await self.response(request,self.jpeg,kind='image/jpeg',etag=etag)
        return await self.response(request,{'error':'Ruta no disponible'},404)
    def set_state(self,data):
        if not isinstance(data,dict) or not isinstance(data.get('status'),dict):raise ValueError('Estado invalido')
        self.state=data;self.updated=time.time();self.broadcast('state',json.dumps({'type':'state','data':data},ensure_ascii=False,allow_nan=False,separators=(',',':')))
    def set_frame(self,data):
        if not isinstance(data,bytes) or not data.startswith(b'\xff\xd8') or len(data)>1024*1024:raise ValueError('JPEG invalido')
        self.jpeg=data;self.camera_time=time.time();self.serial+=1;self.broadcast('frame',data)
    async def post(self,request):
        if not equal(self.token(request),self.owner):return await self.response(request,{'error':'Acceso denegado'},403)
        path=request.path
        try:
            if path!='/publish/start' and (not self.viewer or request.headers.get('X-Modix-Session')!=self.session):return await self.response(request,{'error':'Sesion sustituida o cerrada'},409)
            raw=await request.read()
            if len(raw)>(14*1024*1024 if path=='/publish/model' else 1024*1024):raise ValueError('Carga excesiva')
            data=None if path=='/publish/camera' else await asyncio.to_thread(json.loads,raw)
            if path=='/publish/start':
                key=data.get('viewer');session=data.get('session')
                if not isinstance(key,str) or len(key)<32 or not isinstance(session,str) or len(session)<16:raise ValueError('Identidad invalida')
                await self.revoke_peers();self.viewer=key;self.session=session;self.updated=0;self.camera_time=0;self.state=self.model=self.jpeg=self.model_encoded=None
            elif path=='/publish/state':self.set_state(data)
            elif path=='/publish/camera':self.set_frame(raw)
            elif path=='/publish/model':
                if data is not None and (not isinstance(data,dict) or len(data.get('segments',[]))>100000):raise ValueError('Modelo invalido')
                generation=self.session;encoded=await asyncio.to_thread(lambda:gzip.compress(json.dumps({'gcode':data},allow_nan=False,separators=(',',':')).encode(),compresslevel=1))
                if generation!=self.session:return await self.response(request,{'error':'Sesion cambiada'},409)
                self.model=data;self.model_encoded=encoded
            elif path=='/publish/stop':
                self.viewer='';self.session='';self.state=self.model=self.jpeg=self.model_encoded=None;self.updated=self.camera_time=0;await self.revoke_peers()
            else:return await self.response(request,{'error':'Ruta no disponible'},404)
            return await self.response(request,{'ok':True})
        except (ValueError,TypeError,OverflowError,UnicodeError):return await self.response(request,{'error':'Carga invalida'},400)
    async def publisher(self,request):
        if not equal(self.token(request),self.owner):return await self.response(request,{'error':'Acceso denegado'},403)
        generation=request.headers.get('X-Modix-Session')
        if not self.viewer or generation!=self.session:return await self.response(request,{'error':'Sesion cambiada'},409)
        ws=web.WebSocketResponse(heartbeat=12,max_msg_size=1024*1024,compress=False);await ws.prepare(request);self.publishers.add(ws)
        try:
            async for message in ws:
                if generation!=self.session:break
                if message.type==WSMsgType.BINARY:self.set_frame(bytes(message.data))
                elif message.type==WSMsgType.TEXT:
                    data=json.loads(message.data)
                    if data.get('type')=='state':self.set_state(data['data'])
                elif message.type==WSMsgType.ERROR:break
        except (ValueError,KeyError,TypeError):await ws.close(code=1008,message=b'Datos invalidos')
        finally:self.publishers.discard(ws)
        return ws
    async def viewer_stream(self,request):
        token=self.token(request)
        if not equal(token,self.viewer):return await self.response(request,{'error':'Acceso denegado'},403)
        if len(self.peers)>=8:return await self.response(request,{'error':'Demasiados visores'},429)
        ws=web.WebSocketResponse(heartbeat=10,max_msg_size=1024,compress=False);await ws.prepare(request);generation=self.session;queue={'state':None,'frame':None,'wake':asyncio.Event()};self.peers[ws]=queue;self.viewed=time.time()
        if self.state:queue['state']=json.dumps({'type':'state','data':self.state},ensure_ascii=False,allow_nan=False,separators=(',',':'))
        if self.jpeg and time.time()-self.camera_time<3:queue['frame']=self.jpeg
        queue['wake'].set()
        async def send():
            while not ws.closed:
                try:await asyncio.wait_for(queue['wake'].wait(),timeout=2)
                except asyncio.TimeoutError:pass
                queue['wake'].clear()
                if not equal(token,self.viewer) or generation!=self.session or time.time()-self.updated>15:await ws.close(code=1008,message=b'Principal desconectada o acceso cerrado');break
                self.viewed=time.time()
                for kind in ('state','frame'):
                    payload=queue[kind];queue[kind]=None
                    if payload is None:continue
                    if not self.spend(len(payload)):await ws.close(code=1008,message=b'Limite gratuito de transferencia');return
                    # Como máximo una imagen pendiente por cliente. Un visor lento
                    # se vuelve a conectar a la imagen reciente, nunca a una cola antigua.
                    try:await asyncio.wait_for(ws.send_bytes(payload) if kind=='frame' else ws.send_str(payload),timeout=3)
                    except (asyncio.TimeoutError,ConnectionError):await ws.close();return
        sender=asyncio.create_task(send())
        try:
            async for message in ws:
                # El visor no puede enviar órdenes ni modificar el estado de la estación.
                if message.type==WSMsgType.ERROR:break
        finally:self.peers.pop(ws,None);sender.cancel();await asyncio.gather(sender,return_exceptions=True)
        return ws
def create_app(owner=None,limit=None):
    owner=owner if owner is not None else os.environ.get('MODIX_OWNER_TOKEN','');hub=Hub(owner,limit if limit is not None else int(os.environ.get('MODIX_OUTPUT_LIMIT','1000000000')));app=web.Application(client_max_size=16*1024*1024);app['hub']=hub;app.router.add_get('/publish/stream',hub.publisher);app.router.add_get('/stream',hub.viewer_stream);app.router.add_get('/{path:.*}',hub.get);app.router.add_post('/{path:.*}',hub.post);return app
def main():
    app=create_app()
    if len(app['hub'].owner)<32:raise SystemExit('Falta MODIX_OWNER_TOKEN')
    web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT','10000')),access_log=None,print=None)
if __name__=='__main__':main()
