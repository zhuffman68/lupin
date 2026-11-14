"""One full-height Prices viewport, retaining each view's scroll position."""
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import QPushButton,QVBoxLayout

from .motion import ContentArea


class PriceViews(ContentArea):
    view_changed=Signal()

    def __init__(self,detail,screen,parent=None):
        super().__init__(parent)
        self.detail=detail;self.screen_view=screen;self.pane=None;self.view_key=None
        self.positions={'detail':0,'screen':0}
        self.identity=None;self.reset_detail=False
        self.switch_button=QPushButton('Back to on-screen items')
        self.switch_button.setCheckable(True)
        self.switch_button.toggled.connect(lambda *_:self.view_changed.emit())
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        layout.addWidget(self.switch_button,0,Qt.AlignmentFlag.AlignTop)
        layout.addWidget(detail,1);layout.addWidget(screen,1)
        self.switch_button.hide();detail.hide()

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
        return layout_changed
