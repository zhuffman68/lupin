# Where seen — shop sightings

The **Where seen** subtab belongs to selected item cards in Prices and Database.
It shows MesoWatch's recently observed seller, channel, FM room or other map,
asking amount, quantity, optional stock and last-seen age. It is also available
for exact catalog selections before the local database is downloaded. Cash items
have Sources and Where seen; other item cards retain Overview and Sources.
Monsters, skills, maps, quests and compact on-screen listings do not acquire an
irrelevant shop-sighting tab.

These are sightings, not live availability or purchase links. They can be sold
out before the user arrives. Missing channel/location fields remain unknown.
Lupin does not verify equipment stats from these sightings, so these offers are
not certified clean/unscrolled equipment. Sale-based market references remain
independent and keep their existing unscrolled policy.

## Request and cache lifecycle

`PriceService.listings` owns one `ListingService`, shared by both item views.
Only a visible, selected Where seen tab supplies demand. Opening Overview,
Sources, a search result, an overlay or a watched item does not download item
details. Animated tab transitions check explicit subtab/owner selection without
walking Qt's private page containers;
temporarily showing outgoing pages cannot create another request. Hiding or
minimizing the view removes pending demand and its age timer. An already started
request may complete into the cache.

The hidden tab does not build its body, query its saved state or construct
sighting-row widgets. Build and refresh that presentation only when explicitly
selected and visible. Hidden source changes leave retained rows alone; opening
the tab reconciles them with the latest cached snapshot. This keeps cached
popular items from adding hundreds of widgets to an unrelated card transition.

One native helper runs at a time for this service. New selections replace pending
demand; they never create a queue of obsolete items. If a full-market refresh is
already busy, sightings wait without blocking the GUI or screen reader. A later
full-market refresh remains independent of an already running sighting request.

The cache lifetime is **15 minutes from the completed attempt**, independently of
the user's full-market refresh interval. Successful empty results and failed
attempts also retain this cooldown. Reopening the tab or restarting the app
does not repeat a fresh saved request. Once expired, an open tab requests another
copy; otherwise the next visit does. Failures retain the previous successful
data with its original check/publication ages and an explicit refresh warning.
Expiry never makes an old sighting newly current. There is no background sweep
of all items, no notification bot and no per-frame or per-hover network request.

Disk loading, parsing and saving use one bounded `LatestJob` worker. The in-memory
cache holds at most 128 items. The shared SQLite entries cache is bounded and
prunes old non-catalog entries. Only normalized sightings are persisted, never
the detail feed's large sale history or arbitrary additional fields.

## Native source and validation

Both native `lupin-market-fetch` implementations accept a validated
`--listing-item basil:NNNNNNNN` or `cash:NNNNNNNN` argument. They use their ordinary
private WebKitGTK/WebView2 view; no personal browser or game access is involved.
The shared `native/market-fetch/listing_script.h` starts exactly one same-origin
request from the market page:

`/data/markets/Classic%20World/item/basil_NNNNNNNN.json`

The page's current bulk row supplies the listing ID, catalog ID, exact item name
and item/set basis, which the standalone detail document does not itself expose.
The raw detail document must independently report its exact ID, Classic World,
version 2, item kind and a valid publication timestamp. Both IDs must agree with
the selected canonical catalog item; aliases, wrong names/units/worlds and
malformed or future publication times cannot supply sightings. Exact-ID approved
gender spelling uses the same policy as price snapshots. Market coverage cannot
resolve an item identity.

The native request rejects redirects and bounds the decoded network response
to 32 MiB. It strips sale/history arrays, returning at most 500 source listing
rows through the existing 8 MiB UTF-8 IPC limit and 20/25-second helper/parent
deadlines. Python validates amounts as whole positive mesos and quantities,
bounded plain-text names/locations and last-seen timestamps. Removed/sold-out,
incomplete or invalid rows cannot become offers. Exact duplicate rows are
removed; the newest 100 validated sightings from that returned sample are displayed/persisted, with a
limit notice when necessary. A partial source sample is never called complete
market coverage.

The helper exits after each lookup, and late output is discarded on shutdown.
Listing failures retain only fixed diagnostics in `listing-last-error.json`,
separate from full-market diagnostics. No seller/chat/draft text enters logs.

## Presentation and ages

- **Checked** is the local completed successful download time.
- **Source published** is the detail feed's generation time, available on the
  status tooltip.
- **Seen** is each seller/location sighting time. It is never reset by refreshing.
- The whole-number asking amount is for the stated quantity, not an inferred
  unit price. The GUI's small coin remains the currency indicator.

Subtabs use the existing slide animation and fit the minimum-width selected
card. Rows scroll within the panel. Only changed listing data rebuilds rows;
minute age updates retain their widgets. Hidden pages perform no age animation
or background listing refresh. Reduce motion uses the existing app policy.

Verification and live-source evidence are recorded in [VERIFICATION](../VERIFICATION.md).
