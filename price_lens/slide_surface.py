"""Temporary, opaque slide composition for Lupin-owned QWidget pages.

The actual pages retain their geometry, focus and input. Only their repeated
painting is replaced while moving. No desktop/input filter or idle timer exists.
"""
import weakref

from PySide6.QtCore import QEvent,QPoint,QRect,Qt
from PySide6.QtGui import QPainter,QPalette,QRegion
from PySide6.QtWidgets import (QAbstractButton,QAbstractItemView,QAbstractScrollArea,QAbstractSlider,
                              QComboBox,QLineEdit,QPlainTextEdit,QTextEdit,QGraphicsOpacityEffect,QWidget)
from shiboken6 import isValid

from .widget_lifetime import retire_widget


def invalidate_surface(widget,rect=None):
    for ref in getattr(widget,'_motion_surfaces',()):
        surface=ref()
        if surface is not None and isValid(surface):surface.invalidate(widget,rect)


class SlideSurface(QWidget):
    def __init__(self,owner,host):
        super().__init__(host)
        self.owner=owner;self.pictures={};self.pages={};self.nodes={};self.dirty={}
        self.connections=[];self.models=set();self.effects=set();self.rescan=False;self.capturing=False;self.closed=False
        self.ref=weakref.ref(self)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setGeometry(host.contentsRect())
        parent=host;self.background=owner.window().palette().color(QPalette.ColorRole.Window)
        while parent is not None:
            colour=parent.palette().color(QPalette.ColorRole.Window)
            if colour.alpha()==255:self.background=colour;break
            parent=parent.parentWidget()

    def set_pages(self,pages):
        self.pages=dict(pages)
        existing=set(self.pictures)
        self.pictures={index:picture for index,picture in self.pictures.items() if index in self.pages}
        self.dirty={index:rect for index,rect in self.dirty.items() if index in self.pages}
        self.register_nodes()
        for index,page in self.pages.items():
            if index not in self.pictures:self.capture(index)
        # The selected page can have changed its text/size during retargeting.
        if self.owner.currentIndex() in existing:self.capture(self.owner.currentIndex())
        self.setGeometry(self.parentWidget().contentsRect());self.show();self.raise_()

    def register_nodes(self):
        for index,page in self.pages.items():
            for widget in (page,*page.findChildren(QWidget)):
                if getattr(widget,'_motion_style_only',False):continue
                effect=widget.graphicsEffect()
                if isinstance(effect,QGraphicsOpacityEffect) and effect not in self.effects:
                    self.effects.add(effect);callback=lambda *_,widget=widget:self.invalidate(widget)
                    effect.opacityChanged.connect(callback);self.connections.append((effect.opacityChanged,callback))
                if widget in self.nodes:continue
                self.nodes[widget]=index
                refs=tuple(ref for ref in getattr(widget,'_motion_surfaces',()) if ref() is not None)
                widget._motion_surfaces=(*refs,self.ref)
                widget.installEventFilter(self)
                signals=[]
                if isinstance(widget,QLineEdit):signals=[widget.textChanged,widget.selectionChanged,widget.cursorPositionChanged]
                elif isinstance(widget,(QPlainTextEdit,QTextEdit)):signals=[widget.textChanged,widget.selectionChanged,widget.cursorPositionChanged]
                elif isinstance(widget,QAbstractButton):signals=[widget.pressed,widget.released,widget.toggled]
                elif isinstance(widget,QComboBox):signals=[widget.currentIndexChanged]
                elif isinstance(widget,QAbstractSlider):signals=[widget.valueChanged]
                for signal in signals:
                    callback=lambda *_,widget=widget:self.invalidate(widget)
                    signal.connect(callback);self.connections.append((signal,callback))
                if isinstance(widget,QAbstractItemView):
                    model=widget.model()
                    if model is not None and model not in self.models:
                        self.models.add(model)
                        for signal in (model.dataChanged,model.rowsInserted,model.rowsRemoved,model.modelReset,model.layoutChanged):
                            callback=lambda *_,view=widget:self.invalidate(view.viewport())
                            signal.connect(callback);self.connections.append((signal,callback))
                if isinstance(widget,QAbstractScrollArea):
                    for bar in (widget.verticalScrollBar(),widget.horizontalScrollBar()):
                        callback=lambda *_,view=widget:self.invalidate(view.viewport())
                        bar.valueChanged.connect(callback);self.connections.append((bar.valueChanged,callback))
        self.rescan=False

    def invalidate(self,widget,rect=None):
        if self.closed or self.capturing or not isValid(widget):return
        index=self.nodes.get(widget);page=self.pages.get(index)
        if page is None or not isValid(page):return
        if widget is not page and not page.isAncestorOf(widget):return
        if rect is None:rect=widget.rect()
        region=QRegion(rect).translated(widget.mapTo(page,QPoint())).intersected(page.rect())
        if region.isEmpty():return
        self.dirty[index]=self.dirty.get(index,QRegion()).united(region)

    def capture(self,index,rect=None):
        page=self.pages.get(index)
        if page is None or not isValid(page):return
        self.capturing=True
        try:
            picture=self.pictures.get(index)
            if (rect is None or picture is None or picture.deviceIndependentSize().toSize()!=page.size()
                    or picture.devicePixelRatio()!=page.devicePixelRatioF()):
                self.pictures[index]=page.grab()
            else:
                painter=QPainter(picture)
                region=QRegion(rect);painter.setClipRegion(region)
                # QWidget.render maps the source region's origin to targetOffset.
                page.render(painter,region.boundingRect().topLeft(),region)
                painter.end()
        finally:self.capturing=False
        self.dirty.pop(index,None)

    def frame(self):
        if self.closed:return
        if self.rescan:self.register_nodes()
        invalidate_surface(self)
        self.update()

    def paintEvent(self,event):
        if self.closed:return
        for index,rect in tuple(self.dirty.items()):self.capture(index,rect)
        painter=QPainter(self);painter.fillRect(self.rect(),self.background)
        for index,picture in self.pictures.items():
            x=self.owner.base.left()+round((index-self.owner.scroll)*self.owner.slide_width)
            if x<self.width() and x+picture.deviceIndependentSize().width()>0:
                painter.drawPixmap(x,self.owner.base.top(),picture)

    def eventFilter(self,widget,event):
        kind=event.type()
        if kind in (QEvent.Type.ChildAdded,QEvent.Type.ChildRemoved):
            self.rescan=True
            index=self.nodes.get(widget)
            if index in self.pages:self.dirty[index]=QRegion(self.pages[index].rect())
        elif not self.capturing and kind in (QEvent.Type.LayoutRequest,QEvent.Type.Resize,QEvent.Type.StyleChange,QEvent.Type.Show,QEvent.Type.Hide):
            index=self.nodes.get(widget)
            if index in self.pages:self.dirty[index]=QRegion(self.pages[index].rect())
        elif kind in (QEvent.Type.FocusIn,QEvent.Type.FocusOut,QEvent.Type.Enter,QEvent.Type.Leave,
                      QEvent.Type.HoverEnter,QEvent.Type.HoverLeave,QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease):
            self.invalidate(widget)
        return False

    def dispose(self):
        if self.closed:return
        self.closed=True
        for signal,callback in self.connections:
            try:signal.disconnect(callback)
            except (RuntimeError,TypeError):pass
        for widget in self.nodes:
            if not isValid(widget):continue
            widget.removeEventFilter(self)
            widget._motion_surfaces=tuple(ref for ref in getattr(widget,'_motion_surfaces',()) if ref is not self.ref and ref() is not None)
        self.connections.clear();self.models.clear();self.effects.clear();self.nodes.clear();self.pages.clear();self.pictures.clear();self.dirty.clear()
        retire_widget(self.owner,self)
