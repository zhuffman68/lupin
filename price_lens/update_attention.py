"""A button-local, continuous watched-item-style update reminder."""
import math

from PySide6.QtCore import QAbstractAnimation,QEvent,QPointF,QRectF,Qt,QVariantAnimation
from PySide6.QtGui import QColor,QLinearGradient,QPainter,QPainterPath,QPen
from PySide6.QtWidgets import QPushButton

from .motion import enabled


class UpdateSettingsButton(QPushButton):
    def __init__(self,parent=None):
        super().__init__('Settings',parent)
        self.update_available=False
        self.progress=0.0
        self._motion_window=None
        self.animation=QVariantAnimation(self)
        self.animation.setDuration(1600)
        self.animation.setStartValue(0.0);self.animation.setEndValue(1.0)
        self.animation.setLoopCount(-1)
        self.animation.valueChanged.connect(self.advance)

    def set_update_available(self,available):
        available=bool(available)
        if available!=self.update_available:
            self.update_available=available
            self.setText('Settings · update' if available else 'Settings')
            self.update()
        self.sync_motion()

    def sync_motion(self):
        if self.update_available and enabled(self):
            if self.animation.state()!=QAbstractAnimation.State.Running:self.animation.start()
        else:self.stop_motion()

    def stop_motion(self):
        moving=self.animation.state()==QAbstractAnimation.State.Running
        self.animation.stop();self.progress=0.0
        if moving and self.isVisible():self.update()

    def advance(self,value):
        if not self.update_available or not enabled(self):
            self.stop_motion();return
        self.progress=float(value)
        # Repaint this button only: no stylesheet, geometry or parent updates.
        self.update()

    def showEvent(self,event):
        super().showEvent(event)
        window=self.window()
        if window is not self._motion_window:
            if self._motion_window is not None:self._motion_window.removeEventFilter(self)
            self._motion_window=window
            window.installEventFilter(self)
        self.sync_motion()

    def hideEvent(self,event):
        self.stop_motion();super().hideEvent(event)

    def eventFilter(self,watched,event):
        if watched is self._motion_window:
            if event.type()==QEvent.Type.Hide:self.stop_motion()
            elif event.type() in (QEvent.Type.Show,QEvent.Type.WindowStateChange):self.sync_motion()
        return False

    def paintEvent(self,event):
        super().paintEvent(event)
        if not self.update_available:return
        moving=self.animation.state()==QAbstractAnimation.State.Running
        box=QRectF(self.rect()).adjusted(1.5,1.5,-1.5,-1.5)
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#352519'),3.0));painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box,6,6)
        # Keep the gold rim and caption at rest with Reduce motion enabled.
        pulse=(1-math.cos(2*math.pi*self.progress))/2 if moving else 0.0
        painter.setPen(QPen(QColor('#aa783d'),1.3))
        painter.setBrush(QColor(228,178,92,round(8+18*pulse)))
        painter.drawRoundedRect(box,6,6)
        if not moving:return
        band=min(76,max(40,box.width()*.26))
        center=box.left()-band+(box.width()+2*band)*self.progress
        gradient=QLinearGradient(QPointF(center-band/2,box.top()),QPointF(center+band/2,box.bottom()))
        for stop,colour in ((0,QColor(228,178,92,0)),(.3,QColor(225,172,80,38)),
                            (.5,QColor(245,211,145,100)),(.7,QColor(225,172,80,38)),(1,QColor(228,178,92,0))):
            gradient.setColorAt(stop,colour)
        clip=QPainterPath();clip.addRoundedRect(box.adjusted(1,1,-1,-1),5,5)
        painter.setClipPath(clip);painter.fillRect(box,gradient)
