"""Bounded thumbnail prefetch and one source-timed visible monster animation."""
from collections import OrderedDict,deque
from concurrent.futures import ThreadPoolExecutor
import threading
import hashlib
import json
from pathlib import Path
import time
from PySide6.QtCore import QByteArray,QBuffer,QIODevice,QObject,QRect,QSize,QUrl,Qt,Signal,QEvent
from PySide6.QtGui import QColor,QImage,QImageReader,QMovie,QPainter
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkReply,QNetworkRequest
from PySide6.QtWidgets import QWidget
from .reference_data import image_url
from .motion import enabled

MAX_BYTES=4*1024*1024
TTL=30*86400
FAIL_TTL=6*3600


def decode(data):
    if not 24<=len(data)<=MAX_BYTES:return QImage()
    if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data[:4]==b'RIFF' and data[8:12]==b'WEBP'):return QImage()
    buffer=QBuffer();buffer.setData(QByteArray(data));buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buffer);size=reader.size();frames=max(1,reader.imageCount())
    if not(0<size.width()<=1024 and 0<size.height()<=1024 and frames<=160
            and size.width()*size.height()*frames*4<=32*1024*1024):return QImage()
    return reader.read()


class ReferenceMedia(QObject):
    ready=Signal(str)
    _io_done=Signal(object)

    def __init__(self,folder,parent=None,*,validator=image_url,concurrency=4):
        super().__init__(parent);self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.validator=validator;self.concurrency=concurrency
        self.manager=QNetworkAccessManager(self);self.memory=OrderedDict();self.active={};self.queue=deque();self.closed=False
        self.memory_bytes=0;self.disk_checked=0;self.disk_bytes=0;self.disk_files=set()
        self.demand=set();self.scopes={};self.misses={};self.disk_state=OrderedDict();self.processing=set()
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lupin-images')
        self.io_queue=OrderedDict();self.io_active=None;self.cancelled=threading.Event()
        self._io_done.connect(self.io_finished,Qt.ConnectionType.QueuedConnection)
        self._queue_io('@maintenance',('maintenance',None,0))

    def filename(self,url):return self.folder/(hashlib.sha256(url.encode()).hexdigest()+Path(url).suffix)

    def image(self,url):
        if not self.validator(url) or self.closed:return QImage()
        if url in self.memory:self.memory.move_to_end(url);return self.memory[url]
        if url not in self.disk_state or self.disk_state[url] is not None:
            self._queue_io(url,('read',None,0))
        return QImage()

    def path(self,url):
        return self.filename(url) if self.validator(url) and not self.image(url).isNull() else None

    def remember(self,url,image):
        old=self.memory.pop(url,None)
        if old is not None:self.memory_bytes-=old.sizeInBytes()
        self.memory[url]=image;self.memory_bytes+=image.sizeInBytes();self.memory.move_to_end(url)
        while len(self.memory)>128 or self.memory_bytes>8*1024*1024:
            self.memory_bytes-=self.memory.popitem(last=False)[1].sizeInBytes()

    def observe(self,urls,*,owner='database'):
        if self.closed:return
        self.scopes[owner]=list(dict.fromkeys(url for url in urls if self.validator(url)))[:80]
        urls=list(dict.fromkeys(url for group in self.scopes.values() for url in group))[:128]
        self.demand=set(urls)
        for key,work in list(self.io_queue.items()):
            if work[0]=='read' and key not in self.demand:self.io_queue.pop(key,None)
        # Reorder waiting disk reads as well as downloads on viewport changes.
        pending=self.io_queue;self.io_queue=OrderedDict()
        for url in urls:
            if url in pending:self.io_queue[url]=pending.pop(url)
        self.io_queue.update(pending)
        self.queue.clear();now=time.time()
        for url in urls:
            if url in self.active or url in self.processing:continue
            self.image(url)
            if url not in self.disk_state or url==self.io_active or url in self.io_queue:continue
            saved=self.disk_state[url]
            if saved is not None and 0<=now-saved<TTL:continue
            if 0<=now-self.misses.get(url,-FAIL_TTL)<FAIL_TTL:continue
            self.queue.append(url)
        for url,reply in list(self.active.items()):
            if url not in self.demand:reply._reference_cancelled=True;reply.abort()
        self.pump()

    def pump(self):
        while self.queue and len(self.active)+len(self.processing)<self.concurrency and not self.closed:
            url=self.queue.popleft()
            if url not in self.demand or url in self.active or url in self.processing:continue
            request=QNetworkRequest(QUrl(url));request.setTransferTimeout(10000)
            request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,QNetworkRequest.RedirectPolicy.SameOriginRedirectPolicy)
            request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader,'Lupin (Classic World reference images)')
            reply=self.manager.get(request);reply.setReadBufferSize(MAX_BYTES+1);reply._reference_data=bytearray();self.active[url]=reply
            def receive(reply=reply):
                reply._reference_data.extend(bytes(reply.readAll()))
                if len(reply._reference_data)>MAX_BYTES:reply.abort()
            reply.readyRead.connect(receive);reply.finished.connect(lambda url=url,reply=reply:self.finish(url,reply))

    def finish(self,url,reply):
        self.active.pop(url,None)
        if self.closed:reply.deleteLater();return
        if getattr(reply,'_reference_cancelled',False):reply.deleteLater();self.pump();return
        data=bytes(reply._reference_data)+bytes(reply.readAll()) if reply.error()==QNetworkReply.NetworkError.NoError else b''
        reply.deleteLater();self.processing.add(url);self._queue_io(url,('store',data,time.time()));self.pump()

    def _queue_io(self,url,work):
        if self.closed or (url==self.io_active and work[0]=='read'):return
        if url not in self.io_queue or work[0]!='read':self.io_queue[url]=work
        self._pump_io()

    def _pump_io(self):
        if self.closed or self.io_active is not None or not self.io_queue:return
        url,work=self.io_queue.popitem(last=False);self.io_active=url
        future=self.pool.submit(self._disk_work,url,work)
        future.add_done_callback(lambda result:self._io_done.emit(result.result()) if not self.closed else None)

    def _disk_work(self,url,work):
        kind,data,saved=work
        try:
            if self.cancelled.is_set():return url,kind,QImage(),None,{}
            if kind=='maintenance':
                try:misses=json.loads((self.folder/'misses.json').read_text())
                except (OSError,ValueError):misses={}
                return url,kind,QImage(),None,misses
            if kind=='save':
                misses,cleanup,protected=data
                try:
                    temporary=self.folder/'misses.tmp';temporary.write_text(json.dumps(misses));temporary.replace(self.folder/'misses.json')
                    if cleanup:
                        files=sorted([*self.folder.glob('*.png'),*self.folder.glob('*.webp')],key=lambda path:path.stat().st_mtime,reverse=True);total=0
                        for index,path in enumerate(files):
                            total+=path.stat().st_size
                            if (index>=1024 or total>64*1024*1024) and path.name not in protected:path.unlink(missing_ok=True)
                except OSError:pass
                return url,kind,QImage(),None,{}
            path=self.filename(url)
            if kind=='read':
                try:
                    saved=path.stat().st_mtime
                    data=path.read_bytes() if path.stat().st_size<=MAX_BYTES else b''
                except OSError:data=b'';saved=None
                image=decode(data)
                return url,kind,image,saved if not image.isNull() else None,{}
            image=decode(data)
            if not image.isNull() and not self.cancelled.is_set():
                try:
                    temporary=path.with_suffix('.tmp');temporary.write_bytes(data);temporary.replace(path)
                except OSError:pass
            return url,kind,image,saved if not image.isNull() else None,{}
        except Exception:return url,kind,QImage(),None,{}

    def io_finished(self,result):
        url,kind,image,saved,misses=result;self.io_active=None
        if self.closed:return
        if kind in ('maintenance','save'):
            now=time.time()
            self.misses.update({url:at for url,at in misses.items() if self.validator(url) and type(at) in (int,float) and 0<=now-at<FAIL_TTL})
        else:
            self.disk_state[url]=saved;self.disk_state.move_to_end(url)
            while len(self.disk_state)>1024:self.disk_state.popitem(last=False)
            if not image.isNull():self.remember(url,image);self.misses.pop(url,None)
            elif kind=='store':self.misses[url]=time.time()
            if kind=='store':
                self.processing.discard(url)
                self.misses=dict(sorted(self.misses.items(),key=lambda row:row[1],reverse=True)[:512])
                self._persist_misses()
            if not image.isNull() or kind=='store':self.ready.emit(url)
        self._pump_io()
        # No GUI-thread stat/read/decode. Re-evaluate network eligibility once
        # local disk evidence has arrived, preserving per-owner demand.
        self.observe(self.scopes.get('database',()),owner='database')

    def _persist_misses(self):
        misses=dict(self.misses);cleanup=time.monotonic()-self.disk_checked>30
        if cleanup:self.disk_checked=time.monotonic()
        protected={self.filename(url).name for url in self.demand}
        self._queue_io('@save',('save',(misses,cleanup,protected),0))

    def close(self):
        if self.closed:return
        self.closed=True;self.cancelled.set();self.queue.clear();self.io_queue.clear()
        for reply in list(self.active.values()):reply.abort();reply.deleteLater()
        self.active.clear();self.pool.shutdown(wait=False,cancel_futures=True)


class ReferenceSprite(QWidget):
    def __init__(self,media,parent=None):
        super().__init__(parent);self.media=media;self.movie=None;self.url='';self.icon='';self.active=False;self.image=QImage()
        self.setFixedSize(56,56);self.setAccessibleName('Reference image')
        media.ready.connect(self.received)

    def set_source(self,icon,animation=''):
        target=animation or icon
        if target==self.url and icon==self.icon:self.sync();return
        if self.movie:self.movie.stop();self.movie.deleteLater();self.movie=None
        self.url=target;self.icon=icon;self.image=self.media.image(icon);self.received(target);self.update()

    def received(self,url):
        if url not in (self.url,self.icon):return
        self.image=self.media.image(self.icon)
        if url==self.url:
            path=self.media.path(url)
            if path is not None:
                if self.movie:self.movie.stop();self.movie.deleteLater()
                self.movie=QMovie(str(path),parent=self);self.movie.setCacheMode(QMovie.CacheMode.CacheNone)
                self.movie.frameChanged.connect(lambda *_:self.update());self.movie.jumpToFrame(0)
        self.sync();self.update()

    def sync(self):
        if self.movie:
            if self.active and enabled(self):
                if self.movie.state()==QMovie.MovieState.NotRunning:self.movie.start()
                else:self.movie.setPaused(False)
            else:self.movie.setPaused(True)

    def showEvent(self,event):
        super().showEvent(event);self.window().installEventFilter(self);self.sync()

    def hideEvent(self,event):
        if self.movie:self.movie.setPaused(True)
        super().hideEvent(event)

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Type.WindowStateChange,QEvent.Type.Show,QEvent.Type.Hide):self.sync()
        return False

    def paintEvent(self,event):
        image=self.movie.currentImage() if self.movie else self.image
        painter=QPainter(self)
        if image.isNull():
            painter.setPen(QColor('#728198'));painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'—');return
        size=image.size()
        # Integer enlargement keeps small skill/item icons crisp; large mobs fit.
        limit=self.width()-8;factor=min(2,limit//max(size.width(),size.height()))
        if factor>=1:size*=factor
        else:size=size.scaled(QSize(limit,limit),Qt.AspectRatioMode.KeepAspectRatio)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,factor<1)
        painter.drawImage(QRect((self.width()-size.width())//2,(self.height()-size.height())//2,size.width(),size.height()),image)
