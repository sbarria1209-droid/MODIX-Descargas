"""Integración de fusión USB con OBS y supervisión existente."""
import os,time,contextlib
from PyQt5 import QtCore as C,QtWidgets as W
import server
from multicam_engine import FusionEngine,OriginalVisionCamera,load_config
from multicam_panel import MultiCameraDialog

def upgrade(Base):
    class Main(Base):
        def __init__(self):
            self.fusion=FusionEngine(server.DATA/'multicam11.json',server.CFG['plate']);self.fusion_dialog=None;self._fusion_stopping=False
            super().__init__();self.setWindowTitle('MODIX BIGMETER V4 · Control Center 11 · Multicámara')
            if not os.environ.get('MODIX_AUTOTEST') and not self.cfg.contains('video_source11'):
                self.camera_quality.blockSignals(True);self.camera_quality.setCurrentIndex(max(0,self.camera_quality.findData('equilibrada')));self.camera_quality.blockSignals(False)
            self.camera_source.blockSignals(True);self.camera_source.addItem('Fusión de 2–8 cámaras · un vídeo','fusion');saved='usb' if os.environ.get('MODIX_AUTOTEST') else self.cfg.value('video_source11','fusion');self.camera_source.setCurrentIndex(max(0,self.camera_source.findData(saved)));self.camera_source.blockSignals(False)
            self.configure_fusion_button=W.QPushButton('Cámaras…');self.configure_fusion_button.setToolTip('Configurar y calibrar de dos a ocho cámaras');self.configure_fusion_button.clicked.connect(self.configure_fusion)
            layout=self.video.parentWidget().layout();row=layout.itemAt(2).layout()
            if row:row.addWidget(self.configure_fusion_button)
            else:layout.insertWidget(3,self.configure_fusion_button)
            self.camera_source.setMinimumWidth(0);self.camera_source.setSizePolicy(W.QSizePolicy.Ignored,W.QSizePolicy.Fixed);self._source_labels()
        def _source_labels(self):
            if not hasattr(self,'camera_source'):return
            fusion=self.camera_source.currentData()=='fusion'
            if fusion:
                from obs_runtime import PROFILES
                for i in range(self.camera_quality.count()):
                    p=PROFILES[self.camera_quality.itemData(i)];self.camera_quality.setItemText(i,f'OBS · salida {p[0]} × {p[1]} · {p[2]} FPS')
            else:super()._source_labels()
            self.cam_sel.setEnabled(not fusion)
            if hasattr(self,'configure_fusion_button'):self.configure_fusion_button.setVisible(fusion)
        def _obs_buttons(self,enabled):
            super()._obs_buttons(enabled)
            if hasattr(self,'configure_fusion_button'):self.configure_fusion_button.setEnabled(enabled)
            if self.camera_source.currentData()=='fusion':self.cam_sel.setEnabled(False)
        def change_camera_source(self):
            if hasattr(self,'camera_source'):self.cfg.setValue('video_source11',self.camera_source.currentData())
            return super().change_camera_source()
        def configure_fusion(self):
            if self._obs_starting:return
            if self.obs_engine.status()['running']:self.obs_engine.stop()
            if self.fusion.running:
                try:self.fusion.stop()
                except Exception as error:self.msg(str(error));return
            dialog=MultiCameraDialog(self,self.fusion);self.fusion_dialog=dialog;result=dialog.exec_();self.fusion_dialog=None
            if result==W.QDialog.Accepted:self.fusion.config=load_config(self.fusion.path,server.CFG['plate']);self.msg('Configuración multicámara guardada. Pulsa Activar para enviar un único vídeo.')
            dialog.deleteLater()
        def start_cam(self):
            if not hasattr(self,'camera_source') or self.camera_source.currentData()!='fusion':return super().start_cam()
            if self._obs_starting:return
            self._obs_starting=True;self._obs_buttons(False);profile=self.camera_quality.currentData();self.cfg.setValue('video_source11','fusion');self.msg('Abriendo cámaras y preparando un único vídeo…')
            def task():
                self.obs_engine.stop();self.fusion.start(require_two=True)
                try:return self.obs_engine.start(server.CAMERA,profile=profile,source_url=self.fusion.url,source_status=self.fusion.status)
                except Exception:self.fusion.stop();raise
            def done(result,error):
                self._obs_starting=False;self._obs_buttons(True);self._render_sequence=-1
                if self.vision:self.vision.camera=OriginalVisionCamera(self.fusion) if not error else server.CAMERA;self.vision.roi=None
                self.msg(str(error) if error else 'Multicámara activa. Calibra al menos dos vistas para compensar el brazo; las zonas no visibles se marcan en gris.')
            self.run_bg(task,done)
        def stop_cam(self):
            if self._obs_starting:return
            if self.fusion.running or self.fusion.captures:
                self._obs_starting=True;self._fusion_stopping=True;self._obs_buttons(False)
                def task():self.obs_engine.stop();self.fusion.stop()
                def done(result,error):
                    self._obs_starting=False;self._fusion_stopping=False;self._obs_buttons(True)
                    if self.vision:self.vision.camera=server.CAMERA;self.vision.roi=None
                    self.msg(str(error) if error else 'Multicámara detenida')
                self.run_bg(task,done);return
            return super().stop_cam()
        def change_camera_quality(self):
            if hasattr(self,'camera_source') and self.camera_source.currentData()=='fusion':
                self.cfg.setValue('camera_profile',self.camera_quality.currentData())
                if self.obs_engine.status()['running']:self.start_cam()
                return
            return super().change_camera_quality()
        def on_poll(self,data):
            result=super().on_poll(data);axes=((data.get('live') or {}).get('move') or {}).get('axes') or [];values={a.get('letter'):a.get('machinePosition',a.get('userPosition')) for a in axes if isinstance(a,dict)}
            transport=data.get('transport') or {}
            if transport.get('state','online')=='online' and float(transport.get('age') or 0)<1.2 and all(isinstance(values.get(k),(int,float)) for k in 'XYZ'):self.fusion.set_pose([values[k] for k in 'XYZ'])
            return result
        def update_obs_status(self):
            super().update_obs_status()
            if hasattr(self,'camera_source') and self.camera_source.currentData()=='fusion' and not self._obs_starting:
                info=self.fusion.status();coverage=info.get('coverage');self.obs_status.setText(f"Fusión {info['fps']:.1f} FPS · cámaras {info['live']}/{info['configured']}"+(f' · visible {coverage:.1f}%' if coverage is not None else '')+' · '+info['message'])
        def set_visual_region(self,region):
            if hasattr(self,'camera_source') and self.camera_source.currentData()=='fusion':
                if self.vision:self.vision.roi=None
                self.msg('En multicámara, la IA usa una toma original actual; no interpreta el relleno ni las máscaras de la fusión.');return
            return super().set_visual_region(region)
        def closeEvent(self,event):
            if self.fusion_dialog and self.fusion_dialog.busy:self.fusion_dialog.closed=True;event.ignore();C.QTimer.singleShot(500,self.close);return
            if self._obs_starting:
                self.obs_engine.stop_event.set();self.fusion.stop_event.set();event.ignore();C.QTimer.singleShot(500,self.close);return
            with contextlib.suppress(Exception):self.fusion.stop()
            return super().closeEvent(event)
    return Main
