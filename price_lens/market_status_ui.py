"""Stable market-status lines with the same digit motion as tracking values."""
from PySide6.QtCore import QSize,Qt
from PySide6.QtWidgets import QLabel,QSizePolicy,QVBoxLayout,QWidget

from . import gui_currency
from .motion import RollingLabel,enabled,fade_away,reveal


class _StatusLine(RollingLabel):
    """Roll a fitting status line; retain normal wrapping for long errors."""
    def __init__(self,parent):
        super().__init__('',parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)

    def sizeHint(self):return QLabel.sizeHint(self)

    def minimumSizeHint(self):return QSize(0,self.fontMetrics().height())

    def paintEvent(self,event):
        if not enabled(self):self.animation.stop();self.roll.finish()
        if gui_currency.line_width(self.text(),self.fontMetrics())>self.contentsRect().width():
            self.animation.stop();self.roll.finish();QLabel.paintEvent(self,event)
        else:super().paintEvent(event)


class MarketStatus(QWidget):
    """Reuse lines on age ticks instead of fading one multiline caption."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self._text='';self._error=None;self.lines=[]
        self.setAccessibleName('Market status')
        self.line_layout=QVBoxLayout(self);self.line_layout.setContentsMargins(0,0,0,0);self.line_layout.setSpacing(0)

    def text(self):return self._text

    def set_status(self,message,error=False):
        error=bool(error)
        if (message,error)==(self._text,self._error):return
        was_hidden=self.isHidden()
        if self._error!=error:
            self.setStyleSheet('QLabel {color:'+('#e4bd7b' if error else '#9eacbf')+';font-size:11px;}')
            self._error=error
        self._text=message;self.setAccessibleDescription(message)
        # Source errors are bounded upstream; also bound the retained QWidget
        # count if an unfamiliar diagnostic contains many explicit newlines.
        parts=message.splitlines() if message else []
        if len(parts)>8:parts=parts[:7]+[' '.join(parts[7:])]
        while len(self.lines)<len(parts):
            line=_StatusLine(self);self.lines.append(line);self.line_layout.addWidget(line)
        for index,line in enumerate(self.lines):
            if index<len(parts):line.setText(parts[index]);line.show()
            else:line.hide()
        if not message:fade_away(self)
        self.setVisible(bool(message))
        if message and was_hidden:reveal(self)
