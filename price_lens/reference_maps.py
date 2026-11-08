"""A zoomable map preview with independently verified spawn and portal positions."""
from math import isfinite
from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QBitmap,QColor,QImage,QPainter,QPen,QRegion
from PySide6.QtWidgets import QApplication,QFrame,QHBoxLayout,QToolButton,QWidget,QToolTip


class MapPreview(QWidget):
    chosen=Signal(int)
    map_chosen=Signal(int)
    MAX_ZOOM=8.0

    def __init__(self,media,row,parent=None):
        super().__init__(parent);self.media=media;self.row=row;self.geometry_proof=None
        self.markers=[];self.portal_markers=[];self.names={};self.destinations={};self.preview_image=QImage()
        self.zoom=1.0;self.pan=QPointF();self._press=None;self._dragging=False;self._hover=None
        self.setFixedHeight(156);self.setMouseTracking(True)
        self.setAccessibleName('Zoomable map with portals and monster spawn positions')
        self.setAccessibleDescription('Scroll to zoom. Drag to pan. Click a portal to open its destination.')
        self.controls=QFrame(self);self.controls.setObjectName('mapControls')
        self.controls.setStyleSheet('QFrame#mapControls{background:#263448;border-radius:5px;} QToolButton{color:#d3dfed;background:transparent;border:0;border-radius:4px;padding:2px 6px;min-height:18px;} QToolButton:hover{background:#405773;} QToolButton:disabled{color:#64758c;}')
        layout=QHBoxLayout(self.controls);layout.setContentsMargins(2,1,2,1);layout.setSpacing(1)
        self.zoom_out=self.button('−','Zoom out',lambda:self.zoom_at(1/1.5))
        self.fit_button=self.button('Fit','Fit the whole map',self.fit)
        self.zoom_in=self.button('+','Zoom in',lambda:self.zoom_at(1.5))
        for button in (self.zoom_out,self.fit_button,self.zoom_in):layout.addWidget(button)
        self.controls.adjustSize();self.update_controls()
        self.layers=QFrame(self);self.layers.setObjectName('mapLayers')
        self.layers.setStyleSheet('QFrame#mapLayers{background:transparent;} QToolButton{color:#9aadc5;background:transparent;border:0;border-radius:4px;padding:2px 5px;min-height:18px;font-size:10px;} QToolButton:hover{background:#304258;} QToolButton:checked{background:#2b4057;color:#69cfff;} QToolButton#spawnLayer:checked{color:#ffc66f;}')
        layers=QHBoxLayout(self.layers);layers.setContentsMargins(0,0,0,0);layers.setSpacing(3)
        self.portals_button=QToolButton(self.layers);self.portals_button.setText('○ Portals');self.portals_button.setToolTip('Show portals and their destinations')
        self.spawns_button=QToolButton(self.layers);self.spawns_button.setObjectName('spawnLayer');self.spawns_button.setText('• Spawns');self.spawns_button.setToolTip('Show monster spawn points')
        for button in (self.portals_button,self.spawns_button):
            button.setCheckable(True);button.setChecked(True);button.toggled.connect(self.update);layers.addWidget(button)
        self.spawns_button.hide();self.layers.adjustSize()
        self.setToolTip('Scroll to zoom · drag to pan · double-click to fit')

    def button(self,caption,description,action):
        button=QToolButton(self.controls);button.setText(caption);button.setToolTip(description)
        button.setAccessibleName(description);button.clicked.connect(action);return button

    def set_geometry(self,proof,names=None,destinations=None,preview=None):
        names=names or {};destinations=destinations or {};preview=preview if preview is not None else QImage()
        if (proof==self.geometry_proof and names==self.names and destinations==self.destinations
                and preview.cacheKey()==self.preview_image.cacheKey()):return
        self.geometry_proof=proof;self.names=names;self.destinations=destinations;self.preview_image=preview
        self.spawns_button.setVisible(bool(names));self.layers.adjustSize()
        self.markers=[];self.portal_markers=[];self._hover=None;self.clamp_pan();self.update()

    def image(self):
        if self.geometry_proof and self.geometry_proof.get('preview') and not self.preview_image.isNull():return self.preview_image
        return self.media.image(self.row.get('minimap_url',''))

    def viewport_rect(self):return QRectF(self.rect()).adjusted(10,9,-10,-34)

    def source_bounds(self,image):
        key=image.cacheKey()
        if key!=getattr(self,'_image_key',None):
            self._image_key=key;self._source=image.rect()
            if image.hasAlphaChannel():
                bounds=QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect()
                if not bounds.isEmpty():self._source=bounds.adjusted(-2,-2,2,2).intersected(image.rect())
        return self._source

    def fit_size(self):
        image=self.image()
        if image.isNull():return None
        size=self.source_bounds(image).size();size.scale(self.viewport_rect().size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
        return size

    def target_rect(self):
        size=self.fit_size()
        if size is None or size.isEmpty():return QRectF()
        width,height=size.width()*self.zoom,size.height()*self.zoom;center=self.viewport_rect().center()+self.pan
        return QRectF(center.x()-width/2,center.y()-height/2,width,height)

    def clamp_pan(self):
        size=self.fit_size()
        if size is None:return
        viewport=self.viewport_rect();limit_x=max(0,(size.width()*self.zoom-viewport.width())/2);limit_y=max(0,(size.height()*self.zoom-viewport.height())/2)
        self.pan=QPointF(max(-limit_x,min(limit_x,self.pan.x())),max(-limit_y,min(limit_y,self.pan.y())))

    def update_controls(self):
        self.zoom_out.setEnabled(self.zoom>1.001);self.fit_button.setEnabled(self.zoom>1.001)
        self.zoom_in.setEnabled(self.zoom<self.MAX_ZOOM-.001)

    def zoom_at(self,factor,anchor=None):
        old=self.target_rect()
        if old.isEmpty():return
        anchor=anchor or self.viewport_rect().center();zoom=max(1.0,min(self.MAX_ZOOM,self.zoom*factor))
        if zoom==self.zoom:return
        ratio=zoom/self.zoom;relative=anchor-old.topLeft();width,height=old.width()*ratio,old.height()*ratio
        left=anchor.x()-relative.x()*ratio;top=anchor.y()-relative.y()*ratio
        self.zoom=zoom;self.pan=QPointF(left+width/2,top+height/2)-self.viewport_rect().center()
        self.clamp_pan();self.update_controls();QToolTip.hideText();self.update()

    def fit(self):
        self.zoom=1.0;self.pan=QPointF();self._hover=None;self.update_controls();self.update()

    def view_state(self):return dict(zoom=self.zoom,x=self.pan.x(),y=self.pan.y(),portals=self.portals_button.isChecked(),spawns=self.spawns_button.isChecked())

    def restore_view(self,state):
        if not isinstance(state,dict):return
        values=[state.get(key,default) for key,default in (('zoom',1),('x',0),('y',0))]
        if not all(type(v) in (int,float) and isfinite(v) for v in values):return
        self.zoom=max(1.0,min(self.MAX_ZOOM,values[0]));self.pan=QPointF(values[1],values[2])
        for key,button in (('portals',self.portals_button),('spawns',self.spawns_button)):
            if type(state.get(key)) is bool:button.setChecked(state[key])
        self.clamp_pan();self.update_controls();self.update()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.controls.move(max(5,self.width()-self.controls.width()-6),self.height()-self.controls.height()-5)
        self.layers.move(6,self.height()-self.layers.height()-5);self.clamp_pan()

    def projected(self,point,image,source,target,*,spawn=False):
        proof=self.geometry_proof;dx,dy=(proof.get('dx',0),proof.get('dy',0)) if spawn else (0,0)
        x=((point['x']+dx)/proof['width']*image.width()-source.x())/source.width()
        y=((point['y']+dy)/proof['height']*image.height()-source.y())/source.height()
        if not (0<=x<=1 and 0<=y<=1):return None
        center=QPointF(target.x()+x*target.width(),target.y()+y*target.height())
        return center if self.viewport_rect().contains(center) else None

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing,True)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#202a38'));painter.drawRoundedRect(self.rect(),8,8)
        image=self.image();self.markers=[];self.portal_markers=[]
        if image.isNull():
            painter.setPen(QColor('#93a5bd'));painter.drawText(self.viewport_rect(),Qt.AlignmentFlag.AlignCenter,'Minimap loading…');return
        source=self.source_bounds(image);target=self.target_rect();painter.save();painter.setClipRect(self.viewport_rect())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False);painter.drawImage(target,image,QRectF(source))
        proof=self.geometry_proof
        verified=bool(proof and (proof.get('projection_verified') or proof.get('preview') and not self.preview_image.isNull()))
        if verified and proof.get('projection_verified') and abs((image.width()/image.height())/(proof['width']/proof['height'])-1)>.025:verified=False
        if verified:
            if proof.get('spawns_verified',True) and self.spawns_button.isChecked():
                for point in self.row.get('mobs',[]):
                    if point.get('mob_id') not in self.names:continue
                    center=self.projected(point,image,source,target,spawn=True)
                    if center is None:continue
                    painter.setPen(QPen(QColor('#171c25'),1.5));painter.setBrush(QColor('#ffc66f'));painter.drawEllipse(center,3.5,3.5)
                    self.markers.append((center,point['mob_id']))
            for point in proof.get('portals',[]) if self.portals_button.isChecked() else []:
                center=self.projected(point,image,source,target)
                if center is None:continue
                center-=QPointF(0,4);destination=self.destinations.get(point['dest_map_id'],{})
                local=point['dest_map_id']==self.row.get('id');available=bool(destination.get('target')) or local
                colour=QColor('#79d8ac' if local else '#69cfff' if available else '#96a2b2')
                painter.setPen(QPen(QColor('#10222f'),4));painter.setBrush(QColor('#152e41'));painter.drawEllipse(center,4,5)
                painter.setPen(QPen(colour,2,Qt.PenStyle.DashLine if point['type']==3 else Qt.PenStyle.SolidLine));painter.drawEllipse(center,4,5)
                if self._hover==(point['name'],point['dest_map_id']):painter.setPen(QPen(QColor('#ffffff'),1));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawEllipse(center,6,7)
                self.portal_markers.append((center,point,destination))
        painter.restore()

    def target_at(self,point):
        nearby=sorted(((center-point).manhattanLength(),identity) for center,identity in self.markers)
        return nearby[0][1] if nearby and nearby[0][0]<9 else None

    def portal_at(self,point):
        nearby=sorted(enumerate(self.portal_markers),key=lambda item:(item[1][0]-point).manhattanLength())
        return nearby[0][1] if nearby and (nearby[0][1][0]-point).manhattanLength()<11 else None

    def mouseMoveEvent(self,event):
        point=event.position()
        if self._press is not None:
            delta=point-self._press
            if delta.manhattanLength()>=QApplication.startDragDistance():self._dragging=True
            if self._dragging:
                self.pan=self._pan_start+delta;self.clamp_pan();self.setCursor(Qt.CursorShape.ClosedHandCursor);QToolTip.hideText();self.update();return
        portal=self.portal_at(point) if self.viewport_rect().contains(point) else None
        identity=None if portal else self.target_at(point)
        hover=(portal[1]['name'],portal[1]['dest_map_id']) if portal else None
        if hover!=self._hover:self._hover=hover;self.update()
        if portal:
            _,record,destination=portal;local=record['dest_map_id']==self.row.get('id')
            caption=destination.get('name','Destination not confirmed')
            detail='Within this map' if local else 'Hidden portal' if record['type']==3 else 'Portal'
            if destination.get('target') and not local:detail+=' · click to open'
            QToolTip.showText(event.globalPosition().toPoint(),caption+'\n'+detail,self)
        elif identity is not None:QToolTip.showText(event.globalPosition().toPoint(),self.names[identity],self)
        else:QToolTip.hideText()
        clickable=bool(portal and portal[2].get('target') and portal[1]['dest_map_id']!=self.row.get('id')) or identity is not None
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.OpenHandCursor if self.zoom>1 else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.viewport_rect().contains(event.position()):
            self._press=event.position();self._pan_start=QPointF(self.pan);self._dragging=False;event.accept()
        else:super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self._press is None:return super().mouseReleaseEvent(event)
        click=not self._dragging and self.viewport_rect().contains(event.position());self._press=None;self._dragging=False;QToolTip.hideText()
        if click:
            portal=self.portal_at(event.position())
            if portal:
                target=portal[2].get('target')
                if target and target!=('maps',self.row.get('id')):self.map_chosen.emit(target[1])
            else:
                identity=self.target_at(event.position())
                if identity is not None:self.chosen.emit(identity)
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.zoom>1 else Qt.CursorShape.ArrowCursor);event.accept()

    def wheelEvent(self,event):
        if not self.viewport_rect().contains(event.position()):event.ignore();return
        delta=event.angleDelta().y() or event.pixelDelta().y()
        if delta:self.zoom_at(1.25**max(-4,min(4,delta/120)),event.position())
        event.accept()

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self._press=None;self.fit();event.accept()
        else:super().mouseDoubleClickEvent(event)

    def leaveEvent(self,event):
        self._hover=None;QToolTip.hideText();self.update();super().leaveEvent(event)
