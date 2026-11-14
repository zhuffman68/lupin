"""Bounded, cached Classic World item images. Separate from price API demand."""
import struct

from PySide6.QtCore import QObject,Signal,QSize,QRectF,QVariantAnimation,Qt
from PySide6.QtGui import QImage,QPainter,QColor
from PySide6.QtWidgets import QWidget
from .motion import enabled

BASE='https://osmsdataexplorer.com/data/current/images/items/'
MAX_BYTES=256*1024


def source_url(item_id):
    if not isinstance(item_id,int) or isinstance(item_id,bool) or not 1<=item_id<=99999999:raise ValueError('Invalid item ID')
    return BASE+f'{item_id:08d}.png'


def decode(data):
    if len(data)<24 or len(data)>MAX_BYTES or data[:8]!=b'\x89PNG\r\n\x1a\n':return QImage()
    width,height=struct.unpack('>II',data[16:24])
    if not 1<=width<=512 or not 1<=height<=512:return QImage()
    return QImage.fromData(data,'PNG')


class ThumbnailCache(QObject):
    """Exact-ID adapter to the shared disk/network/decoded-image service."""
    ready=Signal(int)

    def __init__(self,folder,parent=None,base_url=None,*,media=None):
        super().__init__(parent)
        from .reference_media import ReferenceMedia
        from .reference_data import image_url
        self.base_url=base_url;self.closed=False;self.owned=media is None
        if base_url and not base_url.startswith('http://127.0.0.1:'):raise ValueError('Only isolated loopback image fixtures may override the source')
        validator=(lambda url:url if url.startswith(base_url) else '') if base_url else image_url
        self.media=media or ReferenceMedia(folder,self,validator=validator,concurrency=2)
        self.media.ready.connect(self.on_ready)

    def url(self,item_id):
        source_url(item_id)  # Validate exactly the same IDs on either route.
        return self.base_url+f'{item_id:08d}.png' if self.base_url else source_url(item_id)

    def image(self,item_id):
        return self.media.image(self.url(item_id))

    def observe(self,items):
        if not self.closed:self.media.observe([self.url(item.game_id) for item in list(items)[:16]],owner='prices')

    @property
    def active(self):
        pending=dict(self.media.active)
        for url in self.media.processing:pending[url]=True
        if self.media.io_active and not self.media.io_active.startswith('@'):pending[self.media.io_active]=True
        for url in self.media.io_queue:
            if not url.startswith('@'):pending[url]=True
        return pending

    @property
    def queue(self):return self.media.queue

    def on_ready(self,url):
        prefix=self.base_url or BASE
        if not self.closed and url.startswith(prefix) and url.endswith('.png'):
            name=url[len(prefix):-4]
            if name.isdecimal():self.ready.emit(int(name))

    def close(self):
        if self.closed:return
        self.closed=True
        if self.owned:self.media.close()
        else:self.media.observe([],owner='prices')


class ItemImage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setFixedSize(42,42);self.image=QImage();self.alpha=1.0
        self.animation=QVariantAnimation(self);self.animation.setDuration(120)
        self.animation.valueChanged.connect(self.advance)
        self.setToolTip('Classic World item image')

    def advance(self,value):
        from .slide_surface import invalidate_surface
        self.alpha=float(value);invalidate_surface(self);self.update()

    def set_image(self,image):
        if self.image.cacheKey()==image.cacheKey():return
        self.animation.stop();self.image=image
        if enabled(self) and not image.isNull():self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()
        else:self.alpha=1.0
        from .slide_surface import invalidate_surface
        invalidate_surface(self)
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setPen(QColor('#3c4b5f'));painter.setBrush(QColor('#222c3b'));painter.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),5,5)
        if self.image.isNull():
            painter.setPen(QColor('#718097'));painter.drawRect(14,12,14,17);painter.drawLine(14,24,19,19);painter.drawLine(19,19,28,26)
        else:
            size=self.image.size().scaled(QSize(32,32),Qt.AspectRatioMode.KeepAspectRatio)
            painter.setOpacity(self.alpha);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
            painter.drawImage(QRectF((42-size.width())/2,(42-size.height())/2,size.width(),size.height()),self.image)

    def hideEvent(self,event):self.animation.stop();self.alpha=1.0;super().hideEvent(event)
