"""Exact Classic World shop sightings, independent of sale-price snapshots."""
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
import time

from .data import timestamp
from .domain import WORLD, item_name_matches

LISTING_TTL = 900
MAX_LISTINGS = 100


def provider_id(item):
    if type(item.game_id) is not int or not 0 < item.game_id < 100000000:
        raise ValueError('Invalid item identity')
    return f'{"cash" if item.cash else "basil"}:{item.game_id:08d}'


def valid_provider_id(identity):
    return isinstance(identity, str) and bool(re.fullmatch(r'(?:basil|cash):\d{8}', identity))


@dataclass(frozen=True)
class ShopListing:
    seller: str
    location: str
    channel: int | None
    room: int | None
    price: int
    quantity: int
    stock: int | None
    last_seen: float

    @property
    def place(self):
        channel = f'CH {self.channel}' if self.channel is not None else 'Channel unknown'
        location = f'FM {self.room}' if self.room is not None else self.location or 'Location unknown'
        return f'{channel} · {location}'


@dataclass(frozen=True)
class ListingSnapshot:
    identity: str
    checked_at: float
    published_at: float
    rows: tuple[ShopListing, ...]
    more: bool = False


def _integer(value, low=1, high=2147483647):
    return value if type(value) is int and low <= value <= high else None


def _text(value, maximum):
    return value.strip() if isinstance(value, str) and len(value) <= maximum and not any(ord(c) < 32 for c in value) else ''


def parse_listings(document, item, checked_at=None):
    now = time.time() if checked_at is None else checked_at
    if not isinstance(now, (int, float)) or not math.isfinite(now):
        raise ValueError('Invalid listing check time')
    identity = provider_id(item)
    if (not isinstance(document, dict) or document.get('version') != 2
            or document.get('kind') != 'item' or document.get('market') != WORLD
            or document.get('id') != identity):
        raise ValueError('Expected exact Classic World item listings')
    catalog = document.get('catalog')
    if (not isinstance(catalog, dict) or catalog.get('id') != identity
            or catalog.get('catalogId') != identity
            or not isinstance(catalog.get('name'), str) or not 1 <= len(catalog['name']) <= 200
            or not item_name_matches(item, catalog['name'])
            or catalog.get('unitBasis') != ('set' if item.per_set else 'item')):
        raise ValueError('Listing item identity or units are unverified')
    published = timestamp(document.get('generated_at'))
    if published is None or not 0 < published <= now + 300:
        raise ValueError('Invalid listing publication time')
    source = document.get('listings')
    if not isinstance(source, list) or len(source) > 500:
        raise ValueError('Invalid shop listing list')
    rows = set()
    for row in source:
        if not isinstance(row, dict):
            raise ValueError('Invalid shop listing')
        price = _integer(row.get('price'))
        quantity = _integer(row.get('qty'))
        stock = _integer(row.get('stock'), 0)
        seen = timestamp(row.get('lastSeen'))
        seller = _text(row.get('seller'), 80)
        # A removed/sold-out shop and an incomplete amount are not offers.
        if (row.get('up') is not True or stock == 0 or price is None or quantity is None
                or not seller or seen is None or not 0 < seen <= min(now, published) + 300):
            continue
        rows.add(ShopListing(seller, _text(row.get('location'), 160),
                            _integer(row.get('channel'), high=1000),
                            _integer(row.get('channelRoom'), high=1000),
                            price, quantity, stock, seen))
    ordered = sorted(rows, key=lambda row: (-row.last_seen, row.price, row.seller, row.place))
    return ListingSnapshot(identity, now, published, tuple(ordered[:MAX_LISTINGS]),
                           bool(document.get('truncated')) or len(ordered) > MAX_LISTINGS)


def compact_document(document, snapshot):
    """Persist only sighting data; never retain the detail feed's sale history."""
    result = {key: document.get(key) for key in ('version', 'kind', 'market', 'id', 'generated_at')}
    result['catalog'] = {key: document['catalog'][key] for key in ('id','catalogId','name','unitBasis')}
    result['listings'] = [dict(seller=row.seller, location=row.location, channel=row.channel,
                              channelRoom=row.room, price=row.price, qty=row.quantity, stock=row.stock,
                              lastSeen=datetime.fromtimestamp(row.last_seen,timezone.utc).isoformat(), up=True)
                          for row in snapshot.rows]
    result['truncated'] = snapshot.more
    return result
