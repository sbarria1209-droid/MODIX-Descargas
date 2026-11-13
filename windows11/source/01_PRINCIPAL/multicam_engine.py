"""Una salida multicámara con píxeles actuales, máscaras y zonas ocultas explícitas."""
import os,json,copy,time,threading,secrets,math,contextlib
from collections import deque
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
import cv2,numpy as np
from multicam_capture import Capture,devices,synchronized,MAX_CAMERAS
from fusion_geometry import Composer,CalibrationError

def default_config(plate=(980,1000,1000)):
    w,d=map(float,plate[:2]);rw=min(300,w);rd=min(300,d)
    return {'version':1,'cameras':[{'enabled':i<2,'index':i,'name':'Cámara '+str(i),'uid':'','calibration':None,'masks':[],'priority':1.0} for i in range(MAX_CAMERAS)],'bed':{'x':0.,'y':0.,'width':w,'depth':d},'reference':{'x':(w-rw)/2,'y':(d-rd)/2,'width':rw,'depth':rd,'z0':0.,'z1':100.},'capture':{'width':1280,'height':720,'fps':30},'kinematics':'bed_moves','canvas':640,'fps':20,'sync_ms':100,'max_age_ms':350,'provenance':False,'pose_mode':'duet','manual_xyz':[w/2,d/2,0.],'arm':{'enabled':True,'axis':'x','beam_width':60.,'beam_bottom':35.,'beam_top':130.,'head_radius':40.,'head_height':130.,'margin':15.,'max_speed':150.}}

def validate(config):
    c=copy.deepcopy(config);cams=c.get('cameras')
    if not isinstance(cams,list) or not 2<=len(cams)<=MAX_CAMERAS:raise ValueError('Configura entre dos y ocho cámaras')
    enabled=[cam for cam in cams if cam.get('enabled')]
    if len(enabled)<2:raise ValueError('Selecciona al menos dos cámaras diferentes')
    indices=[]
    for cam in enabled:
        index=cam.get('index')
        if isinstance(index,bool) or not isinstance(index,int) or not 0<=index<=15:raise ValueError('Índice de cámara inválido')
        indices.append(index)
        if len(cam.get('masks',[]))>24:raise ValueError('Demasiadas máscaras de cámara')
        for polygon in cam.get('masks',[]):
            p=np.asarray(polygon,float)
            if p.ndim!=2 or not 3<=len(p)<=64 or p.shape[1]!=2 or not np.isfinite(p).all() or (p<0).any() or (p>1).any():raise ValueError('Máscara inválida')
        calibration=cam.get('calibration')
        if calibration:
            P=np.asarray(calibration.get('projection'),float)
            if P.shape!=(3,4) or not np.isfinite(P).all() or np.linalg.matrix_rank(P)<3:raise ValueError('Calibración de cámara inválida')
            if not isinstance(calibration.get('frame_size'),list) or min(calibration['frame_size'])<16:raise ValueError('Falta tamaño de imagen de calibración')
    if len(set(indices))!=len(indices):raise ValueError('No se puede abrir dos veces la misma cámara USB')
    identities=[str(cam.get('uid')) for cam in enabled if cam.get('uid')]
    if len(set(identities))!=len(identities):raise ValueError('Selecciona dispositivos USB diferentes')
    c.setdefault('capture',{'width':1280,'height':720,'fps':30})
    if (c['capture'].get('width'),c['capture'].get('height')) not in ((640,480),(1280,720),(1920,1080)):raise ValueError('Formato de captura no admitido')
    for key in ('x','y','width','depth'):
        value=float(c['bed'][key])
        if not math.isfinite(value) or abs(value)>10000 or (key in ('width','depth') and value<20):raise ValueError('Dimensiones de cama inválidas')
        c['bed'][key]=value
    c['canvas']=max(240,min(960,int(c.get('canvas',640))));c['fps']=max(5,min(30,int(c.get('fps',20))));c['sync_ms']=max(20,min(200,int(c.get('sync_ms',100))));c['max_age_ms']=max(150,min(700,int(c.get('max_age_ms',350))))
    if c.get('kinematics') not in ('bed_moves','bed_fixed'):raise ValueError('Selecciona cómo se mueve el eje Z')
    xyz=np.asarray(c.get('manual_xyz',[0,0,0]),float)
    if xyz.shape!=(3,) or not np.isfinite(xyz).all() or np.any(np.abs(xyz)>10000):raise ValueError('Posición manual inválida')
    arm=c['arm']
    for key,limit in [('beam_width',300),('beam_bottom',1000),('beam_top',1000),('head_radius',300),('head_height',1000),('margin',100),('max_speed',1000)]:
        value=float(arm[key])
        if not math.isfinite(value) or not 0<=value<=limit:raise ValueError('Medida de brazo inválida: '+key)
        arm[key]=value
    if arm['beam_top']<=arm['beam_bottom']:raise ValueError('La parte superior del brazo debe superar la inferior')
    return c

def load_config(path,plate=(980,1000,1000)):
    try:return validate(json.loads(Path(path).read_text(encoding='utf-8')))
    except (OSError,ValueError,KeyError,TypeError):return default_config(plate)
def save_config(path,config):
    c=validate(config);p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);temporary=p.with_suffix('.tmp');temporary.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temporary,p);return c

class FeedServer(ThreadingHTTPServer):daemon_threads=True;allow_reuse_address=True

class FusionEngine:
    def __init__(self,path,plate=(980,1000,1000),capture_factory=Capture):
        self.path=Path(path);self.config=load_config(path,plate);self.capture_factory=capture_factory;self.lock=threading.RLock();self.condition=threading.Condition(self.lock);self.captures=[];self.worker=None;self.stop_event=threading.Event();self.poses=deque(maxlen=12);self.frame=None;self.jpeg=None;self.sequence=0;self.stamp=0.;self.http=None;self.http_thread=None;self.token='';self.url='';self.details={'mode':'stopped','message':'Multicámara detenida','coverage':None};self.actual_fps=0.;self.best_camera=None
    @property
    def running(self):return bool(self.worker and self.worker.is_alive() and not self.stop_event.is_set())
    def set_pose(self,xyz,stamp=None):
        if xyz is None:return
        a=np.asarray(xyz,float)
        if a.shape==(3,) and np.isfinite(a).all():
            with self.lock:self.poses.append((time.monotonic() if stamp is None else stamp,a.copy()))
    def pose(self,stamp):
        if self.config.get('pose_mode')=='manual':return {'xyz':list(self.config['manual_xyz']),'uncertainty':0.,'manual':True}
        with self.lock:poses=list(self.poses)
        if not poses or time.monotonic()-poses[-1][0]>1.2:return None
        last,xyz=min(poses,key=lambda p:abs(p[0]-stamp));uncertainty=float(self.config['arm']['max_speed'])*abs(stamp-last)
        for (a,x),(b,y) in zip(poses,poses[1:]):
            if a<=stamp<=b and b>a:xyz=x+(y-x)*(stamp-a)/(b-a);uncertainty=float(self.config['arm']['max_speed'])*(b-a)/2;break
        return {'xyz':xyz.tolist(),'uncertainty':uncertainty,'manual':False}
    def start(self,config=None,require_two=True,identify=True):
        if self.running:
            if config is None:return self.status()
            self.stop()
        if any(c.thread.is_alive() for c in self.captures):raise RuntimeError('Espera a que termine de cerrar la captura anterior')
        self.config=validate(config or self.config);self.stop_event=threading.Event();self.frame=self.jpeg=None;self.sequence=0;self.stamp=0.;self.details={'mode':'starting','message':'Abriendo cámaras USB','coverage':None};self.captures=[];self.best_camera=None
        current=devices() if identify else []
        for camera in self.config['cameras']:
            if not camera.get('enabled'):continue
            camera['capture']=dict(self.config['capture'])
            camera.pop('binding_error',None)
            if camera.get('uid') and identify:
                match=next((d for d in current if d['uid']==camera['uid']),None)
                if match:camera['index']=match['index']
                else:camera['calibration']=None;camera['binding_error']='Cambió la identidad USB; vuelve a seleccionar y calibrar'
            capture=self.capture_factory(camera);self.captures.append(capture);capture.start()
        self.worker=threading.Thread(target=self.run,daemon=True);self.worker.start();self._start_feed()
        if require_two:
            deadline=time.monotonic()+7
            while time.monotonic()<deadline and not self.stop_event.is_set():
                live=sum(bool(c.history()) and time.monotonic()-c.history()[-1][0]<.35 for c in self.captures)
                if live>=2:return self.status()
                self.stop_event.wait(.1)
            count=sum(bool(c.history()) for c in self.captures);self.stop();raise RuntimeError(f'Solo {count} cámaras entregaron imagen. Conecta dos USB distintas y revisa Configurar cámaras.')
        return self.status()
    def _start_feed(self):
        engine=self;self.token=secrets.token_urlsafe(32)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                query=parse_qs(urlsplit(self.path).query);token=query.get('key',[''])[0]
                if not token or not secrets.compare_digest(token,engine.token):self.send_error(403);return
                self.connection.settimeout(1.5);self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=modixframe');self.send_header('Cache-Control','no-store');self.end_headers();previous=-1
                try:
                    while not engine.stop_event.is_set() and secrets.compare_digest(token,engine.token):
                        with engine.condition:
                            engine.condition.wait_for(lambda:engine.sequence!=previous or engine.stop_event.is_set(),timeout=.3);jpeg=engine.jpeg;seq=engine.sequence
                        if not jpeg or seq==previous:continue
                        previous=seq;self.wfile.write(b'--modixframe\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(jpeg)).encode()+b'\r\n\r\n'+jpeg+b'\r\n');self.wfile.flush()
                except (OSError,ConnectionError):pass
        self.http=FeedServer(('127.0.0.1',0),Handler);self.url=f'http://127.0.0.1:{self.http.server_address[1]}/stream?key={self.token}';self.http_thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.http_thread.start()
    def _mosaic(self,views,message):
        out=np.full((720,1280,3),20,np.uint8);n=max(2,len(self.captures));cols=2 if n<=4 else 4;rows=math.ceil(n/cols);cw=1280//cols;ch=620//rows
        frames={v[0]['index']:v[1] for v in views}
        for i,capture in enumerate(self.captures):
            x=(i%cols)*cw;y=60+(i//cols)*ch;frame=frames.get(capture.camera['index'])
            if frame is not None:
                scale=min((cw-12)/frame.shape[1],(ch-30)/frame.shape[0]);im=cv2.resize(frame,(max(1,round(frame.shape[1]*scale)),max(1,round(frame.shape[0]*scale))));h,w=im.shape[:2];out[y+26:y+26+h,x+(cw-w)//2:x+(cw-w)//2+w]=im
            cv2.putText(out,'CAMARA '+str(capture.camera['index'])+(' - SIN IMAGEN' if frame is None else ''),(x+10,y+20),cv2.FONT_HERSHEY_SIMPLEX,.5,(190,210,245),1,cv2.LINE_AA)
        cv2.putText(out,'MODIX V4 - MULTICAMARA / VISTA SIN FUSION',(18,34),cv2.FONT_HERSHEY_SIMPLEX,.7,(70,70,255),2,cv2.LINE_AA);self._caption(out,message);return out
    @staticmethod
    def _caption(out,text):
        cv2.rectangle(out,(0,676),(1279,719),(20,25,35),-1);safe=str(text).encode('ascii','replace').decode();cv2.putText(out,safe[:115],(15,704),cv2.FONT_HERSHEY_SIMPLEX,.52,(210,225,245),1,cv2.LINE_AA)
    def run(self):
        composer=Composer();count=0;began=time.monotonic()
        try:
            while not self.stop_event.is_set():
                started=time.monotonic();views,skew=synchronized(self.captures,self.config['max_age_ms']/1000,self.config['sync_ms']/1000);stamp=max((v[2] for v in views),default=started);pose=self.pose(stamp);calibrated=[v for v in views if v[0].get('calibration')];info={'coverage':None,'valid_views':len(calibrated)}
                if len(views)<2:message='Se necesitan dos imagenes actuales y sincronizadas';mode='mosaic';out=self._mosaic(views,message)
                elif len(calibrated)<2:message='Calibra al menos dos camaras en dos alturas conocidas';mode='mosaic';out=self._mosaic(views,message)
                elif pose is None:message='Conecta Duet para ubicar el brazo, o usa prueba manual de calibracion';mode='mosaic';out=self._mosaic(views,message)
                else:
                    image,info=composer.compose(calibrated,self.config,pose)
                    if info['valid_views']<2:message='Cambio el formato de captura; revisa la calibracion';mode='mosaic';out=self._mosaic(views,message)
                    else:
                        mode='fusion';coverage=info['coverage'];message=f'{len(calibrated)} camaras | visible {coverage:.1f}% | cuadros grises: zona oculta'
                        if pose.get('manual'):message='PRUEBA MANUAL - '+message
                        out=np.full((720,1280,3),18,np.uint8);scale=min(1240/image.shape[1],612/image.shape[0]);image=cv2.resize(image,(round(image.shape[1]*scale),round(image.shape[0]*scale)));h,w=image.shape[:2];out[58:58+h,(1280-w)//2:(1280-w)//2+w]=image
                        cv2.putText(out,'MODIX V4 - FUSION DE CAPA / PIXELES REALES',(18,34),cv2.FONT_HERSHEY_SIMPLEX,.7,(75,90,255),2,cv2.LINE_AA);self._caption(out,message)
                        visible=info.get('visible',{});self.best_camera=calibrated[max(visible,key=visible.get)][0]['index'] if visible else None
                ok,jpeg=cv2.imencode('.jpg',out,[cv2.IMWRITE_JPEG_QUALITY,82])
                if ok:
                    count+=1;now=time.monotonic()
                    if now-began>=1:self.actual_fps=count/(now-began);count=0;began=now
                    with self.condition:
                        self.frame=out;self.jpeg=jpeg.tobytes();self.sequence+=1;self.stamp=time.time();self.details={'mode':mode,'message':message,'coverage':info.get('coverage') if mode=='fusion' else None,'calibrated_live':info.get('valid_views',0),'synchronized':len(views),'skew_ms':skew,'manual':bool(pose and pose.get('manual')),'contributions':info.get('contributions',{})};self.condition.notify_all()
                self.stop_event.wait(max(.001,1/self.config['fps']-(time.monotonic()-started)))
        except Exception as error:
            message='Fusion no disponible: '+str(error)[:180];out=self._mosaic([],message);ok,jpeg=cv2.imencode('.jpg',out)
            with self.condition:
                self.details={'mode':'error','message':message,'coverage':None};self.frame=out;self.jpeg=jpeg.tobytes() if ok else None;self.sequence+=1;self.condition.notify_all()
    def status(self):
        with self.lock:
            sources=[c.status() for c in self.captures];live=sum(s['age_ms'] is not None and s['age_ms']<=self.config['max_age_ms'] for s in sources)
            return {**self.details,'running':self.running,'configured':len(self.captures),'live':live,'fps':round(self.actual_fps,1),'sources':sources}
    def primary_view(self):
        candidates=sorted(self.captures,key=lambda c:c.camera['index']!=self.best_camera)
        for capture in candidates:
            history=capture.history()
            if history and time.monotonic()-history[-1][0]<.35:
                stamp,frame=history[-1];return frame,int(stamp*1000),time.time()-(time.monotonic()-stamp)
        return None,0,0
    def stop(self):
        self.stop_event.set()
        with self.condition:self.condition.notify_all()
        if self.http:self.http.shutdown();self.http.server_close();self.http=None
        if self.http_thread:self.http_thread.join(2);self.http_thread=None
        for capture in self.captures:capture.stop_event.set()
        deadline=time.monotonic()+5
        if self.worker:self.worker.join(max(0,deadline-time.monotonic()))
        for capture in self.captures:capture.thread.join(max(0,deadline-time.monotonic()))
        alive=[c for c in self.captures if c.thread.is_alive()]
        if alive:raise RuntimeError('Una cámara sigue cerrándose; espera antes de reiniciar')
        self.captures=[];self.worker=None;self.token='';self.url='';self.frame=self.jpeg=None
        with self.lock:self.details={'mode':'stopped','message':'Multicámara detenida','coverage':None}

class OriginalVisionCamera:
    """La IA conserva una toma original; nunca analiza el relleno o el mosaico."""
    def __init__(self,engine):self.engine=engine
    def raw_snapshot(self):return self.engine.primary_view()
