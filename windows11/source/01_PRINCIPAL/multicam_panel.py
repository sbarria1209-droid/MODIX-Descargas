"""Asistente de cámaras y calibración de referencias a dos alturas."""
import copy,time
import numpy as np
from PyQt5 import QtCore as C,QtGui as G,QtWidgets as W
from multicam_capture import devices,MAX_CAMERAS
from multicam_engine import validate,save_config
from fusion_geometry import fit_projection,world_references

class CalibrationCanvas(W.QWidget):
    clicked=C.pyqtSignal(float,float);finishMask=C.pyqtSignal()
    def __init__(self):super().__init__();self.setMinimumSize(260,190);self.image=None;self.points=[];self.masks=[];self.pending=[];self.bounds=C.QRectF();self.setMouseTracking(True)
    def set_frame(self,frame):
        if frame is None:self.image=None
        else:
            frame=np.ascontiguousarray(frame);h,w=frame.shape[:2];self.image=G.QImage(frame.data,w,h,frame.strides[0],G.QImage.Format_BGR888).copy()
        self.update()
    def paintEvent(self,event):
        p=G.QPainter(self);p.fillRect(self.rect(),G.QColor('#070d18'));p.setRenderHint(G.QPainter.Antialiasing)
        if self.image is None:p.setPen(G.QColor('#bed0ea'));p.drawText(self.rect(),C.Qt.AlignCenter,'Selecciona cámaras y pulsa Previsualizar');return
        ratio=min(self.width()/self.image.width(),self.height()/self.image.height());w=self.image.width()*ratio;h=self.image.height()*ratio;self.bounds=C.QRectF((self.width()-w)/2,(self.height()-h)/2,w,h);p.drawImage(self.bounds,self.image)
        def point(uv):return C.QPointF(self.bounds.left()+uv[0]*w,self.bounds.top()+uv[1]*h)
        p.setPen(G.QPen(G.QColor('#ffb43c'),2));p.setBrush(G.QColor(255,150,20,75))
        for polygon in self.masks:p.drawPolygon(G.QPolygonF([point(v) for v in polygon]))
        p.setBrush(C.Qt.NoBrush)
        if self.pending:p.drawPolyline(G.QPolygonF([point(v) for v in self.pending]))
        for i,uv in enumerate(self.points):
            q=point(uv);p.setPen(G.QPen(G.QColor('#00e9ff'),2));p.setBrush(G.QColor('#08101b'));p.drawEllipse(q,8,8);p.setPen(G.QColor('#ffffff'));p.drawText(q+C.QPointF(10,-8),str(i+1))
    def mousePressEvent(self,event):
        if event.button()==C.Qt.RightButton:self.finishMask.emit();return
        q=event.localPos()
        if event.button()==C.Qt.LeftButton and self.image and self.bounds.contains(q):self.clicked.emit((q.x()-self.bounds.left())/self.bounds.width(),(q.y()-self.bounds.top())/self.bounds.height())

class MultiCameraDialog(W.QDialog):
    def __init__(self,owner,engine):
        super().__init__(owner);self.owner=owner;self.engine=engine;self.config=copy.deepcopy(engine.config);self.was_running=engine.running;self.busy=False;self.closed=False;self.sessions={};self.row=0;self.pending_mask=[];self.devices=devices();self.setWindowTitle('MODIX V4 · Fusión de 2 a 8 cámaras');self.setMinimumSize(690,500)
        screen=owner.screen().availableGeometry();self.resize(min(1240,screen.width()-30),min(880,screen.height()-45));outer=W.QVBoxLayout(self)
        tip=W.QLabel('Coloca las cámaras a lados distintos, fijas y viendo la zona de impresión. Marca referencias con la máquina en reposo. La app no mueve la impresora.');tip.setWordWrap(True);outer.addWidget(tip)
        split=W.QSplitter();outer.addWidget(split,1);left=W.QWidget();lv=W.QVBoxLayout(left);lv.setContentsMargins(4,4,8,4);self.rows=[]
        lv.addWidget(W.QLabel('1 · Selecciona de dos a ocho cámaras USB'))
        for i,cam in enumerate(self.config['cameras']):
            row=W.QHBoxLayout();enabled=W.QCheckBox(str(i+1));enabled.setChecked(cam.get('enabled',False));select=W.QComboBox();select.setMinimumWidth(0)
            choices=list(self.devices)
            known={d['index'] for d in choices}
            choices.extend({'index':k,'name':'Cámara '+str(k),'uid':''} for k in range(16) if k not in known)
            for item in choices:select.addItem(str(item['index'])+' · '+item['name'],item)
            match=next((k for k in range(select.count()) if cam.get('uid') and select.itemData(k).get('uid')==cam['uid']),None)
            if match is None:match=next((k for k in range(select.count()) if select.itemData(k)['index']==cam['index']),0)
            select.setCurrentIndex(match)
            if cam.get('uid') and select.currentData().get('uid')!=cam['uid']:cam['calibration']=None;cam['masks']=[]
            button=W.QPushButton('Calibrar');button.clicked.connect(lambda _,r=i:self.select_row(r));row.addWidget(enabled);row.addWidget(select,1);row.addWidget(button);lv.addLayout(row);self.rows.append((enabled,select));select.currentIndexChanged.connect(lambda _,r=i:self.device_changed(r))
        self.preview_button=W.QPushButton('Previsualizar selección');self.preview_button.clicked.connect(self.preview);lv.addWidget(self.preview_button)
        self.capture_format=W.QComboBox()
        for w,h in ((640,480),(1280,720),(1920,1080)):self.capture_format.addItem(f'USB · {w} × {h}',[w,h])
        capture=self.config.get('capture') or {'width':1280,'height':720};self.capture_format.setCurrentIndex(max(0,self.capture_format.findData([capture['width'],capture['height']])));self.capture_format.currentIndexChanged.connect(self.capture_changed);lv.addWidget(self.capture_format)
        lv.addWidget(W.QLabel('2 · Referencias físicas (mm)'))
        explanation=W.QLabel('Usa las mismas cuatro posiciones XY a dos alturas conocidas: por ejemplo un tablero en Z=0 y elevado 100 mm, sin mover las cámaras ni el eje Z entre capturas. Evita ojo de pez y cambios de zoom/enfoque.');explanation.setWordWrap(True);lv.addWidget(explanation)
        form=W.QFormLayout();form.setRowWrapPolicy(W.QFormLayout.WrapAllRows);self.fields={}
        for key,text,group in [('x','X mínima de marcas','reference'),('y','Y mínima de marcas','reference'),('width','Separación X de marcas','reference'),('depth','Separación Y de marcas','reference'),('z0','Altura de marcas inferior','reference'),('z1','Altura de marcas superior','reference')]:
            field=W.QDoubleSpinBox();field.setRange(-5000,5000);field.setDecimals(2);field.setSuffix(' mm');field.setValue(self.config[group][key]);form.addRow(text,field);self.fields[key]=field
        self.machine_z=W.QDoubleSpinBox();self.machine_z.setRange(-100,5000);self.machine_z.setSuffix(' mm')
        with engine.lock:xyz=engine.poses[-1][1] if engine.poses else None
        self.machine_z.setValue(float(xyz[2]) if xyz is not None else 0);form.addRow('Z máquina de Duet al calibrar',self.machine_z);lv.addLayout(form)
        self.kinematics=W.QComboBox();self.kinematics.addItem('Cámaras en chasis · la cama baja en Z','bed_moves');self.kinematics.addItem('Cama fija o cámaras sujetas a la cama','bed_fixed');self.kinematics.setCurrentIndex(max(0,self.kinematics.findData(self.config['kinematics'])));lv.addWidget(self.kinematics)
        order=W.QLabel('Orden físico de las marcas, desde el frente:\n 4 (X−,Y+) ───── 3 (X+,Y+)\n 1 (X−,Y−) ───── 2 (X+,Y−)');order.setFont(G.QFont('Consolas',9));lv.addWidget(order)
        lv.addWidget(W.QLabel('3 · Medidas aproximadas de brazo y cabezal'))
        arm=W.QFormLayout();arm.setRowWrapPolicy(W.QFormLayout.WrapAllRows);self.arm_fields={}
        for key,text in [('beam_width','Ancho del travesaño'),('beam_bottom','Travesaño: Z inferior sobre capa'),('beam_top','Travesaño: Z superior sobre capa'),('head_radius','Radio del cabezal'),('head_height','Altura del cabezal'),('margin','Margen de máscara'),('max_speed','Velocidad máxima para margen (mm/s)')]:
            f=W.QDoubleSpinBox();f.setRange(0,1000);f.setValue(self.config['arm'][key]);arm.addRow(text,f);self.arm_fields[key]=f
        self.axis=W.QComboBox();self.axis.addItem('Travesaño paralelo a X','x');self.axis.addItem('Travesaño paralelo a Y','y');self.axis.addItem('Travesaños X e Y','both');self.axis.setCurrentIndex(max(0,self.axis.findData(self.config['arm']['axis'])));arm.addRow('Orientación',self.axis);lv.addLayout(arm)
        self.provenance=W.QCheckBox('Colorear procedencia de cada cámara');self.provenance.setChecked(self.config.get('provenance',False));lv.addWidget(self.provenance)
        performance=W.QFormLayout();self.resolution=W.QComboBox()
        for value in (480,640,800,960):self.resolution.addItem(str(value)+' px de ancho',value)
        self.resolution.setCurrentIndex(max(0,self.resolution.findData(self.config['canvas'])));performance.addRow('Detalle de fusión',self.resolution);self.fps=W.QSpinBox();self.fps.setRange(5,30);self.fps.setValue(self.config['fps']);performance.addRow('FPS objetivo de fusión',self.fps);lv.addLayout(performance)
        self.manual=W.QCheckBox('Prueba de alineación con posición manual');self.manual.setChecked(self.config.get('pose_mode')=='manual');lv.addWidget(self.manual);self.manual_fields=[];mf=W.QFormLayout()
        for i,axis in enumerate('XYZ'):
            f=W.QDoubleSpinBox();f.setRange(-5000,5000);f.setValue(self.config['manual_xyz'][i]);mf.addRow(axis+' manual (mm)',f);self.manual_fields.append(f)
        lv.addLayout(mf);lv.addStretch();scroll=W.QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(left);scroll.setMinimumWidth(250);split.addWidget(scroll)
        right=W.QWidget();rv=W.QVBoxLayout(right);self.camera_title=W.QLabel();self.camera_title.setWordWrap(True);rv.addWidget(self.camera_title);self.plane=W.QComboBox();self.plane.addItems(['Plano inferior · cuatro marcas','Plano superior · cuatro marcas']);self.plane.currentIndexChanged.connect(self.update_canvas);rv.addWidget(self.plane);self.canvas=CalibrationCanvas();self.canvas.clicked.connect(self.point);self.canvas.finishMask.connect(self.finish_mask);rv.addWidget(self.canvas,1)
        buttons=W.QHBoxLayout();self.capture_button=W.QPushButton('Capturar plano seleccionado');self.capture_button.clicked.connect(self.freeze);buttons.addWidget(self.capture_button);undo=W.QPushButton('Deshacer punto');undo.clicked.connect(self.undo);buttons.addWidget(undo);rv.addLayout(buttons)
        fit=W.QPushButton('Calcular y guardar calibración de esta cámara');fit.clicked.connect(self.fit);rv.addWidget(fit);self.mask_mode=W.QCheckBox('Dibujar zona fija que no debe usarse');self.mask_mode.toggled.connect(lambda _:self.clear_pending());rv.addWidget(self.mask_mode);mask_row=W.QHBoxLayout();finish=W.QPushButton('Terminar zona');finish.clicked.connect(self.finish_mask);clear=W.QPushButton('Borrar zonas fijas');clear.clicked.connect(self.clear_masks);mask_row.addWidget(finish);mask_row.addWidget(clear);rv.addLayout(mask_row)
        self.info=W.QLabel('Cada zona gris del vídeo final significa que ninguna cámara aporta un píxel visible. No se rellena con imágenes antiguas ni con IA.');self.info.setWordWrap(True);rv.addWidget(self.info);split.addWidget(right);split.setSizes([400,750]);self.status=W.QLabel('Selecciona las cámaras y pulsa Previsualizar selección.');self.status.setWordWrap(True);outer.addWidget(self.status)
        footer=W.QDialogButtonBox(W.QDialogButtonBox.Save|W.QDialogButtonBox.Cancel);footer.button(W.QDialogButtonBox.Save).setText('Guardar');footer.button(W.QDialogButtonBox.Cancel).setText('Cancelar');footer.accepted.connect(self.save);footer.rejected.connect(self.reject);outer.addWidget(footer);self.timer=C.QTimer(self);self.timer.timeout.connect(self.update_canvas);self.timer.start(150);self.select_row(0)
    def collect(self):
        c=copy.deepcopy(self.config)
        for i,(enabled,select) in enumerate(self.rows):
            value=select.currentData();c['cameras'][i].update({'enabled':enabled.isChecked(),'index':value['index'],'name':value['name'],'uid':value.get('uid','')})
        w,h=self.capture_format.currentData();c['capture']={'width':w,'height':h,'fps':30}
        c['reference']={key:f.value() for key,f in self.fields.items()};c['kinematics']=self.kinematics.currentData();c['arm'].update({key:f.value() for key,f in self.arm_fields.items()});c['arm']['axis']=self.axis.currentData();c['provenance']=self.provenance.isChecked();c['canvas']=self.resolution.currentData();c['fps']=self.fps.value();c['pose_mode']='manual' if self.manual.isChecked() else 'duet';c['manual_xyz']=[f.value() for f in self.manual_fields];return validate(c)
    def capture_changed(self):
        for camera in self.config['cameras']:camera['calibration']=None
        self.sessions={};self.status.setText('Cambió el formato USB. Previsualiza y vuelve a calibrar antes de fusionar.');self.update_canvas()
    def session(self):
        if self.row not in self.sessions:
            old=self.config['cameras'][self.row].get('calibration') or {};points=old.get('points',[[],[]]);self.sessions[self.row]={'points':copy.deepcopy(points),'frames':[None,None],'frame_size':old.get('frame_size'),'machine_z':old.get('machine_z'),'reference':copy.deepcopy(old.get('reference'))}
        return self.sessions[self.row]
    def device_changed(self,row):
        camera=self.config['cameras'][row];new=self.rows[row][1].currentData()
        if camera.get('uid')!=new.get('uid') or camera['index']!=new['index']:
            camera.update({'index':new['index'],'name':new['name'],'uid':new.get('uid',''),'calibration':None,'masks':[]});self.sessions.pop(row,None)
        self.update_canvas()
    def select_row(self,row):self.row=row;self.pending_mask=[];self.update_canvas()
    def source(self):
        value=self.rows[self.row][1].currentData();uid=value.get('uid');return next((c for c in self.engine.captures if (uid and c.camera.get('uid')==uid) or (not uid and c.camera['index']==value['index'])),None)
    def preview(self):
        if self.busy:return
        try:config=self.collect()
        except Exception as error:self.status.setText(str(error));return
        self.busy=True;self.preview_button.setEnabled(False);self.status.setText('Abriendo cámaras en segundo plano…')
        def task():self.engine.stop();return self.engine.start(config,require_two=False)
        def done(result,error):
            self.busy=False
            if self.closed:
                if not self.was_running:
                    with __import__('contextlib').suppress(Exception):self.engine.stop()
                return
            self.preview_button.setEnabled(True);self.status.setText(str(error) if error else 'Previsualización lista. Usa Calibrar en cada fila, captura ambos planos y marca sus cuatro referencias.');self.update_canvas()
        self.owner.run_bg(task,done)
    def freeze(self):
        source=self.source();history=source.history() if source else []
        if not history or time.monotonic()-history[-1][0]>.4:self.status.setText('Esta cámara no tiene imagen reciente. Pulsa Previsualizar selección.');return
        plane=self.plane.currentIndex();state=self.session();reference={key:f.value() for key,f in self.fields.items()}
        if plane==1 and state.get('reference') is not None and (reference!=state['reference'] or abs(self.machine_z.value()-state['machine_z'])>.5):self.status.setText('Cambiaron las medidas o Z entre los planos. Recaptura primero el plano inferior.');return
        if plane==0:state['reference']=reference;state['machine_z']=self.machine_z.value()
        frame=history[-1][1].copy();size=[frame.shape[1],frame.shape[0]]
        if plane==1 and state['frames'][0] is not None and size!=state['frame_size']:self.status.setText('Cambió la resolución entre planos. Recaptura ambos planos.');return
        if plane==0:state['frames'][1]=None;state['points'][1]=[]
        state['frames'][plane]=frame;state['points'][plane]=[];state['frame_size']=size;self.mask_mode.setChecked(False);self.status.setText('Imagen congelada. Marca 1: X−Y−, 2: X+Y−, 3: X+Y+, 4: X−Y+.');self.update_canvas()
    def point(self,u,v):
        if self.mask_mode.isChecked():
            if len(self.pending_mask)<64:self.pending_mask.append([u,v])
        else:
            state=self.session();plane=self.plane.currentIndex()
            if state['frames'][plane] is None:self.status.setText('Captura el plano antes de marcar sus esquinas.');return
            if len(state['points'][plane])<4:state['points'][plane].append([u,v])
        self.update_canvas()
    def undo(self):
        points=self.pending_mask if self.mask_mode.isChecked() else self.session()['points'][self.plane.currentIndex()]
        if points:points.pop()
        self.update_canvas()
    def clear_pending(self):self.pending_mask=[];self.update_canvas()
    def finish_mask(self):
        if len(self.pending_mask)>=3:self.config['cameras'][self.row].setdefault('masks',[]).append(copy.deepcopy(self.pending_mask));self.pending_mask=[];self.status.setText('Zona fija excluida. No marques la pieza ni todo el recorrido del brazo.');self.update_canvas()
    def clear_masks(self):self.config['cameras'][self.row]['masks']=[];self.clear_pending()
    def fit(self):
        try:
            state=self.session()
            if any(len(p)!=4 for p in state['points']):raise ValueError('Necesitas cuatro puntos en cada uno de los dos planos')
            if state.get('reference') is None:raise ValueError('Captura primero las referencias físicas')
            P,rms=fit_projection(world_references(state['reference']),state['points'][0]+state['points'][1],state['frame_size']);camera=self.config['cameras'][self.row];camera['calibration']={'projection':P.tolist(),'points':copy.deepcopy(state['points']),'reference':copy.deepcopy(state['reference']),'frame_size':state['frame_size'],'machine_z':state['machine_z'],'rms':rms};self.status.setText(f'Cámara calibrada: error de ajuste {rms:.2f} px. Repite para la cámara del lado opuesto.');self.update_canvas()
        except Exception as error:self.status.setText(str(error))
    def update_canvas(self):
        if not hasattr(self,'canvas'):return
        camera=self.config['cameras'][self.row];cal=camera.get('calibration');self.camera_title.setText(f"Cámara de fila {self.row+1} · "+('Calibrada' if cal else 'Sin calibrar'));state=self.session();plane=self.plane.currentIndex();frame=state['frames'][plane]
        if frame is None:
            source=self.source();history=source.history() if source else []
            if history and time.monotonic()-history[-1][0]<.5:frame=history[-1][1]
        self.canvas.points=state['points'][plane];self.canvas.masks=camera.get('masks',[]);self.canvas.pending=self.pending_mask;self.canvas.set_frame(frame)
    def save(self):
        if self.busy:self.status.setText('Espera a que termine de abrir las cámaras.');return
        try:self.config=save_config(self.engine.path,self.collect());self.accept()
        except Exception as error:self.status.setText(str(error))
    def done(self,result):
        self.closed=True;self.timer.stop()
        if not self.was_running and not self.busy:
            try:self.engine.stop()
            except Exception:self.status.setText('Una cámara está terminando de cerrar.')
        super().done(result)
