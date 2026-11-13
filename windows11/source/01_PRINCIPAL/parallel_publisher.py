"""Canales HTTPS independientes: una subida de modelo nunca bloquea el vídeo."""
import json,time,secrets,threading,gzip
from pathlib import Path
from urllib.parse import urlsplit,urlencode
import requests
from PyQt5 import QtCore as C
import server

VIDEO_PROFILES={'fluida':{'width':640,'fps':12,'quality':65},'ahorro':{'width':480,'fps':4,'quality':55},'detalle':{'width':960,'fps':6,'quality':78}}
class ParallelPublisher(C.QThread):
    changed=C.pyqtSignal(str,str)
    def __init__(self,url,token):
        super().__init__();u=urlsplit(url.strip())
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):raise ValueError('Dirección HTTPS del puente inválida')
        if len(token)<32:raise ValueError('Configuración privada de estación incompleta')
        self.base=url.rstrip('/');self.owner=token;self.session=secrets.token_urlsafe(24);self.viewer=secrets.token_urlsafe(32);self.stop_event=threading.Event();self.ready=threading.Event();self.lock=threading.RLock();self.uploaded=None;self.video_options=dict(VIDEO_PROFILES['fluida']);self.viewing=False;self.fps=0.;self.video_error='';self.register_generation=0
    def stop(self):self.stop_event.set();return self.wait(16000)
    def http(self):
        session=requests.Session();session.trust_env=False;session.headers.update({'Authorization':'Bearer '+self.owner,'X-Modix-Session':self.session});adapter=requests.adapters.HTTPAdapter(pool_connections=2,pool_maxsize=3,max_retries=0);session.mount('https://',adapter);return session
    def post(self,session,path,data,kind='application/json',timeout=(2,4)):
        payload=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False,allow_nan=False).encode();headers={'Content-Type':kind}
        if kind=='application/json':payload=gzip.compress(payload,compresslevel=1);headers['Content-Encoding']='gzip'
        response=session.post(self.base+path,data=payload,headers=headers,timeout=timeout,allow_redirects=False);response.raise_for_status();return response
    def identity(self,gcode,path):return (str(path),gcode.get('sha256'),len(gcode.get('segments',[]))) if gcode is not None else None
    def snapshot(self):
        from obs_runtime import ENGINE
        with server.LOCK:
            gcode=server.ACTIVE_GCODE;path=server.ACTIVE_FILE;identity=self.identity(gcode,path)
            with self.lock:available=gcode is not None and self.uploaded==identity
            return {'protocol':7,'application_version':11,'obs':ENGINE.status(),'status':dict(server.STATUS),'camera':server.camera_health(),'plate':list(server.CFG['plate']),'profile':server.CFG['profile_name'],'tools':server.CFG.get('tools',{}),'has_gcode':available,'gcode_file':Path(path).name if path else None,'remote_file':server.REMOTE_FILE,'gcode_revision':(gcode or {}).get('sha256') if available else None,'events':server.JOURNAL.records[-12:][::-1]}
    def model_loop(self):
        sent=object();generation=-1
        with self.http() as session:
            while not self.stop_event.is_set():
                if not self.ready.wait(.2):continue
                with self.lock:current_generation=self.register_generation
                if current_generation!=generation:sent=object();generation=current_generation
                with server.LOCK:gcode=server.ACTIVE_GCODE;identity=self.identity(gcode,server.ACTIVE_FILE)
                if sent!=identity:
                    try:
                        self.post(session,'/publish/model',gcode,timeout=(2,8))
                        with self.lock:
                            if generation==self.register_generation:self.uploaded=identity;sent=identity
                    except requests.HTTPError as error:
                        if error.response is not None and error.response.status_code==409:self.ready.clear()
                        self.stop_event.wait(1)
                    except Exception:self.stop_event.wait(1)
                self.stop_event.wait(.2)
    def camera_loop(self):
        previous=None;count=0;since=time.monotonic()
        with self.http() as session:
            while not self.stop_event.is_set():
                started=time.monotonic()
                if not self.ready.wait(.2):continue
                if not self.viewing or (hasattr(self,'streaming') and self.streaming.is_set()):self.stop_event.wait(.2);continue
                server.CAMERA.touch_viewer()
                with server.LOCK:jpeg=server.CAMERA_JPEG;updated=server.CAMERA_UPDATED
                if not jpeg or jpeg is previous or time.time()-updated>4:self.stop_event.wait(.015);continue
                options=dict(self.video_options);payload=jpeg
                try:
                    source=server.CAMERA.status();source_width=min(source.get('width') or 640,1280 if source.get('profile')=='detalle' else 960 if source.get('profile')=='equilibrada' else 640)
                    if source_width>options['width']:
                        import cv2,numpy as np
                        frame=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR)
                        if frame is not None:
                            if frame.shape[1]>options['width']:frame=cv2.resize(frame,(options['width'],round(frame.shape[0]*options['width']/frame.shape[1])))
                            ok,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,options['quality']])
                            if ok:payload=encoded.tobytes()
                    self.post(session,'/publish/camera',payload,'image/jpeg');previous=jpeg;self.video_error='';count+=1
                    duration=time.monotonic()-since
                    if duration>=1:self.fps=round(count/duration,1);count=0;since=time.monotonic()
                except requests.HTTPError as error:
                    code=error.response.status_code if error.response is not None else 0;self.video_error='Límite de datos del puente alcanzado' if code==429 else 'Vídeo remoto reintentando'
                    if code==409:self.ready.clear()
                    self.stop_event.wait(.7)
                except Exception:self.video_error='Vídeo remoto reintentando';self.stop_event.wait(.7)
                self.stop_event.wait(max(.01,1/options['fps']-(time.monotonic()-started)))
    def run(self):
        workers=[threading.Thread(target=target,daemon=True) for target in (self.model_loop,self.camera_loop)]
        for thread in workers:thread.start()
        registered=False;verified=False;viewed_at=0
        with self.http() as session:
            try:
                while not self.stop_event.is_set():
                    started=time.monotonic()
                    try:
                        if not self.ready.is_set():
                            self.changed.emit('Creando enlace HTTPS…','');self.post(session,'/publish/start',{'viewer':self.viewer,'session':self.session});registered=True;verified=False
                            with self.lock:self.uploaded=None;self.register_generation+=1
                            self.ready.set()
                        if not (hasattr(self,'streaming') and self.streaming.is_set()):self.post(session,'/publish/state',self.snapshot())
                        if time.monotonic()-viewed_at>=2:
                            response=session.get(self.base+'/publish/status',timeout=(2,4),allow_redirects=False);response.raise_for_status();self.viewing=bool(response.json().get('viewing'));viewed_at=time.monotonic()
                        if not verified:
                            response=session.get(self.base+'/api/live',headers={'Authorization':'Bearer '+self.viewer},timeout=(2,4),allow_redirects=False);response.raise_for_status()
                            if response.json().get('protocol')!=7:raise ValueError('El puente no devolvió protocolo MODIX')
                            verified=True
                        url=self.base+'/#'+urlencode({'key':self.viewer});self.changed.emit('Internet activo · '+(self.video_error or f'vídeo {self.fps:.1f} FPS · '+('cliente conectado' if self.viewing else 'esperando cliente')),url)
                    except requests.HTTPError as error:
                        code=error.response.status_code if error.response is not None else 0
                        if code in (403,409):self.ready.clear()
                        self.changed.emit('Límite de transferencia del puente alcanzado' if code==429 else f'Puente reintentando (HTTP {code})',self.base+'/#'+urlencode({'key':self.viewer}) if verified else '');self.stop_event.wait(1)
                    except Exception:self.changed.emit('Puente HTTPS reintentando; el vídeo y modelo mantienen conexiones independientes',self.base+'/#'+urlencode({'key':self.viewer}) if verified else '');self.stop_event.wait(1)
                    self.stop_event.wait(max(.01,.8-(time.monotonic()-started)))
            finally:
                self.stop_event.set();deadline=time.monotonic()+7
                for thread in workers:thread.join(max(0,deadline-time.monotonic()))
                if registered:
                    try:self.post(session,'/publish/stop',{},timeout=(2,3))
                    except Exception:pass
                self.changed.emit('Acceso por Internet cerrado','')
