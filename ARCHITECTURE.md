# Lupin architecture

Lupin provides market references, EXP/meso tracking, local Korean translation and a searchable Classic World database for MapleStory Classic World.

## Observation boundary

Game observations come only from ordinary OS-shared screen pixels. No game-process discovery, handles, memory, files, packets, rendering/input hooks or game input are used. The annotation canvas is an independent input-transparent window. OS cursor coordinates position inventory cards. Windows shortcuts use RegisterHotKey; Wayland uses the GlobalShortcuts portal and X11 uses passive grabs for the chosen chords.

Screenshots, chat and drafts remain local. Market downloads contain public market data; image downloads use exact catalog IDs. The Korean writer copies validated text to the OS clipboard only after an explicit action. It never pastes, sends keys or focuses a game field.

## Processes and data flow

```mermaid
flowchart LR
    OS[OS display capture] --> Stream[Persistent capture helper]
    Stream --> Reader[Frame scheduler and Rust OCR]
    Reader --> Identity[Visible name, category and exact-ID artwork]
    Identity --> UI[Prices and independent overlays]
    Snapshot[Full-market download] --> Cache[(Local snapshot)]
    Cache --> UI
    Search[Search and watched items] --> Cache
    Images[Exact-ID item images] --> Search
    Reader --> Tracking[EXP and pickup ledger]
    Stream --> Pickups[Crop-only pickup reader]
    Pickups --> Tracking
    Tracking --> UI
    Stream --> Translate[Local Korean OCR and translation]
    Translate --> UI
    Draft[English draft] --> Writer[Local Korean writer]
    Writer --> Clipboard[OS clipboard]
```

The main Qt process owns settings, layouts, market state and session accounting. Capture and annotations use separate helpers. The Rust reader accepts only local RGBA/PNG input through its own JSON stdin/stdout. Translation workers communicate over bounded local pipes and load their verified models on demand. All portal callbacks enter the Qt GUI thread through signals.

## Capture and recognition

Linux retains its approved PipeWire/portal sharing session. SIGUSR1 hands the capture helper to a replacement UI without another chooser. Normal Quit ends sharing. The explicit KDE screenshot fallback remains available for troubleshooting.

Windows captures the selected OS display with `QScreen.grabWindow(0)`, using desktop GDI rather than Direct3D desktop duplication. It never obtains a game window handle. The dropdown contains real displays; geometry changes update the selected display. Capture runs at most ten times per second, pauses without demand, and skips work while its local output is busy.

Frame dimensions and local buffers are bounded. The client drains packets promptly and retains one newest completed frame; the display interval applies to delivery, not socket reads. Superseded frames are discarded. Pause, stop and display changes clear pending delivery.

`SubmittedRequest` in `reader_request.py` captures each job's mode, implicitly
shared source image, pointer, crop/analysis coordinates, generation, relevant
shop or tracking epoch and timeout deadline. Result handling uses that submitted
context rather than mutable current-frame flags. EXP-only work does not consume
an unread shop sequence. `PixelReader.request_rescan()` requests newest-frame
work without changing the deadline of an already running request.

The visible bottom status bar and static frame evidence locate Classic World. FPS and movable minimap placement are not anchors. Shop/tooltip pixel fingerprints avoid repeated OCR and preserve proven identities through modest movement and occlusion. Equipment names include gender/stat/tier evidence; ambiguous IDs remain unresolved.

Only a missing, uncovered shop price triggers a retry. A cropped shop passes through the unchanged strict upstream reader at two resamplings. Recovery requires agreement on exact name, row position, quantity and the complete meso amount. Existing prices are never overwritten. An eight-patch pixel cache also remembers failures. The pinned Minerva revision and OCR model are unchanged; the worker uses two OCR threads.

`reader/src/shop_names.rs` recovers independently readable native lines across
unread slots on a verified table, including neighbors touched by a description.
The request supplies only known table geometry; fresh compatible row positions
establish its grid. An unrelated palette-compatible window, such as Sold Items,
cannot veto independently proven current components on that table or supply its
grid, rows or hover identity. Native blue/orange text needs visible ink and a complete
ending before a cursor/pane interruption, with agreement at two resamplings.
An explicit native ellipsis may use its smaller natural margin only after both
reads agree on the literal marker and the current pixels contain all three small
aligned dots. Exact catalog-prefix rules still decide identity; arbitrary cut
prefixes do not gain a match. Ordinary asking-line margins and number guards are unchanged.
Each recovered name has `nameArea`; an independently readable asking line has
`priceArea` and must pass strict quantity, grouping and measured-width checks.
Otherwise the row is `nameOnly`, with a null price and no inferred tier. The
fallback neither reads description text nor guesses a hidden name or number.
The glyph cache holds at most 96 successes/misses and work is limited to 24 slots;
it adds no weights or runtime dependencies.

Asking recovery reads the complete quantity, "for" and canonical grouped amount;
the currency word supplies no authority. Both OCR resamplings must agree.
`priceArea` and `priceValueArea` cover the same numeric glyphs and an independently
visible native termination boundary; `priceText` is only `Q for N`. A final group
of three digits requires a blank next-comma footprint, including its descender;
short amounts require a whole next-digit advance. Measured font advances, digit
shape and full core width prevent a clipped continuation or skinny last digit
from masquerading as a complete amount. Joined zeroes retain their separate
measured cells instead of requiring one disconnected ink run per character.
Python independently validates those
rectangles, grammar, text/value equality, native pixels and exact submitted/latest
components. Every mask over numeric ink rejects the amount. This check runs even
when a broader masked row proof matches; page changes discard all prior amounts.
Later visible slots can establish the bounded native row-grid phase when the top
slots are sold out. Current complete ordinary-reader results are not downgraded
merely because optional component recovery cannot reproduce them.

Cursor exclusions match the native inventory proof's 32 by 37 pixel footprint,
six pixels left and seven above the hotspot, scaled with the native UI. Actual foreign pixels remain
invalid outside that envelope. Container checks sample the fixed inner bevel,
not the external shadow or scenery; a character animating behind a shop cannot
make its complete page repeatedly disappear.

Orange-selected component recovery uses the native selection's antialiasing
range and coloured name/price separator. Only bounded outer scanlines may accept
a separately measured native bevel: a broad, uninterrupted prefix must match its
known background palette. Real dark text and unknown popup pixels are retained,
not erased. The Python component check uses the same normalization and the
reader's rounded 8-bit `<160` ink cutoff, so a faint antialias fringe cannot add
a spurious glyph column beyond an exported complete-line proof. A selected row
can therefore be read on a fresh scrolled page without borrowing its old price.

Cached snapshot deliveries for a newly read page are batched into one control
panel update. The annotation helper receives complete references before the
heavier card/history layout. No per-item network call is added. Positive market
values below one display as `<1`, retaining their original numeric comparison.
Single-item inventory/equipped annotations protect their independently verified
native panel (or at least the current title when no panel proof exists), as well
as honoring the game bounds. They cannot follow the pointer across their own
next-read frame/title evidence. Paired inventory cards retain their additional
source-cell, header and comparison guards.
During a brief OCR bridge, independently present retained panel geometry stays
protected even when no new title proof is produced. This is placement evidence
only; it never supplies or changes an item identity.

`PriceObservations` checks component rectangles against their row and submitted
read extent. Native ink, a natural ending, exact submitted/latest pixels and no
mask over semantic glyphs establish component authority. A masked blank tail
cannot invalidate an otherwise complete line; blocked titles or number prefixes
remain unknown. A broad native separator at the top edge may account for OCR's
one-pixel ascent offset; its pixels still match the newest frame exactly, and
isolated white caption/description pixels are not separators.
Independent shop guards and exact catalog resolution remain
mandatory. A covered icon or old popup cannot resolve an ambiguous rescued row.
Loaded identity-only rows survive later misses without acquiring a current offer.
An earlier same-page/slot/exact-item asking amount is retained separately for
presentation; restoring name-only pixels cannot promote it to a fresh offer.
Scrolling clears this amount with the old page. A complete asking read replaces
the name-only row in place.

The UI requests recovery for a pending page, any unknown row or a name-only row
whose asking line remains unread. A verified description touching the table also
keeps this bounded path available: a known subset is not proof that the ordinary
detector returned every occupied slot. Complete pages without a pane skip it.
Unchanged stationary shops no longer repeat description OCR on a 200 ms timer;
pixel changes, pointer changes, explicit rescans and periodic game-location checks
still schedule work. Description geometry uses bounded batched stroke checks
equivalent to the scalar predicate. An unchanged recognized name rectangle may
reuse its panel only while its existing description proof matches both the
submitted and latest images; moved/changed/unverified descriptions are searched
normally. Market references still come exclusively from the shared snapshot.

`tooltip_source.py` gives native item titles their own bounded pixel proof.
Inside an independently present description panel, bright white/colored glyph
positions and colors stay exact while its dark translucent background may vary.
Changed letters, new bright occluders, lost panels and insufficient exposed ink
invalidate the proof. Without panel evidence, matching remains byte-exact.
This does not relax shop-row, item-icon or asking-price source checks. Inventory
associations reuse this title proof, retaining exact source-cell and interior
header/frame guards, with the bounded native decoration rules below.
For that independently bound path only, byte-exact opaque glyph cores anchor a
bounded antialiased fringe whose blended edge colour can follow scenery behind
the panel. Added/moved/recoloured opaque strokes, foreign bright pixels and
erased edges still reject the title, including inside annotation/cursor masks.
The GUI reuses the same immutable association title instead of applying a
second strict fringe check. Generic and shop titles retain exact bright ink.
`inventory_pixels.py` and `reader/src/inventory_pixels.rs` agree on the native
selected-tab white pulse. Version-three exports include an explicit `sourceTab`;
only that verified path uses an immutable `InventoryHeader` rather than a raw
header hash. A per-pixel distance-from-white fit permits bounded 4x lighting
change with three RGB units of quantization/resampling error and a one-pixel
sprite fringe. Enough pink selection must remain, and the caption, buttons and
inactive tabs stay exact outside rounded header corners. Missing/changed tabs,
erased letters and unrelated paint still reject the source. Older metadata
retains its strict guards. The cell interior remains byte-exact outside the
cursor; changed rim pixels may only remain native gold on both frames within
one scaled pixel of the border. At least 16 scaled interior pixels must be
exposed, so the decorative ring alone never supplies item identity.
Tooltip corners require two current strokes in a three-sample lane at each end,
plus a terminating cap and both complete side rails. A single background pixel
can no longer erase a corner; a short inventory divider through the header
cannot replace a full rail. Failed candidate rails continue the bounded search.
Known Lupin annotation rectangles travel with the immutable submitted request
in source-image coordinates. The reader clips them to its analysis origin and
treats those rim samples as unknown, requiring independently exposed samples
on both sides and both corners. It masks that paint out of OCR so Lupin's own
item names cannot become game titles. Python validates the submitted frame with
its submitted rectangles and each latest frame with the current rectangles;
fully hidden rims/corners and changed native title/source/header evidence still
fail. These geometry masks do not excuse source-cell or header pixel changes.
Stationary tooltips reuse the proof instead of repeating OCR for scenery changes.
An ordinary unbound popup must also stay near the submitted pointer's source;
far-away clicked/pinned descriptions retain their separately verified path.

Shop viewport epochs authorize shop rows, independently of current inventory
proofs. Capture discards stale shop/hover fields, preserves newer shop caches and
queues a bounded rescan, then validates an independent tooltip normally. An old
shop-only miss cannot clear a newer inventory card, and removing a stale shop
hover cannot turn its description into an inventory reference. Shop-row retries
do not prevent independent inventory processing. A lost container clears cached
shop routing before reacquisition so its old rectangle cannot block inventory.

`reader/src/shop_panes.rs` keeps the separate sold-items ledger out of listing
selection. Rejection requires its native three-line purchase/summary grid and
following cell geometry, rather than a heading or item-name blacklist. Purchases
remain recognizable when the totals are outside the viewport. It masks only
the proven ledger in a copied shop-selection frame, with at most two retries;
the original pixels remain available to inventory and generic descriptions.

An empty detected blue table is not sufficient to suppress generic inventory tooltips: NPC buy/sell lists share that palette. Such rectangles remain available for fingerprints but do not establish pointer-in-player-shop context without rows. The next hover read uses the full frame, allowing an NPC sell-list item and its comparison panel through the ordinary item-name/catalog rules. Closing the reader marks it paused before draining its process, so a queued scan cannot access deleted Qt children.

## One full-market cache

`PriceService` loads the Classic World regular/cash catalog and manages a single `SnapshotStore`/`SnapshotUpdater`. There is no individual-price provider, per-item HTTP queue or provider-ID index.

Item identification precedes market lookup. `item_identity.py` keeps an exact ID
local to the currently observed row or inventory source; market presence cannot
choose between distinct same-name items or create a global name preference.
Catalog entries retain equipment subcategories and gender. A bounded comparison
of cached exact-ID candidate images may resolve a shop icon only when every
competitor is available and clearly excluded. Shared, covered, missing or weak
artwork remains ambiguous. At most eight candidates and eight million sampled
pixel comparisons are considered; the GUI keeps a bounded image-signature cache.
Thumbnail demand uses the existing image queue and never adds a price request.

Bounded row-pixel proofs validate the submitted name, asking price and icon
against the newest captured frame. Cursor and recognized overlay/description
pixels cannot establish native changes. Lost containers or contradictory source
pixels retire live offers and request a new reading; they do not by themselves
establish scrolling. Recovery of a covered asking price also requires the full
source proof, so an unchanged name band cannot restore a different same-name
item's offer. Recovery caches remain separate from current offers.

Hypothetical native scroll colors narrow actual scroll candidates only. Narrow
quote typography/spacing normalization retains item words and variant roles.
Exact-ID gender suffixes may corroborate known equipment metadata; a combined
variant label such as “Blue or Red” does not establish either individual variant.
`SnapshotStore.lookup` distinguishes priced, no-sales, missing, variant-mismatch
and unit-mismatch states. The shared cards and overlays preserve those reasons
instead of representing every rejection as absent sales or indefinite work.
`market_lookup.py` shares the quote/reason result across the service and views.
An explicit unique search result, including a numeric item ID, is selected from
the catalog independently of snapshot coverage or age. Shared names remain
local ambiguity; the former provider-selection signals, cache and resolver are
removed. The catalog ID index serves direct selection and contextual ID checks.

On every launch, saved data loads immediately and one asynchronous full-market download starts. Later downloads use the earlier of the selected 5/15/30/60-minute interval and the source publication's one-hour expiry. Changing the interval uses that same deadline. Overlapping refreshes coalesce. Overlay, search and watched-item prices are local snapshot reads; typing, selecting, hovering and watching never initiate individual price requests.

A short-lived native `lupin-market-fetch` helper reads the ordinary public market page using system web views: WebKitGTK on Linux and the shared production WebView2 runtime on Windows. It uses an offscreen/invisible window owned by the helper, never a game window. Linux uses an ephemeral context; Windows uses an app-owned data directory and disables OS-account single sign-on. Website permission requests and new windows are denied. No personal browser, installed browser discovery, DevTools socket or resident service is involved. Well-formed source rows with different listing/catalog IDs are excluded as unverified aliases; they never map prices to either ID. Malformed identities, duplicates, wrong worlds and empty exact generations still reject the update.

`SnapshotFetcher` bounds UTF-8 stdout to 8 MiB, retains only bounded diagnostic stderr, accepts one JSON object after a successful helper exit and enforces a deadline. Stop/cancellation discards pending results; refreshes coalesce while a previous helper shuts down. Only the subprocess created by Lupin is terminated. The Windows helper's private job controls its own descendants so cancellation cannot leave its renderer running. Full generation validation still occurs in `SnapshotStore` before replacement.

A complete generation is validated before an atomic SQLite replacement. Checks require Classic World, live list schema, exact IDs/names, clean equipment and item/set units. Failed/invalid refreshes retain the last-good data and its original ages. A transient startup failure gets one retry after 15 seconds, then uses bounded 5/15/60-minute backoff. Missing runtimes and invalid documents do not trigger the startup retry. Successful refreshes never inherit a failure cooldown. `market-last-error.json` retains only the failure kind, exit code, time and up to twelve fixed helper stage/error-code pairs, never page bodies or user text. Connection details shows the current process's retained failure.

Check time, publication time and latest observed-sale time are distinct. Validity ends at the earlier of check time plus the selected interval and publication time plus one hour. An expired publication returned successfully uses a separate bounded 60/300/900-second retry sequence, capped at the selected interval; it cannot trigger a fetch loop or acquire a false publication age. Old/missing observations, thin samples and uncertain units cannot earn deal colors. Rechecking an unchanged publication cannot make its publication or observed sales newer. Missing items stay unpriced. Fresh-generation signals update existing rows even when their numeric price is unchanged, without new OCR, pointer movement or structural animation.

When a successful check still returns an expired publication, Prices keeps a
visible source-age warning with the last successful check and next retry.
The countdown reads the existing retry deadline and makes no requests itself.
A new valid publication clears the warning through normal market signals.

Overlay annotations show the source's latest observed-sale age rather than repeating the snapshot check age. Stale/refresh warnings remain explicit. The larger item panel shows the source's latest observed-sale time. The full list does not supply a verified individual transaction amount; the market median is never presented as the latest sale price.

## Prices and watched items

`PriceObservations` in `price_observations.py` owns accepted shop rows, bounded
recovery caches, identity proofs and shop-description transitions. It has no
widgets, market requests or capture scheduling. `LensWindow` renders its state
and asks the reader for work through the rescan API. Tooltip associations are
constructed once by capture and revalidated in the UI; direct/legacy result
paths retain their bounded decoder. One row source proof supports exact and
verified-selection checks, while the separate icon-result cache retains its
own image signature.

`ShopBrowsing` detects verified native viewport changes using exposed scrollbar
thumb movement, two changed exposed native name bands before OCR, or changed
exact row identities and name ink. Name-band checks normalize ink against the
measured blue/orange background and reject description-tinted/covered pixels.
The frame check is vectorized and retains at most 24 row proofs. Its epoch rejects
late results; its pending state blocks old-page labels until fresh rows arrive.
There is no hover-priority expiry timer. Cursor footprints join tooltip and
annotation exclusions in both frame and row comparisons; a partly hidden thumb
cannot establish a shortened baseline. A single changed source does not prove a scroll.
The native thumb's balanced blue palette is required; a purple description tint
cannot turn two pixels of apparent edge movement into a viewport change.
Name-only frame invalidation requires no unchanged same-slot name anchors and
no unchanged, exposed native scrollbar. Confirmed thumb movement still wins.
Each cached template records whether genuine native name ink was initially
visible; uniform background cannot prove an unchanged item/page. A later masked
read of the same item cannot erase its earlier usable title template.
Advancing the viewport clears every old row, asking price and row-pixel cache,
while retaining the independent fixed-rim container proof. A partly hidden new
page can therefore keep its full scan geometry without inheriting an old item.

Row rejection and loss of the independently verified table are distinct outcomes.
Rejecting an exposed changed item clears that listing and its recovery proof;
the table remains a shop for scan geometry and hover routing. When unchanged
native names at their saved positions support the same loaded page, a blocked
row retains only its last-seen reference/asking-price presentation. Its current
offer is revoked (`price=None`, `reference_only=True`); the original source proof
is not replaced by tooltip pixels. This also covers incomplete description
geometry. Repeated held frames do not repeatedly request OCR or restart widgets.
A changed exposed title or positive viewport invalidation cannot inherit this
presentation. A late OCR
reply validates the accepted rows against the newest frame and returns for a
retry, without clearing surviving rows a second time. Only actual container-proof
loss retires shop context. The same table context is used for both scan hints
and description routing, including pending/unread pages.
Both the observation controller and browsing templates canonicalize OCR-rounded
rectangles before caching. The browsing cache keeps one template per physical
list slot, even after the UI's previous row has been rejected. This prevents
shifted copies of the same name from counting as two changed native rows.

Shop labels stay fully opaque and remain attached to their rows. Native shop
descriptions provide geometry and conservative exact identity evidence only;
they never create an annotation or take over the Prices list. Inventory-primary
source proofs preserve separate inventory/equipped cards while a shop is open.
Removed shop annotations are disposed immediately, without a retirement fade
that could show the prior item's deal colour over a newly scrolled row. Retained
labels preserve their opacity/animation objects. Inventory/translation cards
retain their normal fades.
A clipped visible listing can use its verified full description title when the
same row's catalog candidates agree. No hidden unknown row gains a guessed ID.

`annotation_geometry.py` calculates description and protected-region placement
and drawing bounds. The independent annotation process retains replacement,
opacity, animation and painting. Current tracking annotations use the shared
`tracking` kind; retired `experience` drawing branches are removed.

Selected shop bands can have a different brightness from normal rows. Inside an independently detected shop, the reader measures the blue and orange palettes, validates a single broad selected band, and adjusts only its background pixels in a copy. It reuses the primary strict OCR engine and merges only complete, noncontradicting reads from that band. An eight-entry cache includes current list pixels and coordinates, so price changes and occluders cannot inherit prior amounts. The original frame still drives tooltips and occlusion.

The locator can retain a proven footer span while an item description covers its white rim, provided the independent LV template and OS caption still verify the same coordinates. Cold acquisition additionally permits one independently framed, dark native description with a cyan title marker across the rim, requiring repeated real rim endpoints and a separately verified caption. Arbitrary fragmented rims remain invalid. Losing those anchors still removes the game area. Title retries keep the public description bounds but omit the verified leading marker from the glyph crop; decorative pixels must not become OCR punctuation. Exact catalog rules remain unchanged and no nearest-name fallback is used. Shop selection/unreadable names retain references under verified page guards, without an assumed current listing amount. A listing returns without another OCR pass only when the entire previously read row pixels and page guards match exactly. Description rectangles exclude covered pixels from recognition; late OCR replies cannot restore a description absent from the latest frame. Ordinary item descriptions never dim shop labels. Labels use page/item/list-local slot identities, independent of raw OCR row order or absolute shop position. A verified covered row may preserve its last-confirmed display amount for the lifetime of the verified page, separately from the current-offer field. That presentation is bound to the same verified page/slot/item; current fresh exact-ID quotes may update the comparison in place. Guard exceptions cover only the actual native tooltip pixels and require remaining visible proof. Shop description geometry never changes label opacity.

Paired frame strokes alone do not establish a description: bright shop panes have similar borders. Description geometry also requires a dark native interior, excluding Lupin's own annotation rectangles from both body evidence and name anchors. The same proof validates retained rectangles against current frames. A bounded cyan-marker and paired-frame probe can find a native panel before OCR when the current shop source becomes disrupted. This supplies only an exclusion rectangle. Our own dark labels cannot manufacture evidence for a native pane.

The shop's fixed top and left rims establish its container; its changing scroll
thumb belongs to the separate viewport proof. Ordinary pointer positions can
arrive independently of captured cursor pixels, so at most eight previous
positions remain masked for 750 ms. Native-pane movement has a separate
three-rectangle, 350 ms trail. Duplicate exclusions are merged before the bounded
row proofs. A tooltip mask includes its scaled frame/shadow margin.
When annotations hide the far edge, the native left edge and visible top or
bottom cap can prove just the exposed portion of an occlusion. Search work stops
at that mask instead of borrowing a border from another pane. Cyan scenery cannot
exhaust the bounded header probe: candidates are distributed over spatial cells
and screened for adjacent native frame strokes before detailed validation.
Body validation measures exposed dark pixels densely, avoiding sampling-grid
flicker; the first native bottom cap plus an ending left edge prevents a partial
pane from following a shop border below it. Pointer coordinates never erase a
potential native title marker; source comparisons still mask cursor footprints.
None of these geometry proofs supplies an item
identity or an asking price.

Partial OCR crops cannot replace a still-verified full shop rectangle. Row slots
are normalized before merging missing observations, and exact unchanged pixels
can restore an omitted row. Fully occluded previously verified rows retain only
their presentation, while a complete strict native row is not discarded merely
because a pane touches its edge. Covered unknown placeholders never capture a
description as their item source. A rejected OCR submission cannot retire accepted
rows that independently pass validation against the latest frame; a proven
viewport change still invalidates them immediately. Current offers and held asking-price presentation
remain separate. A shop-origin description cannot become an independent item
card just because the pointer leaves the list; accepted generic titles must
still match the newest captured name pixels. The Sold Items filter checks all
bounded visible rows and does not require the totals header to be visible.
If visible row pixels change before a usable OCR/scrollbar result, their cached
IDs and amounts are removed before container-only recovery. A verified empty
recovery cache retains scan geometry, never resurrects retired items and does not
cycle the shop back through source rejection on every frame.
When the container remains verified, a changed row is retired independently of
other unchanged listings. Only a lost container or changes to all current row
sources retire the entire current observation.

The accepted open shop supplies a full-table geometry hint to the reader's crop
and scrollbar observer, separately from native row/offer authority. A shortened
OCR result cannot shrink later scans permanently to its one exposed row. A queued
rescan actually bypasses ROI cropping; scroll transitions and description closure
therefore reacquire the full frame while preserving the active request deadline.

Clicked item-link descriptions may be located beyond the pointer's usual search area. The Rust reader reuses its existing name/bullet recognizer over bounded analysis regions without changing the real cursor or sending input. The GUI requires a catalog match and a visible anchored native description panel before accepting those results. A structurally verified pair of native frame edges permits a local header-only contrast adjustment when chat shows through the translucent fill or upgraded equipment has colored title ink. The cyan marker and its antialiased fringe stay intact, bright foreign occluders are preserved, and the original frame still drives all shop readings and geometry. The same paired-edge proof keeps adjacent comparison panels separate even when their purple hue is lost. A unique equipment name may drop its visible upgrade count for the existing unscrolled reference; exact catalog names retain priority. Cash descriptions with no cyan marker use a separate bounded header reader. It requires paired vertical frame edges and the horizontal top rim, then reads only centered title lines. Complete descenders are retained; up to eight exact header masks cache successful/failed reads. It never searches arbitrary scene text or substitutes a guessed catalog name. Such cards remain beside the description. Small-font I/l and g/q variants and ellipsis punctuation are accepted only for unique catalog candidates; shorter shared Ink-and-Wash prefixes remain ambiguous.

Search controls sit above one shared content area. Selected-item and on-screen/ready views use the same origin. A missing on-screen item gets a 2 second GUI grace period before its card retires to history; this does not extend an overlay's lifetime or verify an old offer. A replacement item can take over the active area without a ready/history detour. Active-card changes and recent-row movement have independent transitions, so history is not faded through a blank frame with the active card. Empty status rows are hidden. New market generations synchronize retained price cards even while capture is paused. Search is part of Prices and takes space priority while active. Clearing it animates shop cards back into view. Shop cards retain their widget instances and layout positions during quote/age updates. Adding a hovered item does not change shop-card identities. Search, shop and inventory cards share an exact-ID watch star and thumbnails. The removed Details expander has no runtime path.

Watched items start collapsed. Expanding shows a compact list with thumbnails and cached references, capped at three visible rows. Its contents stay at a stable full height while a clipping viewport slides, avoiding repeated list reflow. Header/empty-space clicks toggle the panel; items, stars and the scrollbar retain their actions. Rounded selection covers the full row.

Only an item click opens its larger card and takes space priority. Expanding alone retains the normal item/ready view. Deselecting clears that card while retaining the watched view. Collapsing clears the selection and returns to shop cards. Watching/unwatching changes saved exact IDs, not market demand. In-game watched labels shimmer twice inside a steady border and retain a star. Reduced motion uses a steady marker.

Thumbnail downloads share a two-request queue, bounded memory/disk caches and negative caching. Cached images are used immediately without waiting for a network signal. No fetched thumbnails ship.

## Tracking and translation

Tracking starts stopped. Explicit Start enables EXP sampling once a second and a bounded bottom-right pickup-log crop at up to five samples a second. Pickup OCR uses a separate invocation of the same native binary, restricted to one thread and one in-flight crop; it shares the approved capture and cannot queue a backlog behind shop OCR. Stop releases that worker even when display reading is paused. Timed-out, superseded, covered and wrong-generation replies are discarded.

The pickup reader supplies per-line geometry, kind and normalized visual evidence. Actual EXP, party-bonus and item-receipt messages anchor scrolling without adding currency. White glyphs fading over colored scenery use local blue-channel contrast; yellow EXP text is handled separately. Up to 256 normalized patterns are cached. Unreadable or partially recognized text is distinct from a proven empty log, and exhausting the OCR budget retains recognized rows.

A bounded arrival ledger follows individual lines through upward scrolling, preserves short-lived pending arrivals, distinguishes repeated equal amounts and never confirms a new currency amount from unknown visual evidence alone. A changed, independently recognized bottom slot can prove a replacement burst; this proof cannot promote recovered historical lines above shared anchors. Existing lines are seeded on Start/Resume, after actual coverage loss and after known obstruction. There are at most 96 active records and 301 recent-rate buckets. Frames and chat are not persisted in normal operation. Totals describe confirmed visible pickups, not profit or wallet changes; genuinely unseen or unresolved arrivals can still be missed. Legacy saved runs retain their wallet basis; new history/CSV records use pickups and record coverage gaps.

One recognition gate applies to automatic and manual capture regions, job submission and result acceptance. Losing verified game bounds creates an automatic hold separate from manual Pause. The active clock is capped at the last verified frame, so a stopped stream does not accrue time while a timeout is detected. Capture-generation and tracking-epoch checks discard late work. Fresh same-frame name proofs also bind pickup-only jobs to an established character without additional OCR. Two fresh matching readings confirm the original character before an automatic return; another client cannot reset the held run. Hidden activity is excluded by rebaselining EXP and seeding the returned pickup log. Numerical EXP failures alone do not remove valid game recognition, and map-history changes preserve totals and pace.

EXP pace needs 30 seconds of accepted readings; pickup rates need 10 seconds. Covered/rejected intervals can extend the warmup beyond wall-clock time. A bounded four-reading numerical recovery buffer prevents a bad initial total from rejecting correct readings indefinitely. Replacement requires at least three distinct increasing EXP values, two percentages, compatible inferred totals and two seconds of fresh captures for the same identity/level. Unchanged or repeated-time observations cannot vote a different total into place. Reanchoring retains the session and confirmed gains but excludes the untrusted interval. Pause, capture loss, invalid figures and identity/level changes clear the evidence. The UI distinguishes unreadable pixels, unreadable identity, inconsistent values and an unconfirmed level/change.

Captured name proofs keep OCR spelling changes from creating character switches. The Python reader derives the name region from the native reader's EXP-figure geometry in the same submitted frame, normalizes contrast, and supplies a bounded word mask plus glyph masks. Matching pixels retain a stable identity key even when OCR alternates Z/2 or misses the name. New raster-scale templates additionally require the same recognized name and corroborating glyph shapes; variants are bounded. Missing evidence holds a known identity, while genuinely changed name pixels require fresh confirmation before the existing switch logic accepts them. No game-window handle or process identity is used, and no name images are persisted during normal operation.

The display spelling can refine within that stable identity from fresh, numerically accepted observations. At least six corroborating votes, 80 percent of the last eight and four consecutive recent votes over two seconds are required. Cached, stale, duplicate, paused and rejected readings cannot vote. The correction updates the baseline, current run and same-key saved JSON records without restarting accounting or changing the two-second numerical snapshot. Legacy records without a matching visual key remain unchanged; opaque keys are excluded from CSV. Consistently incorrect OCR cannot correct itself without new evidence.

Percent is the default EXP unit; raw/both remain available. EXP and meso cards narrow from 316 down to 200 logical pixels to fit the independently verified empty corner left of the HUD; only narrower gaps use the above-HUD fallback. Each card is 56 pixels tall, totaling 114 with the gap. Placement scales capture guards into logical coordinates on both axes and never paints over or exempts them from validation. Bold headings sit above two small rate lines and a larger rolling gain; the percent unit scales with that gain. Timers retain their own header space and the footer retains Level X · ETA. Both mode includes raw gain alongside that footer. Totals align beside a fixed shared unit column, with exceptional long values scaled instead of displacing other text. The meso coin aligns with the percent symbol, and the footer shows the last confirmed pickup. Normal EXP and MESO headers omit the rolling-window basis while warmup, Paused and Log hidden states remain available. Both bold headings start after the plus-sign gutter used by the rates beneath them. The tracking page explains both windows once with “Rates based on the last 5 minutes” below the control row. Positive meso figures include a plus sign; GUI figures use the same green. Coverage-gap counts stay in the GUI. Shop price-change chips share the name row, with more vertical space before the market/last-sale line.

One numeric snapshot supplies panel and overlay gains/rates/ETA every two seconds, with immediate state changes. Elapsed clocks read the same active watch clock every second independently of that snapshot. Both pace windows cover up to five active minutes. EXP's event clock survives map-history segments and pauses; its denominator contains accepted observation intervals. Meso uses at most one aggregate bucket per second, trims buckets outside the recent 300-second interval and projects per-minute/per-hour rates from that window. Session gain, the last pickup and history checkpoints remain independent of the rolling buckets. Its ten-second rate minimum is separate from EXP's thirty-second warmup.

Pause copies the displayed rates/ETA and preserves both windows. Resume rebaselines EXP and reseeds visible pickups; retained pace is shown while readings resume. Meso can resume independently of EXP when the captured identity remains confirmed. A map change saves the old history segment and starts the next without clearing pace or cumulative watch totals. Stop and save ends the run; a new explicit Start resets both rate histories, totals and clock. The level badge disables native automatic indentation so its background fits the custom text renderer. Separate visibility settings synchronize between the tracking page and Settings. Reading Pause holds the watch clock; the Prices shortcut remains independent. History/CSV stay local.

User Pause freezes the current reading, run, map, rate snapshot, watch totals and pickup tracker. Incoming frames can confirm visible identity but cannot finish/switch the run, reset pickups or change its label. Loss of the game area invalidates a paused identity binding. Two fresh matching character readings restore it; another character hides the tracking cards and disables Resume while prices remain independent. Resuming rebaselines EXP and seeds old pickup messages, excluding gains made while paused. No OS game-window identity or process access is used.

The detected-map header omits a redundant street prefix and shortens overflowing names at the right edge, with the full value in its hover text. Session data and the Map Label field retain the full detected name; manual labels are not rewritten.

The Korean reader scans the detected full game area for a short configurable window, independent of cursor proximity. New scans supersede old work. Matching source pixels retain cards through modest movement; linger and no-result timers are bounded. The Korean original is retained and unstated price/percentage units are not invented.

Bubble and generic text candidates alternate within the bounded worker budget.
Colored generic ink is normalized before recognition; verified source roles use
geometry, explicit speaker/system prefixes or a current captured shop rectangle.
A bounded event ledger merges an exact same-speaker bubble/chat arrival within
its short evidence window, prefers a visible bubble anchor and reserves both
source locations. Verified same-bubble fragments update one event/history row
atomically, preserving numeric, question, negation and job distinctions. Different
speakers, separately established repeats and anonymous prose are not globally
merged. Scanning and finishing use one phase state in both the GUI and overlay.

`chat_scan.py` owns bounded in-memory scan state. Up to twelve recent text bodies
and their speaker headers can provide a verified first result before full-window
detection. At most two priority results leave room for new text; the ordinary
bubble/colored-text queues continue. A 128-entry exact-pixel cache includes English
and empty reads. Frame geometry changes clear source bindings. Connected-component
run edges are extracted once per mask instead of allocating a new padded row for
every scan line.

OCR retains at most four single-syllable alternatives from uncertain model
emissions. An alternative may complete an anchored, known party-request phrase
only when it preserves all numbers and non-Korean characters. Names are never
corrected this way; ambiguous phrases remain unresolved. A visible warning marks
an accepted alternative and the first OCR reading stays in memory. The neural
model and its weights are unchanged.

`chat_tracking.py` matches meaningful text independently of trailing emphasis and
bubble padding. The header is checked separately. Static matches are cheap;
failed matches use a capped local search within 112 pixels, then native-size
confirmation. Uniform or ambiguous templates reject. No game objects are tracked.
The arrival ledger remains distinct from the GUI: repeated scans of a continuous
source update one event, while separately proved arrivals remain distinct. The
recent-results UI groups consecutive equal same-speaker translations with a
repeat count and reuses its existing widgets instead of rebuilding all cards.

Complete glossary/party templates remain fast. Partial glossary output no longer
prevents mixed sentences reaching the local model; known terms and explicit
numeric roles must survive, otherwise the original/partial result is retained.
The bundled model still has grammar limits; deterministic templates are not
reported as neural inference. `translation_layout.py` sizes cards to their text
at the existing readable font sizes, prefers a five-pixel source gap, avoids
source/annotation/card collisions where space permits and holds a stable side
through modest movement. Geometry caching bounds idle placement work. Lost
source proof freezes the last verified position during the configured linger.

The writer protects exact catalog names and explicit handles before conservative
trade/party shorthand expansion, uses verified Korean game/town terms and checks
numeric roles, questions and negation before explicit Translate & Copy. Enter
freezes the popup's current geometry and enabled palette before a 180 ms fade/slide;
late previews cannot reflow the departing surface. That dismissal preserves only
the explicit copy authorization. Escape/edit revokes it. Translating/copied notices
wait for the surface to leave, occupy its bottom-right corner, crossfade over
200 ms and expire independently of OCR updates. Both verified int8 model bundles
remain included. See [Korean notes](docs/KOREAN_CHAT.md).

`composer_overlay.py` presents the hotkey writer in a separate managed, focusable
surface inside the existing annotation helper. The main `KoreanComposer` remains
the only draft/translation/clipboard authority; the helper is a presentation
mirror with bounded UTF-8 messages, opening sessions and monotonic edit sequences.
Old acknowledgments cannot overwrite newer typing, and geometry/close commands
remain independent of draft freshness. New openings retire old-surface events;
helper failure clears its reserved area and cancels an unsubmitted draft's copy.

The native reader exposes the measured HUD footer span. Shared layout puts the
writer beside that strip at bottom right, narrows to fit, then moves above it
when needed. Its preview grows upward with a short slide/fade; long previews and
warnings scroll within the bounded body while input/actions remain accessible.
Notifications stack above the reserved writer rectangle, incoming cards avoid it,
and all OCR paths exclude it (including crop/ROI coordinate conversion for price
reading). The annotation canvas always remains click-through. Desktop activation
is requested only for the writer, checked on that own surface, and a visible
click-to-type/native-dialog fallback handles denial. Without fresh capture bounds
or a running helper, the existing standalone writer remains available. Live
Wayland/XWayland and native Windows focus acceptance require platform testing.

## Presentation, persistence and packaging

Inter is bundled for consistent interface/price typography. The GUI uses a small coin for currency words, except MESO on the tracking panel and EXP/Meso Tracking on its tab. Market-price overlays remain plain; the tracking gain uses the same coin asset. Tracking unit coins appear only alongside available numbers. The larger, left-aligned rolling tracking timer shares a borderless row with the tracking controls above both metric panels. The timer adds hours while retaining seconds; its reserved width prevents the adjacent buttons from shifting. Digit-place animation keeps surrounding text/columns steady. Page slides and section transitions are interruptible and respect Reduce motion.

A shared, brighter semibold footer keeps the applicable shortcut in the same
position across all four pages. It follows customized assignments and the active
Read/Write translation mode; Database shows its local Ctrl+F search shortcut.

Maximization and control-panel pinning are disabled. Fresh default geometry is 27.0833% × 77.7778% of logical screen dimensions (520 × 840 at 1920 × 1080), clamped to available space with a 460-pixel minimum width. Resizes persist as screen-relative fractions; OS DPI is applied once. Valid older custom sizes migrate without losing the preference; desktop-sized/maximized geometry cannot replace a compact preference. Long item/history lists can scroll independently. Tabs use plain labels, warm selected text and a filled active background.

Programs install to `/opt/lupin` or `%LOCALAPPDATA%\\Programs\\Lupin`; launchers/readers use Lupin names. Windows upgrades move the old program directory, preserve additional files, remove obsolete shipped modules and support rollback before commit. Shutdown sends Quit through Lupin's own local pipe and waits for that specific server process to finish unloading; synchronization-only access comes from the pipe's server PID, with no process enumeration or termination. Stable settings/socket/portal IDs preserve data and approved sharing. The WebView2 SDK, loader and official setup bootstrapper have pinned download hashes. Windows setup checks/prepares the shared runtime before closing an existing installation; Linux package dependencies provide WebKitGTK. The browser engine is not bundled. Both runtime/model manifests are pinned; install roots stay read-only in normal use. Private evidence, credentials, screenshots and caches are excluded. See [packaging](packaging/README.md) and [verification](VERIFICATION.md).

The Windows Korean writer registers the existing PySide6 DLL directory before loading CTranslate2, retaining its directory handle for the worker lifetime. This reuses the bundled Microsoft C++ runtime without importing Qt or requiring a system Visual C++ installation. Cold writer startup has a 60-second deadline; individual inference requests retain their 12-second deadline.

## Local reference database

Database is the fourth tab, with Items / Monsters / Skills / Maps / Quests and local prefix search. Items start with category tiles, then subcategories and weapon types. Skills start with illustrated job families and job lists. Search stays available at each depth; Back restores category, query, scroll position and the selected entry's subpage/rank. Main and subnavigation tabs are centered and use the shared selected/hover colors. `reference_widgets.py` provides fixed-geometry list/tile rows, nearby-image demand and interruptible forward/back slides. Search uses the same content fade as Prices.

`reference_data.py` stores verified source blobs, entities and FTS5 in per-user SQLite WAL storage. `reference_service.py` checks the OSMS Classic World version/hash manifest on launch and daily. Changed items/cash/monsters/skills/maps files replace one complete generation atomically. Wrong-world, hash, count, shape, duplicate and identity failures keep last-good records. Raw client presence does not make a record browsable.

`reference_availability.py` imports positive evidence from NiaMeowDB's sourced release indexes and its never-sold cosmetic exclusion, with exact canonical ID/name matching, future-date/closed-test rejection and explicit GM/test/unreleased exclusions. Monster identity also matches level/HP; duplicate encounter variants do not inherit the ordinary monster's status. Validated MesoWatch snapshots can confirm circulation only with exact names/IDs/world, a positive observed-sale sample and a sale since Founder's Access. Catalog membership, client on-sale flags and undated prices are not evidence. Positive records remain after a sale/event ends; ID/name changes invalidate their join. Release indexes refresh daily with bounded pagination and normal error backoff; saved proofs work offline. Known scheduled content requires a verified release update rather than automatically unlocking on a calendar date. This is a conservative sourced view, not an authoritative complete release registry.

`reference_recipes.py` verifies the optional recipe payload against that same manifest and derives only exact, reachable scroll/catalyst outcomes, using the documented crafting cap and already-released ingredients/base/catalyst. User-confirmed sightings have separate provenance. Fresh native item observations can add `screen` evidence only after exact raw identity and current game/panel pixel checks; aliases, presentation retention and manual searches do not qualify. The raw OCR catalog remains separate from the released search catalog. Already-known observations avoid writes and new identities coalesce catalog refreshes. Neither source creates a market price.

Wiki Cargo observations refresh daily. Their own monster/drop/item joins must match canonical IDs and names; sampled percentages/counts/version/date/interval remain attached. `reference_community.py` supplements a selected ordinary item/monster, cached for 24 hours with a 30-minute error cache. Cash entries have neither generic drop controls nor generic drop requests. Votes never become rates. Related item/monster rows must also have release evidence. Two single-thread reference workers use cancellable requests and GUI-thread result delivery; idle browsing does not poll.

`reference_details.py` owns one complete entry widget. Navigating away disposes that widget and all nested controls, fixing the orphaned skill slider. Background drop results update retained list rows without reconstructing the header, rank control, sprite or subpage. Identical core data does not rebuild the view. Actual changed core records preserve rank/subpage/scroll state. Initial stats start populated; subsequent numeric changes roll. Monster Overview / Locations / Drops have separate scroll areas; ordinary item Sources are separate from Overview. Cash cards omit irrelevant drop/NPC-price scaffolding and repeated name-only descriptions.

`reference_skills.py` preserves raw records while presenting the documented Arrow Bomb explosion and reconciling identified stale rank descriptions with cross-checked numeric data. Exact ID/name/rank/value guards prevent interpolated progressions. [Database sources](docs/DATABASE_SOURCES.md) records the evidence and limitations.

`reference_media.py` retains original decoded pixels in an eight-MiB/128-image LRU. `reference_widgets.py` renders directly at the requested size/device scale: integer enlargement for pixel art, quality downsampling when needed. At most four image requests run; visible rows precede nearby prefetch and obsolete requests yield without creating false negative-cache entries. Up to twelve static landing-page icons can warm while the main window is visible. Disk caching remains 64 MiB/1,024 files, with 30-day freshness and six-hour misses. PNG/WebP byte/dimension/frame limits bound decoding; disk cleanup avoids rescanning on every thumbnail. One selected monster movie uses source timing without a frame cache and pauses when hidden/minimized or under Reduce motion. Downloads remain outside installers/source.

`ReferenceStore.catalog` builds the same released-item identity collection for both manual searches, preserving exact matching domain objects where available. The raw OCR catalog remains separate for recognition. `EntryDetails` embeds the Prices-style `PriceCard` summary beside a sliding stats/Sources panel on both pages; compact on-screen listings remain simple price cards. The narrower price column gives the detail panel more room at 460-pixel window widths. Its height follows the stable card canvas, independently of quote updates. Prices owns selection demand, while Database coordinates the shared reference-image/report services for whichever page is visible. Quote updates retain the header, watch control and stat widgets; core-data changes preserve the selected subpage. Selected cards omit redundant check ages, per-item captions and generic explanations, retaining sale recency and source links.

Database keeps bounded browsing state independently for Items, Monsters, Skills,
Maps and Quests: query, category, sort, selection, subpage/rank, scroll and a
32-entry Back stack. No hidden entry widget or animation is retained for this
memory. `reference_navigation.py` provides a labelled Back action, an immediate
root breadcrumb and a compact ancestor menu whose full path remains accessible
when elided. Scoped search names its current category; Search all keeps the
query and is reversible with Back. Count and sorting share the navigation row.
Quest categories group towns, job advancement and systems/events without
removing Citizenship or crafting quests. Category images use a released entry
with actual artwork when one exists; a reference-book placeholder handles
missing images. Release predicates and canonical links still apply to every
group and result.

Reference headers, category tiles and linked source/drop/reward rows share
spacing and hover states. Combat rows use a flat grid; main monster/skill values
have stronger hierarchy. Quest objectives and rewards retain explicit right-side
quantities alongside their original source metadata. Minimap previews crop only
transparent margins for display. Verified spawn coordinates still refer to the
full source image and are remapped into that displayed crop; cropping never
establishes a projection proof or enables unverified markers.

Database update checks live in Settings and use the manifest/hash comparison, without a forced full refresh. Equipment sorts by class/name/required level; other categories expose relevant type/value/rate orders, monsters level/name, and skills job order without crafting. Monster drops use fixed two-column tiles and preserve subpage/list position across item navigation. `SearchField` supplies the same field geometry and contrasting 28-pixel clear control on both pages.

Market cards read the existing shared snapshot and watch controls, with updates through normal signals. Database browsing never starts individual price requests. Reference, release, drop and market refresh ages stay separate. Raw map placement counts mean spawn points, not server respawn timing; community samples are not official server probabilities.

Korean scans now prioritize exact new/changed candidate pixels, then the least
recently examined candidates, in a 192-entry visit ledger. This replaces the
positional cursor/generation reset in the worker; cancellation still uses the
monotonic request identity and latest-frame slot. The existing exact-pixel OCR
cache and verified-source templates remain separate and bounded. Cadence is
measured from request start, with a 50 ms floor after slow passes and 250 ms for
idle/fast passes. Translation history groups consecutive equal arrivals before
presenting newest-first cards and retaining an older visible scroll anchor.
Complete recruitment templates preserve explicit boss/action/once/occupancy and
bonus/rush/any-party intent; unknown prose retains protected-noun and numeric
validation before partial fallback. No model files, game access or input paths
change.


## Session history and expanded references

`recent_items.py` keeps at most 100 exact-item sightings in memory, replacing
repeated reads and never retaining frames. Live observations and history share
one identity; history uses native painted rows rather than per-row widget trees.
Once shown, an entry stays in history through re-sightings and brief OCR misses.
New rows slide in while older visible rows move down; height changes and rapid
updates are interruptible, respect Reduce motion and preserve the scroll anchor.
Unchanged visible rows reuse their painted content while the active cards or
history geometry move. Each exact item has an independent visual cache, bounded
to viewport neighbors; quote, thumbnail, hover and style changes invalidate only
the affected row. Interrupted insertions retain their current position and opacity.
Price animations advance only changed identities and finish their old glyph
layers; another row's update cannot rewind a settled price. Only visible history
thumbnails enter image demand. Market references are
local snapshot reads, with large rolling prices and muted expired values. History
is cleared on application exit and has no persistent file.

NPC and quest bulk files join the existing validated reference generation. A
cached old manifest that lacks these files triggers only the missing downloads.
`reference_indexes.py` validates map/quest release indexes; developer and known
future content remain unavailable. `reference_relations.py` builds canonical
quest requirements/reward links and reverse item sources, keeping choice/class
pools distinct. Returning from a source restores the previous tab, entry and
subpage. Quests use NPC portraits; Maps use published symbols and minimaps.

`reference_geometry.py` has one cancellable worker for the selected map, positive
and negative caches, content-addressed native-image checks and multiple portal
anchors. A palette/terrain projection check rejects incompatible minimap crops.
No full render is retained; native decoding, if required by the plugin, is capped
at eight million pixels. Markers appear only for verified projections. An API
spawn count is a count of exported placements, not live population or timing.

Reader title contrast now shares colored-ink handling across marker and centered
headers. Exact upgrade-suffix validation also applies to independent second reads;
colored title pixels participate in their cache fingerprint. Frame structure and
exact catalog identity remain required. No hooks, process access or game input
are introduced.

`reader/src/tooltip_frame.rs` fits complete native description frames from raw
capture pixels, before title contrast preparation. Left/right hypotheses require
repeated side strokes and a horizontal cap terminating at its corners. An interior
inventory rail visible through the translucent body cannot supply that boundary.
Owner text can move the item title below the usual header position; the actual
frame cap remains independent. A separately framed comparison can complete a
partly visible neighbour or split an enclosing common-rim union, without borrowing
its title. `tooltip_association.rs` binds these frames to inventory sources.
The inventory need not touch the capture edge, and the comparison's right edge
need not align with the inventory. Native tabs, controls, the hovered grid cell,
top cap and two adjacent horizontal frames establish the primary-left layout
before OCR. Unsupported or ambiguous layouts are rejected rather
than choosing the closest title. Verified standalone inventory descriptions carry
the same cell/header binding. Single/equipped/linked descriptions outside that
source retain their ordinary path, with explicit `tooltipPanel` geometry when a
complete frame is available. Marker-free primary headers require the existing
independent frame proof; unsupported inventory layouts remain outside the override.

One proven pair also retains its panel-body geometry independently of its title
markers. Repeated loss of a primary marker or the primary frame cannot restore
an unchanged surviving comparison through legacy selection. A bounded comparison
title-ink proof preserves that rejection, independent of the changing translucent
background. Removing the comparison or establishing fresh independent source
evidence releases ordinary selection. Source searches reject out-of-frame
pointers before calculating crop bounds.

Cold-start ambiguity also uses independently adjoining native frames, without
requiring both title markers to survive. Missing source/header/cap evidence
cannot authorize the nearest equipped comparison. With a proven primary role
and complete current title ink, `PrimaryTitles` reads only that bounded header
at two agreeing resamplings, caching at most 16 results. It never borrows a
comparison title, previous item name or hidden text. Unprovable paired roles
remain rejected; ordinary single/equipped/linked descriptions retain their path.

`tooltip_association.py` validates this native metadata in the same pixel space
as the recognized name. Version-three metadata carries separate primary/comparison
rectangles (or a single-panel layout), source kind, hovered cell, cursor footprint,
source-header guards and cap flags. Inventory scale comes from its own controls,
with the HUD estimate used only for a bounded search. Source/header guards stay
exact; frame rails are revalidated structurally using Rust's same scaled
middle/outer-stroke sampling, including odd-width antialiasing at 125%. Animated
scenery cannot invalidate a frame merely by changing its translucent colours.
Versions one/two remain readable for compatibility.
Source-cell validation masks old/new cursor footprints only when sufficient
visible evidence remains; pointer motion alone does not invalidate a proven
item. Changing the visible cell, name, guard, origin or token clears both the
retained card and brief OCR bridge. Python geometry preserves separate native
panels instead of joining their translucent backgrounds. Annotation placement
avoids the complete source and both native panels; when no safe placement fits, it withholds the
card. These are screen-image proofs with no game-window identity or fuzzy names.
Inventory annotation commands name the verified primary `description_box` and
optional `comparison_box` separately from protected inventory geometry. Placement
prefers an eight-pixel gap directly above the primary, shifting horizontally to
avoid the inventory and comparison. Adjacent sides, then below, precede the
general safe-space fallback. Cursor motion projects the description family
without moving inventory protection. Fresh geometry resets its pointer offset;
omitted anchors/comparisons clear reused row state. This prevents a wider card
from jumping above the whole inventory when a safe above-description lane exists.

`shop_dialog.py` recognizes the shop's price-entry form from aligned magenta
labels, native paper and independently exposed controls or frame evidence. Detection searches
only a bounded neighbourhood of a verified shop and excludes our annotations.
An already measured form rechecks those controls directly when the cursor splits
a label. Geometry is memoized per immutable capture and source/mask context;
capture can obtain its exclusion before `image_ready` without consuming the GUI
visibility transition. `ShopPriceEntry` blocks source/offer mutation while the
form is visible and after closure until a fresh verified shop read. The GUI
retains stable labels, observations, history and snapshot prices during that
hold. Only while the verified form is actually visible does it export a scaled,
crop-adjusted rectangle on shop annotations. The canvas measures each actual
label and eases intersecting shop labels to 35% opacity over 110 ms; other shop
labels, inventory cards and ordinary descriptions stay opaque. Closing/moving
the form restores unaffected labels through the same interruptible fade without
recreating them. Reduced motion snaps to the target. Exposed fixed table rims
still have to match while held, so a lost container removes labels immediately.
Older in-flight responses cannot mutate held observations. Form changes never
create a market request or imply a scrolled shop.
When our own labels cover the inputs/buttons, those controls are unknown rather
than missing. This path additionally requires exposed caption ink, connected
left/bottom frame strokes, native paper and the three aligned magenta labels.
Exposed contradictory controls still reject the form; owned paint cannot supply
any cue. A measured form uses the same rule on later frames, avoiding a
recognize/fade/forget loop while those masks remain present.

Shop container guards sample the solid outer frame strokes, excluding the
innermost bevel pixel that blends with sold-out/selected listing backgrounds.
Scrolling invalidates listing authority without invalidating that fixed frame.
The bounded description-cap search shares a single native-pixel grid across
candidate widths, using prefix sums instead of repeated frame scans.
When an initial component read establishes new container guards before it can
accept every row, `ShopRead.retry` queues the immediate follow-up through the
existing immutable-request scheduler. Unchanged shop fingerprints cannot defer
that transition until the periodic locator; a known container does not loop.

Removed Prices cards and outgoing animation snapshots use
`widget_lifetime.retire_widget`. It keeps the widget and
its child wrappers alive through Qt's complete deferred child destruction;
the `destroyed` signal queues release for the following event-loop turn, since
that signal itself precedes child teardown. The queue drains after deletion,
and is not a cache of former cards.

Inventory source-cell comparisons exclude the measured animated hand footprint,
including its top outline seven native pixels above the hotspot. Rust metadata
and Python source/title masks round the same 32-pixel width and extended top
outward, retaining the previous bottom/right boundaries. All remaining cell
pixels and title/header/frame proofs remain current. A narrow exposed strip can
remain authoritative with at least 16 exactly matching native pixels (scaled
with source size), alongside the independent title/header/frame proofs. The
minimum is checked before the exact-byte fast path so a wholly hidden cell
cannot alternate between accepted and unknown as the cursor animates. No grace
delay or guessed item identity is used to hide cursor animation.

## Named item sources

`reference_sources.py` imports one bounded public NPC-shop page daily. An exact canonical icon ID and name must match the local item, and the NPC ID/name must match its local entry. Published shop prices remain NPC purchase costs, never market references or historical shop asking prices. Selected-item reward-box relationships use separately verified public item-index bindings for both the item and box. Successes/empty results cache for a day, failures for 30 minutes, and failed updates preserve last-good rows. These calls retrieve database relationships, not individual market prices. Sources sort named shops and boxes first, use compact image rows, and navigate to proven NPC/item entries. Raw versioned reference payloads remain hash-verified and unchanged; conservative scroll-family corrections apply only to the local presentation records.

## Application updates

`update_service.py` owns one background release/check/download job and the launch/Settings timer. `updates.py` validates exact GitHub assets, pinned OpenSSL Ed25519 signatures, sizes and hashes. `update_delta.py` reconstructs native artifacts with bounded 8 MiB prefix chunks. `update_ui.py` and the tray expose update controls without reflowing Prices. Native installation runs only after a verified download and explicit user action; Linux additionally authenticates through the fixed root-owned helper and re-verifies the payload before the GUI closes. Windows uses its per-user installer; old portable swap code remains compatibility-only. Capture compatibility is an explicit signed field; tracking starts stopped after restart. See [update architecture and release preparation](docs/UPDATES.md).

`desktop_environment.py` owns a shared, narrow relaunch allowlist and same-session recovery of missing desktop authentication/schema fields. Only the unprivileged GUI/relaunch uses these values. `update_startup.py` is a Qt-free, bounded regular-file receipt protocol tied to the launched child's PID, exact release version and per-job token. `update_startup_ui.py` publishes readiness only from the GUI event loop after the versioned annotation handshake. Native helpers wait at most twenty seconds and report success only for a live, acknowledged child; the main GUI polls its matching result briefly without polling the network. `overlay.py` limits automatic recovery to two retries, preserves annotation state, revokes writer state on disconnect, exposes manual recovery and stores only fixed-code diagnostics.

Prices search count/results/spacing occupy one clipped `CardArea`, so clearing the field does not wait for a second debounce or layout-gap removal. Interrupted transitions retain outgoing pixels and current item-card identity. Database sorting is a fixed-size popup control in the existing breadcrumb row, preserving navigation and sort state without adding a row.

The Prices scroll area reserves a narrow constant gutter and paints no empty scrollbar; scrollbar visibility cannot change card width or end a transition. A brief unknown name in the same proven shop slot inherits only the prior GUI presentation for two seconds. Its raw observation remains unknown. Masked shop-title identity can use only its exact captured list slot plus independent exposed shop guards and a native description body. Descriptions from shop rows never create a separate price reference. The Prices list and current-page labels keep their existing widgets and keys through hover changes.
