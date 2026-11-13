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

- [ ] Batch database lookups and move snapshot/availability preparation off the GUI thread.
- [ ] Coalesce overlay submissions, bound pending commands, invalidate changed regions only.
- [ ] Reduce frame copies and reuse per-frame analysis without weakening current-pixel proofs.
- [ ] Defer unnecessary OCR initialization; evaluate a shared engine within the vendor pin.
- [ ] Recover primary reader failures and avoid obsolete queued work.
- [ ] Correct late translation accounting and add recoverable worker states.
- [ ] Make incoming translation lazy with bounded idle retention; share frame analysis.
- [ ] Limit presentation work to changed data and active pages; retain smooth numeric motion.
- [ ] Clarify tracking coverage/state and validate pickup/session continuity.
- [ ] Share thumbnail storage/demand and perform disk/decode work off the GUI thread.
- [ ] Batch database navigation and precompute manual-search normalization.
- [ ] Preserve last-good catalogs offline and defer unused reader processes.
- [ ] Coordinate pause/shutdown and restore the intended display/position.
- [ ] Trim release debug data, pin dependencies, and bound/clarify update-cache storage.
- [ ] Extract orchestration/typed state and add bounded end-to-end diagnostics.
- [ ] Archive or purge verified unnecessary development storage after committed checkpoints.
- [ ] Update architecture, changelog, development instructions and verification results.

## Acceptance

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
