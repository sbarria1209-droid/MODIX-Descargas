"""MODIX 6: aplicación de escritorio con el monitor 3D y la cámara del original."""
from __future__ import annotations
import sys,os,json,time,math,argparse,traceback
if os.environ.get('MODIX_DIAGNOSTIC'):
    import faulthandler
    _diagnostic_file=open(os.environ['MODIX_DIAGNOSTIC'],'w',encoding='utf-8')
    faulthandler.enable(file=_diagnostic_file)
    faulthandler.dump_traceback_later(20,repeat=True,file=_diagnostic_file)
from pathlib import Path
import numpy as np
from PyQt5 import QtWidgets as W,QtCore as C,QtGui as G
import pyqtgraph.opengl as gl
from pyqtgraph import Vector
import native_monitor as n
import server
from modix_core import normalize_status,DuetClient
from ui_theme import apply_theme,button,label,card
from workflow import Preparation,Slicing

class Main(n.Main):
    def __init__(self):
        self._transport_ok=False;self._fetch_pending=False;self._auto_fetched=None;self._closing=False;self._revision=None
        super().__init__();self.setWindowTitle('MODIX 6 · Principal · Cámara USB + impresión por capas');self.resize(1600,1000)
        self.setWindowIcon(G.QIcon(str(Path(__file__).with_name('modix.ico'))));self.t_cam.setInterval(125)
        self._camera_timer=C.QTimer(self);self._camera_timer.timeout.connect(self.frame);self._camera_timer.start(180)
        self.statusBar().showMessage('Estación principal de escritorio · Cámara y modelo en esta ventana')
        self.update_metrics()
        if not os.environ.get('MODIX_AUTOTEST') and self.cfg.value('usb_auto','false')=='true':C.QTimer.singleShot(600,self.start_cam)
    def _build_ui(self):
        self.ip=W.QLineEdit(self.cfg.value('ip',''));self.ip.setPlaceholderText('IP del Duet · 192.168.1.50');self.ip.setMinimumWidth(190)
        self.pw=W.QLineEdit();self.pw.setEchoMode(W.QLineEdit.Password);self.pw.setPlaceholderText('Contraseña Duet');self.pw.setMaximumWidth(160)
        self.b_con=button('Conectar',self.toggle_connect,True);self.status=label('Sin conexión Duet','muted');self.status.setWordWrap(True)
        self.banner=label('');self.banner.setWordWrap(True);self.banner.hide();self.banner.mousePressEvent=lambda e:self.banner.hide()
        self.auto_download=W.QCheckBox('Cargar G-code activo automáticamente');self.auto_download.setChecked(True)
        root=W.QWidget();outer=W.QHBoxLayout(root);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        side=W.QFrame();side.setObjectName('sidebar');side.setFixedWidth(205);sl=W.QVBoxLayout(side);sl.setContentsMargins(17,24,17,20)
        sl.addWidget(label('MODIX','brand'));sl.addWidget(label('CONTROL CENTER 7','section'));sl.addSpacing(32)
        self.pages=W.QStackedWidget();self.nav_buttons=[];self.nav_group=W.QButtonGroup(self)
        for i,text in enumerate(['◉  Monitor en vivo','▱  Preparar placa','▤  Laminar','▦  Mapa de cama','⚙  Configuración']):
            b=button(text);b.setCheckable(True);b.setProperty('nav',True);self.nav_group.addButton(b,i);self.nav_buttons.append(b);sl.addWidget(b);b.clicked.connect(lambda checked=False,k=i:self.pages.setCurrentIndex(k))
        self.nav_buttons[0].setChecked(True);sl.addStretch(1);sl.addWidget(label('PRINCIPAL\nCámara USB + monitor 3D\nInterfaz de escritorio','muted'));outer.addWidget(side)
        content=W.QWidget();v=W.QVBoxLayout(content);v.setContentsMargins(23,18,23,16);v.setSpacing(12);outer.addWidget(content,1)
        header=W.QHBoxLayout();header.addWidget(label('Centro de control de impresión','title'));header.addStretch();header.addWidget(label('●  ESTACIÓN PRINCIPAL','section'));v.addLayout(header)
        connect=W.QHBoxLayout();connect.addWidget(self.ip,1);connect.addWidget(self.pw);connect.addWidget(self.b_con);connect.addWidget(self.auto_download);connect.addWidget(button('Abrir G-code',self.open_gcode));connect.addWidget(button('Traer trabajo',self.fetch_job));v.addLayout(connect);v.addWidget(self.banner)
        self.metric_labels={};metrics=W.QHBoxLayout()
        for key,title in [('state','ESTADO DE LA MÁQUINA'),('layer','CAPA EN CURSO'),('progress','AVANCE DEL ARCHIVO'),('tool','HERRAMIENTA ACTIVA')]:
            box=card();bv=W.QVBoxLayout(box);bv.setContentsMargins(16,11,16,11);bv.addWidget(label(title,'metricCaption'));value=label('—','metric');bv.addWidget(value);self.metric_labels[key]=value;metrics.addWidget(box)
        v.addLayout(metrics);v.addWidget(self.pages,1);v.addWidget(self.status)
        self.view=gl.GLViewWidget();self.view.setBackgroundColor((19,14,22));self.grid=gl.GLGridItem();self.grid.setSize(980,1000);self.grid.setSpacing(100,100);self.grid.translate(490,500,0);self.view.addItem(self.grid);self.view.opts['center']=Vector(490,500,0);self.view.setCameraPosition(distance=1500,elevation=38,azimuth=-55)
        self.item_ghost=gl.GLLinePlotItem(mode='lines',width=1,antialias=False,glOptions='translucent');self.item_done=gl.GLLinePlotItem(mode='lines',width=1,antialias=False);self.item_cur=gl.GLLinePlotItem(mode='lines',width=3,antialias=True)
        self.noz_real=gl.GLScatterPlotItem(size=14,color=(1,.12,.28,1),pxMode=True);self.noz_file=gl.GLScatterPlotItem(size=9,color=(1,.8,.3,1),pxMode=True);self.noz_body=gl.GLLinePlotItem(mode='lines',width=3,color=(1,.3,.4,.9))
        for item in (self.item_ghost,self.item_done,self.item_cur,self.noz_body,self.noz_real,self.noz_file):self.view.addItem(item)
        self.mode=W.QComboBox();self.mode.addItems(['En vivo · hasta la línea procesada','Modelo completo','Manual · por capa']);self.mode.setCurrentIndex(int(self.cfg.value('mode',0)));self.mode.currentIndexChanged.connect(self.on_mode)
        self.colmode=W.QComboBox();self.colmode.addItems(['Color por capa','Color por altura','Color por herramienta']);self.colmode.currentIndexChanged.connect(self.recolor)
        self.ghost=W.QCheckBox('Pendiente en gris');self.ghost.setChecked(True);self.ghost.toggled.connect(self.redraw);self.hilite=W.QCheckBox('Resaltar capa');self.hilite.setChecked(True);self.hilite.toggled.connect(self.redraw)
        self.slider=W.QSlider(C.Qt.Horizontal);self.slider.valueChanged.connect(self.on_slider);self.line_lbl=label('Carga el G-code para ver las capas y la línea actual.','muted');self.line_lbl.setWordWrap(True)
        left=card();lv=W.QVBoxLayout(left);lv.addWidget(label('MODELO 3D · AVANCE POR CAPAS','section'));lv.addWidget(self.view,1);lv.addWidget(label('Arrastra para girar · Rueda para acercar o alejar','muted'));row=W.QHBoxLayout();row.addWidget(self.mode,2);row.addWidget(self.colmode);lv.addLayout(row);row=W.QHBoxLayout();row.addWidget(self.ghost);row.addWidget(self.hilite);row.addStretch();lv.addLayout(row);lv.addWidget(self.slider);lv.addWidget(self.line_lbl)
        self.noz=label('Conecta el Duet para recibir posiciones y temperaturas.');self.noz.setWordWrap(True);self.noz.setTextFormat(C.Qt.RichText)
        self.cam_sel=W.QComboBox();self.fill_cams();self.cam_sel.setMinimumWidth(120)
        saved=self.cfg.value('cam_index',0,type=int);idx=self.cam_sel.findData(saved)
        if idx>=0:self.cam_sel.setCurrentIndex(idx)
        self.video=label('CÁMARA USB DE ESTA PC\n\nSelecciona la cámara y pulsa Activar.');self.video.setAlignment(C.Qt.AlignCenter);self.video.setMinimumSize(300,200);self.video.setSizePolicy(W.QSizePolicy.Ignored,W.QSizePolicy.Ignored);self.video.setStyleSheet('background:#0b090e;color:#b998a8;border:1px solid #503043;border-radius:8px')
        cam=card();cv=W.QVBoxLayout(cam);cv.addWidget(label('CÁMARA USB EN DIRECTO','section'));row=W.QHBoxLayout();row.addWidget(self.cam_sel,1);row.addWidget(button('↻',self.fill_cams));row.addWidget(button('Activar',self.start_cam,True));row.addWidget(button('Detener',self.stop_cam));cv.addLayout(row);cv.addWidget(self.video,1)
        self.tabs=W.QTabWidget();self.code=W.QPlainTextEdit();self.code.setReadOnly(True);self.code.setLineWrapMode(W.QPlainTextEdit.NoWrap);self.code.setFont(G.QFont('Consolas',10));self.tabs.addTab(self.code,'G-code');self.tabs.addTab(self._events_tab(),'Eventos');self.tabs.addTab(self._remote_tab(),'Segunda PC')
        right=W.QWidget();rv=W.QVBoxLayout(right);rv.setContentsMargins(0,0,0,0);rv.addWidget(self.noz);rsp=W.QSplitter(C.Qt.Vertical);rsp.addWidget(cam);rsp.addWidget(self.tabs);rsp.setSizes([380,210]);rv.addWidget(rsp,1)
        split=W.QSplitter();split.addWidget(left);split.addWidget(right);split.setStretchFactor(0,3);split.setStretchFactor(1,2);split.setSizes([820,550])
        monitor=W.QWidget();mv=W.QVBoxLayout(monitor);mv.setContentsMargins(0,0,0,0);mv.addWidget(split,1)
        actions=W.QHBoxLayout()
        for text,kind in [('Pausar','pause'),('Reanudar','resume'),('Cancelar','cancel')]:actions.addWidget(button(text,lambda checked=False,a=kind:self.machine_action(a),kind=='pause'))
        actions.addWidget(button('Subir G-code',self.upload_only));actions.addWidget(button('Subir e iniciar…',lambda:self.upload(self.path)));actions.addStretch();mv.addLayout(actions)
        self.pages.addWidget(monitor);self.preparation=Preparation(self);self.pages.addWidget(self.preparation);self.slicing=Slicing(self);self.pages.addWidget(self.slicing);self.pages.addWidget(self.bed_page());self.pages.addWidget(self.settings_page())
        self.setCentralWidget(root)
    def _events_tab(self):
        w=super()._events_tab();v=w.layout();old=v.takeAt(0).layout();controls=[]
        self.auto_fil.setText('Reanudar si falta filamento')
        for item in w.findChildren(W.QLabel):
            text=item.text()
            if 'Cancelar la impresión en el error' in text:item.setText('Cancelar en el error')
            elif 'seguido en la misma boquilla' in text:item.setText('Seguidos · Espera')
        for b in w.findChildren(W.QPushButton):
            if b.text()=='Reanudar con resurrect.g (M916)':b.setText('Reanudar con M916')
            elif b.text()=='Abrir carpeta de registros':b.setText('Abrir registros')
        while old.count():
            item=old.takeAt(0)
            if item.widget():controls.append(item.widget())
        grid=W.QGridLayout()
        for i,widget in enumerate(controls):grid.addWidget(widget,i//3,i%3)
        v.insertLayout(0,grid)
        # Put the four recovery actions into two rows so they fit beside the live camera.
        old=v.takeAt(v.count()-1).layout();grid=W.QGridLayout();i=0
        while old.count():
            item=old.takeAt(0)
            if item.widget():grid.addWidget(item.widget(),i//2,i%2);i+=1
        v.addLayout(grid);return w
    def _remote_tab(self):
        w=W.QWidget();v=W.QVBoxLayout(w);v.addWidget(label('Cliente de escritorio de la otra PC','section'));tip=label('Pulsa Compartir, copia el enlace y pégalo en MODIX_Cliente.exe. Comparte la cámara USB y el seguimiento por capas.','muted');tip.setWordWrap(True);v.addWidget(tip)
        self.b_srv=button('Compartir en la red',self.toggle_server,True);v.addWidget(self.b_srv);self.remote_link=W.QLineEdit();self.remote_link.setReadOnly(True);v.addWidget(self.remote_link);v.addWidget(button('Copiar enlace',lambda:W.QApplication.clipboard().setText(self.remote_link.text())));self.srv_lbl=label('Acceso cerrado','muted');self.srv_lbl.setWordWrap(True);v.addWidget(self.srv_lbl);v.addStretch();return w
    def bed_page(self):
        w=W.QWidget();v=W.QVBoxLayout(w);v.addWidget(label('Mapa real y compensación visual de la cama','title'));v.addWidget(label('La superficie medida se muestra junto al modelo 3D. La exageración es solo visual.','muted'))
        row=W.QHBoxLayout();row.addWidget(button('Obtener heightmap de Duet',self.fetch_heightmap,True));row.addWidget(button('Abrir heightmap.csv',self.open_heightmap));v.addLayout(row)
        self.show_bed=W.QCheckBox('Mostrar cama medida en el monitor');self.show_bed.setChecked(True);self.show_bed.toggled.connect(self.apply_heightmap);v.addWidget(self.show_bed)
        self.deform=W.QCheckBox('Deformar modelo según el mapa');self.deform.setChecked(True);self.deform.toggled.connect(self.apply_heightmap);v.addWidget(self.deform)
        self.exag=W.QDoubleSpinBox();self.exag.setRange(1,500);self.exag.setValue(float(self.cfg.value('exag',20)));self.exag.setPrefix('Exageración × ');self.exag.editingFinished.connect(self.apply_heightmap);v.addWidget(self.exag);self.hm_lbl=label('Sin heightmap','muted');v.addWidget(self.hm_lbl);self.bed_preview=label('El mapa y su deformación aparecerán en el monitor 3D.');self.bed_preview.setAlignment(C.Qt.AlignCenter);v.addWidget(self.bed_preview,1);return w
    def settings_page(self):
        w=W.QWidget();v=W.QVBoxLayout(w);v.addWidget(label('Configuración de la estación','title'));form=W.QFormLayout();v.addLayout(form);self.plate_fields=[]
        for i,k in enumerate('XYZ'):
            s=W.QDoubleSpinBox();s.setRange(1,5000);s.setValue(server.CFG['plate'][i]);self.plate_fields.append(s);form.addRow(f'Volumen {k} (mm)',s)
        self.usb_auto=W.QCheckBox('Activar la cámara USB seleccionada al abrir la principal');self.usb_auto.setChecked(self.cfg.value('usb_auto','false')=='true');form.addRow(self.usb_auto)
        form.addRow(button('Guardar configuración',self.save_native_settings,True));form.addRow(button('Abrir registros',self.open_logs))
        group=W.QGroupBox('Ajustes manuales de impresión');f=W.QFormLayout(group);self.tune_fields={}
        for kind,text,low,high,val in [('speed','Velocidad (%)',25,150,100),('flow','Flujo (%)',60,140,100),('fan','Ventilador (%)',0,100,100),('nozzle_temp','Herramienta activa (°C)',0,290,200)]:
            row=W.QHBoxLayout();spin=W.QSpinBox();spin.setRange(low,high);spin.setValue(val);self.tune_fields[kind]=spin;row.addWidget(spin);row.addWidget(button('Aplicar',lambda checked=False,k=kind:self.tune(k)));f.addRow(text,row)
        v.addWidget(group);v.addStretch();return w
    def save_native_settings(self):
        try:server.changed_settings({'plate':[s.value() for s in self.plate_fields]});self.cfg.setValue('usb_auto','true' if self.usb_auto.isChecked() else 'false');self.cfg.setValue('cam_index',self.cam_sel.currentData());self.msg('Configuración guardada');self.preparation.refresh()
        except Exception as e:self.msg(str(e))
    def start_cam(self):
        index=self.cam_sel.currentData()
        if not isinstance(index,int):self.msg('Selecciona una cámara USB');return
        try:server.CAMERA.start(index);self.cfg.setValue('cam_index',index);self.cfg.setValue('cam',self.cam_sel.currentText());self.msg('Abriendo la cámara USB de esta PC…')
        except Exception as e:self.msg(str(e))
    def stop_cam(self):
        try:server.CAMERA.stop();server.CAMERA_JPEG=None;server.CAMERA_UPDATED=0;self.video.clear();self.video.setText('Cámara USB detenida')
        except Exception as e:self.msg(str(e))
    def frame(self):
        c=server.CAMERA.status();jpeg=server.CAMERA.jpeg
        if c['live'] and jpeg:
            image=G.QImage.fromData(jpeg,'JPG');self.video.setPixmap(G.QPixmap.fromImage(image).scaled(self.video.size(),C.Qt.KeepAspectRatio,C.Qt.SmoothTransformation))
        elif c['running'] or c.get('error'):self.video.clear();self.video.setText(c.get('error') or 'Conectando cámara USB…')
    def toggle_server(self):
        try:
            if server.REMOTE_SERVER:
                server.stop_remote();self.server=None;self.b_srv.setText('Compartir en la red');self.remote_link.clear();self.srv_lbl.setText('Acceso cerrado; enlace revocado')
            else:
                info=server.start_remote();self.server=server.REMOTE_SERVER;self.remote_link.setText(info['url']);self.b_srv.setText('Cerrar acceso');self.srv_lbl.setText('Cliente habilitado en la red local · solo lectura')
        except Exception as e:self.msg(str(e))
    def stop_tunnel(self):pass
    def toggle_connect(self):
        super().toggle_connect()
        if not self.poller:self._transport_ok=False;self.live={};self.line_live=self.k_live=None;self.publish_status();self.update_metrics();self.redraw()
    def on_poll(self,data):
        self._transport_ok=True;super().on_poll(data)
        name,size=self.job_file();key=(name,size)
        if self.auto_download.isChecked() and name and (self.live.get('state') or {}).get('status') in n.ACTIVE and not self.file_match and not self._fetch_pending and key!=self._auto_fetched:
            self._fetch_pending=True;self._auto_fetched=key;self.fetch_job()
    def on_fail(self,error):
        self._transport_ok=False;super().on_fail(error);self.publish_status();self.update_metrics()
    def _loaded(self,g,error):
        self._fetch_pending=False;super()._loaded(g,error)
        if g is not None and not error:self.publish_model();self.publish_status();self.update_metrics()
    def publish_model(self):
        g=self.g
        if g is None:return
        step=max(1,math.ceil(g.N/50000));indices=np.arange(0,g.N,step);segments=[]
        for i in indices:segments.append([*map(float,g.segs[i].reshape(-1)),int(g.starts[g.seg_line[i]+1]),int(g.seg_tool[i])])
        bounds=[g.segs.reshape(-1,3).min(0).tolist(),g.segs.reshape(-1,3).max(0).tolist()] if g.N else None
        info={'segments':segments,'layers':g.nl,'z_layers':g.layer_z.tolist(),'bounds':bounds,'bytes':g.size,'tools':g.tools_used,'sha256':g.sha256,'layer_offsets':[[int(g.starts[g.seg_line[i]]),float(g.layer_z[k])] for k,i in enumerate(g.layer_start)] if g.N else [],'note':'Modelo del monitor nativo; vista remota muestreada'}
        with server.LOCK:server.ACTIVE_FILE=g.path;server.ACTIVE_GCODE=info;server.REMOTE_FILE=self.job_file()[0] if self.file_match else None
    def publish_status(self):
        if not self._transport_ok:
            s={'connected':False,'status':'disconnected','timestamp':time.time()}
        else:
            s=normalize_status({'state':self.live.get('state'),'job':self.job,'move.axes':(self.live.get('move') or {}).get('axes'),'heat':self.live.get('heat'),'tools':self.tools,'fans':self.live.get('fans'),'sensors':self.live.get('sensors') or {'filamentMonitors':self.fil_mon}})
        with server.LOCK:server.STATUS=s
        if self.g and self.file_match:server.REMOTE_FILE=self.job_file()[0]
        return s
    def push_remote(self):
        super().push_remote();self.publish_status()
        if hasattr(self,'metric_labels'):self.update_metrics()
    def update_metrics(self):
        s=server.STATUS;self.metric_labels['state'].setText(n.ST_ES.get(s.get('status'),'Sin conexión'));self.metric_labels['progress'].setText(f"{s['progress']:.1f} %" if s.get('progress') is not None else '—');self.metric_labels['tool'].setText(f"T{s['tool']}" if s.get('tool') is not None and s['tool']>=0 else '—')
        if self.g and self.g.N and (self.file_match or not self._transport_ok):
            layer=self.g.layer_at_k(self.k_live) if self.k_live is not None else self.slider.value();self.metric_labels['layer'].setText(f'{layer+1} / {self.g.nl}')
        else:self.metric_labels['layer'].setText(str(s.get('layer') or '—'))
    def _finish_event(self,event):
        super()._finish_event(event)
        try:server.JOURNAL.add(event.get('evento','EVENTO'),event.get('detalle',''),dict(server.STATUS))
        except OSError:pass
    def machine_action(self,kind):
        if not self.duet or not self._transport_ok:self.msg('Conecta la impresora primero');return
        if kind=='cancel' and (self.live.get('state') or {}).get('status') not in ('paused','pausing'):self.msg('Pausa el trabajo antes de cancelar');return
        if W.QMessageBox.question(self,'Confirmar comando',{'pause':'¿Pausar la impresión?','resume':'¿Reanudar la impresión?','cancel':'¿Cancelar la impresión pausada?'}[kind])!=W.QMessageBox.Yes:return
        duet=self.duet;self.run_bg(lambda:duet.gcode({'pause':'M25','resume':'M24','cancel':'M0'}[kind]),lambda _,e:self.msg(str(e) if e else 'Comando enviado a Duet'))
    def upload_only(self):
        if not self.duet or not self.path:self.msg('Conecta Duet y carga un G-code');return
        duet=self.duet;path=self.path;self.run_bg(lambda:duet.upload('0:/gcodes/'+os.path.basename(path),path),lambda _,e:self.msg(str(e) if e else 'G-code subido; la impresión no se ha iniciado'))
    def tune(self,kind):
        if not self.duet or not self._transport_ok:self.msg('Conecta Duet primero');return
        value=self.tune_fields[kind].value()
        if W.QMessageBox.question(self,'Confirmar ajuste',f'¿Enviar {kind}: {value} al Duet?')!=W.QMessageBox.Yes:return
        adapter=DuetClient(self.ip.text());duet=self.duet;adapter.req=lambda path,params=None,**kwargs:duet.get(path.lstrip('/'),params).json();tool=(self.live.get('state') or {}).get('currentTool')
        self.run_bg(lambda:adapter.tune(kind,value,tool),lambda _,e:self.msg(str(e) if e else 'Ajuste enviado'))
    def closeEvent(self,event):
        self._closing=True;self._camera_timer.stop();server.stop_remote()
        try:server.CAMERA.stop()
        except Exception:pass
        self.server=None
        if self.poller:
            self.poller.running=False
            if not self.poller.wait(18000):event.ignore();self.msg('Esperando el cierre de la conexión Duet…');return
            self.poller=None
        super().closeEvent(event)

from control_center import upgrade_main
Main=upgrade_main(Main)
from studio_app import upgrade_studio
Main=upgrade_studio(Main)
from automation9 import upgrade as upgrade_automation
Main=upgrade_automation(Main)
from obs10 import upgrade as upgrade_obs
Main=upgrade_obs(Main)
from multicam11 import upgrade as upgrade_multicam
Main=upgrade_multicam(Main)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--open');parser.add_argument('--smoke',action='store_true');args=parser.parse_args()
    C.QCoreApplication.setAttribute(C.Qt.AA_EnableHighDpiScaling,True);C.QCoreApplication.setAttribute(C.Qt.AA_UseDesktopOpenGL,True);C.QCoreApplication.setAttribute(C.Qt.AA_ShareOpenGLContexts,True)
    app=W.QApplication(sys.argv);apply_theme(app);window=Main();window.show()
    if args.open:C.QTimer.singleShot(300,lambda:window.load(args.open))
    if args.smoke:C.QTimer.singleShot(2500,window.close)
    return app.exec_()

if __name__=='__main__':
    try:sys.exit(main())
    except Exception:
        error=traceback.format_exc();directory=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'MODIX_6';directory.mkdir(exist_ok=True);(directory/'error_principal.log').write_text(error,encoding='utf-8')
        print(error,file=sys.stderr);sys.exit(1)
