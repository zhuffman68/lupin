"""Keep the live price summary steady while its detail tabs slide and resize."""
from PySide6.QtCore import QPoint
from PySide6.QtGui import QPainter
from .slide_surface import SlideSurface


class SummarySurface(SlideSurface):
    def __init__(self,card,parts):
        super().__init__(card,card)
        self.pages=dict(enumerate(parts));self.register_nodes()
        for index in self.pages:self.capture(index)
        self.sync_geometry();self.show();self.raise_()

    def sync_geometry(self):
        rectangles=[part.geometry() for part in self.pages.values()]
        rect=rectangles[0]
        for other in rectangles[1:]:rect=rect.united(other)
        if rect!=self.geometry():self.setGeometry(rect)

    def capture(self,index,rect=None):
        # These two small transparent sections need a fresh native background
        # when text shrinks. Compositing new ink over the old pixmap leaves
        # remnants; no full-card or subpage snapshot is required.
        super().capture(index)

    def invalidate(self,widget,rect=None):
        super().invalidate(widget,rect)
        if self.dirty:self.update()

    def eventFilter(self,widget,event):
        result=super().eventFilter(widget,event)
        if self.dirty:self.update()
        return result

    def paintEvent(self,event):
        if self.closed:return
        if self.rescan:self.register_nodes()
        for index,region in tuple(self.dirty.items()):self.capture(index,region)
        painter=QPainter(self);painter.fillRect(self.rect(),self.background)
        for index,picture in self.pictures.items():
            part=self.pages[index]
            painter.drawPixmap(part.mapTo(self.owner,QPoint())-self.pos(),picture)
