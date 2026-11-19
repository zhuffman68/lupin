"""A zoomable map preview with independently verified spawn and portal positions."""
from math import isfinite
from PySide6.QtCore import Qt, QPointF, QRect, QRectF, QTimer, Signal
from PySide6.QtGui import QBitmap, QColor, QFont, QImage, QPainter, QPen, QRegion
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMenu, QToolButton, QWidget, QToolTip


def portal_key(point):
    return (point['name'], point['type'], point['dest_map_id'], point.get('dest_portal') or '', point['x'], point['y'])


class MapPreview(QWidget):
    def redraw(self,*_):
        from .slide_surface import invalidate_surface
        self.sync_portal_label()
        invalidate_surface(self);super().update()

    chosen=Signal(int)
    map_chosen=Signal(int)
    MAX_ZOOM=8.0

    def __init__(self,media,row,parent=None):
        super().__init__(parent);self.media=media;self.row=row;self.geometry_proof=None
        self.markers=[];self.portal_markers=[];self.names={};self.destinations={};self.preview_image=QImage()
        self.zoom=1.0;self.pan=QPointF();self._press=None;self._dragging=False;self._hover=None
        self.portals = {}
        self.selected_portal = None
        self._pressed_target = None
        self.setFixedHeight(156);self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Zoomable map with portals and monster spawn positions')
        self.setAccessibleDescription('Scroll to zoom. Drag to pan. Hover over a portal or use Find portal. Click a portal to open its map.')
        self.controls=QFrame(self);self.controls.setObjectName('mapControls')
        self.controls.setStyleSheet('QFrame#mapControls{background:#263448;border-radius:5px;} QToolButton{color:#d3dfed;background:transparent;border:0;border-radius:4px;padding:2px 6px;min-height:18px;} QToolButton:hover{background:#405773;} QToolButton:disabled{color:#64758c;}')
        layout=QHBoxLayout(self.controls);layout.setContentsMargins(2,1,2,1);layout.setSpacing(1)
        self.zoom_out=self.button('−','Zoom out',lambda:self.zoom_at(1/1.5))
        self.fit_button=self.button('Fit','Fit the whole map · double-click the map',self.fit)
        self.zoom_in=self.button('+','Zoom in',lambda:self.zoom_at(1.5))
        for button in (self.zoom_out,self.fit_button,self.zoom_in):layout.addWidget(button)
        self.controls.adjustSize();self.update_controls()
        self.layers=QFrame(self);self.layers.setObjectName('mapLayers')
        self.layers.setStyleSheet('QFrame#mapLayers{background:transparent;} QToolButton{color:#9aadc5;background:transparent;border:0;border-radius:4px;padding:2px 5px;min-height:18px;font-size:10px;} QToolButton:hover{background:#304258;} QToolButton:checked{background:#2b4057;color:#69cfff;} QToolButton#spawnLayer:checked{color:#ffc66f;} QToolButton:disabled{color:#677991;}')
        layers=QHBoxLayout(self.layers);layers.setContentsMargins(0,0,0,0);layers.setSpacing(3)
        self.portals_button=QToolButton(self.layers);self.portals_button.setText('○ Portals');self.portals_button.setToolTip('Show portals and their destinations')
        self.spawns_button=QToolButton(self.layers);self.spawns_button.setObjectName('spawnLayer');self.spawns_button.setText('• Spawns');self.spawns_button.setToolTip('Show monster spawn points')
        for button in (self.portals_button,self.spawns_button):
            button.setCheckable(True);button.setChecked(True);button.toggled.connect(self.redraw);layers.addWidget(button)
        self.portal_picker = QToolButton(self.layers)
        self.portal_picker.setObjectName('findPortal')
        self.portal_picker.setStyleSheet('QToolButton#findPortal{background:#27394e;color:#c4d7ea;'
                                         'padding:2px 17px 2px 6px;}'
                                         'QToolButton#findPortal:hover{background:#385169;}'
                                         'QToolButton#findPortal:disabled{background:transparent;color:#677991;}'
                                         'QToolButton#findPortal::menu-indicator{subcontrol-origin:padding;'
                                         'subcontrol-position:right center;right:4px;}')
        self.portal_picker.setText('Find portal')
        self.portal_picker.setToolTip('Locate a portal by its destination')
        self.portal_picker.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.portal_picker.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.portal_menu = QMenu(self.portal_picker)
        self.portal_menu.setStyleSheet('QMenu{background:#172334;color:#dae7f5;border:1px solid #405671;'
                                       'padding:4px;menu-scrollable:1;}'
                                       'QMenu::item{padding:4px 12px;}'
                                       'QMenu::item:selected{background:#304861;color:#eef5fc;}')
        self.portal_menu.aboutToShow.connect(self.populate_portal_menu)
        self.portal_picker.setMenu(self.portal_menu)
        self.portal_picker.setEnabled(False)
        layers.addWidget(self.portal_picker)
        self.spawns_button.hide();self.layers.adjustSize()
        self.portal_label = QLabel(self)
        self.portal_label.setAccessibleName('Portal destination')
        self.portal_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.portal_label.setTextFormat(Qt.TextFormat.PlainText)
        self.portal_label.setWordWrap(True)
        self.portal_label.setMargin(5)
        self.portal_label.setStyleSheet('background:#142234;color:#eef5fc;border:1px solid #5c7993;'
                                        'border-radius:5px;font-size:11px;font-weight:600;')
        self.portal_label.hide()

    def button(self,caption,description,action):
        button=QToolButton(self.controls);button.setText(caption);button.setToolTip(description)
        button.setAccessibleName(description);button.clicked.connect(action);return button

    def set_geometry(self,proof,names=None,destinations=None,preview=None):
        names=names or {};destinations=destinations or {};preview=preview if preview is not None else QImage()
        if (proof==self.geometry_proof and names==self.names and destinations==self.destinations
                and preview.cacheKey()==self.preview_image.cacheKey()):return
        self.geometry_proof=proof;self.names=names;self.destinations=destinations;self.preview_image=preview
        if proof and proof['height'] > proof['width']:
            axis, cross = 'y', 'x'
        else:
            axis, cross = 'x', 'y'
        points = sorted((proof or {}).get('portals', ()), key=lambda p: (p[axis], p[cross], portal_key(p)))
        self.portals = {portal_key(point): (index, point) for index, point in enumerate(points, 1)}
        if proof and self.selected_portal not in self.portals:
            self.selected_portal = None
        self.portal_menu.close()
        self._pressed_target = None
        self._image_key = None
        self.spawns_button.setVisible(bool(names));self.layers.adjustSize()
        self.markers=[];self.portal_markers=[];self._hover=None;self.clamp_pan();self.redraw()

    def image(self):
        if self.geometry_proof and self.geometry_proof.get('preview') and not self.preview_image.isNull():return self.preview_image
        return self.media.image(self.row.get('minimap_url',''))

    def viewport_rect(self):return QRectF(self.rect()).adjusted(10,9,-10,-34)

    def verified_view(self, image):
        proof = self.geometry_proof
        if image.isNull() or not proof:
            return False
        if proof.get('projection_verified'):
            return abs((image.width()/image.height())/(proof['width']/proof['height'])-1) <= .025
        return bool(proof.get('preview') and not self.preview_image.isNull())

    def source_bounds(self,image):
        key=image.cacheKey()
        if key!=getattr(self,'_image_key',None):
            self._image_key=key;self._source=image.rect()
            if image.hasAlphaChannel():
                bounds=QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect()
                if not bounds.isEmpty():
                    # A verified entrance can lie in a transparent margin of
                    # the provider's render. Keep it inside the fitted view.
                    if self.verified_view(image):
                        proof = self.geometry_proof
                        for _, point in self.portals.values():
                            x = int(point['x'] * image.width() / proof['width'])
                            y = int(point['y'] * image.height() / proof['height'])
                            bounds = bounds.united(QRect(x, y, 1, 1))
                    self._source=bounds.adjusted(-2,-2,2,2).intersected(image.rect())
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
        self.zoom=zoom;self.pan=QPointF(left+width/2,top+height/2)-self.viewport_rect().center();self._hover=None
        self.clamp_pan();self.update_controls();QToolTip.hideText();self.redraw()

    def fit(self):
        self.zoom=1.0;self.pan=QPointF();self._hover=None;self.update_controls();self.redraw()

    def view_state(self):
        return dict(zoom=self.zoom, x=self.pan.x(), y=self.pan.y(), portals=self.portals_button.isChecked(),
                    spawns=self.spawns_button.isChecked(), selected_portal=self.selected_portal)

    def restore_view(self,state):
        if not isinstance(state,dict):return
        values=[state.get(key,default) for key,default in (('zoom',1),('x',0),('y',0))]
        if not all(type(v) in (int,float) and isfinite(v) for v in values):return
        self.zoom=max(1.0,min(self.MAX_ZOOM,values[0]));self.pan=QPointF(values[1],values[2])
        saved = state.get('selected_portal')
        self.selected_portal = saved if isinstance(saved, tuple) else None
        for key,button in (('portals',self.portals_button),('spawns',self.spawns_button)):
            if type(state.get(key)) is bool:button.setChecked(state[key])
        self.clamp_pan();self.update_controls();self.redraw()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.controls.move(max(5,self.width()-self.controls.width()-6),self.height()-self.controls.height()-5)
        self.layers.move(6,self.height()-self.layers.height()-5);self.clamp_pan();self.sync_portal_label()

    def projected(self,point,image,source,target,*,spawn=False,clip=True):
        proof=self.geometry_proof;dx,dy=(proof.get('dx',0),proof.get('dy',0)) if spawn else (0,0)
        x=((point['x']+dx)/proof['width']*image.width()-source.x())/source.width()
        y=((point['y']+dy)/proof['height']*image.height()-source.y())/source.height()
        if not (0<=x<=1 and 0<=y<=1):return None
        center=QPointF(target.x()+x*target.width(),target.y()+y*target.height())
        return center if not clip or self.viewport_rect().contains(center) else None

    def portal_center(self, point, image, source, target):
        center = self.projected(point, image, source, target)
        if center is None:
            return None
        inset = self.viewport_rect().adjusted(9, 9, -9, -9)
        return QPointF(min(inset.right(), max(inset.left(), center.x())),
                       min(inset.bottom(), max(inset.top(), center.y()-4)))

    def paired_portal(self, point):
        if point['dest_map_id'] != self.row.get('id') or not point.get('dest_portal'):
            return None
        keys = [key for key in self.portals if key[0] == point['dest_portal'] and key != portal_key(point)]
        return keys[0] if len(keys) == 1 else None

    def portal_caption(self, key):
        number, point = self.portals[key]
        if point['dest_map_id'] == self.row.get('id'):
            paired = self.paired_portal(point)
            name = f'Portal {self.portals[paired][0]} on this map' if paired else 'Within this map'
        else:
            name = self.destinations.get(point['dest_map_id'], {}).get('name', 'Destination unknown')
        suffix = ' · Hidden' if point['type'] == 3 else ''
        return f'{number}  →  {name}{suffix}'

    def populate_portal_menu(self):
        self.portal_menu.clear()
        for key in self.portals:
            action = self.portal_menu.addAction(self.portal_caption(key).replace('&', '&&'))
            action.triggered.connect(lambda _checked=False, key=key: self.locate_portal(key))

    def locate_portal(self, key):
        entry = self.portals.get(key)
        image = self.image()
        if not entry or not self.verified_view(image):
            return
        _, point = entry
        center = self.projected(point, image, self.source_bounds(image), self.target_rect(), clip=False)
        if center is None:
            return
        viewport = self.viewport_rect()
        if not viewport.adjusted(12, 12, -12, -12).contains(center):
            self.pan += viewport.center() - center
            self.clamp_pan()
        self._hover = None
        self.selected_portal = key
        self.portals_button.setChecked(True)
        # Let the popup finish restoring its previous focus first.
        QTimer.singleShot(0, self, self.focus_selected_portal)
        self.redraw()

    def focus_selected_portal(self):
        if self.isVisible() and self.selected_portal in self.portals:
            self.setFocus(Qt.FocusReason.OtherFocusReason)

    def sync_portal_label(self):
        image = self.image()
        available = bool(self.portals) and self.verified_view(image)
        self.portal_picker.setEnabled(available)
        key = self._hover or self.selected_portal
        entry = self.portals.get(key)
        if not (available and entry and self.portals_button.isChecked() and not self._dragging):
            self.portal_label.hide()
            return
        center = self.portal_center(entry[1], image, self.source_bounds(image), self.target_rect())
        if center is None:
            self.portal_label.hide()
            return
        caption = self.portal_caption(key)
        label = self.portal_label
        if label.text() != caption:
            label.setText(caption)
        area = self.viewport_rect().toAlignedRect().adjusted(2, 2, -2, -2)
        width = min(246, area.width(), label.fontMetrics().horizontalAdvance(caption)+16)
        if width < 20:
            label.hide()
            return
        height = label.heightForWidth(width)
        x = max(area.left(), min(round(center.x()-width/2), area.right()+1-width))
        y = round(center.y()) - 13 - height
        if y < area.top():
            y = min(round(center.y())+13, area.bottom()+1-height)
        if height <= 0 or y < area.top():
            label.hide()
            return
        label.setGeometry(x, y, width, height)
        label.show()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing,True)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#202a38'));painter.drawRoundedRect(self.rect(),8,8)
        image=self.image();self.markers=[];self.portal_markers=[]
        if image.isNull():
            painter.setPen(QColor('#93a5bd'));painter.drawText(self.viewport_rect(),Qt.AlignmentFlag.AlignCenter,'Minimap loading…');return
        source=self.source_bounds(image);target=self.target_rect();painter.save();painter.setClipRect(self.viewport_rect())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False);painter.drawImage(target,image,QRectF(source))
        proof=self.geometry_proof
        if self.verified_view(image):
            if proof.get('spawns_verified',True) and self.spawns_button.isChecked():
                for point in self.row.get('mobs',[]):
                    if point.get('mob_id') not in self.names:continue
                    center=self.projected(point,image,source,target,spawn=True)
                    if center is None:continue
                    painter.setPen(QPen(QColor('#171c25'),1.5));painter.setBrush(QColor('#ffc66f'));painter.drawEllipse(center,3.5,3.5)
                    self.markers.append((center,point['mob_id']))
            self.paint_portals(painter, image, source, target)
        painter.restore()

    def paint_portals(self, painter, image, source, target):
        if not self.portals_button.isChecked():
            return
        active = self._hover or self.selected_portal
        entry = self.portals.get(active)
        paired = self.paired_portal(entry[1]) if entry else None
        font = QFont(self.font())
        font.setPixelSize(10)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        labels, dots = [], []
        occupied = QRegion()
        # Reserve the highlighted entrances first. Other overlapping pins
        # remain small selectable dots at their verified positions.
        order = sorted(self.portals, key=lambda key: 0 if key == active else 1 if key == paired else 2)
        for key in order:
            number, point = self.portals[key]
            center = self.portal_center(point, image, source, target)
            if center is None:
                continue
            destination = self.destinations.get(point['dest_map_id'], {})
            local = point['dest_map_id'] == self.row.get('id')
            color = QColor('#79d8ac' if local else '#69cfff' if destination.get('target') else '#96a2b2')
            radius = max(8, painter.fontMetrics().horizontalAdvance(str(number))/2+3)
            bounds = QRectF(center.x()-radius, center.y()-8, radius*2, 16)
            self.portal_markers.append((center, point, destination))
            footprint = bounds.adjusted(-2, -2, 2, 2).toAlignedRect()
            if key not in (active, paired) and occupied.intersects(footprint):
                dots.append((center, color))
            else:
                occupied |= QRegion(footprint)
                labels.append((key, point['type'], number, bounds, color))
        for center, color in dots:
            painter.setPen(QPen(QColor('#122234'), 1))
            painter.setBrush(color)
            painter.drawEllipse(center, 3, 3)
        # Draw selected pins last so they remain legible on top of the layer.
        for key, kind, number, bounds, color in reversed(labels):
            if key in (active, paired):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor('#eef5fc' if key == active else '#79d8ac'))
                painter.drawEllipse(bounds.adjusted(-2, -2, 2, 2))
            painter.setPen(QPen(color, 1.5, Qt.PenStyle.DashLine if kind==3 else Qt.PenStyle.SolidLine))
            painter.setBrush(QColor('#122234'))
            painter.drawEllipse(bounds)
            painter.setPen(QColor('#eef5fc'))
            painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter, str(number))

    def target_at(self,point):
        nearby=sorted(((center-point).manhattanLength(),identity) for center,identity in self.markers)
        return nearby[0][1] if nearby and nearby[0][0]<9 else None

    def portal_at(self,point):
        image = self.image()
        if not (self.portals_button.isChecked() and self.viewport_rect().contains(point) and self.verified_view(image)):
            return None
        source, target = self.source_bounds(image), self.target_rect()
        nearest = None
        best = (12, False)
        for key, (_, record) in self.portals.items():
            center = self.portal_center(record, image, source, target)
            if center is None:
                continue
            score = ((center-point).manhattanLength(), key != self.selected_portal)
            if score < best:
                best = score
                nearest = (center, record, self.destinations.get(record['dest_map_id'], {}))
        return nearest

    def open_portal(self, key):
        entry = self.portals.get(key)
        if not (entry and self.portals_button.isChecked() and self.verified_view(self.image())):
            return
        _, point = entry
        target = self.destinations.get(point['dest_map_id'], {}).get('target')
        if point['dest_map_id'] != self.row.get('id') and target == ('maps', point['dest_map_id']):
            self.map_chosen.emit(target[1])
        else:
            self.locate_portal(key)

    def mouseMoveEvent(self,event):
        point=event.position()
        if self._press is not None:
            delta=point-self._press
            if delta.manhattanLength()>=QApplication.startDragDistance():self._dragging=True
            if self._dragging:
                self._hover=None;self.pan=self._pan_start+delta;self.clamp_pan();self.setCursor(Qt.CursorShape.ClosedHandCursor);QToolTip.hideText();self.redraw();return
        portal=self.portal_at(point) if self.viewport_rect().contains(point) else None
        identity=None if portal else self.target_at(point)
        hover=portal_key(portal[1]) if portal else None
        if hover!=self._hover:self._hover=hover;self.redraw()
        if identity is not None:QToolTip.showText(event.globalPosition().toPoint(),self.names[identity],self)
        else:QToolTip.hideText()
        clickable=portal is not None or identity is not None
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.OpenHandCursor if self.zoom>1 else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.viewport_rect().contains(event.position()):
            portal = self.portal_at(event.position())
            self._pressed_target = portal_key(portal[1]) if portal else self.target_at(event.position())
            self._press=event.position();self._pan_start=QPointF(self.pan);self._dragging=False;event.accept()
        else:super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self._press is None:return super().mouseReleaseEvent(event)
        click=not self._dragging and self.viewport_rect().contains(event.position());self._press=None;self._dragging=False;QToolTip.hideText()
        pressed = self._pressed_target
        self._pressed_target = None
        portal = self.portal_at(event.position()) if click else None
        target = portal_key(portal[1]) if portal else self.target_at(event.position()) if click else None
        if click and pressed is None and target is None:
            self.selected_portal = None
        self.redraw()
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.zoom>1 else Qt.CursorShape.ArrowCursor);event.accept()
        if target is None or target != pressed:
            return
        if portal:
            self.open_portal(target)
        else:
            self.chosen.emit(target)

    def keyPressEvent(self, event):
        if self.selected_portal and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()
            self.open_portal(self.selected_portal)
        elif self.selected_portal and event.key() == Qt.Key.Key_Escape:
            self.selected_portal = None
            self.redraw();event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self,event):
        if not self.viewport_rect().contains(event.position()):event.ignore();return
        delta=event.angleDelta().y() or event.pixelDelta().y()
        if delta:self.zoom_at(1.25**max(-4,min(4,delta/120)),event.position())
        event.accept()

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self._press=None;self.fit();event.accept()
        else:super().mouseDoubleClickEvent(event)

    def leaveEvent(self,event):
        self._hover=None;QToolTip.hideText();self.redraw();super().leaveEvent(event)

    def hideEvent(self, event):
        self.portal_menu.close()
        self._hover = self._press = self._pressed_target = None
        self._dragging = False
        self.portal_label.hide()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_portal_label()
