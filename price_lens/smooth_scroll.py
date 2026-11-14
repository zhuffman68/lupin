"""Bounded wheel motion for Lupin's own viewports. No global input listener."""
from PySide6.QtCore import QEvent,QEasingCurve,QObject,Qt,QVariantAnimation
from PySide6.QtWidgets import QApplication,QAbstractItemView,QListWidget,QScrollArea
from shiboken6 import isValid


class SmoothWheel(QObject):
    def __init__(self,area):
        super().__init__(area)
        self.area=area;self.bar=area.verticalScrollBar();self.target=float(self.bar.value());self.writing=False
        self.animation=QVariantAnimation(self);self.animation.setDuration(125)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.bar.valueChanged.connect(self.external_value)
        self.bar.rangeChanged.connect(lambda *_:self.stop())
        self.bar.sliderPressed.connect(self.stop)
        for obj in (area,area.viewport(),self.bar):obj.installEventFilter(self)

    def stop(self):
        self.animation.stop()
        if isValid(self.bar):self.target=float(self.bar.value())

    def external_value(self,value):
        if not self.writing:self.stop()

    def advance(self,value):
        if value is None:return
        if not isValid(self.bar):self.animation.stop();return
        if not self.area.isVisible() or self.area.window().isMinimized():self.stop();return
        self.writing=True
        try:self.bar.setValue(round(value))
        finally:self.writing=False

    def eventFilter(self,obj,event):
        kind=event.type()
        if kind in (QEvent.Type.Hide,QEvent.Type.MouseButtonPress,QEvent.Type.KeyPress):
            self.stop()
        if kind!=QEvent.Type.Wheel:return False
        if not isValid(self.bar) or not self.area.isVisible() or self.area.window().isMinimized():return False
        delta=event.angleDelta()
        # Preserve native high-resolution/gesture scrolling and modifiers used
        # by child controls. An exhausted inner list can pass to its outer page.
        if (not event.pixelDelta().isNull() or event.phase()!=Qt.ScrollPhase.NoScrollPhase
                or event.modifiers()!=Qt.KeyboardModifier.NoModifier or abs(delta.x())>abs(delta.y())):
            self.stop();return False
        if not delta.y() or self.bar.maximum()<=self.bar.minimum():return False
        app=QApplication.instance()
        if app.wheelScrollLines()<=0:return False
        distance=delta.y()/120*max(1,self.bar.singleStep())*app.wheelScrollLines()
        target=float(max(self.bar.minimum(),min(self.bar.maximum(),self.target-distance)))
        if target==self.target and not self.animation.state()==self.animation.State.Running:return False
        self.target=target
        if app.property('reduceMotion'):
            self.animation.stop();self.advance(target)
        else:
            self.animation.stop();self.animation.setStartValue(float(self.bar.value()))
            self.animation.setEndValue(target);self.animation.start()
        event.accept();return True


def smooth_scrolling(area):
    controller=getattr(area,'smooth_wheel',None)
    if controller is None:
        if isinstance(area,QAbstractItemView):area.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        controller=area.smooth_wheel=SmoothWheel(area)
    return controller


class SmoothScrollArea(QScrollArea):
    def __init__(self,parent=None):
        super().__init__(parent);smooth_scrolling(self)


class SmoothListWidget(QListWidget):
    def __init__(self,parent=None):
        super().__init__(parent);smooth_scrolling(self)
