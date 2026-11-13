# Inventory pricing and Korean reading follow-up

Started 2026-11-13 from committed performance checkpoint `ded3177`, after the
user reported intermittent inventory overlays and weak Korean recognition/output.
Use existing approved sharing and saved fixtures; do not require another manual
demonstration or automate game input. Installer/publication work is out of scope.

## Confirmed annotation liveness regression

The performance pass suppressed identical state packets, but the annotation
canvas still required a command within five seconds. A healthy unchanged item
could therefore remain priced in the GUI while its canvas became hidden.
Identical authorized updates now send a tiny heartbeat at most once a second,
only with a ready helper and clear pipe. They do not resend rows, restart motion
or advance presentation IDs. No independent timer keeps stale authorization
alive if the GUI stops producing updates. The receiver can restore unchanged
rows after a temporary timeout; empty state remains hidden. Six seconds without
authorization still expires the canvas. An eight-second controlled regression
exercises sender/canvas together, including expiry, recovery and clear.

## Confirmed inventory routing defect

The scheduler previously disabled tooltip work whenever the pointer was inside
the cached shop rectangle. That rectangle cannot establish foreground ownership:
an inventory window can be in front of it. A new regression fails on the old
code because it sends `tooltip: false` for precisely that overlap.

The new `inventory_only` native request mode attempts independently source-bound
inventory recognition at those coordinates. It cannot publish a generic shop or
equipped-comparison title as that inventory item. Ordinary outside-shop inventory,
equipped and linked-item reading retains its normal path. A verified inventory
phase may publish early; it excludes a second shop partial phase on the same job.

An exact negative cache covers the native source-header search area, pointer and
image dimensions. It skips repeated absent-source work only while those pixels
remain unchanged. A source candidate with a delayed description is never cached
as absent. Changes outside the shop table but inside that header area invalidate
it. This cache supplies no identity or offer evidence. Resetting area clears it.

The native source selector, submitted/current header/cell/title proofs, exact
catalog identities, NPC exclusion and price-entry behavior remain required.

## Korean investigation

Recognition and translation are separate acceptance targets. Saved Korean images
are replayed through full-frame detection, native chat-history proposals and the
real OCR model; aggregate stage results contain no chat transcription. Existing
deduplication between bubbles/history must remain intact. Keep uncertain text
conservative rather than lowering global thresholds or guessing player names.

Verified history rows can recover a confident body even when the sender or
timestamp is unreadable. A closed timestamp fragment and a confident measured
colon establish the crop; the body keeps its normal 90 percent threshold, and
the sender stays empty. Generic text cannot use this route. Bubble fill now
tolerates independent channel rounding within the same 237–239 range.

The seven saved-image replays retain the known speech/chat/banner cases. The
original failing history screenshot is recognized before and after this change;
it is not claimed as a newly fixed case. Malformed-header and rounded-channel
cases have separate deterministic regressions. Additional generic proposals in
two static replays are not proof of correct new messages. Arbitrary live Korean
recognition remains a practical acceptance limit.

The synthetic translation check reproduced incorrect shortage wording, lost
party-member counts and Heal rendered as Hill. Beam sizes 1/2/3 were compared
using the same local model and two low-priority compute threads. On this small
unpaired corpus, median model-only latency was 90.0/100.8/112.1 ms. Two candidates
allow preserving a valid alternative instead of accepting the first contradictory
or incomplete output. These are not live OCR/compositor timings.

Implementation adds complete party/member/skill-request grammar and conservative
checks for explicit shortage/negation, alongside existing protected names and
numeric-unit checks. Freeform output remains approximate; these checks are not
a general proof of translation accuracy. Neither model bundle is replaced.

## Validation

- The routing test reproduces failure before the change.
- 75 native tests pass; the updated GNU release reader builds.
- Focused native/GUI checks cover comparison rejection, title delay, shop-only
  suppression and negative-cache invalidation. Fixture settings are explicit
  about enabling inventory reading; corrected focused checks pass 36 tests.
- All 26 saved inventory cases also match with a forced shop routing rectangle
  over the pointer, with no wrong-item annotations. This is a controlled routing
  stress test, not a claim that the synthetic rectangle is a verified live shop.
- Saved-screen Korean recognition replay and the broader suite are complete.
  Detailed private results live under
  `evidence/performance-2026-11-13/inventory-followup/` and are not packaged.

The final full suite passes **1,386 tests**, with three platform/opt-in skips,
in **198.024 s**. The focused helper/canvas, Korean and routing checks pass
149 tests; 75 Rust tests and 39 packaging-tool tests also pass. The GNU reader
was rebuilt for the preview. No installer was built, installed or published.

## User preview

The source preview at `7250e8c` is open as **Lupin — inventory and Korean preview**.
The original sharing helper retains its PID/start identity. Fresh frames, game
identification and a ready annotation helper were verified after handoff. Tracking
still starts stopped; incoming Korean models still load only on a requested scan.

For up to 30 minutes, this private preview overwrites one small diagnostic file
every two seconds with numerical state, recent timings and rejection counts.
It records neither messages/player names nor images and cannot drive game input.
This gives later inconsistent behavior an investigation trail without requiring
the user to prepare a recording. No live inventory-hover or Korean-message
demonstration was requested or automated during this follow-up. Actual remaining
recognition/placement misses therefore remain possible despite the passing
fixtures and the two confirmed overlay failure paths addressed here.
