# Performance and resource pass

Started 2026-11-13 from committed release `ad213e2` (1.0.5).

The user approved the complete read-only audit's recommendations, including
storage cleanup or relocation to `/mnt/sda1`. Commit source before cleanup.
Do not publish or replace the installed application as part of this pass without
the appropriate release/install step. Preserve the existing capture session,
screen-only boundary, exact identity/current-pixel proofs, both model bundles,
recordings, and unrelated workloads.

## Baseline

The audit's short, uncontrolled existing-process sample was approximately
327 MiB proportional RAM and 1.8% of one CPU core. This is not a busy-shop,
translation, peak-memory, or physical Windows acceptance result.

A read-only replay of market availability validation used 2,014 SQLite
connections/queries and took 0.685 s. A monster drop-list replay used 63
connections/65 statements and took 0.032 s. These instrumented single runs
are comparison points, not latency guarantees.

Installed Linux files were about 899 MiB; Windows staging was about 651 MiB.
Both model bundles total about 306 MiB. The Linux CTranslate2 binding contains
63.8 MiB of non-allocated debug sections. Update artifacts occupy about 886 MiB
(two bases; the named package and current base are hard-linked). The source
workspace occupies about 38 GiB, predominantly build tools, distributions,
evidence and Cargo outputs.

## Work ledger

Each implementation entry below must describe its validation and limitations.

### Checkpoint 1

Implemented the catalog-retention fix, batched name/entry/drop lookups, owned
snapshot preparation plus GUI adoption, and one-running/one-pending cancellable
background jobs. The snapshot and reference availability paths no longer perform
bulk validation/writes on the GUI thread. Focused snapshot/reference/overlay
regressions passed (63 tests), plus the first five new performance-path tests.

Overlay states now suppress identical writes, keep one latest pending state under
pipe backpressure, and invalidate changed label regions. Reading no longer builds
the same overlay twice. Numeric opt-in paint acknowledgments extend the bounded
diagnostics through the helper's paint callback, not physical display presentation.

The primary reader is lazy, has bounded restart delays, and releases after an idle
pause. Positive viewport changes can cancel obsolete native repair between OCR
stages/rows without changing the original request deadline or interrupting every
pointer movement. Native tooltip geometry borrows the submitted frame and copies
only its analysis panel. The Minerva reader is initialized only on the fallback
path. A single shared engine cannot be introduced through the pinned dependency's
current public API; its private recognizer must not be bypassed or the vendor pin
modified. Full engine consolidation remains an upstream API opportunity.

Incoming translation is lazy, idle retention is configurable (default three
minutes), worker recovery/loading is bounded, accepted rows alone count as hits,
and late rows require fresh exact matching source pixels. One frame-scoped RGB
representation is shared by scan passes; it cannot authorize another frame.

Prices/history/watchlists and Database now use a common bounded image service.
Disk reads, decoding, writes and cleanup run in a bounded background queue.
Independent demand scopes prevent a hidden tab from cancelling another tab's
images. Async image/lifecycle regressions required fixture timing updates; the
broader suite is in progress. The 73 Rust tests passed after the native changes;
final native replay awaits rebuilding the executable used by Python fixtures.

Hidden Prices pages defer card layout while retaining observations/session
history. Tracking controls update only on context changes; numeric/clock cadence
is preserved. Saved display/position is restored without a later forced move.
Process retirement is parallel and asynchronous, with a final bounded drain.
Source dependencies now pin the release's Qt version. Linux runtime trimming
archives non-loaded debug symbols outside the package. Update settings expose
hard-link-aware cached installer usage and a busy-gated Clear action.

No installed files, live sharing helper, user settings or original recordings
have been changed. Storage migration has not started at this checkpoint.

### Checkpoint 2

The first full run covered 1,362 tests and found eager-start assumptions in
fixtures, synchronous-shutdown assertions, and two cleanup/late-callback issues.
Fixtures now explicitly start the reader when testing OCR rather than startup;
shutdown assertions verify the GUI never waits. At that checkpoint snapshot
storage briefly shared the catalog pool; the final implementation separates it
again so slow catalog networking cannot delay price adoption. Overlay close is
idempotent and queued renders ignore closed
or destroyed windows. Async direct image reads are kept independently of
viewport download demand.

The rebuilt Linux reader passed the 75 Rust tests, including explicit obsolete
request/repair cancellation. The focused native capture, transport, scheduler,
media, overlay and performance suite passed 94 tests in 11.626 s. The next full
suite is running against the corrected source and rebuilt reader.

Read-only post-change validation on the current saved 2,014-row snapshot used
one connection/one statement and 25.735 ms, versus 2,014 connections/statements
and 685 ms in the audit. A first batched drop replay reduced 63 connections to
one but remained about 31 ms; it was then tightened to project only the needed
identities within a consistent read transaction. Repeat timing is pending.

### Final source validation

The complete application suite passes **1,370 tests**, with three platform/opt-in
skips, in 205.088 s. **75 Rust tests** and **39 release-tool tests** pass.
The GNU reader and pinned-toolchain musl release reader both build. Checks use
private Xvfb/D-Bus/HOME/XDG state, software rendering, two native build jobs and
low scheduling priority. They do not automate game input or request sharing.

The actual native/GUI replay also matches **all 26 saved inventory cases** with
no wrong-item annotation commands. Its 20 positive cases have a 187.85 ms median
first-correct command and 659.6 ms maximum, with three above 500 ms. It uses fake
market/media/annotation sinks. This is a new unpaired fixture sample, not evidence
of improved live response or a physical display timing.

The final overlay regressions verify one latest pending state under real helper
pipe backpressure, no duplicate state write, and an actual numeric paint callback
acknowledgment. Snapshot storage is independent of catalog networking; a test
blocks that network path and verifies cached catalog display, Qt responsiveness
and a completed snapshot refresh. Disabling refresh suppresses late adoption.
Invalid replacement catalogs cannot overwrite last-good local identities.

The last read-only database replay still used **one connection/one statement**
for 2,014 market rows and returned the same 1,487 release proofs. Its 49.984 ms
under concurrent QA/build load differs from the earlier 25.735 ms; neither is a
guaranteed latency. The largest drop list (32 displayable rows) now took
**5.146 ms, one connection/five statements**, including its explicit read
transaction. The original replay took 31.228 ms after initial batching and about
32 ms before the pass. Query counts and current identity checks remain the
stronger evidence than a single wall-clock sample.

Hidden tracking pages continue model accounting, state/status and button updates;
only numerical/clock presentation waits until visible. Hidden Prices pages keep
observations and recent-item history without card layout. Reading Pause is
explicit about holding screen-based prices, tracking and incoming translation;
manual search/database access remains independent. Existing coverage/pickup,
pause/identity/map, NPC/add-form and current-pixel regressions pass unchanged.

Incoming translation preserves both model bundles and the user's enabled setting
while releasing idle workers. Frame RGB conversion is lazy and scoped to one
scan; text proposals use bounded integer arrays instead of full-scene float64
temporaries and four retained neighbor arrays. Late text requires current exact
source pixels, and only accepted rows count toward a successful scan.

New update bases record their signed release version. After installation, older
version-proven cached bases can be pruned without deleting unknown legacy data;
Clear remains available. Tests cover inode accounting, unrelated files, symlinks,
and filesystems where hard links are unavailable. Private QA also removes
inherited diagnostic-export paths so test runs cannot write to host diagnostics.

### Storage and runtime

After committed checkpoint `604a7fd`, **19.83 GiB / 326 paths** were hash-verified
and moved to `/mnt/sda1/lupin-archive/2026-11-13-performance/`. Original paths now
point there; live-source compatibility links preserve old evidence scripts.
Another **885.2 MiB** of verified obsolete update packages and **24.3 MiB** of
retired app-only browser cache were purged. The manifest, purge record and restore
procedure are described in [Storage maintenance](STORAGE_MAINTENANCE.md).

Current 1.0.5 installers, installed files, both model bundles, useful toolchains,
user settings/history, original recordings, live processes and the approved
sharing session were retained. No new installer was installed or published.

The separate Linux QA stage removes **69,148,113 bytes (65.95 MiB)** of
non-allocated debug sections from CTranslate2 and PyYAML, with separate symbols
archived by original SHA-256. The roughly 830 MiB stage retains both models and
runtime libraries. The stripped runtime's self-test and both actual translation
workers passed, including the final source/musl stage. Exact checks are recorded
in VERIFICATION.md. These checks establish import/model/plugin/OCR/IPC behavior,
not physical Windows screen capture or sustained busy-game CPU/RAM savings.

### Deliberate limits

The vendor remains pinned. Its private recognizer has no supported injection
API, so full OCR-engine sharing was evaluated but not forced through a vendor
change. Initialization and copies that could be removed safely were deferred or
removed instead. Cross-process shared-memory frame transport also remains a
future measured experiment: this pass reduces discarded-frame conversions and
copies while retaining the existing owned-buffer protocol and handoff semantics.
It does not claim zero-copy capture or a universal half-second response time.

Physical Windows capture, live busy-game hover/scroll performance, compositor
latency and monitor-power behavior were not exercised. Optional numeric timings
now reach through the helper's paint callback, which enables a later comparison
without recording chat, item names or screenshots. No game hooks, process access,
input listeners or automated replies were introduced.

- [x] Batch database lookups and move snapshot/availability preparation off the GUI thread.
- [x] Coalesce overlay submissions, bound pending commands, invalidate changed regions only.
- [x] Reduce frame copies and reuse per-frame analysis without weakening current-pixel proofs.
- [x] Defer unnecessary OCR initialization; evaluate a shared engine within the vendor pin.
- [x] Recover primary reader failures and avoid obsolete queued work.
- [x] Correct late translation accounting and add recoverable worker states.
- [x] Make incoming translation lazy with bounded idle retention; share frame analysis.
- [x] Limit presentation work to changed data and active pages; retain smooth numeric motion.
- [x] Clarify tracking coverage/state and validate pickup/session continuity.
- [x] Share thumbnail storage/demand and perform disk/decode work off the GUI thread.
- [x] Batch database navigation and precompute manual-search normalization.
- [x] Preserve last-good catalogs offline and defer unused reader processes.
- [x] Coordinate pause/shutdown and restore the intended display/position.
- [x] Trim release debug data, pin dependencies, and bound/clarify update-cache storage.
- [x] Extract orchestration/typed state and add bounded capture-to-paint diagnostics.
- [x] Archive or purge verified unnecessary development storage after committed checkpoints.
- [x] Update architecture, changelog, development instructions and verification results.

## Additional selected-item shop sightings

The user approved an item-card **Where seen** subtab after the read-only source
investigation. Prices and Database share one bounded, asynchronous sighting cache
with a 15-minute positive/empty/failure lifetime. Only the selected visible
subtab requests data; regular price cards, overlays, typing and OCR still use
the local full-market snapshot exclusively. The reader/helper is independent of
the game. Native helpers are short-lived; hidden/minimized pages stop demand
and age animation, and unchanged sighting rows retain their widgets.

Both native platform sources compile. A real isolated Linux request returned
26 validated Work Gloves sightings in 4,754 IPC bytes; large sale histories are
not retained. The complete Python suite passes 1,426 tests with three skips;
subsequent focused checks cover the final identity-cache guard as well. Cards
fit the 460-pixel minimum width. Physical Windows networking/capture remains an
acceptance check. [MARKET_LISTINGS.md](MARKET_LISTINGS.md) and
[VERIFICATION.md](../VERIFICATION.md) record details. This is part of the source
preview; no package, install or publication is requested.

Combined-preview review also found the first-price confirmation referring to
draw-local variables from the separate paint-timing callback. It now remains in
the draw path; timing acknowledgments consume only their report. Two dedicated
regressions and the existing wrong-reference rejection pass in the final
22-test guard run, after the complete 1,426-test run and 194-test focused pass.
Live preview startup then exposed a slide callback retaining an invalidated
Python container proxy, although the native page container remained present.
Completion/movement/resize safely discard retired targets, and listing demand
uses explicit owner/subtab selection without walking Qt's private parent
containers. Animation/listing/card checks include target retirement and live
selection checks during a slide. The actual preview's normal cache
also contains 26 successfully downloaded sightings; this is distinct from the
isolated source check and does not establish live game/OCR performance.

## Shared detailed card follow-up

The user approved consolidation of searched and automatically read item cards,
with a compact price header above full-width detail tabs. The common factory
retains exact identity checks, optional current/last-seen asking context, lazy
source/listing demand and the existing GUI-only grace/history lifecycle. Normal
Overview cards use their natural compact height; unusually long equipment uses
the outer page scrollbar. Stable summary dimensions prevent quote/count updates
from moving the tabs. Shop rows retain compact browsing and open the shared
details on click. The normal star action does not select a card.

The complete run passes 1,437 tests with three skips. Six final guards and
controlled 460/520-pixel renders cover later offer/caption refinements, common
card heights, quote stability and long-overview overflow. Native OCR/capture and
the vendor pin are unchanged. [ITEM_CARDS.md](ITEM_CARDS.md) and
[VERIFICATION.md](../VERIFICATION.md) contain the current contract and evidence.

## Acceptance

### Rendered motion follow-up — 2026-11-14

The card-size changes are now animated, rather than established immediately
behind a slide. Owned tab geometry avoids the native tab widget clipping new
content until a resize ends. Detail height uses the existing 220 ms subtab curve,
and automatic-card canvases follow its exact delta. Replacements interpolate a
native styled border around unscaled foreground text/images with the full
130 ms fade/lift. Retargeting starts from the visible frame/height, including
rapid reversal before the first height tick.

Page slides use transient opaque composition, repainting affected regions for
live text, digits, models, images, controls and nested animation. Real widgets
retain input/focus. All images, connections and own-widget event filters are
released when the slide finishes or hides. This adds no idle frame loop.
Watched expansion still moves a fixed content canvas over 220 ms; it has not
been replaced with an instant swap. A sighting response now creates one virtual
viewport with at most 100 lightweight records, instead of a row widget tree.
Visible age digits/fades retain shared 160/110 ms clocks.

The private xcb/software-rendered check uses a real Qt event loop, copied local
reference/price data, offline capture/image/listing services, and lossless
60 fps recording. It covers all four tabs, watched expansion, item subtab
growth/shrinkage, equipment/consumable/scroll replacement, search/clearing,
100-entry history insertion/scrolling and rolling figures. Rendered strips were
inspected alongside paint-event timing; deterministic tests also compare exact
native endpoint pixels and live partial updates.

At 520 × 840 / 1× scale, the 24-action final sample records:

| Moving view | Mean paint CPU per frame | Largest observed moving-frame gap |
| --- | ---: | ---: |
| Main navigation | 0.65 ms | 16.80 ms |
| Item replacements | 0.82 ms | 17.29 ms |
| Item detail tabs | 2.86 ms | 17.95 ms |
| Watched expansion/collapse | 4.19 ms | 18.31 ms |
| History insertion/scrolling | 1.00 ms | 17.11 ms |

The `d2e8dfa` comparison sequence averaged 3.87 ms for main navigation and
3.80 ms for replacements: approximately 83%/78% less paint CPU in these samples.
Animation durations remain intact. Card preparation is a separate cost, roughly
50–80 ms in the sampled real-database selections; these figures do not claim
sub-frame construction or eliminate source/network latency.

A separate 460 × 840 / 2× scale sequence keeps sampled moving-frame gaps below
20 ms and paint callbacks below 10 ms, including watched expansion. Idle samples
use 4.56/5.34 ms of UI-thread CPU over 1.5 seconds, with no retained slide/card
surfaces. Whole fixture-process peak RSS is approximately 207/222 MiB; this is
not a live OCR/translation memory figure or the allocation cost of animations.
Other host workloads are left running. These checks establish the tested Qt
render path, not physical compositor presentation, native Windows performance
or a universal FPS guarantee.

Evidence, recordings and profiles are under
`evidence/smooth-motion-2026-11-14/`. Current regression results are recorded in
[VERIFICATION.md](../VERIFICATION.md). No installer, release or game-reader
change is part of this animation follow-up.

The scrolling/card-opening follow-up adds one bounded wheel animation per own
viewport, preserves direct trackpad/scrollbar input and disables motion when
hidden or reduced. Reference-list media demand is coalesced during motion, and
watched-thumbnail selection uses the existing exact-ID catalog index. Prices
cards retain their full 130 ms opening/closing transition. Page slides,
watched-section motion and number rolls retain their effects and durations.
Glyph/height caching, affected-layout propagation, unchanged-style guards,
cached database counts and deferred hidden sightings reduce work around those
animations. The summary is initialized once with its actual data. The timing
evidence and regression outcome are recorded in
[VERIFICATION.md](../VERIFICATION.md); no game capture/recognition or release
artifact changes are part of this follow-up.

Run focused meaningful regressions as each subsystem changes, then the full
Python, release-tool and Rust suites. GUI/native-helper checks use isolated
Xvfb, D-Bus and HOME/XDG directories with software rendering. Limit native
build/test concurrency and use low priority. Never drive the game.

Compare cold/warm fixture latency, counts of database operations and overlay
submissions, and bounded process/resource samples. Include scrolling/hovering,
comparison panels, NPC/add-item forms, pauses/reacquisition, translation
interruption, hidden/tray behavior, and stale market generations. Fixture or
Wine checks do not establish physical Windows capture performance. Record
untested physical/display-sleep cases explicitly.

## Storage rules

Inventory before moving. Keep source and the currently useful build available.
Archive originals with a manifest and verified hashes before removing their
NVMe copies; preserve old paths using symlinks where tooling/evidence depends
on them. Purge only reproducible outputs or demonstrably obsolete app-owned
caches. Never move a live helper/runtime out from under a running process.
Do not touch personal browser profiles, game files, unrelated repositories,
release-signing keys, or user settings/history. Record bytes reclaimed and
restore instructions.
