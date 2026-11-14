# Shared item cards

Prices search, watched/recent selections, automatically read inventory/equipment
or linked-item descriptions, and Database items share the same detailed card.
The item picture/name/watch control sit above a compact market/asking-price
summary. Overview, Sources and Where seen span the width below it. Player-shop
rows retain a compact browsing form; clicking one opens the detailed card with
its asking price and comparison. Clicking its star only changes the watch list.

## Ownership and identity

`item_cards.py` is the common detailed-card factory. It requires a matching exact
catalog ID/name before attaching local database details. Missing entries receive
the same summary/tab layout with explicit unavailable-detail text. An ambiguous
OCR identity remains a neutral compact card and cannot acquire another item's
database entry or listings. Equipment Overview values are base database stats,
independently of the native item's rolled/scrolled values.

Automatic descriptions stay in the existing `ActiveCards`/`CardArea` lifecycle:
the two-second grace and bounded session history remain in place. A new item
replaces that active slot; only actual expiry moves it into history. Explicit
search/watch/history/shop selections retain precedence over automatic readings.
The shared factory constructs entry-specific widgets on an item/core-data
change; quotes, report ages and counts update retained fields. The selected tab
and list scroll positions survive same-item price updates.

## Layout

`PriceCard` supplies both compact shop rows and the detailed summary. Header,
price and metadata rows have stable dimensions for the selected item/width, so
changing digits or quote ages cannot move the tabs. `ItemDetailTabs` measures
Overview's natural height, and source/listing views use a bounded list viewport.
Overview contains a plain widget, with two fact cells per row and inline
requirements. It has no nested scrollbar; unusually long content belongs to the
outer Prices/Database page. Sources uses its list's scrolling rather than a
scroll area around another scrolling list. Cash items retain Sources/Where seen
without an irrelevant Overview.

Sizing is established before inserting a new card and measured again on width
or tab changes. Automatic cards notify their canvas when that height changes;
the canvas adjusts through its normal height animation. CardArea invalidates
application layouts without descending into Qt's private tab-container layouts.
Item tabs retain their existing slide and reduced-motion behavior.

Opening and closing a selected item in Prices retain the full 130 ms composited
fade/lift transition. The factory initializes the price summary with the actual
selected quote/offer once, avoiding temporary empty-price renders. Do not replace
this motion with an immediate swap or a shortened fade to meet performance
targets. Page slides, watched-section expansion and rolling numbers also retain
their durations; only Reduce motion and hidden surfaces bypass their effects.

Animation work is bounded independently of its duration. Number rolls reuse
glyph advances, wrapped labels cache a small set of measured heights, and
unchanged capture/translation status cannot repeatedly repolish its style.
Watched expansion settles only the affected owner layouts, stopping before
Qt's private page stack. Adjacent tab slides keep unrelated pages hidden; a
longer slide still shows every page in its travel range, with live page content.
Database count/date summaries refresh on database updates rather than each
navigation/status tick.

## Scrolling

`smooth_scroll.py` eases ordinary wheel input over 125 ms in Lupin's own lists
and scroll areas. Repeated notches retarget one bounded animation; there is no
queue of delayed scrolling. Lists use pixel scrolling. Trackpad pixel/gesture
input, modified wheel events and scrollbar dragging retain Qt's direct behavior.
External position changes take over immediately; hiding a viewport cancels
motion. Reduce motion makes wheel movement immediate. Event filters belong
only to the app's own viewports and scrollbars, never to the desktop or game.
Reference-image demand is coalesced during wheel animation, with a final demand
update when movement settles and the existing nearby-image prefetch retained.

## Asking prices and refreshes

An expanded shop card retains the asking quantity/amount alongside the shared
market reference. The current page/slot/item must still match to call that offer
current. Closing/scrolling/pausing or losing that offer changes its caption to
**Last seen price**. It remains historical context and cannot establish a live
deal or an overlay offer. Search/history may show a last-seen asking price from
the bounded session record; inventory sightings alone never invent one.

Screen recognition, current-offer validation and annotation construction remain
independent of card enrichment. Card layout runs after annotation delivery. All
reference values still come from the local full-market snapshot.

## Background demand

Stats and cached sources come from the local database. External item-source
requests begin only for a visible Sources view. An automatic cash card showing
its default Sources tab uses cached data until the user activates that tab.
Where seen retains its separate 15-minute positive/empty/failure cache and only
the selected visible item tab supplies demand; moving through descriptions does
not preload every item's listings. Its body and cached sighting rows are also
created only when that tab is visible; hidden refresh signals do not build or
rebuild them. Previously displayed rows remain retained for the next visit.
A new automatic item starts on its default
tab. Visibility uses explicit owner/subtab state, never parent walks through
Qt's private stacked widgets. Shared image demand includes the visible automatic
card, with late media/report results updating its retained rows.

See [the market-listing contract](MARKET_LISTINGS.md),
[the recognition contract](SHOP_RECOGNITION.md) and
[verification](../VERIFICATION.md) for validation and platform limits.
