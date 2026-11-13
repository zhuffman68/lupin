# Blue-description price stability — 2026-11-13

This is unreleased source work following the
[inventory and Korean follow-up](INVENTORY_AND_KOREAN_FOLLOWUP.md).
It changes independent description prices, not the ownership of player-shop
listing labels. No game hooks, input handling or game-process access are added.

## Current pixels own the reference

Previously, missing inventory metadata could clear a valid description before
the short OCR bridge ran. That bridge also expired after 400 ms. A temporary
recognition failure could therefore remove a price even though the same blue
window, source cell and title remained visible.

`TooltipReference.current` revalidates an already established identity against
the latest owned frame. A modern inventory reference requires its source cell,
header, primary title and native frames, including the comparison where present.
Missing or rejected new OCR metadata alone does not revoke that independently
current reference. A different OCR guess cannot replace its exact item ID while
the existing source and title pixels still match. Holding a reference does not
establish new availability, a new asking price or a new item identity.

Leaving the source cell, changing its contents, changing opaque title strokes,
closing the description or losing its structural proof clears the reference.
The normal capture-freshness and canvas-watchdog limits still apply. There is
no longer a 400 ms expiry for a description with current proof. The legacy
unproved short bridge remains bounded; an explicitly rejected legacy association
cannot restore a comparison item.

Ordinary generic descriptions retain their explicit current title/panel proof
while the pointer remains within the existing eight-pixel tolerance. A clicked
item-link window can retain that proof independently of cursor position, even
when the pointer moves onto another display. Neither case authorizes a changed
title or an absent blue panel. Generic descriptions still reacquire after larger
pointer movements; they do not inherit inventory-cell authority.

## Motion without identity OCR

For modern independently bound inventory proofs, pointer movement within the
same verified cell can propose a translation of the measured native panes.
The bounded candidates are the pointer delta and its two axis projections.
Both panes, source/header/cell evidence and the translated title must still pass
the existing current-pixel checks. An out-of-image cap, unknown source or changed
opaque title is rejected. The reference keeps its exact identity and changes
only measured geometry. Legacy unclassified popup guards cannot use this path.

Capture can reuse such a current source-bound proof after pointer movement
instead of treating every within-cell movement as a reason to repeat OCR.
Generic title/fingerprint shortcuts still require a stationary pointer.
Explicit retries and changed shop pixels retain their normal scheduling.

The annotation's pointer region is the actual proved inventory cell, transformed
into screen coordinates, rather than the entire game area. Scaled cells retain
their measured extent; generic rows keep the existing 64-pixel motion limit.
Reusing a label explicitly resets that source-bound mode when it becomes generic.

The label avoids the source and both native panes. During capture latency it
protects both their captured and predicted positions, rather than only the
prediction. This prevents Lupin's own card from covering the current title/frame
and creating a disappear/reacquire loop. Geometry-only updates do not rebuild
the Prices card layout or restart the label's identity animation.

## Shop ownership

Hovering a player-shop list continues to use its listing labels only. A source-
bound inventory window in front of a shop remains independent. An unbound
shop description cannot use the retention path to become an inventory price.
NPC-list exclusion, viewport epochs, exact amount checks and add-item-form
fading are unchanged. See [shop recognition](SHOP_RECOGNITION.md).

## Verification

Focused source checks pass 223 tests. Regressions exercise prolonged missing OCR
metadata through 300 simulated seconds, pointer-driven pane motion, changed
source/title pixels, pane closure, wrong fresh OCR guesses, linked-window
pointer departure, scaled source cells and protection of both pane positions.
The native-to-GUI regression verifies a real admitted inventory item survives
missing/rejected metadata without accepting a different item.

The complete source suite passes 1,400 tests with three skips in 177.775 s;
39 release-tool checks also pass. These checks use an isolated desktop and
private user/cache state, leaving the existing host sharing session untouched.

The private saved-image replay runs actual native IPC, frame/source admission,
GUI annotation construction and the real annotation canvas's placement and
painting. Market/media responses remain controlled. Its 26-case oracle includes
20 correct item cases and six deliberate rejections, with no wrong-item labels.
This is stronger than checking only annotation commands, but is not a live
Wayland compositor or physical Windows capture test.

Private logs and replay results remain under
`evidence/performance-2026-11-13/blue-description/`; they are excluded from
packages. Final full-suite results and preview state are recorded in
[VERIFICATION.md](../VERIFICATION.md). No installer or release publication is
part of this follow-up.
