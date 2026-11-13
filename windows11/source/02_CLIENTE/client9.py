"""Cliente MODIX 9: supervisión, cámara e historial; sin órdenes a la impresora."""
import os,time,json,math,base64
from pathlib import Path
import numpy as np
from PyQt5 import QtCore as C,QtGui as G,QtWidgets as W
import pyqtgraph.opengl as gl
from pyqtgraph import Vector
from studio_widgets import AccentFrame,VideoSurface,CameraWindow,icon
from ui_theme import label,button
from history_panel import HistoryPanel,duration

class ProgressRing(W.QWidget):
    def __init__(self):super().__init__();self.value=0;self.setFixedSize(52,52)
    def paintEvent(self,event):
        p=G.QPainter(self);p.setRenderHint(G.QPainter.Antialiasing);r=C.QRectF(5,5,42,42);p.setPen(G.QPen(G.QColor('#1b2d49'),6));p.drawEllipse(r);gradient=G.QConicalGradient(26,26,90);gradient.setColorAt(0,G.QColor('#00e694'));gradient.setColorAt(.8,G.QColor('#0095ff'));gradient.setColorAt(1,G.QColor('#1a54d4'));p.setPen(G.QPen(G.QBrush(gradient),6));p.drawArc(r,90*16,-round(self.value*3.6*16))
class ClientHeader(W.QWidget):
    def __init__(self):
        super().__init__();self.setMinimumHeight(86);h=W.QHBoxLayout(self);h.setContentsMargins(8,8,10,8);brand=label('MODIX');brand.setStyleSheet('color:#ff143e;font-size:36px;font-weight:900');h.addWidget(brand);self.logo=label('');self.logo.setPixmap(G.QPixmap(str(Path(__file__).with_name('assets')/'canal_panama_blanco.png')).scaled(220,47,C.Qt.KeepAspectRatio,C.Qt.SmoothTransformation));h.addSpacing(20);h.addWidget(self.logo);self.description=label('Cliente de Supervisión\nSolo lectura');self.description.setStyleSheet('font-size:14px;color:#ffe08a');h.addSpacing(20);h.addWidget(self.description);h.addStretch();self.settings=W.QToolButton();self.settings.setIcon(icon('link'));self.settings.setToolTip('Mostrar conexión');h.addWidget(self.settings);self.connection=label('● Sin conexión');self.connection.setStyleSheet('color:#e1b06b');h.addWidget(self.connection)
    def resizeEvent(self,event):super().resizeEvent(event);self.logo.setVisible(self.width()>820);self.description.setVisible(self.width()>610)
    def paintEvent(self,event):
        p=G.QPainter(self)
        for offset,color in ((0,'#00417d'),(95,'#0066bc'),(185,'#be0c35')):x=self.width()-300+offset;p.setPen(G.QPen(G.QColor(color),9));p.drawLine(x+65,0,x,self.height())

class ClientResponsive(C.QObject):
    def __init__(self,window):super().__init__(window);self.window=window;self.queued=False;window.installEventFilter(self);window.viewport.viewport().installEventFilter(self);self.apply();screen=window.screen() or W.QApplication.primaryScreen();bounds=screen.availableGeometry();window.resize(min(1660,bounds.width()-30),min(980,bounds.height()-45));window.move(bounds.x()+15,bounds.y()+15)
    def eventFilter(self,obj,event):
        if event.type() in (C.QEvent.Resize,C.QEvent.Show) and not self.queued:self.queued=True;C.QTimer.singleShot(0,self.apply)
        return False
    def apply(self):
        self.queued=False;w=self.window;available=max(1,w.viewport.viewport().width()-24);cols=6 if available>=1130 else 3 if available>=560 else 2;grid=w.metric_grid
        while grid.count():grid.takeAt(0)
        for i,tile in enumerate(w.metric_tiles):grid.addWidget(tile,i//cols,i%cols)
        for i in range(6):grid.setColumnStretch(i,1 if i<cols else 0)
        w.metric_container.setFixedHeight(math.ceil(6/cols)*98-8)
        for metric in w.metrics.values():metric.setStyleSheet('font-size:'+('18' if available/cols<215 else '22')+'px;font-weight:750')
        narrow=available<1000;w.scene.setOrientation(C.Qt.Vertical if narrow else C.Qt.Horizontal);w.scene.setMinimumHeight(650 if narrow else 340);w.scene.setSizes([360,300] if narrow else [int(available*.61),int(available*.39)]);w.bottom.setOrientation(C.Qt.Vertical if available<780 else C.Qt.Horizontal);w.bottom.setMinimumHeight(320 if available<780 else 192);w.sidebar.setFixedWidth(70 if w.width()<900 else 92)
        for b in w.nav_buttons:b.setIconSize(C.QSize(26,26) if w.height()<650 else C.QSize(32,32));b.setMinimumHeight(65 if w.height()<650 else 88)
        w.monitor_page.setMinimumHeight((650 if narrow else 340)+(320 if available<780 else 175)+14);w.content.updateGeometry()

def upgrade_main(Base):
    class Main(Base):
        def __init__(self):
            W.QMainWindow.__init__(self);self.setWindowTitle('MODIX V4 · Cliente 11 · Multicámara');self.setWindowIcon(G.QIcon(str(Path(__file__).with_name('modix.ico'))));self.setMinimumSize(700,500);self.setStyleSheet('QLabel{font-size:14px} QLabel#panelTitle{font-size:18px;font-weight:750} QLabel#muted{font-size:13px}');self.worker=None;self.data={};self.gcode={};self.segments=None;self.fitted=False;self.last_frame=None;self._last_qimage=None;self.camera_window=None;self.last_received=0.;self.last_state=0.;self.errors={};self._connection_auto_hidden=False;self._draw_key=None;self._trail_sequence=None;self._trail_file=None;self.history_rows=[]
            self.directory=Path(os.environ.get('MODIX_CLIENT_DATA_DIR',str(Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'MODIX_6_Cliente')));self.directory.mkdir(parents=True,exist_ok=True);self.config=self.directory/'conexion.json';self.build();self.timer=C.QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.tick);self.timer.start();self._responsive=ClientResponsive(self)
        def build(self):
            root=W.QWidget();outer=W.QHBoxLayout(root);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0);self.setCentralWidget(root);self.sidebar=W.QFrame();self.sidebar.setObjectName('sidebar');sv=W.QVBoxLayout(self.sidebar);sv.setContentsMargins(5,12,5,12);sv.setSpacing(13);brand=label('M','brand');brand.setAlignment(C.Qt.AlignCenter);sv.addWidget(brand);self.nav_buttons=[];self.nav_group=W.QButtonGroup(self)
            self.pages=W.QStackedWidget()
            for index,(text,name) in enumerate([('Vista','monitor'),('Cámara','camera'),('Historial','clock')]):
                b=W.QToolButton();b.setText(text);b.setIcon(icon(name));b.setCheckable(True);b.setProperty('nav',True);b.setToolButtonStyle(C.Qt.ToolButtonTextUnderIcon);b.setSizePolicy(W.QSizePolicy.Expanding,W.QSizePolicy.Fixed);b.clicked.connect(lambda checked=False,i=index:self.pages.setCurrentIndex(i));self.nav_group.addButton(b);sv.addWidget(b);self.nav_buttons.append(b)
            self.nav_buttons[0].setChecked(True);sv.addStretch();self.rail_state=label('● Sin enlace');self.rail_state.setStyleSheet('color:#d8b579;font-size:10px');sv.addWidget(self.rail_state);outer.addWidget(self.sidebar)
            self.content=W.QWidget();v=W.QVBoxLayout(self.content);v.setContentsMargins(13,2,13,12);v.setSpacing(14);self.header=ClientHeader();v.addWidget(self.header)
            connect=W.QWidget();self.connection_row=connect;self.header.settings.clicked.connect(lambda:self.connection_row.setVisible(not self.connection_row.isVisible()));row=W.QHBoxLayout(connect);row.setContentsMargins(0,0,0,0);self.url=W.QLineEdit();self.url.setMinimumWidth(150);self.url.setPlaceholderText('Pega el enlace que genera Compartir por Internet en la principal');row.addWidget(self.url,1);self.connect_button=button('Conectar',self.connect_server,True);row.addWidget(self.connect_button);row.addWidget(button('Desconectar',self.disconnect));self.remember=W.QCheckBox('Recordar enlace');row.addWidget(self.remember);v.addWidget(connect)
            try:self.url.setText(json.loads(self.config.read_text(encoding='utf-8'))['url']);self.remember.setChecked(True)
            except (OSError,ValueError,KeyError):pass
            self.metric_container=W.QWidget();self.metric_grid=W.QGridLayout(self.metric_container);self.metric_grid.setContentsMargins(0,0,0,0);self.metric_grid.setSpacing(8);self.metrics={};self.metric_tiles=[]
            for key,title,name in [('status','Estado Duet','printer'),('layer','Capa Actual','layers'),('progress','Avance','clock'),('tool','Herramienta','heat'),('elapsed','Tiempo Transcurrido','clock'),('remaining','Tiempo Restante','timer')]:
                tile=AccentFrame();tile.setMinimumWidth(0);tile.setSizePolicy(W.QSizePolicy.Ignored,W.QSizePolicy.Preferred);h=W.QHBoxLayout(tile);h.setContentsMargins(10,8,10,8)
                if key=='progress':self.progress_ring=ProgressRing();h.addWidget(self.progress_ring)
                else:symbol=label('');symbol.setPixmap(icon(name,'#ff123d',34).pixmap(34,34));symbol.setFixedWidth(34);h.addWidget(symbol)
                texts=W.QVBoxLayout();caption=label(title);caption.setStyleSheet('font-size:12px;color:#b5c6e7');caption.setWordWrap(True);texts.addWidget(caption);self.metrics[key]=label('—');self.metrics[key].setMinimumWidth(0);self.metrics[key].setStyleSheet('font-size:17px;font-weight:750');self.metrics[key].setSizePolicy(W.QSizePolicy.Ignored,W.QSizePolicy.Preferred);texts.addWidget(self.metrics[key]);h.addLayout(texts,1);self.metric_tiles.append(tile)
            v.addWidget(self.metric_container);v.addWidget(self.pages,1);self.monitor_page=W.QWidget();mv=W.QVBoxLayout(self.monitor_page);mv.setContentsMargins(0,0,0,0);mv.setSpacing(10);self.scene=W.QSplitter();self.scene.setChildrenCollapsible(False);mv.addWidget(self.scene,3)
            model=AccentFrame();ml=W.QVBoxLayout(model);ml.setContentsMargins(12,10,12,10);row=W.QHBoxLayout();symbol=label('');symbol.setPixmap(icon('cube','#ff123e').pixmap(26,26));row.addWidget(symbol);row.addWidget(label('Modelo 3D · Seguimiento de Impresión','panelTitle'),1);self.layer_header=label('Capa: —');row.addWidget(self.layer_header);self.layer_options=W.QToolButton();self.layer_options.setIcon(icon('layers'));self.layer_options.setToolTip('Opciones de capas y recorrido');row.addWidget(self.layer_options);fit=button('Ver placa',self.fit_plate);fit.setIcon(icon('cube'));row.addWidget(fit);ml.addLayout(row);self.view=gl.GLViewWidget();self.view.setBackgroundColor((5,11,20));self.view.setMinimumHeight(220);ml.addWidget(self.view,1);self.grid=gl.GLGridItem();self.view.addItem(self.grid)
            self.pending=gl.GLLinePlotItem(mode='lines',width=1,glOptions='translucent');self.done=gl.GLLinePlotItem(mode='lines',width=1.3);self.current=gl.GLLinePlotItem(mode='lines',width=2.4);self.nozzle=gl.GLScatterPlotItem(size=13,color=(1,.08,.25,1));self.file_nozzle=gl.GLScatterPlotItem(size=8,color=(1,.78,.1,1));self.trail=gl.GLLinePlotItem(mode='line_strip',width=2.5,color=(0,.85,1,.9));self.nozzle_body=gl.GLLinePlotItem(mode='lines',width=3,color=(1,.13,.35,1))
            for item in (self.pending,self.done,self.current,self.nozzle,self.file_nozzle,self.trail,self.nozzle_body):self.view.addItem(item)
            self.model_controls=W.QWidget();control_layout=W.QVBoxLayout(self.model_controls);control_layout.setContentsMargins(0,0,0,0);row=W.QHBoxLayout();self.mode=W.QComboBox();self.mode.addItems(['En vivo · recorrido por bytes','Modelo completo','Manual por capa']);self.mode.setMinimumWidth(100);self.mode.setSizePolicy(W.QSizePolicy.Expanding,W.QSizePolicy.Fixed);self.mode.currentIndexChanged.connect(self.draw);row.addWidget(self.mode,1);self.ghost=W.QCheckBox('Pendiente en gris');self.ghost.setChecked(True);self.ghost.toggled.connect(self.draw);row.addWidget(self.ghost);control_layout.addLayout(row);self.slider=W.QSlider(C.Qt.Horizontal);self.slider.valueChanged.connect(self.slider_changed);control_layout.addWidget(self.slider);ml.addWidget(self.model_controls);self.model_controls.hide();self.layer_options.clicked.connect(lambda:self.model_controls.setVisible(not self.model_controls.isVisible()));self.layer_info=label('Rojo: boquilla de Duet · cian: posiciones recibidas · amarillo: posición del archivo','muted');self.layer_info.setWordWrap(True);ml.addWidget(self.layer_info);self.scene.addWidget(model)
            camera=AccentFrame();cv=W.QVBoxLayout(camera);cv.setContentsMargins(12,10,12,10);row=W.QHBoxLayout();symbol=label('');symbol.setPixmap(icon('camera','#ff123e').pixmap(26,26));row.addWidget(symbol);row.addWidget(label('Cámara USB en Directo','panelTitle'),1);self.camera_status=label('● Sin imagen');row.addWidget(self.camera_status);expand=button('Ampliar',self.expand_camera);expand.setIcon(icon('expand'));row.addWidget(expand);cv.addLayout(row);self.video=VideoSurface('Conecta el cliente para recibir la cámara de la principal');self.video.doubleClicked.connect(self.expand_camera);cv.addWidget(self.video,1);self.camera_detail=label('Esperando transmisión','muted');self.camera_detail.setWordWrap(True);cv.addWidget(self.camera_detail);self.scene.addWidget(camera)
            self.bottom=W.QSplitter();self.bottom.setChildrenCollapsible(False);mv.addWidget(self.bottom,1);temp=AccentFrame();tv=W.QVBoxLayout(temp);tv.addWidget(label('Temperaturas','panelTitle'));self.thermal_labels={};self.thermal_bars={};row=W.QHBoxLayout()
            for key,title,maximum,color in [('tool','Extrusor',300,'#ff123e'),('bed','Cama',150,'#00aaff'),('ambient','Ambiente',60,'#00d480')]:
                box=W.QFrame();box.setObjectName('card');bv=W.QVBoxLayout(box);bv.addWidget(label(title,'muted'));value=label('—');value.setStyleSheet('font-size:25px;font-weight:750');bv.addWidget(value);bar=W.QProgressBar();bar.setTextVisible(False);bar.setRange(0,maximum*10);bar.setMaximumHeight(9);bar.setStyleSheet('QProgressBar{background:#12223d;min-height:7px}QProgressBar::chunk{background:'+color+'}');bv.addWidget(bar);self.thermal_labels[key]=value;self.thermal_bars[key]=bar;row.addWidget(box,1)
            tv.addLayout(row);self.bottom.addWidget(temp);info=AccentFrame();iv=W.QVBoxLayout(info);iv.addWidget(label('Información de Trabajo','panelTitle'));self.job=label('Sin trabajo activo');self.job.setWordWrap(True);iv.addWidget(self.job,1);self.temps=label('');self.temps.hide();self.light_status=label('Luces: esperando información de Duet','muted');self.light_status.setWordWrap(True);iv.addWidget(self.light_status);self.bottom.addWidget(info);self.pages.addWidget(self.monitor_page)
            cam_page=W.QWidget();cl=W.QVBoxLayout(cam_page);cl.addWidget(label('Cámara de la estación principal','panelTitle'));self.large_video=VideoSurface('Sin imagen actual');self.large_video.doubleClicked.connect(self.expand_camera);cl.addWidget(self.large_video,1);cl.addWidget(button('Abrir pantalla completa',self.full_camera));cam_page.setMinimumHeight(480);self.pages.addWidget(cam_page);self.history_page=HistoryPanel(lambda:self.history_rows,False);self.history_page.setMinimumHeight(450);self.pages.addWidget(self.history_page)
            footer=AccentFrame();fv=W.QVBoxLayout(footer);self.status=label('Pega el enlace de la principal y conecta.');self.status.setWordWrap(True);fv.addWidget(self.status);self.alert_status=label('','muted');self.alert_status.setWordWrap(True);fv.addWidget(self.alert_status);v.addWidget(footer);self.events=W.QPlainTextEdit();self.events.setReadOnly(True);self.events.hide();self.resource_status=label('');self.resource_status.hide();self.viewport=W.QScrollArea();self.viewport.setWidgetResizable(True);self.viewport.setFrameShape(W.QFrame.NoFrame);self.viewport.setHorizontalScrollBarPolicy(C.Qt.ScrollBarAlwaysOff);self.viewport.setWidget(self.content);outer.addWidget(self.viewport,1)
            for text in self.content.findChildren(W.QLabel):
                if text.objectName()=='panelTitle':text.setMinimumWidth(0);text.setSizePolicy(W.QSizePolicy.Ignored,W.QSizePolicy.Preferred);text.setWordWrap(True)
            self.job.setMinimumWidth(0);self.job.setSizePolicy(W.QSizePolicy.Ignored,W.QSizePolicy.Preferred);self.fit_plate()
        def fit_plate(self):
            plate=self.data.get('plate') or [980,1000,1000];x,y=plate[:2];self.grid.setSize(x,y);self.grid.setSpacing(max(10,round(x/10)),max(10,round(y/10)));self.grid.resetTransform();self.grid.translate(x/2,y/2,0);self.view.opts['center']=Vector(x/2,y/2,0);self.view.setCameraPosition(distance=max(x,y)*1.55,elevation=38,azimuth=-55)
        def connect_server(self):
            super().connect_server()
            if self.worker:self.worker.resource_error.connect(self.on_resource_error)
        def disconnect(self):
            if self.worker and not self.worker.stop():self.status.setText('Esperando cerrar la conexión anterior');return False
            self.connection_row.show();self._connection_auto_hidden=False;self.worker=None;self.data={};self.last_frame=self._last_qimage=None;self.last_received=self.last_state=0;self.set_video_text('Cliente desconectado');self.on_error('Cliente desconectado');self.draw();return True
        def set_video_text(self,text):
            self.video.setText(text);self.large_video.setText(text)
            if self.camera_window:self.camera_window.video.setText(text)
        def tick(self):
            if self.worker:
                rgb=self.worker.take_rgb() if hasattr(self.worker,'take_rgb') else None
                if rgb is not None:self.on_rgb(rgb)
                jpeg=self.worker.take_frame()
                if jpeg:self.on_frame(jpeg)
            age=time.time()-self.last_received if self.last_received else None
            if age is not None and age>4:self.set_video_text('Imagen desactualizada · reconectando');self._last_qimage=None;self.camera_status.setText('● Sin imagen reciente')
            stats=self.worker.video_stats() if self.worker and hasattr(self.worker,'video_stats') else getattr(self.worker,'stream_stats',{}) if self.worker else {};self.camera_detail.setText((stats.get('transport') or 'Sin enlace')+(f" · {stats['fps']:.1f} FPS" if 'fps' in stats else '')+(f' · imagen hace {age:.1f}s' if age is not None else ''))
            fusion=(self.data.get('obs') or {}).get('fusion') or {}
            if fusion.get('running'):
                coverage=fusion.get('coverage');self.camera_detail.setText(self.camera_detail.text()+f" · fusión {fusion.get('fps',0):.1f} FPS · cámaras {fusion.get('live',0)}/{fusion.get('configured',0)}"+(f' · visible {coverage:.1f}%' if isinstance(coverage,(int,float)) else '')+'\n'+fusion.get('message',''))
            if self.last_state and time.time()-self.last_state>5:self.header.connection.setText('● Datos desactualizados');self.header.connection.setStyleSheet('color:#ffbf5b');self.metrics['status'].setText('Sin datos recientes');self.data['status']={**(self.data.get('status') or {}),'connected':False};self.nozzle.setData(pos=np.empty((0,3)));self.nozzle_body.setData(pos=np.empty((0,3)))
        def on_rgb(self,rgb):
            h,w=rgb.shape[:2];image=G.QImage(rgb.data,w,h,rgb.strides[0],G.QImage.Format_RGB888).copy();self.last_received=time.time();self._last_qimage=image;self.last_frame=None;self.video.setImage(image);self.large_video.setImage(image);self.camera_status.setText('● OBS en línea');self.camera_status.setStyleSheet('color:#00e59d')
            fusion=(self.data.get('obs') or {}).get('fusion') or {}
            if fusion.get('running'):self.camera_status.setText('● Fusión' if fusion.get('mode')=='fusion' else '● Sin fusión');self.camera_status.setStyleSheet('color:#00e59d' if fusion.get('mode')=='fusion' else 'color:#f4bd50')
            if self.camera_window and self.camera_window.isVisible():self.camera_window.video.setImage(image)
        def on_frame(self,jpeg):
            if jpeg is self.last_frame and self._last_qimage is not None:self.last_received=time.time();return
            image=G.QImage.fromData(jpeg,'JPG')
            if image.isNull():return
            self.last_received=time.time();self.last_frame=jpeg;self._last_qimage=image;self.video.setImage(image);self.large_video.setImage(image);self.camera_status.setText('● En línea');self.camera_status.setStyleSheet('color:#00e59d')
            if self.camera_window and self.camera_window.isVisible():self.camera_window.video.setImage(image)
        def expand_camera(self):
            if self.camera_window is None:self.camera_window=CameraWindow(self)
            if self._last_qimage is not None:self.camera_window.video.setImage(self._last_qimage)
            self.camera_window.show();self.camera_window.raise_()
        def full_camera(self):self.expand_camera();self.camera_window.showFullScreen()
        def on_error(self,error):self.status.setText('Sin actualización · '+error);self.header.connection.setText('● Reconectando' if self.worker else '● Sin conexión');self.header.connection.setStyleSheet('color:#e6b269');self.rail_state.setText('● Sin enlace' if not self.worker else '● Reintento')
        def on_resource_error(self,resource,error):self.errors[resource]=error;self.resource_status.setText(' · '.join(v for v in self.errors.values() if v))
        def on_state(self,data):
            if not self._connection_auto_hidden:self.connection_row.hide();self._connection_auto_hidden=True
            self.data=data;self.last_state=time.time();s=data.get('status') or {};names={'processing':'Imprimiendo','idle':'En espera','paused':'Pausada','pausing':'Pausando','resuming':'Reanudando','halted':'Detenida','changingTool':'Cambio T','disconnected':'Desconectada'};connected=s.get('connected');self.metrics['status'].setText(names.get(s.get('status'),'Sin datos') if connected else 'Desconectada');self.metrics['layer'].setText(f"{s.get('layer') or '—'} / {self.gcode.get('layers') or s.get('total_layers') or '—'}");p=s.get('progress');self.metrics['progress'].setText(f'{p:.1f} %' if isinstance(p,(int,float)) else '—');self.progress_ring.value=max(0,min(100,p)) if isinstance(p,(int,float)) else 0;self.progress_ring.update()
            nozzle=s.get('nozzle') or {};temperature=nozzle.get('current');self.metrics['tool'].setText(('T'+str(s['tool']) if isinstance(s.get('tool'),int) and s['tool']>=0 else '—')+(f' · {temperature:.0f} °C' if isinstance(temperature,(int,float)) else ''))
            for key in ('elapsed','remaining'):self.metrics[key].setText(duration(s.get(key)))
            for key,value in [('tool',temperature),('bed',next((b.get('current') for b in s.get('beds',[]) if isinstance(b.get('current'),(int,float))),None)),('ambient',s.get('ambient'))]:self.thermal_labels[key].setText(f'{value:.1f} °C' if isinstance(value,(int,float)) else '—');self.thermal_bars[key].setValue(round(value*10) if isinstance(value,(int,float)) else 0)
            plate=s.get('plate_info') or {};dims=plate.get('dimensions') or data.get('plate');self.job.setText('Perfil: '+data.get('profile','Modix')+'\nPlaca '+('confirmada: ' if plate.get('confirmed') else 'de referencia: ')+(' × '.join(f'{v:g}' for v in dims)+' mm' if dims else 'por confirmar')+'\nTrabajo: '+str(s.get('file') or 'Sin trabajo activo')+'\n'+str(s.get('auto_file') or ''))
            lights=s.get('lights') or [];self.light_status.setText('Luces: '+(' · '.join(l.get('name','')+': '+l.get('label','sin confirmar') for l in lights) if lights else 'sin salidas identificadas'));self.history_rows=s.get('history') or [];self.history_page.refresh();alerts=s.get('alerts') or [];self.alert_status.setText(' · '.join(a.get('message','') for a in alerts) or ((s.get('recovery') or {}).get('message','')));transport=s.get('transport') or {};ok=connected and transport.get('state','online')=='online';self.header.connection.setText('● Conectado' if ok else '● Duet sin datos recientes');self.header.connection.setStyleSheet('color:#00e59d' if ok else 'color:#f3ba69');self.rail_state.setText('● En línea');self.rail_state.setStyleSheet('color:#00e59d;font-size:10px');self.status.setText(('Conexión activa con la principal' if ok else 'Principal conectada · comunicación de Duet pendiente')+' · '+time.strftime('%H:%M:%S'));self.draw()
        def on_model(self,gcode):
            try:
                geometry=gcode.get('geometry') or {};count=geometry.get('count',0)
                if geometry.get('codec')=='modix-geometry-1':
                    if not isinstance(count,int) or not 0<=count<=100001:raise ValueError('Tamaño de geometría inválido')
                    coords=np.frombuffer(base64.b64decode(geometry['coordinates'],validate=True),dtype='<f4').reshape(count,6);offsets=np.frombuffer(base64.b64decode(geometry['offsets'],validate=True),dtype='<u8');tools=np.frombuffer(base64.b64decode(geometry['tools'],validate=True),dtype='<i2')
                    if len(offsets)!=count or len(tools)!=count or not np.isfinite(coords).all() or np.any(offsets[1:]<offsets[:-1]):raise ValueError('Geometría inválida')
                    segments=np.column_stack((coords,offsets,tools))
                else:segments=np.asarray(gcode.get('segments',[]),dtype=np.float64).reshape(-1,8)
                if len(segments)>100001 or not np.isfinite(segments).all():raise ValueError('Modelo inválido')
                self.gcode=gcode;self.segments=segments;self._points=np.ascontiguousarray(segments[:,:6].reshape(-1,2,3),dtype=np.float32);self._offsets=segments[:,6];self._heights=np.maximum(segments[:,2],segments[:,5]);self.slider.setRange(0,max(0,len(gcode.get('z_layers') or [])-1));self._draw_key=None;self.fit_plate();bounds=gcode.get('bounds')
                if bounds:
                    a,b=np.asarray(bounds,dtype=float);self.view.opts['center']=Vector(*((a+b)/2));self.view.setCameraPosition(distance=max(40,float(max(b-a))*2.2),elevation=32,azimuth=-55)
                self.draw();self.on_resource_error('model','')
            except (ValueError,KeyError,TypeError):self.on_resource_error('model','El modelo recibido no es válido')
        def draw(self,*args):
            s=self.data.get('status') or {};axes=s.get('axes') or [];coords=[next((a.get('userPosition',a.get('position')) for a in axes if a.get('axis')==axis),None) for axis in 'XYZ'];live=s.get('connected') and all(isinstance(v,(int,float)) and np.isfinite(v) for v in coords)
            self.nozzle.setData(pos=np.asarray([coords],np.float32) if live else np.empty((0,3)));self.nozzle_body.setData(pos=np.asarray([coords,[coords[0],coords[1],coords[2]+15]],np.float32) if live else np.empty((0,3)))
            trajectory=s.get('trajectory') or {};sequence=(trajectory.get('file'),trajectory.get('sequence'))
            if sequence!=self._trail_sequence:
                self._trail_sequence=sequence;points=np.asarray(trajectory.get('points') or [],dtype=np.float32)
                if points.size and points.ndim==2 and points.shape[1]>=3 and len(points)<=1600 and np.isfinite(points).all():self.trail.setData(pos=np.ascontiguousarray(points[:,:3]))
                else:self.trail.setData(pos=np.empty((0,3)))
            seg=self.segments
            if seg is None or not len(seg):
                for item in (self.pending,self.done,self.current,self.file_nozzle):item.setData(pos=np.empty((0,3)))
                return
            base=lambda value:str(value or '').replace('\\','/').split('/')[-1].casefold();matched=bool(s.get('connected') and s.get('model_verified',True) and s.get('file') and s.get('size')==self.gcode.get('bytes') and base(s['file']) in (base(self.data.get('gcode_file')),base(self.data.get('remote_file'))));position=s.get('position');verified=matched and isinstance(position,(int,float));mode=self.mode.currentIndex();layers=self.gcode.get('z_layers') or []
            if mode==0 and layers:
                layer=s.get('layer')
                if not isinstance(layer,int) and verified:
                    k=int(np.searchsorted(self._offsets,position,side='right'))-1
                    if k>=0:layer=int(np.argmin(np.abs(np.asarray(layers)-seg[k,5])))+1;self.metrics['layer'].setText(f'{layer} / {len(layers)}');self.metrics['layer'].setToolTip('Capa estimada a partir de la posición en bytes del archivo')
                if isinstance(layer,int):self.slider.blockSignals(True);self.slider.setValue(max(0,min(len(layers)-1,layer-1)));self.slider.blockSignals(False)
            z=layers[self.slider.value()] if layers else 0;key=(id(seg),mode,position if verified else None,self.slider.value(),self.ghost.isChecked())
            if key==self._draw_key:return
            self._draw_key=key;mask=np.ones(len(seg),bool) if mode==1 else self._heights<=z+.001 if mode==2 else self._offsets<=position if verified else np.zeros(len(seg),bool);points=self._points;self.done.setData(pos=points[mask].reshape(-1,3),color=(.9,.94,1,1));self.pending.setData(pos=points[~mask].reshape(-1,3) if self.ghost.isChecked() else np.empty((0,3)),color=(.55,.62,.74,.23));highlight=mask&(np.abs(self._heights-z)<.01);self.current.setData(pos=points[highlight].reshape(-1,3),color=(1,.14,.34,1));indices=np.flatnonzero(mask);self.file_nozzle.setData(pos=points[indices[-1],1:2] if verified and len(indices) else np.empty((0,3)));self.layer_header.setText(f'Capa: {self.slider.value()+1} / {len(layers)}');self.layer_info.setText(('Recorrido del archivo sincronizado por bytes' if verified else 'Esperando coincidencia de archivo y posición')+(' · vista muestreada' if (self.gcode.get('geometry') or {}).get('sampled') else '')+' · rojo: Duet · cian: posiciones recibidas')
        def slider_changed(self):
            if self.slider.isSliderDown():self.mode.setCurrentIndex(2)
            self.draw()
        def closeEvent(self,event):
            if not self.disconnect():event.ignore();return
            self.timer.stop()
            if self.camera_window:self.camera_window.close()
            event.accept()
    return Main
