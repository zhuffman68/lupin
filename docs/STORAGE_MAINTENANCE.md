# Development storage maintenance

## Completed 2026-11-13

Source was committed at `604a7fd` before any original data was removed.
The private archive is `/mnt/sda1/lupin-archive/2026-11-13-performance/`.

- **19.83 GiB across 326 paths** moved from the development workspace: older
  installer artifacts, historical evidence, obsolete release-client caches and
  dedicated retired market/browser helper profiles.
- Every copied regular file was SHA-256 checked before its NVMe original was
  removed. `manifest.json` records original/archive paths, sizes, hashes and
  completion status. Old paths are symlinks to the archive.
- **885.2 MiB** of cached 1.0.3/1.0.4 update packages/bases were purged after
  checking embedded package metadata against the installed 1.0.5 version.
  Hard links are counted once. Signed update metadata was retained.
- **24.3 MiB** of the retired, app-owned market-browser cache was purged. This
  was not a personal browser profile. `purged-caches.json` records the decision.

The installed `/opt/lupin`, current 1.0.5 installers, model bundles, virtualenv,
active evidence, reader build output and useful compiler/Wine toolchains remain
on NVMe. Settings, market/session databases, capture helpers, original recordings,
signing keys and unrelated projects were not moved or purged. The workspace
dropped from about 38 GiB to about 20 GiB before further QA outputs; these totals
are approximate and change as builds run.

## Working with the archive

Keep `/mnt/sda1` mounted when opening historical paths. Archived scripts that
derive their repository root from `__file__.resolve()` have compatibility links
to the current source/tools. These links are recorded in `live-source-links.json`:
they are **not a frozen copy of an old checkout**. No `.git` link was added.
Use Git commits for historical source. Archive permissions are private.
Scripts that invoke Git must use the current checkout explicitly; the archive
is not itself a Git repository.

To restore one entry, find its `source` and `archive` in `manifest.json`. Copy
the archive to a temporary sibling of the original path (preserving links and
metadata), verify its regular-file hashes against that entry, remove only the
verified original symlink, then rename the temporary copy into place. Never
restore over a directory containing newer work. The archived copy can remain as
a backup. Relative symlinks copied during migration were rebased to preserve
their original destinations; inspect these links when making a portable copy.

The purged obsolete caches are reproducible; their old installers can be fetched
again if needed. They are not part of the archival restore manifest.

## Future maintenance

Prefer archiving historical evidence over deleting it. Inventory and commit
source first, verify copies before removing originals, retain the current useful
build, and never move a running runtime. Do not delete model/runtime dependencies
merely because they are large. Linux debug symbols are now stored separately in
`.build-tools/debug-symbols/linux/`, indexed by the original file SHA-256; the
packaged runtime report records the symbols removed and their byte savings.

The normal Update settings page reports app-owned installer-cache usage and
offers a safe Clear action. It does not manage development archives.
