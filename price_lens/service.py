"""One shared market snapshot; item views never issue individual price requests."""
from concurrent.futures import CancelledError,ThreadPoolExecutor
from PySide6.QtCore import QObject,Qt,QTimer,Signal,Slot
from .data import Cache,load_catalog
from .domain import DEFAULT_TTL,Quote
from .http_json import RequestToken,request_scope
from .snapshot import SnapshotStore
from .snapshot_updater import SnapshotUpdater
from .tls import retryable_catalog_error
from .market_lookup import LookupResult


class PriceService(QObject):
    catalog_ready=Signal(object)
    quote_ready=Signal(int,object)
    error=Signal(int,str)
    state_changed=Signal()
    _completed=Signal(object)

    def __init__(self,cache_path,parent=None):
        super().__init__(parent)
        self.cache=Cache(cache_path);self.snapshot=SnapshotStore(self.cache)
        self.snapshot_updater=None;self.refresh_snapshot=False;self.interval=DEFAULT_TTL
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lupin-catalog')
        self.closed=False;self.catalog_pending=False;self.catalog_retries=0;self.catalog_token=None
        self.delivered={};self.manual_item=None
        self._screen_demand=[]
        self.catalog_retry_timer=QTimer(self);self.catalog_retry_timer.setSingleShot(True)
        self.catalog_retry_timer.setInterval(1500);self.catalog_retry_timer.timeout.connect(self._request_catalog)
        self._completed.connect(self._finish_catalog,Qt.ConnectionType.QueuedConnection)

    def start(self):
        if self.closed or self.catalog_pending:return
        self.catalog_retry_timer.stop();self.catalog_retries=0;self._request_catalog()
        if self.refresh_snapshot:self.set_snapshot_enabled(True)

    @property
    def catalog_retrying(self):return self.catalog_retry_timer.isActive()

    def _request_catalog(self):
        if self.closed or self.catalog_pending:return
        self.catalog_pending=True;self.catalog_token=RequestToken()
        token=self.catalog_token
        def load():
            with request_scope(token):return load_catalog(self.cache)
        future=self.pool.submit(load)
        future.add_done_callback(lambda result:self._completed.emit(result) if not self.closed else None)
        self.state_changed.emit()

    @Slot(object)
    def _finish_catalog(self,future):
        if self.closed:return
        self.catalog_pending=False
        try:self.catalog_ready.emit(future.result())
        except CancelledError:pass
        except Exception as error:
            if self.catalog_retries==0 and retryable_catalog_error(error):
                self.catalog_retries=1;self.catalog_retry_timer.start()
            self.error.emit(0,'Item catalog unavailable: '+str(error))
        self.state_changed.emit()

    def set_refresh_interval(self,seconds):
        self.interval=max(300,min(3600,int(seconds)))
        if self.snapshot_updater:self.snapshot_updater.set_interval(self.interval)

    def set_snapshot_enabled(self,enabled):
        self.refresh_snapshot=bool(enabled)
        if self.closed:return
        if self.snapshot_updater is None:
            self.snapshot_updater=SnapshotUpdater(self.snapshot,self)
            self.snapshot_updater.set_interval(self.interval)
            self.snapshot_updater.updated.connect(self._snapshot_updated)
            self.snapshot_updater.changed.connect(self.state_changed.emit)
        self.snapshot_updater.set_enabled(enabled)

    def snapshot_summary(self):
        return self.snapshot_updater.summary() if self.snapshot_updater else ''

    def _snapshot_updated(self):
        self.observe(self._screen_demand)
        self.state_changed.emit()

    def cached(self,item):
        """Exact-ID, name and unit validation, using the in-memory generation only."""
        return self.snapshot.quote(item) if item else None

    def lookup(self,item):
        """Read one local result, including an explicit negative reference."""
        result=self.snapshot.lookup(item)
        quote=result.quote
        if quote is None and item is not None:
            checked=(self.snapshot.meta or {}).get('checked_at',0)
            published=(self.snapshot.meta or {}).get('published_at')
            basis={'no-sales':'No observed sales for this exact item',
                   'variant-mismatch':'Market variant does not match this item',
                   'unit-mismatch':'Market price units do not match this item',
                   'missing':'Item is absent from the market snapshot'}.get(result.reason,'Item identity is not verified')
            quote=Quote(item.game_id,None,checked,None,0,'MesoWatch','https://meso.watch/','no data',
                        basis=basis,per_set=item.per_set,uncertain=True,published_at=published)
        return LookupResult(quote,result.reason)

    def reference(self,item):
        """Reference Quote convenience API; does not change market demand."""
        return self.lookup(item).quote

    def _deliver(self,item):
        if self.closed:return
        quote=self.reference(item)
        if self.delivered.get(item.game_id)!=quote:
            self.delivered[item.game_id]=quote;self.quote_ready.emit(item.game_id,quote)

    def observe(self,items):
        if self.closed:return
        items=list(items);self._screen_demand=items
        demands={item.game_id:item for item in items}
        if self.manual_item:demands[self.manual_item.game_id]=self.manual_item
        for item in demands.values():self._deliver(item)

    def clear_visible(self):self.observe([])

    def set_manual(self,item):
        self.manual_item=item;self.observe(self._screen_demand)

    def state_for(self):
        updater=self.snapshot_updater
        if updater and updater.busy:return 'refreshing'
        if updater and updater.error:return 'retry'
        return ''

    def close(self):
        if self.closed:return
        self.closed=True;self.catalog_retry_timer.stop()
        if self.catalog_token:self.catalog_token.cancel()
        if self.snapshot_updater:self.snapshot_updater.close()
        self.pool.shutdown(wait=False,cancel_futures=True)
