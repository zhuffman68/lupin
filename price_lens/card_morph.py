"""Cached card content with a continuously resized native styled frame."""
from dataclasses import dataclass
from math import floor,ceil

from PySide6.QtCore import QPoint,QPointF,QRect,QRectF,Qt
from PySide6.QtGui import QBitmap,QPainter,QPalette,QPixmap,QRegion
from PySide6.QtWidgets import QFrame,QWidget


def background(widget):
    while widget is not None:
        colour=widget.palette().color(QPalette.ColorRole.Window)
        if colour.alpha()==255:return colour
        widget=widget.parentWidget()
    return Qt.GlobalColor.transparent


def draw_frame(painter,widget,rect):
    rect=QRect(rect)
    if widget.size()!=rect.size():widget.resize(rect.size())
    widget.render(painter,rect.topLeft(),QRegion(widget.rect()),QWidget.RenderFlag(0))


@dataclass
class CardPixels:
    rect:QRect
    viewport:QRect
    offset:QPointF
    foreground:QPixmap

    @classmethod
    def capture(cls,pixels,rect,viewport,style,colour):
        dpr=pixels.devicePixelRatio()
        bounds=QRect(0,0,round(pixels.width()/dpr),round(pixels.height()/dpr))
        viewport=viewport.intersected(bounds);clip=rect.intersected(viewport)
        if clip.isEmpty():return None
        physical=QRect(floor(clip.x()*dpr),floor(clip.y()*dpr),
                       ceil((clip.x()+clip.width())*dpr)-floor(clip.x()*dpr),
                       ceil((clip.y()+clip.height())*dpr)-floor(clip.y()*dpr))
        origin=QPointF(physical.x()/dpr,physical.y()/dpr)
        foreground=pixels.copy(physical);bare=QPixmap(foreground.size());bare.setDevicePixelRatio(dpr);bare.fill(colour)
        painter=QPainter(bare);painter.translate(-origin);draw_frame(painter,style,rect);painter.end()
        difference=foreground.toImage();painter=QPainter(difference)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Difference)
        painter.drawPixmap(0,0,bare);painter.end()
        foreground.setMask(QBitmap.fromImage(difference.createMaskFromColor(0xff000000,Qt.MaskMode.MaskInColor)))
        return cls(QRect(rect),QRect(viewport),origin-QPointF(rect.topLeft()),foreground)


def capture_card(widget,root,pixels):
    if widget is None or widget.isHidden():return None
    rect=QRect(widget.mapTo(root,QPoint()),widget.size());clip=root.rect()
    parent=widget.parentWidget()
    while parent is not None:
        clip=clip.intersected(QRect(parent.mapTo(root,QPoint()),parent.size()))
        if parent is root:break
        parent=parent.parentWidget()
    return CardPixels.capture(pixels,rect,clip,widget,background(root))


class CardMorph:
    def __init__(self,before,after,old,new,host):
        self.old=old;self.new=new;self.colour=background(host)
        self.style=QFrame(host);self.style._motion_style_only=True;self.style.setObjectName('card');self.style.hide()
        self.before=self.erased(before,old);self.after=self.erased(after,new)

    def erased(self,pixels,card):
        copy=QPixmap(pixels)
        if card and not copy.isNull():
            painter=QPainter(copy);painter.fillRect(card.rect.intersected(card.viewport),self.colour);painter.end()
        return copy

    def geometry(self,progress):
        old=self.old.rect if self.old else self.new.rect.adjusted(0,0,0,-self.new.rect.height())
        new=self.new.rect if self.new else self.old.rect.adjusted(0,0,0,-self.old.rect.height())
        return QRect(*(round(a+(b-a)*progress) for a,b in zip(old.getRect(),new.getRect())))

    def snapshot(self,pixels,progress):
        rect=self.geometry(progress)
        return CardPixels.capture(pixels,rect,self.viewport(progress),self.style,self.colour)

    def viewport(self,progress):
        old=self.old.viewport if self.old else self.new.viewport
        new=self.new.viewport if self.new else self.old.viewport
        return QRect(*(round(a+(b-a)*progress) for a,b in zip(old.getRect(),new.getRect())))

    def replace_after(self,pixels,new):self.new=new;self.after=self.erased(pixels,new)

    def paint(self,painter,progress):
        painter.drawPixmap(0,-round(5*progress),self.before)
        painter.setOpacity(progress);painter.drawPixmap(0,round(5*(1-progress)),self.after)
        self.paint_card(painter,progress)

    def paint_card(self,painter,progress):
        painter.save()
        rect=self.geometry(progress)
        painter.setClipRect(self.viewport(progress),Qt.ClipOperation.IntersectClip)
        opacity=1 if self.old and self.new else progress if self.new else 1-progress
        painter.setOpacity(opacity);draw_frame(painter,self.style,rect)
        painter.setClipRect(rect,Qt.ClipOperation.IntersectClip)
        for card,alpha,lift in ((self.old,1-progress,-5*progress),(self.new,progress,5*(1-progress))):
            if card:
                painter.setOpacity(alpha)
                painter.drawPixmap(QPointF(rect.topLeft())+card.offset+QPointF(0,lift),card.foreground)
        painter.restore()
