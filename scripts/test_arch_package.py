"""Exercise pacman install/check/remove in a disposable root, never the host database."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from qa_common import (add_release_arguments, artifact_path, desktop_process_environment,
                       migration_packages, qa_entrypoint)

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_release_arguments(parser)
    parser.add_argument("--upgrade-from", type=Path, action="append", default=[],
                        help="Additional older Arch package in dist/; may be repeated")
    parser.add_argument("--in-fakeroot", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    package = artifact_path(ROOT / "dist", "arch", args.version)
    previous_packages = migration_packages(ROOT / "dist", "arch", args.version,
                                           required=args.require_migrations,
                                           upgrade_from=args.upgrade_from,
                                           report=print if args.in_fakeroot else lambda _: None)
    if not args.in_fakeroot:
        subprocess.run(["fakeroot", sys.executable, "-B", __file__, *sys.argv[1:], "--in-fakeroot"], check=True)
        return
    folder = ROOT / ".build-tools/test-roots/pacman"
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "var/lib/pacman").mkdir(parents=True)
    (folder / "cache").mkdir()
    (folder / "user-cache").mkdir()
    config = folder / "pacman.conf"
    config.write_text("[options]\nArchitecture = auto\nSigLevel = Never\n")
    marker = folder / "user-cache/preserve.txt"
    marker.write_text("Keep user data.\n")
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    log_path = evidence / "package-pacman.log"
    pacman = ["pacman", "--root", str(folder), "--dbpath", str(folder / "var/lib/pacman"),
              "--cachedir", str(folder / "cache"), "--logfile", str(folder / "pacman.log"),
              "--config", str(config), "--noconfirm", "--ask", "4"]
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONDONTWRITEBYTECODE": "1",
           "XDG_CACHE_HOME": str(folder / "user-cache")}
    with log_path.open("w") as log:
        def run(command, cwd=None):
            # D-Bus authenticates real user credentials; only pacman needs fake
            # ownership/UID metadata. GUI clients retain the private desktop.
            child_env = env if command[0] == "pacman" else desktop_process_environment(env)
            subprocess.run(command, cwd=cwd or ROOT, env=child_env, stdout=log, stderr=subprocess.STDOUT, check=True)
        # Only dependency checks are skipped: dependencies come from the host,
        # while all package/database writes are confined to this disposable root.
        for previous in previous_packages:
            run([*pacman, "-Udd", str(previous)])
        run([*pacman, "-Udd", str(package)])
        launcher = folder / "usr/bin/lupin"
        assert launcher.is_file() and not launcher.is_symlink(), "Lupin launcher missing"
        assert not (folder/'usr/bin/classic-price-lens').exists(), "Legacy launcher remains"
        desktop = folder / "usr/share/applications/io.github.zhuffman68.ClassicPriceLens.desktop"
        assert "Name=Lupin\n" in desktop.read_text(), "Application menu name is stale"
        run([str(launcher), "--version"])
        run([str(launcher), "--self-test"])
        app = folder / "opt/lupin"
        run([str(app / "runtime/bin/python3"), "-B", "-c",
             f"from price_lens import __version__; assert __version__ == {args.version!r}, __version__"], app)
        assert not (folder/'opt/classic-price-lens').exists(), "Legacy install folder remains"
        assert (app/'bin/lupin-market-fetch').is_file(), "Native market helper missing"
        assert not (app/'price_lens/snapshot_browser.py').exists(), "Retired browser integration remains"
        run([str(app / "runtime/bin/python3"), "-B", "-m", "unittest", "discover", "-s", "tests", "-q"], app)
        run([*pacman, "-Qkk", "lupin"])
        run([*pacman, "-Rdd", "lupin"])
        assert not launcher.exists(), "Uninstall left launcher behind"
        assert not app.exists(), "Uninstall left application files behind"
        assert marker.is_file(), "Uninstall removed user data"
    print("PASS: pacman install, launch, offline OCR/overlay, tests, file checks and removal", flush=True)
    print("Log:", log_path, flush=True)


if __name__ == "__main__":
    qa_entrypoint(main, __file__)
