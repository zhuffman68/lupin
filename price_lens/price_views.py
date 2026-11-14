"""One full-height Prices viewport, retaining each view's scroll position."""
import weakref
from PySide6.QtCore import Signal,Qt,QTimer,QPoint,QRect
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QPushButton,QVBoxLayout,QWidget
from shiboken6 import isValid

from .motion import ContentArea
from .card_morph import background


class _PaneFrame(QWidget):
    """Separate whole views spatially; never crossfade their unrelated text."""
    def __init__(self,before,after,parent,direction):
        super().__init__(parent)
        self.before=before;self.after=after;self.direction=direction;self.progress=0.
        self.colour=background(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def replace_after(self,pixels,card):self.after=pixels

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),self.colour)
        distance=self.width()*self.direction
        painter.drawPixmap(round(-distance*self.progress),0,self.before)
        painter.drawPixmap(round(distance*(1-self.progress)),0,self.after)


class PriceViews(ContentArea):
    view_changed=Signal()

    def __init__(self,detail,screen,parent=None):
        super().__init__(parent)
        self.detail=detail;self.screen_view=screen;self.pane=None;self.view_key=None
        self.positions={'detail':0,'screen':0}
        self.identity=None;self.reset_detail=False
        self.route_before=None;self.dirty_frame=None
        self.route_positions={};self.route_layout_enabled=None
        self.destination_nodes=set();self.destination_ref=weakref.ref(self);self.capturing_destination=False
        self.refresh_timer=QTimer(self);self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.refresh_pending)
        self.switch_button=QPushButton('Back to on-screen items')
        self.switch_button.setCheckable(True)
        self.switch_button.toggled.connect(lambda *_:self.view_changed.emit())
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        layout.addWidget(self.switch_button,0,Qt.AlignmentFlag.AlignTop)
        layout.addWidget(detail,1);layout.addWidget(screen,1)
        self.switch_button.hide();detail.hide()

    def begin(self):
        prior=self.pane;super().begin();self.route_before=prior

    def make_frame(self,before,after,old_card,new_card):
        self.watch_destination()
        if self.route_before in ('detail','screen') and self.pane in ('detail','screen') and self.route_before!=self.pane:
            page=self.detail if self.pane=='detail' else self.screen_view
            self.route_positions={widget:QRect(widget.geometry()) for widget in (page,self.switch_button) if not widget.isHidden()}
            self.route_layout_enabled=self.layout().isEnabled();self.layout().setEnabled(False)
            return _PaneFrame(before,after,self,1 if self.pane=='detail' else -1)
        return super().make_frame(before,after,old_card,new_card)

    def position_route(self,progress):
        frame=self.outgoing
        if not isinstance(frame,_PaneFrame):return
        offset=QPoint(round(frame.direction*self.width()*(1-progress)),0)
        for widget,rect in self.route_positions.items():widget.move(rect.topLeft()+offset)

    def advance(self,progress):
        self.position_route(float(progress));super().advance(progress)

    def refresh_destination(self):
        # Capture destination coordinates, then restore the live controls to
        # their visible slide positions before any input can be processed.
        for widget,rect in self.route_positions.items():widget.setGeometry(rect)
        try:super().refresh_destination()
        finally:self.position_route(float(self.animation.currentValue() or 0))

    def watch_destination(self):
        page=self.detail if self.pane=='detail' else self.screen_view
        for widget in (page,*page.findChildren(QWidget)):
            if widget in self.destination_nodes:continue
            refs=tuple(ref for ref in getattr(widget,'_motion_surfaces',()) if ref() is not None)
            widget._motion_surfaces=(*refs,self.destination_ref);self.destination_nodes.add(widget)

    def invalidate(self,widget,rect=None):
        if not self.capturing_destination:self.queue_refresh()

    def queue_refresh(self,*_):
        if self.outgoing is not None:
            self.dirty_frame=self.outgoing
            if not self.refresh_timer.isActive():self.refresh_timer.start(0)

    def refresh_pending(self):
        frame,self.dirty_frame=self.dirty_frame,None
        if frame is not None and frame is self.outgoing:
            self.watch_destination();self.capturing_destination=True
            try:self.refresh_destination()
            finally:self.capturing_destination=False

    def finish(self):
        self.refresh_timer.stop();self.dirty_frame=None
        for widget,rect in self.route_positions.items():
            if isValid(widget):widget.setGeometry(rect)
        self.route_positions.clear()
        if self.route_layout_enabled is not None:
            self.layout().setEnabled(self.route_layout_enabled);self.route_layout_enabled=None
            self.layout().activate()
        for widget in self.destination_nodes:
            if isValid(widget):widget._motion_surfaces=tuple(ref for ref in getattr(widget,'_motion_surfaces',())
                                                          if ref is not self.destination_ref and ref() is not None)
        self.destination_nodes.clear();super().finish()

    def select_detail(self,identity=None):
        if identity!=self.identity:
            self.identity=identity;self.positions['detail']=0;self.reset_detail=True
        if self.switch_button.isChecked():
            blocked=self.switch_button.blockSignals(True)
            self.switch_button.setChecked(False);self.switch_button.blockSignals(blocked)

    def apply(self,*,detail,active,count,available):
        if not active:self.select_detail()
        screen=not active or self.switch_button.isChecked()
        pane='screen' if screen else 'detail' if detail else None
        navigation=active and available and not screen
        key=(pane,navigation)
        layout_changed=key!=self.view_key
        if layout_changed:
            if self.before is None:self.begin()
            self.view_key=key
        changed=pane!=self.pane
        areas={'detail':self.detail,'screen':self.screen_view}
        if changed and self.pane:self.positions[self.pane]=areas[self.pane].verticalScrollBar().value()
        self.pane=pane
        text=f'← On-screen items · {count}'
        if self.switch_button.text()!=text:
            self.switch_button.setText(text);self.switch_button.setAccessibleName(text)
        self.switch_button.setVisible(navigation)
        self.detail.setVisible(pane=='detail');self.screen_view.setVisible(pane=='screen')
        self.layout().activate()
        if pane=='detail' and self.reset_detail:
            self.detail.verticalScrollBar().setValue(0);self.reset_detail=False
        elif changed and pane:areas[pane].verticalScrollBar().setValue(self.positions[pane])
        self.complete()
        if not layout_changed:self.queue_refresh()
        return layout_changed
