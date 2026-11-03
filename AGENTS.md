# Lupin (formerly Classic Price Lens)

This is a screen-only companion for **MapleStory Classic World**.

- Never attach to, inspect or enumerate the game process, read game memory/files/packets, hook a renderer, send game input/messages, or parent an overlay to the game window.
- Observe through ordinary OS capture. OS pointer coordinates are allowed; input/event hooks are not. Annotation canvases are independent and click-through. The explicitly opened clipboard-only Korean writer is a separate, managed, focusable Lupin surface; never make the canvas interactive. Tests may drive our own UI or fixtures; game actions must remain user-driven.
- Configurable hotkeys must use OS shortcut registration only: Windows RegisterHotKey, the Wayland GlobalShortcuts portal or an X11 passive grab for the chosen chord. Never use keyboard hooks/listeners, poll keyboard state or synthesize game input. Test hotkeys through our own messages or an isolated X server, without sending game input.
- Shop-row labels remain visible while a shop is open. A pointer over its listing uses only the shop reference; hovering inventory or equipment outside the list can show its own card at the same time. Inventory hover pricing defaults on, with a persistent toggle.
- Equipment is assumed unscrolled. Validate exact item IDs, handle duplicate names conservatively, and never substitute NX retail costs for meso market prices.
- Full-market rows whose well-formed listing and catalog IDs differ are unverified aliases: omit them without mapping either ID or blocking unrelated exact rows. Reject malformed identities, duplicates, wrong worlds and generations with no exact rows.
- Cache successful, empty, unsupported and old-report responses for the selected TTL. Market-data validity and HTTP-cache validity are separate. Never fetch on every frame.
- Full-market snapshots refresh asynchronously on launch and at the selected interval. All price views use this snapshot; do not restore individual price API requests. Keep them local, preserve last-good data on failures, validate Classic World/exact IDs/names/units, and keep publication/check/report ages distinct. Use only the short-lived native system-web-view helper: WebKitGTK on Linux, production WebView2 on Windows. It exits after each update, uses no personal browser profile or DevTools socket and never touches the game. Keep the subprocess pipe/deadline bounded and reject cancelled/late output.
- Preserve the user's active sharing session during a Linux UI update: SIGUSR1 to our main process performs a handoff; normal close stops sharing. Do not restart the capture helper for routine UI changes.
- `python -m unittest discover -s tests -q` checks prices, real OCR fixtures, local frame IPC and UI context. Use offscreen Qt for automated UI tests. Native Windows game capture is not proven by Wine/offscreen tests.
- Windows packaging: `scripts/package_windows.py` stages verified runtime downloads and the compiled Windows reader; `scripts/build_windows_installer.py` creates Setup. Normal release checksums and signed metadata contain only Windows Setup, Arch and DEB packages. Portable Windows archives are retired. `setup-windows.ps1` supports a native source build. See docs/DEVELOPING.md, README and VERIFICATION for the current workflow, evidence and platform limits.
- Installer/package builds: see `packaging/README.md`. Keep install roots read-only during normal use; write logs, settings and price caches only to per-user paths. Windows upgrade/removal may close only our app via its local control socket. Never use a generic process killer or global Wine prefix. Validate package transactions in isolated roots, preserving active host sharing.

Keep vendor Minerva at its pinned revision; read its own AGENTS.md before changing it. Do not include private `evidence/`, live screenshots, caches or database files in a package.

On a Linux desktop, run GUI/native-helper QA and Wine UI tests inside an isolated Xvfb display with WAYLAND_DISPLAY/WAYLAND_SOCKET unset; use GDK_BACKEND=x11 and software rendering for test helpers. Offscreen Qt alone does not isolate GTK/Wine helper windows. Set QT_QPA_PLATFORM=offscreen inside Windows Python before constructing QApplication, rather than relying on Wine to forward the shell variable. Never let test copies of Lupin or transient helper windows appear over the user's desktop.

Lupin keeps legacy internal application/settings/socket IDs for upgrade compatibility. Price Search works without capture and reads the same full-market snapshot as overlays and watched items. Typing, selecting, hovering or watching items must not issue individual price requests.

EXP tracking starts only after the user presses Start tracking, always begins stopped on app launch, and disables its reader when stopped; percentage rates are the default, with raw/both settings. Keep header/display/tabs fixed between pages. Respect Reduce motion and stop the header movie while hidden. Market coverage never establishes item identity. Unique exact-ID search selections remain independent of snapshot availability; ambiguous names require current visual or explicit selection evidence.

Linux packages are named `lupin` and replace `classic-price-lens`. Preserve existing per-user data and the desktop/portal identity during migration. Prices includes manual search; Translation has its own tab. Shortcuts default on both platforms to Super/Win+F9 prices, +F10 EXP, +F11 reading Korean and +F8 writing Korean; retain explicitly customized assignments. Shop labels stay fully opaque and in place for the verified current page, except where a verified add-item form overlaps their measured rectangles. Native shop descriptions may refine a clipped listing identity, but never create another price overlay or replace the shop list in Prices.

Super/Win+F8 opens the clipboard-only Korean writer, independently of capture and incoming translation. Only explicit Enter/Translate & Copy may write the current validated draft to the OS clipboard; edit/cancel must invalidate pending copies. Never paste, send keys or focus a game field. Keep known item names, explicit numeric scales/currency/percent roles, UTF-8 pipes and local-only processing. All Wayland portal callbacks must marshal onto the Qt GUI thread; activation tokens may focus only our own surface. Both verified local model bundles ship on Windows and Linux; no chat/drafts may enter logs or packages.

With fresh verified game bounds, the hotkey writer occupies a compact bottom-right corner beside the measured HUD, expanding upward; use an above-HUD fallback when the side lane is too narrow. Translation/draft/clipboard authority remains in the main GUI; the annotation helper hosts only a managed writer surface with bounded, session/sequence-checked state messages. A stale draft acknowledgment cannot block geometry/close commands. Keep writer rectangles out of translation, pickup and price OCR and reserve notification space above them. Check activation only on our own window, offer click-to-type/native-dialog fallback if denied, and preserve the ordinary dialog when capture/geometry/helper is unavailable. Never force a keyboard grab or activate a game field.

Price-search thumbnails use exact game IDs from the current Classic World OSMS image route. Keep image demand separate from price calls, bound downloads/cache sizes, cache misses, and show a placeholder for missing/ambiguous identities. Do not ship fetched images or user caches.

Program packaging uses /opt/lupin, the lupin launcher and lupin-screen-reader binaries; Windows installs to Programs\Lupin and moves the old program directory during upgrade. Retain stable settings/socket/portal identities so the rename preserves data and approved sharing.

The control panel cannot be pinned on top or maximized. Clear the removed keep-on-top preference during migration. Watched-item rows show thumbnails and cached references, with three visible before scrolling. Expanding shows the list only; a click opens an item card. Deselecting keeps the watched view; collapsing clears it and returns to store cards. Watch alerts shimmer twice inside the annotation, with a steady border. GUI currency words use the small coin except MESO on the tracking panel and EXP/Meso Tracking on the tab. Price-overlay text remains plain; the tracking meso gain uses a tiny coin aligned with the EXP percent symbol. Hide tracking coin units until their values exist.

Fresh windows use 27.0833% of the logical screen width and 77.7778% of its height (520 × 840 at 1920 × 1080), bounded to the available area. Remember manual resizing as screen-relative fractions and retain the 460-pixel minimum width. All price cards share the exact-ID watch control. An expanded watch list alone does not hide the ready/shop view; only a selected item takes priority. Tabs use plain labels and a filled active-tab background. Shop labels never dim for a cursor or item description. Tooltip geometry remains an OCR exclusion, not a presentation mode. Listing amounts can return without another OCR pass only when the exact previously read row pixels and page guards match. A tall description may cross the footer rim: cached game bounds require the independent LV anchor and caption to remain verified. Clicked item-link descriptions may be located away from the cursor using the same pixel-only reader, followed by catalog and panel validation.

Meso tracking counts confirmed visible pickup-log arrivals, independently of EXP gains; it does not scan the wallet or infer potion costs/profit. Seed messages already visible at Start/Resume or after lost coverage. Keep the ledger bounded, distinguish repeated amounts in different arrivals, and hold when known windows cover the log. EXP and meso overlays are separate compact cards stacked in the empty corner left of the HUD, with an above-HUD fallback when that corner is too narrow and independent checkboxes. Preserve the native locator's guard pixels instead of weakening detection to tolerate our overlays. Gains, rates and ETA update every two seconds; elapsed clocks tick each second, with immediate pause/context changes. User Pause freezes identity, map, run, watch totals and pickup state; another visible character must not reset or switch them. Reconfirm the original captured identity before showing its paused cards or enabling Resume on a changed game area. Preserve the basis of legacy wallet-history records. Enter in the Korean popup submits its current draft, animates the popup closed without canceling that authorization, then copies and shows an expiring overlay notification. Escape/edit still revoke pending copies.

EXP warmup requires 30 seconds of clear accepted readings, not wall-clock time. Both EXP and meso rates average up to five active minutes; pickup rates have a ten-second minimum. Pause preserves the displayed pace/ETA and both recent windows. Map-history segments must never reset rate history or cumulative gains. Stop and save ends the session; a new Start resets it. Elapsed clocks update every second independently of two-second gains/rates/ETA snapshots. Meso uses bounded one-second pickup buckets and retains the last confirmed pickup across pauses/maps. The MESO header omits its normal basis text while retaining Paused/Log hidden states; its footer shows Last pickup. Use plus signs and the overlay's green for GUI meso figures.

Distinguish held readings from numerical validation or reacquisition. Relearn an inconsistent numerical baseline only from bounded, fresh, changing and mutually consistent observations for the same captured identity/level; retain confirmed gains and exclude the untrusted interval. Captured name proofs come from the same submitted frame as the EXP result. Keep visual identity stable through OCR spelling changes, with bounded template variants and conservative confirmation for genuinely changed pixels; never globally alias characters such as Z and 2. Tracking gains use a large rolling font, bold headings, a larger percent unit and aligned units in 56-pixel cards. Narrow down to 200 logical pixels before using the above-HUD fallback. The tracking page explains both rate windows once with “Rates based on the last 5 minutes”; normal overlay headers omit a rolling-window label. Keep warmup/paused/held states, and indent EXP/MESO headings past the plus-sign gutter. Use Level X · ETA on both displays.

Shop occlusion geometry requires a native dark body and structural frame evidence.
A bounded cyan-marker/frame probe may find a description before OCR when a
verified shop source is disrupted. It supplies geometry only, never item identity
or an asking price. Exclude our annotation pixels and both cursor footprints from
row, frame and scrollbar comparisons; cursor-covered thumb edges remain unknown.
Use fixed table rims for container proof, independently of scrollbar animation.
Allow a bounded 750 ms trail of at most eight ordinary pointer positions for
capture latency. Pointer masks apply to source comparisons, never to finding
native frame/body geometry. A previous native pane has its own 350 ms trail.
Native geometry masks include their frame/shadow margin; a
clipped native occlusion still requires independent native edges and body pixels.
Canonicalize verified slots before merging omitted rows so OCR rounding cannot
duplicate labels. Generic tooltip names must match the latest captured pixels.
Tooltip-title proofs may tolerate dark translucent background changes only with
an independently present native panel. Independently bound inventory titles
also permit antialiased fringe blending immediately around byte-exact opaque
glyphs; added/moved/recolored opaque strokes, foreign ink and erased edges fail.
Generic/shop title policies stay strict. Do not weaken shop-row or asking-price
proofs to achieve this. Inventory source cells and interior header/frame guards
remain independently verified. With an explicit native sourceTab, recognize
only the selected-tab white pulse using the shared bounded colour-direction
fit; retain exact caption/buttons/inactive-tab pixels and visible pink selection.
Changed native-gold rim pixels may animate within the scaled outermost cell
pixel. A second inset scanline and its blended fringe are allowed only with
enough exposed, aligned gold anchors in both frames and bounded native colour
directions; never ignore a wider border wholesale. Exposed icon interiors must
match exactly with a scaled 16-pixel
minimum even on a byte-identical cursor frame. Older metadata retains strict
guards. Fully covered
cells remain unknown rather than alternating authority with cursor animation.
Native capped frames need bounded corner lanes and both full-height rails;
a short divider cannot supply their boundary. Carry only Lupin-owned annotation
rectangles with each immutable request, in source coordinates, and convert them
to the actual native analysis origin. Treat those rim samples as unknown and
black out that paint for OCR. Python checks the old frame with its submitted
masks and the latest frame with current masks. Require exposed native rails and
corners; these masks never excuse changed cell/header/title pixels or borrow a
comparison name. Completely hidden geometry remains unverified.
Shop epochs/retries must not discard independently current inventory proofs.
Discard stale shop/hover authority without allowing its old description to
become an inventory reference. Clear cached shop routing when its container is
lost. Inventory/equipped pricing remains independent while a shop is open.

Verified scrolling advances the viewport epoch and invalidates previous-page
labels immediately. Clear row/offer caches while preserving independent fixed-rim
geometry proof; covered new rows cannot inherit a previous item. Reject purple
tooltip-tinted thumb pixels as unknown, not scrolling. There is no temporary
shop-hover priority timer. Keep
submitted reader context immutable and request fresh work through
`PixelReader.request_rescan`; UI code must not reset an active timeout. Known
last-seen asking prices remain available for the lifetime of the verified page,
separately from current offers. Market expiry and exact identity checks still
apply, and fresh compatible quotes may update an existing comparison in place.
Unchanged exposed native names at the saved slots support retention of loaded
references beneath descriptions, even when pane geometry is incomplete. Such
held rows have no current offer. An exposed changed title must not inherit the
old item; positive scrolling clears all old rows. A same-slot name anchor or an
unchanged exposed thumb vetoes name-only frame scroll detection, while confirmed
thumb movement wins. Blank background is not a name anchor. Preserve an earlier
usable same-item title template when a later read is masked.
When an exposed shop name is readable but its asking line is blocked, the local
reader may return a name-only row with its own exact name rectangle. Require
independent table proof and unique catalog identity; do not resolve a covered
icon or infer an amount/tier. A fresh name can finish viewport reacquisition.
Retain that identity without a current offer until a complete asking line is read.
Apply bounded component recovery to every unread slot on the verified table,
independently of the pointer's row. Native blue/orange text must have a complete
ending before a pane/cursor; description text never supplies a new listing.
Keep this path available while a verified pane touches the table, even if every
returned row is known: omitted slots are not proof of a complete page. An
unrelated palette-compatible panel cannot supply its rows or grid to that hint.
Complete native UI ellipses require three actual aligned dot components as well
as agreeing OCR before using their smaller blank margin; ordinary asking guards are unchanged.
Independent asking recovery requires two agreeing reads of the complete
quantity, "for" and strictly grouped amount; no currency word is required.
Bind priceText (`Q for N`) to the numeric tuple. priceArea and priceValueArea
must match and include the positively visible blank next-comma footprint for
complete three-digit groups, or the next-digit advance for short amounts.
Validate digit shape, font advances, core width and exact latest numeric pixels;
joined zeroes may contain multiple measured cells within one ink run.
A mask over any numeric ink rejects the amount. Always validate this proof even
when the broader masked row matches. Preserve complete current ordinary-reader
rows when optional recovery fails; never borrow a prior-page price. Later native
slots can establish the row-grid phase when the first slots are sold out.
Cursor footprints match the native inventory proof: 32 by 37 pixels at 1x,
with six pixels left and seven above the hotspot for the animated top outline.
Round outward consistently at fractional scales, preserving the bottom bound. Fixed container guards stay inside the inner bevel, away from
animated scenery. Batch cached price deliveries and draw annotations before
performing the heavier control-panel card layout.
Orange-selected components use their native antialiasing and separator palette.
Known bevel colours may be normalized only at bounded outer scanlines with a
broad uninterrupted native prefix; retain all dark glyphs and foreign pixels.
Python must match the reader's rounded 8-bit <160 ink cutoff when validating
exported components. A new scrolled selected row requires fresh identity/amount
proof; it cannot inherit a prior-page price.
Names and amounts have separate current-pixel proofs. Blank-tail clipping or a
masked-margin change cannot discard otherwise complete exposed components.
A name-only update may retain an earlier same-page/slot/exact-item amount for
presentation, separately from its null current offer; scrolling clears both.
Unchanged stationary shops need no fixed 200 ms description OCR loop. Pixel or
pointer changes, explicit retries and periodic locator checks still trigger work.

Native tooltip frames use raw captures and independently terminating cap corners;
inventory rails visible through a translucent body cannot define its boundary.
Owner tags do not set title-to-cap padding. A separately framed comparison can
split a common-rim union without supplying the primary's title. Version-three
inventory proofs bind both single descriptions and primary-left pairs to exact
source/header/cell/title pixels; translucent rails use the same scaled structural
predicate in Rust and Python. Protect the complete source and both native panels
from our annotations. A positively verified shop price-entry form fades only
shop labels whose actual annotation rectangles overlap it, retaining stable
labels/observations/history. Closing the form restores opacity, while source and
offer updates still require a newly submitted, verified shop read. Exposed table
rims must remain current throughout; losing the container removes the labels.
Late replies cannot mutate held observations. Form evidence excludes Lupin's
own labels and supports partially covered fields without treating those labels
as native controls. Fully covered inputs/buttons may remain unknown only with
independent exposed caption ink, connected frame strokes, paper and all three
magenta labels. A previously verified form may relocate from exposed native
fields, footer controls and its right/bottom rails when our labels hide the
magenta column. Capture paths which omit our paint may recover only from the
complete current native grid plus both physical rails; metadata rectangles alone
are never evidence of a form. Visible contradictory controls reject the form. Inventory labels
and ordinary shop descriptions never dim. Inventory cards prefer directly above
the verified hovered description, using side/below fallbacks when necessary;
never anchor them to the inventory or equipped comparison. Reset pointer offsets
when description geometry changes and clear omitted anchor metadata.

On-screen item cards have a GUI-only 2 second grace period before retirement to session history. Current observations alone supply overlays and offer verification. Animate the active-card canvas independently of history, including the first history header/gap; quote and age updates must not restart structural motion. Keep at most 100 unique session entries and animate/repaint only visible rows. Stable shop annotation keys use the verified page, canonical item and list-local slot. Held shop presentation stays separate from current offers and requires the same verified page/slot/item and a fresh exact-ID market reference. Nearest-name/fuzzy pricing remains deferred; native retries may omit a decorative marker only on a proven marker-bearing title path.

GitHub Releases is the sole distribution and update destination. GitHub application updates use the public stable release feed, pinned Ed25519 signatures and exact artifact hashes. Check on launch and the configured timer; never install without Download & install. Linux authentication goes through the fixed root-owned polkit helper and native package manager. Never bypass authentication or patch managed install files in place. Source checkouts do not automatically check/install. Keep release signing keys outside the repository and all packages. Patch decoding uses bounded chunks, with verified full-download fallback. Publication and repository visibility still require user authorization. Exact source/panel/guard proofs remain mandatory; no fuzzy name matching is added.

An available application update gives Settings a repeating pulse/shimmer, confined
to that button. Stop its animation while hidden/minimized or with Reduce motion;
retain a static update indication. Repeated status updates must not restart it.

NPC buy, Buy Back and sell lists never supply market prices, including their native hover
descriptions. Classify them from independent current controls and frame/tab
structure, not potion names, blue row colours or missing asking prices. Keep
ordinary inventory/equipped pricing independent. A cached NPC list rectangle is
for capture scheduling only, never player-shop routing or recent-item history.
Accept current shop rows independently while retrying a failed neighbour. Slot
geometry can refine its vertical position from native dividers; this must never
weaken title, numeric-ending, exact-ID or current-source proofs.
NPC control acquisition must cover the entire connected window from either
column. Reusable control samples exclude selected tabs, wallet digits, item rows
and portraits. Present/unknown/absent states keep uncertain known bounds excluded
until current exposed controls release them; an OCR metadata flag cannot bypass
this policy. Independent overlapping inventory needs its validated ordinary
header, source cell and title. Keep capture's source/current-frame filtering and
the UI's immediate overlapping-cache retirement in sync. The detailed current
contract is docs/SHOP_RECOGNITION.md; update it with changes to this pipeline.

Pickup-only admission remains independent of EXP numerical candidates. Bind
each job to its captured character proof: a missing proof holds that job, while
positively different pixels hold the session for EXP/context reconfirmation.
Do not reset arrival continuity on an ordinary temporary OCR failure or extend
freshness/timeouts to guess missed pickups. Keep numeric diagnostics bounded and
text-free; optional LUPIN_READER_DIAGNOSTICS export is developer-only.

The native complete-page cache requires capture_generation, shop_epoch, a
current shop_area and exact table/icon/rim pixels. It must never bypass Python's
latest-frame source/NPC/offer checks or retain a stale hover title. Keep geometry
available when shop_recovery is disabled. progressive_shop permits at most one
shopPartial reply before the final result, with one immutable request and its
original deadline; never enqueue another request between phases. Ordinary
complete native rows may export numeric proofs from their existing strict read;
missing components still need two agreeing independent OCR readings. Keep
scroll-tier picture protection and clipped-title refinement when skipping
unnecessary description recognition.

Only an already verified add-item form may treat the bounded current cursor as
unknown control pixels, with independent current native controls/frame evidence.
Cursor masks cannot bootstrap a new form, excuse contradictory exposed controls,
or retain a form after its native structure disappears. See
docs/TRACKING_AND_READER_PERFORMANCE.md for the current evidence and test limits.
