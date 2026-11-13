"""Cámaras USB independientes con memoria y sincronización acotadas."""
import os,time,threading,hashlib,contextlib
from collections import deque
import cv2

MAX_CAMERAS=8
def devices():
    initialized=False
    try:
        if os.name=='nt':
            import comtypes
            comtypes.CoInitialize();initialized=True
        return _devices()
    finally:
        if initialized:comtypes.CoUninitialize()

def _devices():
    result=[]
    if os.name=='nt':
        try:
            import comtypes
            from comtypes import GUID
            from comtypes.persist import IPropertyBag
            from pygrabber.dshow_graph import SystemDeviceEnum,DeviceCategories
            enumerator=SystemDeviceEnum().system_device_enum.CreateClassEnumerator(GUID(DeviceCategories.VideoInputDevice),dwFlags=0);index=0
            while True:
                try:moniker,count=enumerator.Next(1)
                except ValueError:break
                if not count:break
                bag=moniker.BindToStorage(0,0,IPropertyBag._iid_).QueryInterface(IPropertyBag);name=str(bag.Read('FriendlyName',pErrorLog=None))
                try:identity=str(bag.Read('DevicePath',pErrorLog=None))
                except Exception:identity=name+'#'+str(index)
                result.append({'index':index,'name':name,'uid':hashlib.sha256(identity.encode()).hexdigest()[:32]});index+=1
            return result
        except Exception:pass
    try:
        from pygrabber.dshow_graph import FilterGraph
        names=FilterGraph().get_input_devices()
        return [{'index':i,'name':n,'uid':hashlib.sha256((n+'#'+str(i)).encode()).hexdigest()[:32]} for i,n in enumerate(names)]
    except Exception:return result

class Capture:
    def __init__(self,camera,width=640,height=480,fps=30):
        capture=camera.get('capture') or {};self.camera=camera;self.width=capture.get('width',width);self.height=capture.get('height',height);self.fps_target=capture.get('fps',fps);self.lock=threading.RLock();self.frames=deque(maxlen=8);self.stop_event=threading.Event();self.thread=threading.Thread(target=self.run,daemon=True);self.error='Abriendo cámara';self.fps=0.;self.running=False
    def start(self):self.thread.start()
    def history(self):
        with self.lock:return list(self.frames)
    def status(self):
        with self.lock:
            stamp=self.frames[-1][0] if self.frames else None
            return {'index':self.camera['index'],'name':self.camera.get('name','Cámara'),'fps':round(self.fps,1),'age_ms':round((time.monotonic()-stamp)*1000) if stamp is not None else None,'error':self.error,'running':self.running}
    def run(self):
        cap=None
        try:
            if self.camera.get('binding_error'):self.error=self.camera['binding_error'];return
            while not self.stop_event.is_set():
                cap=cv2.VideoCapture(int(self.camera['index']),cv2.CAP_DSHOW if os.name=='nt' else cv2.CAP_ANY)
                if not cap.isOpened():
                    cap.release();cap=cv2.VideoCapture(int(self.camera['index']))
                if not cap.isOpened():
                    self.error='No abre: comprueba USB y que otra app no la esté usando';cap.release();cap=None;self.stop_event.wait(2);continue
                cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'));cap.set(cv2.CAP_PROP_FRAME_WIDTH,self.width);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,self.height);cap.set(cv2.CAP_PROP_FPS,self.fps_target);cap.set(cv2.CAP_PROP_BUFFERSIZE,1);self.running=True;count=0;began=time.monotonic()
                while not self.stop_event.is_set():
                    started=time.monotonic();ok,frame=cap.read();stamp=time.monotonic()
                    if not ok:self.error='Sin imagen; reconectando';break
                    with self.lock:self.frames.append((stamp,frame));self.error=''
                    count+=1
                    if stamp-began>=1:self.fps=count/(stamp-began);began=stamp;count=0
                    if stamp-started<.002:self.stop_event.wait(.002)
                cap.release();cap=None;self.running=False;self.stop_event.wait(.5)
        except Exception as error:self.error='Cámara: '+type(error).__name__
        finally:
            if cap:cap.release()
            self.running=False
    def stop(self):
        self.stop_event.set();self.thread.join(4)
        if self.thread.is_alive():raise RuntimeError('La cámara '+str(self.camera['index'])+' sigue cerrándose; espera antes de volver a activarla')
        with self.lock:self.frames.clear()

def synchronized(captures,max_age=.35,tolerance=.10,now=None):
    now=time.monotonic() if now is None else now;histories=[]
    for capture in captures:
        frames=[(stamp,frame) for stamp,frame in capture.history() if 0<=now-stamp<=max_age]
        if frames:histories.append((capture,frames))
    anchors=sorted({frames[-1][0] for _,frames in histories},reverse=True);best=[];best_anchor=0
    for anchor in anchors:
        chosen=[]
        for capture,frames in histories:
            window=[f for f in frames if anchor-tolerance<=f[0]<=anchor]
            if window:
                stamp,frame=window[-1];chosen.append((capture.camera,frame,stamp))
        if len(chosen)>len(best):best=chosen;best_anchor=anchor
    stamps=[v[2] for v in best]
    return best,round((max(stamps)-min(stamps))*1000,1) if stamps else None
