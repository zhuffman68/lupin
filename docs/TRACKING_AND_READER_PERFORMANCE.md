# Pickup delivery and shop-reader performance

This document records the current implementation work, its evidence and its
remaining acceptance checks. It supplements [ARCHITECTURE.md](../ARCHITECTURE.md)
and [SHOP_RECOGNITION.md](SHOP_RECOGNITION.md); the latter remains authoritative
for shop, inventory and NPC source proofs.

## Baseline — 2026-11-02

A 30-second authorized screen observation showed the live meso total unchanged
at +1,581 while new literal pickup messages appeared. EXP and the elapsed clock
continued updating. Replaying all 145 saved frames through the native pickup
reader and an isolated arrival ledger produced readable results throughout,
without continuity gaps. That replay omitted the live admission and identity
checks and had no preceding session ledger: its sum is not an independently
annotated ground-truth total.

Saved shop-page requests took approximately 0.5–1.36 seconds in the native
reader alone. These timings exclude capture, GUI delivery, source validation and
painting. Cache warmth, frame content and other host work affect the numbers.
Market references already come from the shared local full-market snapshot.

## Implementation sequence

1. Add bounded, text-free admission and timing diagnostics. Reproduce pickup
   delivery through capture and the tracking panel, including EXP confirmation.
2. Give pickups a dedicated admission path using current game/character proofs,
   independent of numerical EXP candidates. Distinguish worker deadlines, frame
   age and arrival continuity. Preserve pause, source-change and double-count
   protections and make waiting states describe the actual cause.
3. Reduce duplicate shop OCR and cache independently verified components. Keep
   name/amount proofs separate and invalidate previous-page authority on scroll.
4. Schedule newest shop work promptly without starving EXP. Retain bounded
   workers and overlay-first drawing. Consider progressive native replies only
   if the simpler measured changes do not meet the target.
5. Replay regressions, run isolated integration tests, measure before/after and
   update architecture, verification and changelog documentation. Remove replaced
   paths rather than leaving parallel legacy behavior.

## Acceptance

- Fully observed, annotated pickup arrivals count exactly once, including equal
  amounts in different messages. Existing messages seed Start/Resume safely.
- EXP numerical uncertainty does not suppress independently verified pickups.
- True character/capture changes, pause and covered logs reject unsafe arrivals.
- Real coverage loss retains totals and establishes a fresh safe baseline.
- Gains/rates keep their two-second presentation cadence; clocks tick each second.
- Opening/scrolling a shop rejects old-page replies immediately. Hovering keeps
  loaded current-page labels. Inventory/equipped pricing and NPC exclusion remain
  independent.
- Aim for first clear-shop labels in 300–500 ms and typical completion under one
  second; report cold/warm timings separately rather than claiming this universally.
- Work queues, diagnostics and caches remain bounded; stationary shops do little
  repeated OCR. No individual market-price HTTP calls are introduced.

## Verification log

- Baseline evidence is private under `evidence/meso-observation-20261102-194132`
  and `evidence/meso-price-analysis-20261102`. No captures enter packages or Git.
- Implementation and automated validation are complete; live acceptance remains
  pending. No release package has been built or published for this work.
- First implementation checkpoint: 93 focused Python tests pass, covering the
  tracking panel, visual identity, native-worker transport, capture admission,
  pickup arrival matching and bounded diagnostics. Numerical EXP confirmation
  no longer blocks independently verified pickup jobs. A missing name proof
  holds that job; a positively different proof still holds the session.
- Waiting states now distinguish a covered log, delayed frame, restarting/timed
  out worker and unreadable character proof. A stale reading alone no longer
  claims that the log is hidden. Metrics remain in memory, with at most 64 event
  codes and 240 numeric timing samples shared by capture and the tracking panel.
- Native stage timing isolated two substantial costs: ordinary shop reads can
  repeatedly search a hovered description, and component recovery can recognize
  already-read digits twice more. The next checkpoint measures targeted removal
  of those costs. Scroll-tier picture protection and clipped-title refinement
  retain the optional native hover pass.
- Shop implementation now retains one complete page with byte-exact table,
  icon and rim pixels, keyed by capture generation and viewport epoch. Cache
  hits receive the current timestamp, omit stale hover titles and veto a tier
  beneath the current cursor. Clipped names still take the fresh hover path.
  Cache hits do not bypass Python's independent latest-frame source validation.
- Missing-line recovery can send one opt-in partial shop reply containing
  independently complete ordinary rows before the final result. Only shop-only
  requests use it; inventory requests and complete/cache-hit pages stay atomic.
  Both replies share the same immutable request, epoch and original timeout.
- Added the reported add-item-form regression to this pass. Known forms now
  treat the bounded current cursor footprint as unknown control pixels while
  requiring independent current native structure. Cursor masks cannot establish
  a new form. Only overlapping shop labels fade; live confirmation is pending
  because the user cannot currently reproduce the issue.

## Measured checkpoint

The complete Python suite passes **1,285 tests, three skips, 161.818 s**. All
**69 native image/proof/cache unit tests** pass. Focused real-native delivery,
component recovery and tracking-admission checks pass 32 tests. The form/UI/
annotation run passes 165 tests, including 30 cursor positions over controls at
five scales and the existing overlap-only, interruptible fade and closure tests.

The lossless 145-frame recording now also passes capture-result admission and
the tracking panel while an EXP numerical candidate deliberately remains
unconfirmed. Every job has a matching same-frame name proof; the ledger matches
the direct replay's 281 with zero gaps. This is **not** an annotated claim that
281 is the user's full correct income: the replay starts without the preceding
27-minute ledger and supplies verified game readiness in its harness. The
committed anonymized burst fixture separately establishes an exact known total,
including repeated amounts and duplicate delivery through production admission.

Native-only timing on the saved OBS shop frames, with bounded threads and other
host work present:

| Case | First useful reply | Final reply | Priced rows |
| --- | ---: | ---: | ---: |
| Cold reader/opening | 1,203 ms | 1,203 ms | 6 |
| Known unchanged full frame | 39 ms | 39 ms | 6 |
| Same page with recovery disabled | 21 ms | 21 ms | 6 |
| New page | 582 ms | 582 ms | 6 |
| Same page through a cropped request | 3 ms | 3 ms | 6 |
| Partially covered page | 384 ms | 615 ms | 3 initially; 4 after recovery |

The first measured before/after warm request dropped from 787 ms to 77 ms before
adding the whole-page cache. A new exposed page with component proofs dropped
from 1,495 ms to 755 ms. These individual measurements vary with cache warmth and
host load; they are not end-to-end compositor timings or a percentile benchmark.
Cold first recognition still exceeds the 300–500 ms goal. Current results do not
justify weakening identity/amount guards to force that target.

Remaining acceptance is an uninterrupted live training comparison and the user's
reported add-item case. Physical Windows gameplay/capture has not been retested
in this pass. The native binary was rebuilt locally for fixture testing;
installers, the installed package and publication remain untouched.

The updated **Lupin — tracking and shop preview** is running (PID 1925988).
SIGUSR1 handoff retained helper 846570 and its original start tick 5282269.
Settings were backed up before reload, the preview log is empty, and tracking
starts stopped for an explicit new session. An authorized read-only frame shows
six populated player-shop labels; live diagnostics record cache hits and recent
capture-to-reader delivery around 93–160 ms. This is a smoke check, not live
acceptance of pickup totals or the reported add-item edge case.
