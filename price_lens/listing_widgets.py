"""Compact cached shop sightings for the shared selected-item card."""
import time
from urllib.parse import quote
from shiboken6 import isValid

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout, QWidget

from .domain import age_text
from .market_listings import provider_id
from .motion import MotionLabel
from .smooth_scroll import SmoothScrollArea
from .listing_rows import ListingRow,ListingRows


def label(value='', *, muted=False, bold=False):
    widget = MotionLabel(value)
    widget.setWordWrap(True)
    widget.setStyleSheet(f'background:transparent;border:0;font-size:10px;color:{"#a7b7cd" if muted else "#e4eaf3"};font-weight:{650 if bold else 400};')
    return widget


class WhereSeenPanel(SmoothScrollArea):
    def __init__(self, item, service, *, source_requested=None, selected=None):
        super().__init__()
        self.item, self.service = item, service
        self.source_requested = source_requested
        self.selected = selected or (lambda: True)
        self.allowed = True
        self.rows = []
        self.signature = None
        self.observing = False
        self.observed_window = None
        self.built = False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.timer = QTimer(self)
        self.timer.setInterval(60000)
        self.timer.timeout.connect(self.refresh)
        if service:
            service.changed.connect(self.changed)

    def build_body(self):
        if self.built:return
        self.built=True
        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(3,7,3,0)
        self.body.setSpacing(6)
        self.status = label(muted=True)
        self.body.addWidget(self.status)
        self.note = label('Recent shop sightings; availability may have changed.', muted=True)
        self.body.addWidget(self.note)
        self.listing_view=ListingRows(content)
        self.body.addWidget(self.listing_view)
        self.more = label('Showing up to 100 reported sightings.', muted=True)
        self.more.hide()
        self.body.addWidget(self.more)
        self.source = QPushButton('MesoWatch ↗')
        self.source.setObjectName('quiet')
        self.source.clicked.connect(self.visit_source)
        self.body.addWidget(self.source,0,Qt.AlignmentFlag.AlignLeft)
        self.body.addStretch()
        self.setWidget(content)

    def visit_source(self):
        if self.source_requested:
            self.source_requested('https://meso.watch/?item='+quote(provider_id(self.item),safe=''))

    def _selected(self):
        # Explicit owner selection avoids creating base-class wrappers while
        # walking Qt's private stacked widgets during a live tab animation.
        return self.allowed and self.selected() and self.isVisible() and not self.window().isMinimized()

    def sync(self):
        if not isValid(self) or not isValid(self.timer):return
        active=self._selected()
        if active:self.build_body()
        observing = bool(self.service and active)
        if observing != self.observing:
            self.observing = observing
            self.service.set_interest(self,self.item if observing else None)
        if observing:
            self.timer.start()
        else:
            self.timer.stop()
        if active:self.refresh()

    def set_active(self, active):
        self.allowed = bool(active)
        self.sync()

    def changed(self, identity):
        if identity == self.item.game_id:
            self.refresh()

    def refresh(self):
        if not self.built or not self._selected():return
        now = time.time()
        state = self.service.state(self.item) if self.service else None
        snapshot = state.snapshot if state else None
        loading = bool(self.service and self.service.loading(self.item))
        if snapshot:
            checked = age_text(max(0,now-snapshot.checked_at))
            status = f'Checked {checked} ago'
            if loading:status += ' · refreshing…'
            elif state.error:status += ' · refresh unavailable'
            self.status.setText(status)
            self.status.setToolTip(f'Source published {age_text(max(0,now-snapshot.published_at))} ago. Refresh interval: 15 minutes.')
            self.note.setText(('Items may have sold; stats unverified.' if self.item.equipment else 'Recent sightings; items may have sold.')
                              if snapshot.rows else 'No available shop sightings reported for this item.')
        else:
            self.status.setText('Looking up shop sightings…' if loading else
                                state.error if state and state.error else
                                'Open this tab to look up recent shops.' if self.service else 'Shop sightings unavailable.')
            self.note.setText('Shop sightings are cached for 15 minutes.')
        signature = snapshot.rows if snapshot else ()
        if signature != self.signature:
            self.signature = signature
            self.rows = [ListingRow(row,self.item.per_set) for row in signature]
            for row in self.rows:row.update_age(now)
            self.listing_view.set_rows(self.rows)
        self.more.setVisible(bool(snapshot and snapshot.more))
        self.listing_view.refresh_ages(now)

    def showEvent(self,event):
        super().showEvent(event)
        if self.observed_window is not self.window():
            if self.observed_window:self.observed_window.removeEventFilter(self)
            self.observed_window = self.window()
            self.observed_window.installEventFilter(self)
        QTimer.singleShot(0,self.sync)

    def hideEvent(self,event):
        super().hideEvent(event)
        self.sync()

    def eventFilter(self,watched,event):
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0,self.sync)
        return super().eventFilter(watched,event)


ITEM_TAB_STYLE = ('QWidget#itemDetailTabs,QWidget#itemDetailTabs QWidget{background:transparent;}'
                  'QTabWidget{background:transparent;} QTabWidget::pane{border:0;padding:0;}'
                  'QTabWidget QWidget{background:transparent;} QTabWidget::tab-bar{alignment:center;}'
                  'QTabBar::tab{font-size:10px;padding:6px 5px;margin:0 1px 0 0;border-radius:5px;color:#b5c3d6;}'
                  'QTabBar::tab:selected{background:#3a495f;color:#f1dfbf;} QScrollArea{border:0;}')


def add_fallback_panel(card, item, market, source_requested, *, active=lambda:True):
    """An exact catalog selection can have sightings before its database exists."""
    card.listing_item = item
    from .price_widgets import ItemDetailTabs
    card.tabs = ItemDetailTabs()
    card.tabs.setStyleSheet(ITEM_TAB_STYLE)
    for title, note in (('Overview','Item details are not in the local database.'),
                        ('Sources','Obtain sources are not in the local database.')):
        page = QWidget()
        body = QVBoxLayout(page)
        body.setContentsMargins(5,7,5,0)
        body.addWidget(label(note,muted=True))
        body.addStretch()
        card.tabs.addTab(page,title)
    card.where_seen = WhereSeenPanel(item,getattr(market,'listings',None),source_requested=source_requested,
                                    selected=lambda:card.tabs.currentWidget() is card.where_seen and active())
    card.tabs.addTab(card.where_seen,'Where seen')
    card.tabs.currentChanged.connect(lambda *_:card.where_seen.sync())
    card.set_panel(card.tabs)
    card.tabs.fit_page()
