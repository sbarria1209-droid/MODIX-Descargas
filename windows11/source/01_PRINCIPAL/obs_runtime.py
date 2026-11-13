"""OBS portátil aislado y entrada RTMP local; H.264 se conserva comprimido."""
import os,time,json,secrets,socket,subprocess,threading,configparser,contextlib
from pathlib import Path
from fractions import Fraction
from media10 import PacketBus

ROOT=Path(__file__).resolve().parent
PROFILES={'fluida':(1280,720,30,1800),'equilibrada':(640,360,20,650),'detalle':(1920,1080,30,3500)}
def port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

class ObsEngine:
    def __init__(self):
        self.bus=PacketBus();self.process=None;self.ingest=None;self.reader=None;self.client=None;self.stop_event=threading.Event();self.lock=threading.RLock();self.encoder='';self.profile='fluida';self.camera=None
    def status(self):
        result={**self.bus.status(),'running':bool(self.process and self.process.poll() is None),'encoder':self.encoder,'profile':self.profile,'resolution':list(PROFILES[self.profile][:2]),'lan_port':getattr(getattr(self,'lan',None),'port',None)}
        source=getattr(self,'source_status',None)
        if callable(source):result['fusion']=source()
        return result
    def _write_profile(self,encoder,width,height,fps,bitrate,rtmp):
        base=ROOT/'_obs';config=base/'config';profile=config/'obs-studio/basic/profiles/MODIX_V4';profile.mkdir(parents=True,exist_ok=True)
        (base/'portable_mode.txt').touch();(config/'obs-studio/basic/scenes').mkdir(parents=True,exist_ok=True)
        global_ini=config/'obs-studio/global.ini';app_ini=config/'obs-studio/user.ini'
        global_ini.write_text('[General]\nFirstRun=false\nLastVersion=553648384\n\n[Basic]\nProfile=MODIX V4\nProfileDir=MODIX_V4\nSceneCollection=MODIX V4\nSceneCollectionFile=MODIX_V4\n\n[BasicWindow]\nPreviewEnabled=true\n\n[OBSWebSocket]\nServerEnabled=true\n',encoding='utf-8')
        app_ini.write_text('[General]\nFirstRun=false\nLastVersion=553648384\n',encoding='utf-8')
        basic=f'[General]\nName=MODIX V4\n\n[Video]\nBaseCX={width}\nBaseCY={height}\nOutputCX={width}\nOutputCY={height}\nFPSType=0\nFPSCommon={fps}\nColorFormat=NV12\nColorSpace=709\nColorRange=Partial\n\n[Output]\nMode=Advanced\n\n[AdvOut]\nEncoder={encoder}\nAudioEncoder=ffmpeg_aac\nTrackIndex=1\nApplyServiceSettings=false\nRescale=false\n'
        (profile/'basic.ini').write_text(basic,encoding='utf-8')
        settings={'bitrate':bitrate,'target_bitrate':bitrate,'keyint_sec':1,'rate_control':'CBR','profile':'baseline','preset':'veryfast','tune':'zerolatency','latency':'ultra-low','bf':0,'bframes':0,'repeat_headers':True,'x264opts':'bframes=0 repeat-headers=1 scenecut=0'}
        (profile/'streamEncoder.json').write_text(json.dumps(settings),encoding='utf-8')
        (profile/'service.json').write_text(json.dumps({'type':'rtmp_custom','settings':{'server':rtmp,'key':'modix','use_auth':False}}),encoding='utf-8')
        scenes=config/'obs-studio/basic/scenes/MODIX_V4.json'
        # This collection belongs exclusively to MODIX, never the user's OBS profile.
        scenes.write_text(json.dumps({'name':'MODIX V4','current_scene':'MODIX CAM','current_program_scene':'MODIX CAM','scene_order':[{'name':'MODIX CAM'}],'sources':[{'name':'MODIX CAM','id':'scene','versioned_id':'scene','settings':{'items':[]},'mixers':0,'enabled':True,'muted':False}]}),encoding='utf-8')
        plugins=config/'obs-studio/plugin_config/obs-websocket';plugins.mkdir(parents=True,exist_ok=True)
        (plugins/'config.json').write_text(json.dumps({'server_enabled':True,'server_port':self.ws_port,'auth_required':True,'server_password':self.ws_password,'alerts_enabled':False,'first_load':False}),encoding='utf-8')
    def _hardware_encoder(self):
        try:
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
            result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command','(Get-CimInstance Win32_VideoController).Name -join ";"'],capture_output=True,text=True,timeout=6,creationflags=flags)
            names=result.stdout.lower()
            if 'nvidia' in names:return 'obs_nvenc_h264_tex'
            if 'intel' in names:return 'obs_qsv11_v2'
            if 'radeon' in names or 'amd' in names:return 'h264_texture_amf'
        except Exception:pass
        return 'obs_x264'
    def start(self,camera,index=0,name='',profile='fluida',test_image=None,software=False,source_url=None,source_status=None):
        with self.lock:
            if self.process and self.process.poll() is None:return self.status()
            self.camera=camera;self.source_status=source_status;self.profile=profile if profile in PROFILES else 'fluida';self.stop_event=threading.Event();self.bus.error='Preparando OBS…';self.bus.last=0;self.bus.running=True
        obs=ROOT/'_obs/bin/64bit/obs64.exe'
        if not obs.exists():self.bus.running=False;raise RuntimeError('Falta el motor OBS incluido con MODIX 10. Reinstala la principal completa.')
        camera.start_external(self.profile);width,height,fps,bitrate=PROFILES[self.profile];self.ws_port=port();self.ws_password=secrets.token_urlsafe(32);rtmp_port=port();rtmp=f'rtmp://127.0.0.1:{rtmp_port}/live'
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        import imageio_ffmpeg
        log_dir=Path(os.environ.get('MODIX_DATA_DIR',str(Path(os.environ.get('LOCALAPPDATA',ROOT))/'MODIX_6')))/'obs';log_dir.mkdir(parents=True,exist_ok=True)
        self._log=(log_dir/'entrada.log').open('w',encoding='utf-8')
        args=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','warning','-listen','1','-i',rtmp+'/modix','-map','0:v:0','-an','-c:v','copy','-bsf:v','h264_mp4toannexb','-f','mpegts','-mpegts_flags','resend_headers','-muxdelay','0','-flush_packets','1','pipe:1']
        self.ingest=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=self._log,creationflags=flags,bufsize=0)
        self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()
        chosen='obs_x264' if software else self._hardware_encoder()
        try:
            for encoder in dict.fromkeys((chosen,'obs_x264')):
                if self.stop_event.is_set():raise RuntimeError('Inicio de OBS cancelado')
                self.encoder=encoder;self._write_profile(encoder,width,height,fps,bitrate,rtmp)
                self.process=subprocess.Popen([str(obs),'--portable','--multi','--profile','MODIX V4','--collection','MODIX V4','--minimize-to-tray','--disable-updater','--disable-shutdown-check','--websocket_port',str(self.ws_port),'--websocket_password',self.ws_password,'--websocket_ipv4_only'],cwd=obs.parent,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
                import obsws_python as obsws
                import logging
                logging.getLogger('obsws_python').setLevel(logging.CRITICAL)
                deadline=time.monotonic()+40;self.client=None
                while time.monotonic()<deadline and not self.stop_event.is_set():
                    if self.process.poll() is not None:break
                    candidate=None
                    try:
                        candidate=obsws.ReqClient(host='127.0.0.1',port=self.ws_port,password=self.ws_password,timeout=3);candidate.get_version();self.client=candidate;break
                    except Exception:
                        if candidate:
                            with contextlib.suppress(Exception):candidate.disconnect()
                        self.stop_event.wait(.3)
                if not self.client:raise RuntimeError('OBS no inició su conexión local. Revisa el aviso de OBS o reinstala la principal.')
                self.client.set_video_settings(fps,1,width,height,width,height)
                self.client.set_stream_service_settings('rtmp_custom',{'server':rtmp,'key':'modix','use_auth':False})
                self._source(index,name,width,height,test_image,source_url)
                try:
                    self.client.start_stream();break
                except Exception:
                    if encoder=='obs_x264':raise
                    self._close_obs();self.stop_event.wait(.3)
            deadline=time.monotonic()+(8 if encoder!='obs_x264' else 18)
            while time.monotonic()<deadline and not self.bus.active() and not self.stop_event.is_set():self.stop_event.wait(.1)
            if not self.bus.active() and encoder!='obs_x264' and not self.stop_event.is_set():
                self.stop()
                return self.start(camera,index,name,profile,test_image,True,source_url,source_status)
            if not self.bus.active():raise RuntimeError('OBS inició, pero no entregó imagen. Comprueba la cámara USB en la ventana de OBS.')
            from lan_video import LanVideo
            self.lan=LanVideo(self.bus);self.lan.start();self.bus.error='';return self.status()
        except Exception:
            self.stop();raise
    def _source(self,index,name,width,height,test_image,source_url=None):
        client=self.client
        if source_url:
            from urllib.parse import urlsplit
            u=urlsplit(source_url)
            if u.scheme!='http' or u.hostname!='127.0.0.1':raise ValueError('La fuente de fusión debe ser local')
            client.create_input('MODIX CAM','MODIX Fusion','ffmpeg_source',{'is_local_file':False,'input':source_url,'input_format':'mpjpeg','ffmpeg_options':'fflags=nobuffer flags=low_delay','restart_on_activate':True,'clear_on_media_end':True,'close_when_inactive':False,'buffering_mb':1,'hw_decode':False},True);input_name='MODIX Fusion'
        elif test_image:
            browser=Path(test_image).suffix.lower()=='.html';kind='browser_source' if browser else 'image_source';settings={'is_local_file':True,'local_file':str(test_image),'width':width,'height':height,'fps':30,'shutdown':False} if browser else {'file':str(test_image)}
            client.create_input('MODIX CAM','MODIX prueba',kind,settings,True);input_name='MODIX prueba'
        else:
            client.create_input('MODIX CAM','MODIX USB','dshow_input',{},True);input_name='MODIX USB'
            choices=client.get_input_properties_list_property_items(input_name,'video_device_id').property_items
            choices=[c for c in choices if c.get('itemEnabled',True) and c.get('itemValue')]
            if not choices:raise RuntimeError('OBS no encuentra cámaras USB. Conecta la cámara y vuelve a activar.')
            match=next((c for c in choices if c.get('itemName','').casefold()==name.casefold()),None) or choices[min(max(0,index),len(choices)-1)]
            client.set_input_settings(input_name,{'video_device_id':match['itemValue'],'last_video_device_id':match['itemValue'],'resolution_type':0,'deactivate_when_not_showing':False},True)
        client.set_current_program_scene('MODIX CAM')
        items=client.get_scene_item_list('MODIX CAM').scene_items
        item=next(i for i in items if i['sourceName']==input_name)
        client.set_scene_item_transform('MODIX CAM',item['sceneItemId'],{'boundsType':'OBS_BOUNDS_SCALE_INNER','boundsWidth':width,'boundsHeight':height,'positionX':0.0,'positionY':0.0})
    def _read(self):
        import av
        preview=None;count=0;start=time.monotonic();last_preview=0
        try:
            preview=av.CodecContext.create('h264','r')
            with av.open(self.ingest.stdout,format='mpegts',options={'probesize':'32768','analyzeduration':'0'},buffer_size=4096) as container:
                for packet in container.demux(video=0):
                    if self.stop_event.is_set():break
                    if not packet.size or packet.pts is None:continue
                    payload=bytes(packet);pts=int(packet.pts*packet.time_base*90000);self.bus.publish(payload,pts,packet.is_keyframe);count+=1;now=time.monotonic()
                    if now-start>=1:self.bus.fps=round(count/(now-start),1);count=0;start=now
                    try:frames=preview.decode(packet)
                    except av.FFmpegError:
                        preview=av.CodecContext.create('h264','r');continue
                    for frame in frames:
                        if now-last_preview>=1/15:
                            self.camera.external_frame(frame.to_ndarray(format='bgr24'),self.bus.fps);last_preview=now
        except Exception as error:
            if not self.stop_event.is_set():self.bus.error='OBS: entrada de vídeo interrumpida ('+type(error).__name__+')'
        finally:self.bus.running=False
    def _close_obs(self):
        if self.client:
            with contextlib.suppress(Exception):self.client.stop_stream()
            with contextlib.suppress(Exception):self.client.disconnect()
            self.client=None
        if self.process and self.process.poll() is None:
            self.process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):self.process.wait(5)
        self.process=None
    def stop(self):
        self.stop_event.set();self.bus.running=False;self._close_obs()
        if getattr(self,'lan',None):self.lan.stop();self.lan=None
        if self.ingest and self.ingest.poll() is None:
            self.ingest.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):self.ingest.wait(3)
        if self.reader and self.reader is not threading.current_thread():self.reader.join(3)
        if hasattr(self,'_log') and self._log:self._log.close();self._log=None
        self.ingest=None;self.reader=None
        if self.camera:self.camera.stop()
ENGINE=ObsEngine()
