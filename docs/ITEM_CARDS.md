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

## Browsing and returning to a card

`price_views.py` owns the Prices content switch. The navigation button sits
above one full-height view: either the selected item or on-screen cards/history.
There is no capped second list beneath an open card. Returning to on-screen
items retains the selected card, its subtab and both outer scroll positions;
Return to item details restores that same object. A genuinely new selection
starts at the top. Price updates still reach the retained card without changing
the visible view or initiating an individual price request.

The return action remains available if the shop closes while the list is open.
Clearing/replacing the selection and watch-list collapse retain their existing
navigation behavior. Hidden details release visible source/listing demand; an
on-screen description can supply that demand instead when its card is visible.
The navigation state is GUI-only and cannot validate an offer or an overlay.

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
or tab changes. `ItemDetailTabs` eases its height over 220 ms while its pages
remain laid out at the destination size. Growing content is revealed through
the moving viewport rather than squeezed or clipped until the final frame.
Automatic cards pass the exact height delta to their `CardArea`; a second height
animation must not trail the tab's clock. Retargeting starts at the visible
height, including a return before the first tick. Quote updates retain the
current geometry and transition clock.

Opening and closing a selected item in Prices retain the full 130 ms composited
fade/lift transition. The factory initializes the price summary with the actual
selected quote/offer once, avoiding temporary empty-price renders. Do not replace
this motion with an immediate swap or a shortened fade to meet performance
targets. Page slides, watched-section expansion and rolling numbers also retain
their durations; only Reduce motion and hidden surfaces bypass their effects.
Cached thumbnails are populated before the new card is shown, so the full card
reveal includes its image instead of capturing an inner image fade at zero.

`card_morph.py` interpolates the actual styled frame when replacing cards of
different sizes. Foreground text and images keep their native size and crossfade
with the existing short lift; the complete card is never stretched as a bitmap.
Clipping follows its outer viewport. An interruption captures the currently
visible composition, avoiding a jump to an obsolete endpoint.

Animation work is bounded independently of its duration. Number rolls reuse
glyph advances, wrapped labels cache a small set of measured heights, and
unchanged capture/translation status cannot repeatedly repolish its style.
Watched expansion settles only the affected owner layouts, stopping before
the main page stack. `AnimatedTabs` owns its tab bar/stack geometry and changes
the native current page after the slide, so Qt cannot prematurely hide the
departing page or end its child animations. Adjacent slides keep unrelated
pages hidden; a longer slide shows every page in its travel range.
`slide_surface.py` temporarily composites opaque page images to avoid painting
the complete widget tree each frame. The departing page retains its exact
captured appearance through the slide; background data, child fades and layout
changes cannot dissolve its cards while it moves away. Intermediate pages are
also static. Capture departure pixels before disabling stack painting, otherwise
Qt can return a blank child image despite its visible state. Incoming own-widget
text, rolling digits, models, images, control
state and geometry changes invalidate affected regions. Reversing a slide
promotes its new destination to the latest live state. Nested motion propagates
into a live containing surface. The real widgets keep focus and
input; there is no application-wide or desktop input filter. Completion/hide
disconnects observers and releases pictures, with no resting animation timer.
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
`listing_rows.py` holds at most 100 lightweight sighting records in one painted
viewport, without a widget tree per seller. Only exposed rows paint. Minute age
changes retain visible rolling digits/fades using shared clocks rather than one
animation per row; unchanged refreshes do not restart them.
A new automatic item starts on its default
tab. Visibility uses explicit owner/subtab state, never parent walks through
Qt's private stacked widgets. Shared image demand includes the visible automatic
card, with late media/report results updating its retained rows.

See [the market-listing contract](MARKET_LISTINGS.md),
[the recognition contract](SHOP_RECOGNITION.md) and
[verification](../VERIFICATION.md) for validation and platform limits.
