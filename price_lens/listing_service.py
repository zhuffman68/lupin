"""One demand-driven sighting reader, bounded cache and asynchronous disk work."""
from collections import OrderedDict
from dataclasses import dataclass
import time
import weakref

from PySide6.QtCore import QObject, QTimer, Signal

from .background_job import LatestJob
from .market_listings import LISTING_TTL, compact_document, parse_listings, provider_id
from .snapshot_fetcher import SnapshotFetcher


class ListingFetcher(SnapshotFetcher):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.identity = ''
        self.error_filename = 'listing-last-error.json'

    def command(self):
        from .market_listings import valid_provider_id
        if not valid_provider_id(self.identity):
            raise ValueError('Invalid listing identity')
        return super().command() + ['--listing-item', self.identity]


@dataclass
class ListingState:
    snapshot: object = None
    attempt_at: float = 0
    error: str = ''
    document: object = None


class ListingService(QObject):
    changed = Signal(int)

    def __init__(self, cache, parent=None, *, fetcher=None, clock=time.time, market_busy=None):
        super().__init__(parent)
        self.cache, self.clock = cache, clock
        self.market_busy = market_busy or (lambda: False)
        self.fetcher = fetcher or ListingFetcher(cache.path.parent / 'listing-webview', self)
        self.fetcher.ready.connect(self._received)
        self.fetcher.failed.connect(self._failed)
        self.storage = LatestJob('lupin-listings', self)
        self.storage.completed.connect(self._stored)
        self.states = OrderedDict()
        self.interests = OrderedDict()
        self.operation = None
        self.fetching = None
        self.closed = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._pump)

    def state(self, item):
        return self.states.get((provider_id(item),item.name,item.per_set))

    def loading(self, item):
        key = provider_id(item)
        return bool((self.fetching and provider_id(self.fetching) == key)
                    or (self.operation and provider_id(self.operation[1]) == key))

    def set_interest(self, owner, item):
        key = id(owner)
        self.interests.pop(key, None)
        if item is not None and not self.closed:
            self.interests[key] = (weakref.ref(owner), item)
        self._pump()

    def _desired(self):
        for key, (owner, _) in list(self.interests.items()):
            if owner() is None:
                self.interests.pop(key, None)
        return next(reversed(self.interests.values()))[1] if self.interests else None

    def _remember(self, item, state):
        key = (provider_id(item),item.name,item.per_set)
        self.states[key] = state
        self.states.move_to_end(key)
        while len(self.states) > 128:
            self.states.popitem(last=False)

    def _pump(self):
        self.timer.stop()
        if self.closed or self.operation or self.fetching:
            return
        item = self._desired()
        if item is None:
            return
        state = self.state(item)
        if state is None:
            self.operation = ('load', item)
            def load(token):
                record = self.cache.get('market-listings', provider_id(item))
                token.check()
                return self._decode(record, item)
            self.storage.submit(load)
            self.changed.emit(item.game_id)
            return
        due = state.attempt_at + LISTING_TTL
        if 0 <= self.clock() - state.attempt_at < LISTING_TTL:
            self.timer.start(max(1000, min(900000, int((due - self.clock()) * 1000) + 1)))
            return
        # Avoid two simultaneous web views when the full-market update starts.
        if self.market_busy():
            self.timer.start(1000)
            return
        self.fetching = item
        self.fetcher.identity = provider_id(item)
        self.fetcher.start()
        self.changed.emit(item.game_id)

    def _decode(self, record, item):
        if not isinstance(record, dict):
            return ListingState()
        try:
            checked = record.get('checked_at', 0)
            snapshot = parse_listings(record['document'], item, checked) if record.get('document') else None
            attempt = record.get('attempt_at', checked)
            if type(attempt) not in (int, float) or not 0 < attempt <= self.clock() + 300:
                return ListingState()
            return ListingState(snapshot, attempt, 'Shop sightings could not be refreshed.' if record.get('error') else '',
                                record.get('document'))
        except (ValueError, TypeError, KeyError, OverflowError):
            return ListingState()

    def _received(self, document):
        if self.closed or self.fetching is None:
            return
        item = self.fetching
        now = self.clock()
        self.operation = ('save', item)
        def save(token):
            snapshot = parse_listings(document, item, now)
            compact = compact_document(document, snapshot)
            token.check()
            self.cache.put('market-listings', provider_id(item),
                           {'checked_at': now, 'attempt_at': now, 'document': compact})
            return ListingState(snapshot, now, '', compact)
        self.storage.submit(save)

    def _failed(self, _message):
        if self.closed or self.fetching is None:
            return
        item = self.fetching
        old = self.state(item) or ListingState()
        state = ListingState(old.snapshot, self.clock(), 'Shop sightings could not be refreshed.', old.document)
        self.operation = ('failure', item)
        def save_failure(token):
            token.check()
            self.cache.put('market-listings', provider_id(item),
                           {'checked_at': old.snapshot.checked_at if old.snapshot else 0,
                            'attempt_at': state.attempt_at, 'document': old.document, 'error': True})
            return state
        self.storage.submit(save_failure)

    def _stored(self, result):
        if self.closed or self.operation is None:
            return
        kind, item = self.operation
        self.operation = None
        if result.error is not None and kind == 'save':
            # Validation failures must retain the last-good sightings as well.
            self._failed('')
            return
        state = result.value
        if result.error is not None:
            old = self.state(item) or ListingState()
            state = ListingState(old.snapshot, self.clock(), 'Shop sightings are unavailable.', old.document)
        self._remember(item, state)
        if kind != 'load':
            self.fetching = None
        self.changed.emit(item.game_id)
        self._pump()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        self.interests.clear()
        self.fetcher.close()
        self.storage.close()

    def wait_closed(self):
        self.storage.pool.shutdown(wait=True, cancel_futures=True)
