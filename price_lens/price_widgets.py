"""Persistent price cards: update fields in place instead of rebuilding on every quote."""
from PySide6.QtCore import Qt,QTimer,Signal,QVariantAnimation,QEasingCurve,QSize,QRect
from PySide6.QtWidgets import QFrame,QHBoxLayout,QPushButton,QVBoxLayout,QWidget,QSizePolicy

from .domain import WORLD,age_text,compare
from .motion import AnimatedTabs,RollingLabel,visibility,enabled
from .ui_components import COLORS,mesos,text_label
from .thumbnails import ItemImage
from .watchlist_ui import WatchButton


LOOKUP_MESSAGES={'no-sales':'No observed sales','variant-mismatch':'Item variant unverified',
                 'unit-mismatch':'Price units unverified','identity-mismatch':'Market reference unverified'}


class ItemDetailTabs(AnimatedTabs):
    """Owned tab geometry: stable destination pages inside an animated card."""
    height_changed=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('itemDetailTabs')
        self.animation.setDuration(220)
        self.measure=QTimer(self);self.measure.setSingleShot(True);self.measure.setInterval(0)
        self.measure.timeout.connect(self.fit_page)
        self.currentChanged.connect(lambda *_:self.measure.start())
        self.height_animation=QVariantAnimation(self);self.height_animation.setDuration(220)
        self.height_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.height_animation.valueChanged.connect(self.resize_height)
        self.height_animation.finished.connect(self.finish_height)
        self.resizing=False;self.target_height=None;self.visual_height=0
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)

    def addTab(self,page,title):
        index=super().addTab(page,title);self.measure.start();return index

    def removeTab(self,index):
        super().removeTab(index);self.measure.start()

    def setTabText(self,index,title):super().setTabText(index,title);self.measure.start()
    def sizeHint(self):return QSize(200,self.height())
    def minimumSizeHint(self):return QSize(0,self.height())

    def motion_rect(self):
        return QRect(0,0,self.width(),max(0,(self.target_height or self.height())-self.bar_height()))

    def place_children(self):
        bar_height=self.bar_height();width=min(self.width(),self.bar.sizeHint().width())
        self.bar.setGeometry((self.width()-width)//2,0,width,max(0,bar_height-4))
        height=max(self.visual_height,(self.target_height or self.height())-bar_height) if self.resizing else max(0,self.height()-bar_height)
        self.stack.setGeometry(0,bar_height,self.width(),height)

    def page_height(self):
        page=self.currentWidget()
        if page is None:return self.height()
        content=180
        if self.tabText(self.currentIndex())=='Overview' and page.layout():
            layout=page.layout();width=max(140,self.width()-2)
            content=max(42,layout.totalHeightForWidth(width) if layout.hasHeightForWidth() else layout.sizeHint().height())
        return content+self.bar_height()

    def prepare_page(self,index):self.fit_page()

    def fit_page(self):
        height=self.page_height()
        if self.resizing and height==self.target_height:return
        if self.height()==height:
            if self.resizing:self.target_height=height;self.finish_height()
            return
        current=self.height();self.height_animation.stop();self.resizing=False
        if not enabled(self) or self.target_height is None:
            self.target_height=height;self.setFixedHeight(height);self.place_children();self.height_changed.emit();return
        self.visual_height=max(self.stack.height(),height-self.bar_height())
        self.target_height=height;self.resizing=True;self.hold_layout('height');self.place_children()
        self.base=self.motion_rect();self.slide_width=self.base.width()
        for index in range(self.count()):self.widget(index).resize(self.base.size())
        self.height_animation.setStartValue(float(current));self.height_animation.setEndValue(float(height));self.height_animation.start()

    def resize_height(self,value):
        if not enabled(self):self.finish_height();return
        self.setFixedHeight(round(value));self.height_changed.emit()

    def finish_height(self):
        self.height_animation.stop();self.resizing=False
        if self.target_height is not None:self.setFixedHeight(self.target_height)
        self.visual_height=0;self.place_children()
        self.release_layout('height')
        self.height_changed.emit()

    def resizeEvent(self,event):
        self.place_children()
        if self.resizing and event.oldSize().width()==event.size().width():return
        super().resizeEvent(event);self.measure.start()

    def showEvent(self,event):
        super().showEvent(event)
        if self.height_animation.state()==self.height_animation.State.Paused:
            if enabled(self):self.height_animation.resume()
            else:self.finish_height()
        self.measure.start()

    def hideEvent(self,event):
        if self.height_animation.state()==self.height_animation.State.Running:self.height_animation.pause()
        super().hideEvent(event)


def display_age(quote,now,ttl):
    """Only changes that can alter visible reference text invalidate a card."""
    if quote is None:return None
    return (quote.cache_valid(now,ttl),quote.fresh(now,ttl),
            age_text(max(0,now-quote.observed_at)) if quote.observed_at is not None else '',
            age_text(max(0,now-quote.fetched_at)) if quote.source!='MesoWatch' else '')


class PriceCard(QFrame):
    activated=Signal(object,object)

    def __init__(self,watchlist=None,watch_button=None,**data):
        super().__init__()
        self.selectable=False
        self.setObjectName("card")
        layout=QVBoxLayout(self)
        layout.setContentsMargins(12,10,12,10)
        layout.setSpacing(7)
        self.fields={}
        def field(name,parent,style="font-size: 11px; color: #98a3b1",wrap=True):
            numeric = name in ('store','market')
            widget=RollingLabel() if numeric else text_label('',style,wrap)
            widget.setStyleSheet(style)
            self.fields[name]=widget
            parent.addWidget(widget)
            return widget
        self.header_widget=QWidget();self.header_widget.setStyleSheet('background:transparent')
        header=self.header=QHBoxLayout(self.header_widget);header.setContentsMargins(0,0,0,0);header.setSpacing(8)
        self.thumbnail=ItemImage();self.thumbnail.hide();header.addWidget(self.thumbnail)
        names=QVBoxLayout();names.setContentsMargins(0,0,0,0);names.setSpacing(4)
        field("name",names,"font-size: 14px; font-weight: 650")
        field("context",names,"font-size: 10px; color: #98a3b1")
        header.addLayout(names,1)
        self.watch_button=watch_button if watch_button is not None else WatchButton(self)
        if watchlist is not None:self.watch_button.bind(watchlist)
        header.addWidget(self.watch_button,0,Qt.AlignmentFlag.AlignTop);layout.addWidget(self.header_widget)
        self.selected_mode=bool(data.get('selected'))
        self.price_column=QWidget();self.price_column.setStyleSheet('background:transparent')
        values=QVBoxLayout(self.price_column);values.setContentsMargins(0,0,0,0);values.setSpacing(6)
        layout.addWidget(self.price_column)
        if not self.selected_mode:field("status",values)
        numbers=QHBoxLayout()
        self.store=QWidget()
        self.store.setStyleSheet("background: transparent")
        store=QVBoxLayout(self.store);store.setContentsMargins(0,0,0,0)
        self.store_caption=text_label("Store price","font-size: 10px; color: #98a3b1")
        store.addWidget(self.store_caption)
        field("store",store,"font-size: 17px; font-weight: 650")
        numbers.addWidget(self.store)
        market=QVBoxLayout()
        market.addWidget(text_label("Market reference","font-size: 10px; color: #98a3b1"))
        field("market",market,"font-size: 17px; font-weight: 650")
        numbers.addLayout(market)
        if self.selected_mode:
            numbers.addStretch()
            status=field('status',numbers,'font-size:11px;color:#98a3b1')
            status.setMaximumWidth(126);status.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            status.setFixedHeight(40)
            policy=status.sizePolicy();policy.setRetainSizeWhenHidden(True);status.setSizePolicy(policy)
            self.fields['store'].setMinimumWidth(116);self.fields['market'].setMinimumWidth(116)
        values.addLayout(numbers)
        if self.selected_mode:
            metadata=QHBoxLayout();metadata.setSpacing(8)
            field('recent',metadata,'font-size:10px;color:#b3c0d2',False)
            field('sales',metadata,'font-size:10px;color:#a5b5ca',False)
            for name in ('recent','sales'):
                self.fields[name].setMinimumWidth(0);self.fields[name].setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
            self.fields['sales'].setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            metadata.setStretch(0,3);metadata.setStretch(1,2)
            values.addLayout(metadata)
        else:
            field('recent',values,'font-size:10px;color:#b3c0d2')
            field('sales',values,'font-size:10px;color:#a5b5ca')
        for name in ("units","age","progress","explanation"):field(name,values,"font-size: 10px; color: #98a3b1")
        self.link=QPushButton('View price source ↗');self.link.setObjectName('quiet')
        self.link.clicked.connect(self.visit_source);values.addWidget(self.link,0,Qt.AlignmentFlag.AlignLeft)
        self.update_data(**data)

    def set_panel(self,panel):
        panel.setMinimumWidth(0);self.layout().addWidget(panel)
        self.sync_summary_size()

    def sync_summary_size(self):
        if not self.selected_mode:return
        width=max(120,self.width()-24-40-32-16)
        title=max(self.fields['name'].fontMetrics().height(),self.fields['name'].heightForWidth(width))
        context=self.fields['context'].fontMetrics().height()+4 if self.fields['context'].text() else 0
        self.header_widget.setFixedHeight(max(42,title+context))
        # Numbers, captions and metadata keep stable rows as price/count digits
        # change. Optional set units depend on the item, never the quote age.
        self.price_column.setFixedHeight(66+(20 if self.fields['units'].text() else 0))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'selected_mode'):self.sync_summary_size()

    def set_selectable(self,enabled):
        if self.selectable==bool(enabled):return
        self.selectable=bool(enabled)
        self.setProperty('clickableItem',self.selectable)
        self.style().unpolish(self);self.style().polish(self)
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.setToolTip('Open item details' if enabled else '')

    def mouseReleaseEvent(self,event):
        if self.selectable and event.button()==Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit(self.content_item,self.content_row);event.accept();return
        super().mouseReleaseEvent(event)

    def put(self,name,text,style=None):
        label=self.fields[name]
        label.setText(text)
        visibility(label,bool(text))
        if style and label.styleSheet()!=style:label.setStyleSheet(style)

    def visit_source(self):
        callback=self.data.get("open_source")
        quote=self.data.get("quote")
        if callback and quote:callback(quote.url)

    def update_data(self,*,item,row,quote,now,ttl,paused=False,old_capture=False,lookup_error=False,
                    lookup_state="",lookup_reason="",open_source=None,
                    hovered=False,example=False,context_name=None,selected=False):
        self.data={"open_source":open_source,"quote":quote,"lookup_reason":lookup_reason}
        self.content_item,self.content_row=item,row
        price=row.get('price') or {}
        signature=(item,row.get('name') if item is None else None,price.get('quantity'),price.get('mesos'),
                   quote,ttl,paused,old_capture,lookup_error,lookup_state,lookup_reason,row.get('_identity_reason'),
                   hovered,example,context_name,selected,row.get('_offer_context'),display_age(quote,now,ttl))
        if signature==getattr(self,'display_signature',None):return
        self.display_signature=signature
        identity=item.game_id if item else None
        changing=selected and getattr(self,'selected_identity',None)!=identity
        self.selected_identity=identity
        if changing:
            for label in self.fields.values():label.setProperty('quietUpdates',True)
        self.watch_button.set_item(item)
        price=row.get("price") or {}
        verdict=compare(item,price.get("quantity"),price.get("mesos"),quote,now,ttl)
        reason=lookup_reason
        if item and quote:
            if quote.game_id!=item.game_id or quote.world!=WORLD or quote.condition!='clean':reason='identity-mismatch'
            elif quote.per_set!=item.per_set:reason='unit-mismatch'
        incompatible_reason=reason in ('variant-mismatch','unit-mismatch','identity-mismatch')
        compatible=bool(item and quote and quote.game_id==item.game_id and quote.world==WORLD
                        and quote.condition=="clean" and quote.per_set==item.per_set and not incompatible_reason)
        has_price=bool(compatible and quote.price is not None and reason not in ('no-sales','missing'))
        fresh=bool(has_price and quote.fresh(now,ttl))
        stale=paused or old_capture
        if not item:
            message,tone=('Item name ambiguous' if row.get('_identity_reason')=='ambiguous' or reason=='ambiguous'
                          else 'Item unidentified'),'muted'
        elif stale:message,tone=("Paused · last read item" if paused else "Waiting for a fresh screen"),"muted"
        elif not has_price:
            message=({'refreshing':'Updating market prices…','queued':'Market refresh queued…'}.get(lookup_state) or
                     ('Market update unavailable' if lookup_error or lookup_state=='retry' else
                      LOOKUP_MESSAGES.get(reason,'No market reference')))
            tone="muted"
        elif not fresh:
            message={"refreshing":"Refreshing market reference…","queued":"Market refresh queued…",
                     "retry":"Refresh unavailable · retry later"}.get(lookup_state,
                     ("Market report age unknown · reference only" if quote.observed_at is None else "Older market reports · reference only")
                     if quote.cache_valid(now,ttl) else "Older reference · refresh needed")
            tone="muted"
        elif quote.sample_count<5 or quote.uncertain:message,tone="Few price reports · reference only","muted"
        elif row.get('_offer_context')=='last_seen' and price:message,tone='Last seen listing','muted'
        elif hovered and not price:message,tone=("" if selected else "Market reference"),"blue"
        elif verdict.delta is not None:
            direction="below" if verdict.delta<0 else "above"
            message=f"{abs(verdict.delta):.0f}% {direction} reference" if verdict.delta else "Near reference"
            if verdict.tone=="blue" and verdict.delta:message="Near reference · "+message
            tone=verdict.tone
        else:message,tone="Store price unclear","muted"
        self.put("name",item.name if item else row.get("name") or "Item name unclear")
        self.fields['name'].setProperty('currencyIcon',False)
        self.put("context","EXAMPLE PRICES" if example else (context_name or "Item description") if hovered or selected else "")
        self.put("status",message,f"color: {COLORS[tone]}; font-size: 11px")
        self.store_caption.setText('Last seen price' if row.get('_offer_context')=='last_seen' else 'Store price')
        self.store.setVisible(not hovered or selected and bool(price))
        self.put("store",mesos(verdict.unit_price)+(" mesos" if verdict.unit_price is not None else ""))
        value=quote.price if has_price else None
        self.put("market",mesos(value)+(" mesos" if value is not None else ""),
                 f"font-size: 17px; font-weight: 650; color: {'#e8d2ac' if fresh and not stale else '#98a3b1'}")
        self.put("units",('Per set' if item and item.per_set else '') if selected else (("Prices are per set" if item.per_set else "Prices are per item")+
                          (" · resale value in mesos" if item.cash else "")) if item else "")
        age=f'Price checked {age_text(max(0,now-quote.fetched_at))} ago' if compatible and quote.source!='MesoWatch' else ''
        if compatible and quote.source!='MesoWatch':
            age+=' · latest market report '+(age_text(max(0,now-quote.observed_at))+' ago' if quote.observed_at else 'unknown')
        if compatible and quote.source!='MesoWatch' and quote.published_at is not None:age+=f' · snapshot {age_text(now-quote.published_at)} old'
        self.put('age',age if not example and not selected else '')
        # Refresh progress belongs to the shared market status. Per-card progress
        # changed card height on every refresh and shifted surrounding content.
        self.put('progress','')
        explanation=({'variant-mismatch':'The market row names a different or combined item variant. Its price is withheld.',
                      'unit-mismatch':'The market price units do not match this item. Its price is withheld.',
                      'identity-mismatch':'The market reference does not identify this exact item. Its price is withheld.',
                      'no-sales':'The source lists this exact item but has no observed sales for it.'}.get(reason,
                     'The market snapshot has no verified reference for this item.') if item and value is None else
                     'Several item IDs share this name. An exact item selection or clear item icon is needed.'
                     if not item and (row.get('_identity_reason')=='ambiguous' or reason=='ambiguous') else
                     'Keep the full item name visible. The current text does not identify a catalog item.' if not item else '')
        self.put('explanation',explanation)
        if selected:self.put('explanation','')
        if has_price and quote.source=='MesoWatch' and quote.observed_at is not None:
            from datetime import datetime,timezone
            stamp=datetime.fromtimestamp(quote.observed_at,timezone.utc).strftime('%b %d, %H:%M UTC')
            self.put('recent',('Latest observed sale · ' if selected else 'Most recent observed sale · ')+age_text(max(0,now-quote.observed_at))+' ago'+('' if selected else ' · '+stamp))
            self.fields['recent'].setToolTip(stamp)
        else:self.put('recent','')
        sales=(f'{quote.sample_count:,} sales in the last 24hr' if quote.period=='24h' else f'Reference from {quote.sample_count:,} recent sales') if has_price and quote.sample_count else ''
        self.put('sales',sales if selected else '')
        self.link.setVisible(bool(not selected and hovered and compatible and quote.url and open_source))
        if changing:
            for label in self.fields.values():label.setProperty('quietUpdates',False)
        self.sync_summary_size()
