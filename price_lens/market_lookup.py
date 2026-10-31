"""Shared local market lookup result and adapters, without UI dependencies."""
from dataclasses import dataclass

from .domain import Quote


@dataclass(frozen=True)
class LookupResult:
    """Reference and its identity/data status, separate from freshness."""
    quote: Quote | None
    reason: str


def market_lookup(market,item):
    """Read one local reference; support small cached-only service doubles.

    Production PriceService.lookup returns both fields in one operation. This
    adapter never requests, refreshes, observes or writes anything.
    """
    if item is None:return LookupResult(None,'unidentified')
    lookup=getattr(market,'lookup',None)
    if callable(lookup):
        result=lookup(item)
        if isinstance(result,LookupResult):return result
    cached=getattr(market,'cached',None)
    quote=cached(item) if callable(cached) else None
    reason_lookup=getattr(market,'lookup_reason',None)
    reason=reason_lookup(item) if callable(reason_lookup) else None
    if not isinstance(reason,str) or not reason:
        reason='priced' if quote is not None and quote.price is not None else 'missing'
    return LookupResult(quote,reason)


def market_lookup_reason(market,item):
    return market_lookup(market,item).reason
