# Shop recognition and price ownership

This document describes the current source implementation. It complements
[ARCHITECTURE.md](../ARCHITECTURE.md), the user-facing [README](../README.md),
and the dated evidence in [VERIFICATION.md](../VERIFICATION.md).

Lupin observes ordinary OS-captured pixels. It does not inspect game processes,
memory, game files or packets, register input hooks, or send game input. Nothing
in this flow makes an individual market-price request: accepted exact item IDs
use the existing full-market snapshot.

## Ownership comes before pricing

Player shops and NPC shops share much of their blue list palette. A readable
name, an empty column, a missing asking price, or a market reference cannot
identify which kind of window owns a row.

| Captured source | Pricing behavior |
| --- | --- |
| Verified player-shop listing | Use the listing's exact item identity and independently proved asking amount. |
| Description originating from that player-shop list | Refine an already established listing where allowed; never add a second description overlay. |
| NPC buy list, Buy Back list, or sell list | Exclude rows from market overlays, Prices cards, recent-item observations and watched-item encounters. |
| Description originating from an NPC list | Exclude it from market pricing. |
| Separately proved ordinary inventory/equipment window | Keep hover pricing available, including when its description overlaps an NPC shop. |
| Manual search or a selected Database entry | Use its explicit exact-ID selection, independently of screen recognition. |

The Database's named NPC-shop sources still show independently sourced NPC
purchase costs. Those are reference relationships, not live market overlays,
player asking prices or observed sales.

## Modules

| Module | Responsibility |
| --- | --- |
| `reader/src/shop_panes.rs` | Reject the native three-line Sold Items ledger before player-list selection. |
| `reader/src/shop_names.rs` | Recover complete current name/asking components on a hinted native table; the hint never establishes an item or price. |
| `reader/src/shop_cache.rs` | Reuse one complete page only with the same capture/viewport and byte-exact current table, pictures and rim; omit old hover titles. |
| `price_lens/pixel_components.py` | Connect native colour runs in two dimensions with a work limit. Shared by NPC controls and the add-item form. |
| `price_lens/npc_shop.py` | Acquire NPC-window evidence, revalidate its stable controls, and enforce row/description ownership. |
| `price_lens/capture.py` | Bind recognition to immutable submitted frames, track current NPC state, filter replies, validate inventory source proofs, and schedule capture/reader work. |
| `price_lens/price_observations.py` | Accept individual current player rows and retain only independently allowed same-page presentation. |
| `price_lens/shop_rows.py` and `shop_browsing.py` | Own table guards, slots, asking-price retention and viewport epochs. |
| `price_lens/ui.py` | Remove conflicting player caches on NPC discovery, render accepted observations and request cached references. |

Shop-only requests can publish complete ordinary rows before missing-line
recovery finishes. The partial and final replies share one immutable submitted
frame, generation, epoch and deadline, and both pass the filters below.
Cached native results receive the new capture timestamp but do not establish
current offers by themselves: Python still checks all current source/amount
proofs. See [the performance record](TRACKING_AND_READER_PERFORMANCE.md) for
cache limits, scheduling and numerical diagnostics.

The add-item form is independent presentation state. Only overlapping shop
labels fade, while observations/history remain intact. A previously verified
form can mask the bounded current cursor over its controls, with independent
current frame/control evidence; initial acquisition cannot use this mask.
Exposed contradictions or disappearance release the form. Stale recognition
replies cannot confirm that a closed form is still open.

The native reader can recognize text in an NPC list because the palettes are
shared. A name-only reader result is not an exemption from NPC filtering.

## Acquiring an NPC window

`find_npc_shop` operates on the immutable source image used by a reader request.
A native table rectangle may bound the search, but supplies no classification
authority. The search extends on both sides so a hint from the right-hand sell
column still includes the left-hand Buy and Leave controls.

The detector finds orange button components in two dimensions. Vertically
overlapping orange scenery cannot merge unrelated controls into one global
row band. Candidate pairs establish the scale from their horizontal separation.
The native interior is checked within a bounded vertical offset of the measured
button components to accommodate bevel/capture rounding.

Initial acquisition requires the complete, exposed native arrangement:

- The paired orange Buy/Sell controls and green Leave control above Buy.
- The white wallet-field rails, excluding its changing digits.
- The connected red divider and independent bevel samples from both headers.
- Both category strips, accepting their native neutral and pink colours without
  requiring any particular selected tab.

All and Buy Back are both valid left-tab states. Equip, Use, Set-up and Etc. are
all valid right-tab states. Their contents may be empty, populated, scrolled or
selected. Tab highlight, item names, portrait animation, wallet value and list
contents do not enter the reusable control samples.

Lupin-owned annotation rectangles and bounded captured/current cursor footprints
are excluded from evidence. A masked control
is unknown; our own text/background cannot supply native proof. Initial
acquisition does not accept unknown required controls. A completely obscured
NPC header cannot be newly classified from its blue rows alone.

## Revalidation and uncertainty

`NpcShop` records the measured bounds, scale, stable control rectangles and their
captured pixels. Revalidation first compares only those small rectangles. If
they remain byte-identical, no full discovery scan is needed. If they differ,
the same bounded native predicates are checked again in the measured header.
These classify window geometry; they do not relax item-name, icon or amount
proofs elsewhere in the application.

| State | Evidence and behavior |
| --- | --- |
| `present` | Every stable control/frame check is current. Keep both NPC lists excluded. |
| `unknown` | Required pixels are covered without exposed contradictions, or one check is damaged while at least six other checks remain positive. Retain exclusion of the previously proved bounds, without authorizing any item or player-shop context. |
| `absent` | The header is entirely outside the captured image or sufficient exposed controls contradict the old window. Release its bounds and capture-only fingerprint. |

There is no timer that promotes unknown NPC rows into player rows. Uncertainty
can persist while the controls remain covered; exposed contradictions release
it. Closing or moving the window normally contradicts several stable checks.
A moved NPC is acquired afresh from a subsequent submitted frame, rather than
moving an old exclusion based on a guessed drag distance. Resetting the capture
area/source clears the NPC state with the other recognition state.

`PixelReader.observe_shop_frame` revalidates an already known NPC before the
captured image reaches the UI. It does not discover NPCs across the full frame
on every capture. Discovery runs when a submitted price result provides a shop
candidate or a found ordinary description. An inventory-only result does not
trigger a new full NPC search: it must still pass complete source/header/cell/title
validation, and any already known NPC exclusion still applies. `npc_shop_changed` emits only when excluded
bounds enter, leave or change; tab and list changes do not repeatedly advance
shop epochs or rebuild the Prices page.

## Submission, current frame and late replies

Each reader request owns its source frame, pointer, crop coordinates, capture
generation, shop epoch, annotation rectangles and deadline. NPC handling checks
the submitted frame and current frame separately:

1. Reuse or acquire NPC proof in the submitted source. Old NPC-owned rows remain
   excluded even if that shop closed while OCR was running.
2. Revalidate the current NPC context against current pixels, accepting a newly
   acquired source context only if the latest header supports it.
3. Filter NPC-owned rows before creating player-shop routing context or emitting
   observations. Current NPC bounds also block old player rows beneath them.
4. Apply the ordinary viewport-epoch rules. A late shop reply cannot revive an
   older page or invalidate independently current inventory proof.
5. Validate any inventory source/header/slot/title against both submitted and
   current pixels, then apply description ownership.

The source pointer is converted using the immutable request crop; the current
pointer uses the same source coordinate system. Price-row exclusion uses native
table bounds. Description exclusion follows its source pointer and independently
validated source proof, rather than where the description happens to be drawn.

A raw `inventory-primary` metadata flag cannot bypass NPC exclusion. Inside NPC
bounds, bypass requires an actual `TooltipAssociation` with a validated ordinary
`InventoryHeader` and the pointer in its bound source slot. Outside NPC bounds,
ordinary description validation continues normally. A legacy association without
the explicit header proof cannot override an overlapping NPC source.

## Cache and UI cleanup

On entry into verified/uncertain NPC bounds, capture clears any overlapping
cached player-shop routing rectangle. The UI retires overlapping player
observations, resets their table/row/offer recovery caches and advances the
viewport epoch once. It paints removal before subsequent card layout. A
same-position NPC cannot inherit an earlier player shop's blue frame proof.

The measured NPC list region may be fingerprinted to avoid unnecessary reader
work. This rectangle is strictly a capture optimization. It is never returned as
player-shop context and never supplies an asking amount or item identity.

After exclusion, NPC rows do not reach native-availability promotion, exact-ID
market demand, watched encounters or recent-item observation. Existing history
is not deleted just because a later NPC sells an item with the same name.
Independent ordinary inventory/equipment observations still use those paths.

## Work limits and regression checks

The detector rejects search regions over four million pixels, examines at most
128 button candidates, and bounds each candidate's vertical refinement to three
scaled pixels. The shared component helper stops after 65,536 colour runs.
Repeated known-window checks use small static samples; no new OCR model,
background scanning thread, API polling loop or individual-price call is added.

Core regression coverage is in `test_npc_shop.py`, `test_pixel_components.py`,
`test_shop_viewport_capture.py`, `test_capture_requests.py` and
`test_shop_ui_identity.py`. It includes all left/right tab combinations,
empty/populated transitions, detection from either column, unrelated orange
scenery, supported raster scales, unknown/recovery/closure, late replies and
independently proved inventory overlapping NPC bounds. Public player-shop
fixtures remain negative NPC-classification checks. Add-item-form tests cover
the shared component helper's other caller.

OBS replay is useful for sequence, visible failures and robustness checks.
Compression changes exact RGB values, so it does not replace lossless source
fixtures or live acceptance. Keep private recordings/screenshots under ignored
`evidence/`; do not package them. Run GUI/native-helper tests with fresh isolated
Xvfb, D-Bus and HOME/XDG state as described in [DEVELOPING.md](DEVELOPING.md).
Record results and physical-platform limitations in [VERIFICATION.md](../VERIFICATION.md).
