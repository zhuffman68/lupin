"""Short, interruptible QWidget motion; idle and hidden widgets do no animation work."""
import re
import math
from PySide6.QtCore import QEasingCurve,QPoint,Qt,QVariantAnimation,QSize,QRect,Signal
from PySide6.QtGui import QPainter, QPalette,QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLabel, QTabWidget, QWidget,QSizePolicy,QStackedWidget,QStyle,QStyleOption,QScrollArea,QScrollBar,QTabBar
from shiboken6 import isValid
from .number_motion import NumberRoll
from . import gui_currency
from .widget_lifetime import retire_widget
from .smooth_scroll import smooth_scrolling
from .slide_surface import SlideSurface,invalidate_surface
from .card_morph import CardMorph,capture_card,background


def enabled(widget):
    app = QApplication.instance()
    ancestor=widget
    while ancestor is not None:
        if ancestor.property('suppressMotion'):return False
        ancestor=ancestor.parentWidget()
    return bool(app and not app.property("reduceMotion") and widget.isVisible()
                and not widget.window().isMinimized())


class _QuietScrollBar(QScrollBar):
    def paintEvent(self,event):
        if self.maximum()>self.minimum():super().paintEvent(event)


class StableScrollArea(QScrollArea):
    """Reserve a constant narrow gutter; draw a scrollbar only when needed.

    A changing viewport width rewraps every card and interrupts CardArea's
    snapshot. Keep the gutter even when the content fits, without an empty
    scrollbar handle/track or a horizontal scrollbar at the default width.
    """
    def __init__(self,parent=None):
        super().__init__(parent)
        bar=_QuietScrollBar(Qt.Orientation.Vertical,self)
        self.setVerticalScrollBar(bar)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bar.rangeChanged.connect(lambda low,high:bar.setEnabled(high>low))
        bar.setEnabled(False)
        smooth_scrolling(self)


class MotionLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text,parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self._height_cache={}
        self.alpha = 1.0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(110)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._alpha)
        self.number_roll=NumberRoll(gui_currency.visual_text(text))
        self.digits=QVariantAnimation(self);self.digits.setDuration(160)
        self.digits.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.digits.valueChanged.connect(self._digits)

    def _alpha(self, value):
        self.alpha = float(value)
        invalidate_surface(self)
        self.update()

    def _digits(self,value):
        self.number_roll.progress=float(value);invalidate_surface(self);self.update()

    def clear(self):self.setText('')

    def setText(self, value):
        if value == self.text():return
        self._height_cache.clear()
        animate = enabled(self) and not self.property("quietUpdates")
        old=self.text()
        shape=lambda text:re.sub(r'\d+(?:[,.]\d+)*','#',text)
        only_numbers=bool(any(c.isdigit() for c in value) and shape(old)==shape(value)
                          and gui_currency.line_width(value,self.fontMetrics())<=self.contentsRect().width())
        if animate and not value and self.text():fade_away(self)
        self.animation.stop()
        self.digits.stop()
        self.number_roll.set_text(gui_currency.visual_text(value),animate and only_numbers)
        super().setText(value)
        invalidate_surface(self)
        if animate and only_numbers:
            self.alpha=1.0
            self.digits.setStartValue(0.0);self.digits.setEndValue(1.0);self.digits.start()
        elif animate:
            self.animation.setStartValue(.55)
            self.animation.setEndValue(1.0)
            self.animation.start()
        else:self.alpha = 1.0

    def paintEvent(self, event):
        if (self.animation.state()!=self.animation.State.Stopped or self.digits.state()!=self.digits.State.Stopped) and not enabled(self):
            self.animation.stop();self.digits.stop();self.number_roll.finish();self.alpha=1.0
        if self.property('elideRight'):
            painter=QPainter(self);painter.setFont(self.font());painter.setOpacity(self.alpha)
            painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
            value=self.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,self.contentsRect().width())
            painter.drawText(self.contentsRect(),self.alignment(),value)
            return
        # Keep one renderer for a numeric caption at rest and in motion. Native
        # QLabel shaping and per-cell drawing differ in rounding/kerning; swapping
        # between them made the surrounding words move during every roll.
        numeric_line = (self.number_roll.numeric and '\n' not in self.text()
                        and self.number_roll.layout(self.fontMetrics(),True)[1]<=self.contentsRect().width())
        if numeric_line:
            painter=QPainter(self);painter.setFont(self.font())
            painter.setOpacity(self.alpha)
            painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
            self.number_roll.paint(painter,self.contentsRect(),self.alignment(),gui_currency.paint_icon);return
        if self.property('currencyIcon') is not False and gui_currency.PATTERN.search(self.text()):
            painter=QPainter(self);gui_currency.paint_document(self,painter,self.alpha);return
        if self.alpha >= .999:
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setOpacity(self.alpha)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        flags = int(self.alignment()) | int(Qt.TextFlag.TextWordWrap if self.wordWrap() else Qt.TextFlag.TextSingleLine)
        painter.drawText(self.contentsRect(),flags,self.text())

    def hideEvent(self, event):
        self.animation.stop()
        self.digits.stop();self.number_roll.finish()
        self.alpha = 1.0
        super().hideEvent(event)

    def heightForWidth(self,width):
        margins=self.contentsMargins()
        key=(self.text(),width,self.wordWrap(),self.textFormat(),self.property('currencyIcon') is not False,
             self.margin(),self.indent(),int(self.alignment()),
             self.fontMetrics().fontDpi(),margins.left(),margins.top(),margins.right(),margins.bottom())
        cache=self._height_cache
        if key in cache:return cache[key]
        if self.wordWrap() and self.property('currencyIcon') is not False and gui_currency.PATTERN.search(self.text()):
            doc=gui_currency.document(self).clone();doc.setTextWidth(width)
            height=round(doc.size().height()+margins.top()+margins.bottom())
        else:height=super().heightForWidth(width)
        if len(cache)>=8:cache.clear()
        cache[key]=height;return height

    def changeEvent(self,event):
        cache=getattr(self,'_height_cache',None)
        if cache is not None:cache.clear()
        super().changeEvent(event)


def reveal(widget):
    if not enabled(widget):return
    previous = getattr(widget,"_reveal",None)
    if previous:previous.stop();previous.deleteLater()
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QVariantAnimation(widget)
    widget._reveal = animation
    animation.setDuration(85)
    animation.setStartValue(.80)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.valueChanged.connect(effect.setOpacity)
    def finish():
        if widget._reveal is animation:
            widget._reveal = None
            widget.setGraphicsEffect(None)
        animation.deleteLater()
    animation.finished.connect(finish)
    animation.start()


def fade_away(widget):
    """Keep outgoing pixels visible while their source layout is cleared."""
    if not enabled(widget) or widget.size().isEmpty():return
    host=widget.parentWidget()
    snapshot=QLabel(host);snapshot.setPixmap(widget.grab());snapshot.setGeometry(widget.geometry())
    snapshot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    effect=QGraphicsOpacityEffect(snapshot);snapshot.setGraphicsEffect(effect)
    animation=QVariantAnimation(snapshot);animation.setDuration(100)
    animation.setStartValue(1.0);animation.setEndValue(0.0);animation.valueChanged.connect(effect.setOpacity)
    animation.finished.connect(lambda:retire_widget(host,snapshot))
    snapshot.show();snapshot.raise_();animation.start()


def card_pixels(area,pixels,*,current=False,root=None):
    if pixels is None:return None
    frame=getattr(area,'outgoing',None)
    if not current and frame is not None and getattr(frame,'morph',None):
        return frame.morph.snapshot(pixels,frame.progress)
    target=getattr(area,'frame_target',None)
    return capture_card(target(),root or area,pixels) if target else None


class _ContentFrame(QWidget):
    def __init__(self,before,after,parent,old_card=None,new_card=None):
        super().__init__(parent);self.before=before;self.after=after;self.progress=0.0
        self.morph=CardMorph(before,after,old_card,new_card,self) if old_card or new_card else None
        if self.morph:self.before=self.morph.before;self.after=self.morph.after
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.background_colour=background(parent)

    def replace_after(self,pixels,card):
        self.after=pixels
        if self.morph:
            self.morph.replace_after(pixels,card);self.after=self.morph.after

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),self.background_colour)
        if self.morph:self.morph.paint(painter,self.progress);return
        # Retain outgoing pixels while the incoming page settles. There must
        # never be a blank midpoint, including when a transition is interrupted.
        progress=self.progress
        painter.setOpacity(1-progress if self.after.isNull() else 1.0)
        painter.drawPixmap(0,-round(5*progress),self.before)
        painter.setOpacity(progress)
        painter.drawPixmap(0,round(5*(1-progress)),self.after)


class ContentArea(QWidget):
    """Replace content in one layout, without animating its height."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.before=None;self.before_card=None;self.frame_target=None;self.outgoing=None
        self.animation=QVariantAnimation(self);self.animation.setDuration(130)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.finish)

    def begin(self):
        pixels=self.grab() if enabled(self) and not self.size().isEmpty() else None
        card=card_pixels(self,pixels)
        self.finish();self.before=pixels;self.before_card=card

    def complete(self):
        pixels=self.before;old_card=self.before_card;self.before=None;self.before_card=None
        if pixels is None or not enabled(self):return
        if self.layout():self.layout().activate()
        after=self.grab();new_card=card_pixels(self,after,current=True)
        self.outgoing=self.make_frame(pixels,after,old_card,new_card)
        self.outgoing.setGeometry(self.rect())
        self.outgoing.show();self.outgoing.raise_()
        self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()

    def make_frame(self,before,after,old_card,new_card):
        return _ContentFrame(before,after,self,old_card,new_card)

    def refresh_destination(self):
        """Update incoming pixels without replaying a structural transition."""
        frame=self.outgoing
        if frame is None:return
        # No event loop is entered while our snapshot is hidden. The next
        # physical paint still sees it, now with the current destination data.
        frame.hide()
        try:
            if self.layout():self.layout().activate()
            pixels=self.grab();card=card_pixels(self,pixels,current=True)
        finally:frame.show();frame.raise_()
        frame.replace_after(pixels,card);invalidate_surface(frame);frame.update()

    def advance(self,progress):
        if not enabled(self):self.finish();return
        if self.outgoing:
            self.outgoing.progress=float(progress);invalidate_surface(self.outgoing);self.outgoing.update()

    def finish(self):
        self.animation.stop();self.before=None;self.before_card=None
        if self.outgoing:
            retire_widget(self,self.outgoing);self.outgoing=None

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.outgoing:self.outgoing.setGeometry(self.rect())

    def hideEvent(self,event):
        self.finish();super().hideEvent(event)


class CardArea(QWidget):
    """A fixed-size card canvas whose clipped height moves its siblings.

    Children are laid out once at their destination size. Only this viewport's
    height changes during motion, so wrapped text is never squeezed each frame.
    History remains a live sibling and is never part of a card snapshot.
    """
    def __init__(self,parent=None):
        super().__init__(parent)
        self.content=QWidget(self);self.before=None;self.before_card=None;self.frame_target=None;self.outgoing=None
        self.full_height=0;self.start_height=0;self.setFixedHeight(0)
        self.animation=QVariantAnimation(self);self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.finish)

    def begin(self):
        current_height=self.height()
        pixels=(self.grab() if current_height>0 else QPixmap()) if enabled(self) else None
        card=card_pixels(self,pixels,root=self.content)
        self.finish();self.setFixedHeight(current_height);self.before=pixels;self.before_card=card;self.start_height=current_height

    def measure(self):
        layout=self.content.layout()
        if layout is None or not any(layout.itemAt(i).widget() and not layout.itemAt(i).widget().isHidden() for i in range(layout.count())):return 0
        # A card removal invalidates its immediate layout first. Qt propagates
        # that to ancestor size hints through a queued LayoutRequest, but this
        # measurement happens before the event is delivered. Refresh children
        # before parents so the animation never adopts an old card's height.
        def invalidate(current):
            for index in range(current.count()):
                item=current.itemAt(index);child=item.widget()
                # Tab widgets own their private page-stack layout. Its public
                # height is measured by the item card; descending into Qt's
                # internal containers can invalidate live animation wrappers.
                nested=(None if isinstance(child,QTabWidget) else child.layout()) if child is not None else item.layout()
                if nested is not None:invalidate(nested)
            current.invalidate()
            current.activate()
        invalidate(layout)
        return max(0,layout.totalHeightForWidth(self.width()) if layout.hasHeightForWidth() else layout.totalSizeHint().height())

    def complete(self):
        pixels=self.before;old_card=self.before_card;self.before=None;self.before_card=None
        target=self.measure()
        if pixels is None and self.animation.state()!=self.animation.State.Stopped and enabled(self):
            # Quote/age changes update the destination pixels, without restarting
            # a replacement or flashing its live widgets through the snapshot.
            progress=float(self.animation.currentValue() or 0)
            if target!=self.full_height and progress<1:
                self.start_height=(self.height()-target*progress)/(1-progress)
            self.full_height=target;self.content.resize(self.width(),target)
            if self.content.layout():self.content.layout().activate()
            if self.outgoing:
                after=self.content.grab() if target else QPixmap()
                self.outgoing.replace_after(after,card_pixels(self,after,current=True,root=self.content))
                self.outgoing.setGeometry(0,0,self.width(),max(self.height(),target,round(self.start_height)))
                self.outgoing.update()
            return
        self.full_height=target
        self.content.resize(self.width(),self.full_height)
        if self.content.layout():self.content.layout().activate()
        self.content.setVisible(self.full_height>0)
        if not enabled(self):
            self.finish();return
        if pixels is None:
            if self.height()!=self.full_height:
                self.start_height=self.height()
                self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()
            return
        after=self.content.grab() if self.full_height else QPixmap()
        self.outgoing=_ContentFrame(pixels,after,self,old_card,card_pixels(self,after,current=True,root=self.content))
        self.outgoing.setGeometry(0,0,self.width(),max(self.start_height,self.full_height))
        self.content.hide();self.outgoing.show();self.outgoing.raise_()
        self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()

    def advance(self,progress):
        if not enabled(self):self.finish();return
        progress=float(progress)
        self.setFixedHeight(round(self.start_height+(self.full_height-self.start_height)*progress))
        if self.outgoing:
            self.outgoing.progress=progress;invalidate_surface(self.outgoing);self.outgoing.update()
        parent=self.parentWidget()
        if parent and parent.layout():parent.layout().activate()

    def follow_height(self,delta):
        """A child owns this resize clock; do not start a second easing curve."""
        self.full_height=max(0,self.full_height+delta)
        self.content.resize(self.width(),self.full_height)
        self.setFixedHeight(self.full_height)
        if self.content.layout():self.content.layout().activate()

    def finish(self):
        self.animation.stop();self.before=None;self.before_card=None
        if self.outgoing:
            retire_widget(self,self.outgoing);self.outgoing=None
        self.setFixedHeight(self.full_height)
        self.content.setVisible(self.full_height>0)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if event.oldSize().width()!=event.size().width():
            self.finish();self.full_height=self.measure()
            self.content.resize(self.width(),self.full_height);self.setFixedHeight(self.full_height)

    def hideEvent(self,event):
        self.finish();super().hideEvent(event)


def visibility(widget, shown):
    """Animate a layout section's height without leaving an invisible input target."""
    if getattr(widget,"_motion_target",not widget.isHidden()) == shown:return
    widget._motion_target = shown
    old = getattr(widget,"_section_animation",None)
    if old:old.stop();old.deleteLater()
    cap = getattr(widget,"_section_cap",widget.maximumHeight())
    widget._section_cap = cap
    if not enabled(widget.parentWidget() or widget):
        widget.setMaximumHeight(cap)
        widget.setVisible(shown)
        return
    current = widget.height() if not widget.isHidden() else 0
    target = min(cap,widget.sizeHint().height()) if shown else 0
    widget.setVisible(True)
    widget.setEnabled(shown)
    animation = QVariantAnimation(widget)
    widget._section_animation = animation
    animation.setDuration(widget.property('sectionDuration') or 130)
    animation.setStartValue(current)
    animation.setEndValue(target)
    animation.setEasingCurve(QEasingCurve.Type.InOutCubic if widget.property('sectionDuration') else QEasingCurve.Type.OutCubic)
    animation.valueChanged.connect(lambda height:widget.setMaximumHeight(round(height)))
    def finish():
        if widget._section_animation is animation:
            widget.setVisible(shown)
            widget.setMaximumHeight(cap)
            widget.setEnabled(True)
            widget._section_animation = None
        animation.deleteLater()
    animation.finished.connect(finish)
    animation.start()


def fading_visibility(widget,shown):
    """Fade small adornments while their retained-size policy holds alignment."""
    if getattr(widget,'_fade_target',not widget.isHidden())==shown:return
    widget._fade_target=shown
    old=getattr(widget,'_presence_animation',None)
    if old:old.stop();old.deleteLater()
    effect=widget.graphicsEffect()
    start=effect.opacity() if isinstance(effect,QGraphicsOpacityEffect) else (0.0 if widget.isHidden() else 1.0)
    if not enabled(widget.parentWidget() or widget):
        widget.setGraphicsEffect(None);widget.setVisible(shown);widget._presence_animation=None;return
    if not isinstance(effect,QGraphicsOpacityEffect):
        effect=QGraphicsOpacityEffect(widget);widget.setGraphicsEffect(effect)
    effect.setOpacity(start);widget.setVisible(True)
    animation=QVariantAnimation(widget);widget._presence_animation=animation
    animation.setDuration(140);animation.setStartValue(start);animation.setEndValue(1.0 if shown else 0.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic);animation.valueChanged.connect(effect.setOpacity)
    def finish():
        if widget._presence_animation is animation:
            widget.setVisible(shown);widget.setGraphicsEffect(None);widget._presence_animation=None
        animation.deleteLater()
    animation.finished.connect(finish);animation.start()


class TabMotion:
    """Retargetable page motion, independent of native stack visibility changes."""
    def init_motion(self,stack):
        self.previous_page=None
        self.previous_index=0
        self.sliding=False
        self.scroll=0.0
        self.stack=stack
        self.surface=None
        self.layout_locks=set();self.layout_enabled=True
        self.mouse_before={}
        self.moving_pages=[]
        self.animation=QVariantAnimation(self)
        self.animation.setDuration(260)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self.move_pages)
        self.animation.finished.connect(self.finish_slide)
        self.currentChanged.connect(self.transition)

    def transition(self,index):
        page=self.currentWidget()
        previous=self.previous_page;old_index=self.previous_index
        self.previous_page=page
        self.previous_index=index
        if not page or not previous or not enabled(self):
            self.finish_slide();return
        stack=self.stack
        if stack is None or not isValid(stack):return
        self.animation.stop()
        if not self.sliding:
            self.stack=stack;self.base=self.motion_rect();self.slide_width=self.base.width()
            if self.slide_width<=0:return
            self.scroll=float(old_index)
            self.hold_layout('slide')
            self.sliding=True
        if self.surface is None:
            self.surface=SlideSurface(self,stack)
            self.surface.pages={old_index:previous};self.surface.capture(old_index)
        self.surface.freeze(old_index)
        stack.setUpdatesEnabled(False)
        self.prepare_page(index)
        self.base=self.motion_rect();self.slide_width=self.base.width()
        first=max(0,math.floor(min(self.scroll,index)))
        last=min(self.count()-1,math.ceil(max(self.scroll,index)))
        self.moving_pages=[]
        for i in range(self.count()):
            child=self.widget(i)
            if child not in self.mouse_before:
                self.mouse_before[child]=child.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,child is not page)
            if first<=i<=last:
                child.resize(self.base.size());child.show();self.moving_pages.append((i,child))
            else:child.hide()
        self.move_pages(self.scroll)
        page.raise_();stack.setUpdatesEnabled(True)
        self.surface.set_pages(self.moving_pages)
        self.animation.setStartValue(self.scroll)
        self.animation.setEndValue(float(index))
        self.animation.start()

    def prepare_page(self,index):pass

    def motion_rect(self):return self.stack.contentsRect()

    def hold_layout(self,reason):
        if self.stack is None or not isValid(self.stack):return
        if not self.layout_locks:
            self.layout_enabled=self.stack.layout().isEnabled();self.stack.layout().setEnabled(False)
        self.layout_locks.add(reason)

    def release_layout(self,reason):
        self.layout_locks.discard(reason)
        if not self.layout_locks and self.stack is not None and isValid(self.stack):
            self.stack.layout().setEnabled(self.layout_enabled);self.stack.layout().activate()

    def move_pages(self,value):
        if not self.sliding:return
        if self.stack is None or not isValid(self.stack):self.finish_slide();return
        if not enabled(self):self.finish_slide();return
        self.scroll=float(value)
        for i,child in self.moving_pages:
            child.move(self.base.left()+round((i-self.scroll)*self.slide_width),self.base.top())
        if self.surface:self.surface.frame()

    def finish_slide(self):
        self.animation.stop()
        if self.surface:self.surface.dispose();self.surface=None
        if not self.sliding:return
        self.sliding=False;self.moving_pages=[];stack=self.stack
        if stack is None or not isValid(stack):
            self.stack=None;self.mouse_before.clear();self.layout_locks.clear();return
        current=self.currentWidget()
        stack.setUpdatesEnabled(False)
        stack.setCurrentIndex(self.currentIndex())
        for i in range(self.count()):
            child=self.widget(i)
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,self.mouse_before.get(child,False))
            child.setGeometry(self.motion_rect());child.setVisible(child is current)
        self.mouse_before.clear()
        self.release_layout('slide')
        stack.setUpdatesEnabled(True)

    def hideEvent(self,event):
        self.finish_slide();super().hideEvent(event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.sliding:
            if self.stack is None or not isValid(self.stack):self.finish_slide();return
            # Status text and page layouts can resize the viewport during a tab
            # change. Scroll in page units so the same animation/easing survives.
            self.base=self.motion_rect();self.slide_width=self.base.width()
            if self.slide_width<=0:
                self.finish_slide();return
            self.stack.setUpdatesEnabled(False)
            for _,child in self.moving_pages:child.resize(self.base.size())
            self.move_pages(self.scroll)
            if self.surface:
                self.surface.setGeometry(self.stack.contentsRect())
                for page in self.surface.pages.values():self.surface.invalidate(page)
            self.stack.setUpdatesEnabled(True)


class AnimatedTabs(TabMotion,QWidget):
    currentChanged=Signal(int)
    tabBarClicked=Signal(int)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('motionTabs')
        self.bar=QTabBar(self);self.bar.setExpanding(False);self.bar.setDrawBase(False)
        self.init_motion(QStackedWidget(self))
        self.bar.currentChanged.connect(self.select_page)
        self.bar.tabBarClicked.connect(self.tabBarClicked.emit)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setStyleSheet('QWidget#motionTabs,QWidget#motionTabs > QStackedWidget{background:transparent;border:0;}')

    def addTab(self,page,title):
        index=self.stack.addWidget(page);self.bar.addTab(title);self.place_children();return index

    def removeTab(self,index):
        page=self.widget(index)
        if page:self.stack.removeWidget(page)
        self.bar.removeTab(index);self.place_children()

    def tabBar(self):return self.bar
    def count(self):return self.bar.count()
    def currentIndex(self):return self.bar.currentIndex()
    def currentWidget(self):return self.widget(self.currentIndex())
    def widget(self,index):return self.stack.widget(index)
    def setCurrentIndex(self,index):self.bar.setCurrentIndex(index)
    def setCurrentWidget(self,page):self.setCurrentIndex(self.stack.indexOf(page))
    def tabText(self,index):return self.bar.tabText(index)
    def setTabText(self,index,title):self.bar.setTabText(index,title);self.place_children()
    def sizeHint(self):return QSize(400,400)
    def minimumSizeHint(self):return QSize(0,0)

    def select_page(self,index):
        if self.previous_page is None or not enabled(self):self.stack.setCurrentIndex(index)
        focus=QApplication.focusWidget();previous=self.previous_page
        self.currentChanged.emit(index)
        page=self.currentWidget()
        if previous is not None and focus is not None and previous.isAncestorOf(focus) and page is not None:
            target=page.focusWidget() or page;target.setFocus(Qt.FocusReason.TabFocusReason)

    def bar_height(self):return 0 if self.bar.isHidden() else self.bar.sizeHint().height()+4

    def place_children(self):
        height=self.bar_height();width=min(self.width(),self.bar.sizeHint().width())
        self.bar.setGeometry((self.width()-width)//2,0,width,max(0,height-4))
        self.stack.setGeometry(0,height,self.width(),max(0,self.height()-height))

    def resizeEvent(self,event):
        self.place_children();super().resizeEvent(event)

    def showEvent(self,event):
        self.place_children();super().showEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab) and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step=-1 if event.key()==Qt.Key.Key_Backtab or event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            if self.count():self.setCurrentIndex((self.currentIndex()+step)%self.count())
            event.accept();return
        super().keyPressEvent(event)


class RollingLabel(QLabel):
    """Clip and roll changed digits only; semantic text updates immediately."""
    def __init__(self,text="",parent=None):
        super().__init__(text,parent)
        self.roll=NumberRoll(gui_currency.visual_text(text))
        self.animation=QVariantAnimation(self);self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.setMinimumWidth(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        margins=self.contentsMargins()
        reserved=self.property('reserveText')
        width=max(90,self.fontMetrics().horizontalAdvance(reserved)+4) if reserved else 90
        return QSize(width,self.fontMetrics().height()+margins.top()+margins.bottom())

    def minimumSizeHint(self):return self.sizeHint()

    def advance(self,value):self.roll.progress=float(value);invalidate_surface(self);self.update()

    def clear(self):self.setText('')

    def setText(self,text):
        if text==self.text():return
        self.animation.stop()
        super().setText(text)
        invalidate_surface(self)
        if self.roll.set_text(gui_currency.visual_text(text),enabled(self)):
            self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.start()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setFont(self.font());painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        if self.animation.state()!=self.animation.State.Stopped and not enabled(self):self.animation.stop();self.roll.finish()
        self.roll.paint(painter,self.contentsRect(),self.alignment(),gui_currency.paint_icon)

    def hideEvent(self,event):
        self.animation.stop();self.roll.finish();super().hideEvent(event)
