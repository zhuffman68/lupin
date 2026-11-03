# Developing Lupin

Start with the [README](../README.md) for installation and the
[architecture](../ARCHITECTURE.md) for component boundaries. Read `AGENTS.md`
before changing the source. Run the commands below from a repository checkout;
installing a release does not require a compiler or Python installation.

## Source setup

Use Python 3.11 or newer supported by `requirements.txt`, Rust 1.90 or newer,
Git and the platform's C/C++ build tools. Release toolchain versions and runtime
hashes are pinned in `packaging/`; release builds use those manifests rather
than whichever versions happen to be installed.

On Linux, install the WebKitGTK 4.1/GTK 3 development headers and `pkg-config`.
Debian/Ubuntu packages are `build-essential pkg-config libwebkit2gtk-4.1-dev`;
Arch/Manjaro uses `base-devel pkgconf webkit2gtk-4.1 gtk3`.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./setup.sh
./run.sh
```

`setup.sh` obtains and checks Minerva's pinned revision, builds the screen reader
with two Cargo jobs, and builds the native market helper. It does not modify the
game or the installed Lupin package. Keep Minerva pinned at
`7e1aa7d418fb255bd66eb4dce848fc9eb305cd81`.

On Windows, use an x64 Visual Studio Developer PowerShell:

```powershell
.\setup-windows.ps1
.\run-windows.bat
```

The setup script creates `.venv`, installs the Python dependencies, and builds
the reader and native WebView2 market helper. Fetching prices also needs the
production Microsoft WebView2 runtime; release Setup prepares it when missing.

For local Korean reading and writing, prepare the verified model bundles once:

```sh
python scripts/prepare_chat_models.py
```

Use `.venv\Scripts\python.exe` for that command on Windows. Model downloads and
converted weights stay in ignored `models/` and `.build-tools/` directories.
`prepare_compose_model.py` prepares or verifies only the English-to-Korean bundle.

## Tests

Tests may drive Lupin's own UI, fixtures and an isolated desktop. Never send input
to the game or interrupt an existing screen-sharing session. On a Linux desktop,
isolate GUI/native-helper checks with Xvfb, a private D-Bus session and fresh
HOME/XDG directories, not just Qt's offscreen plugin. The existing QA helpers
create and safely clean up that environment:

```sh
nice -n 15 .venv/bin/python -B - <<'PY'
import subprocess, sys
from scripts.qa_common import create_private_root, private_environment, cleanup_private_root

folder, token = create_private_root()
status = None
try:
    result = subprocess.run([
        "xvfb-run", "-a", "-s", "-screen 0 1920x1080x24 -nolisten tcp",
        "dbus-run-session", "--", sys.executable, "-B", "-m", "unittest",
        "discover", "-s", "tests", "-q",
    ], env=private_environment(folder), check=False)
    status = result.returncode
finally:
    cleanup_private_root(folder, token, child_status=status)
raise SystemExit(status)
PY
```

Use `-p test_npc_shop.py` with unittest discovery for a focused recognition run.
The focused tracking/performance tests include `test_tracking_delivery.py`
(capture admission through the panel and arrival ledger), `test_reader_metrics.py`,
`test_shop_reader_delivery.py` (real native cache/partial protocol),
`test_capture_requests.py`, and `test_shop_dialog.py`. Run them in the same private
desktop. The local reader must be rebuilt when its protocol changes; this is
distinct from building installers. Performance/acceptance notes live in
[TRACKING_AND_READER_PERFORMANCE.md](TRACKING_AND_READER_PERFORMANCE.md).

For a local source diagnostic, set `LUPIN_READER_DIAGNOSTICS` to a JSON path in an
existing writable directory before launching Lupin. Every two seconds it writes
an atomic private snapshot (0600 on POSIX) of bounded counters and numeric stage timings, including
pickup delivery/rejection reasons and native shop cache hits. No OCR text,
character names, chat or screenshots are included. Without this variable normal
runs perform no diagnostics file I/O. Counter names describe processing stages:
`pickup.accepted` counts admitted jobs, not individual pickup arrivals;
`pickup.credited` counts batches that increased the ledger. Clear the variable
after investigating. Never publish private captures or evidence scripts.

Then run release-tool tests and the native compile check as appropriate:

```sh
python -B -m unittest discover -s scripts/tests -q
cargo check --locked --manifest-path reader/Cargo.toml -j 2
```

The installed Windows `selftest-windows.bat` runs `python -m price_lens
--self-test`: bundled OCR, local overlay IPC and a synthetic media frame without
screen capture. Package tests, Wine checks and fixture tests do not establish
physical Windows capture, shortcut or fullscreen acceptance. Record those limits
in [VERIFICATION.md](../VERIFICATION.md).

For shop and hover changes, follow [Shop recognition and price ownership](SHOP_RECOGNITION.md).
It documents the player/NPC boundary, submitted/current-frame filtering,
present/unknown/absent NPC states, independent inventory proofs, work limits and
the relevant regression suites. Both NPC columns and every All/Buy Back and
inventory-tab transition need coverage; an empty-list fixture with All selected
does not establish that changing tabs works. OBS clips supply sequence evidence;
use lossless/generated pixels for exact proof checks. Historical verification
notes describe the behavior of their dated versions, not current requirements.

## Build and release tools

| Tools | Purpose |
| --- | --- |
| `download_runtime.py`, `build_market_helpers.py` | Obtain pinned inputs and build the platform market helper. |
| `prepare_chat_models.py`, `prepare_compose_model.py` | Verify and prepare both local translation directions. |
| `package_common.py`, `package_linux.py`, `package_windows.py`, `trim_runtime.py` | Stage the application, notices and verified models; trim unused runtime files. |
| `build_linux_packages.py`, `build_windows_installer.py` | Produce Arch, DEB and Windows Setup packages. |
| `test_arch_package.py`, `test_linux_packages.py`, `test_windows_installer.py` | Check install, upgrade, uninstall and installed offline behavior in isolated environments. |
| `qa_common.py`, `windows_stage.py` | Select exact QA artifacts, isolate test desktops, report migration coverage and reject incomplete Windows release stages. |
| `release_checksums.py`, `release_updates.py` | Validate the three release artifacts and prepare signed GitHub update metadata. |
| `export_icons.py` | Export platform icons from the approved native Lupin master. |

All tools in the table live under `scripts/`. Follow the
[packaging guide](https://github.com/zhuffman68/lupin/blob/main/packaging/README.md)
for pinned toolchains and complete platform commands, and
[update documentation](UPDATES.md) for signing and installation behavior.
Windows portable archives are retired; normal releases contain only Windows
Setup, Arch/Manjaro and Debian/Ubuntu packages.

Package QA defaults to the exact current source version; `--version X.Y.Z`
selects another exact release. It never chooses a file by modification time.
Missing historical migration packages print `SKIP`; use `--require-migrations`
for release acceptance. Windows additionally needs `--upgrade-from PATH` in that
mode. These are package transactions, separate from the source-only tests above.
Arch/DEB accept repeated `--upgrade-from dist/PACKAGE` arguments for an available
recent baseline, such as 1.0.1. Each explicit package must match the platform and
be older than the selected release; a missing explicit baseline always fails.
The old 0.8/0.9/0.10 baseline results remain separately visible as passed/skipped.
Linux-host Arch and Wine QA create a private Xvfb display, D-Bus session, home and
XDG directories automatically, with Wayland unset and software rendering. They
require `xvfb-run` and `dbus-run-session` but never install host tools. DEB QA
creates the same isolation inside its disposable distribution root. Wine's Python
entry points also set Qt offscreen inside Windows Python before importing UI code.

Keep signing keys, credentials, user databases, caches, drafts, recordings and
private test evidence out of Git and release stages. Stable internal
settings/socket/desktop/portal IDs remain necessary for upgrades. Building or
passing tests does not authorize publication or changes to a running installation.

macOS is not a validated release target. Linux-specific XWayland/KDE adapters and
Windows-specific runtime preparation need separate platform alternatives before
claiming support.
