"""Shared artifact selection and private desktop setup for package QA only."""
import os
import errno
import hmac
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from price_lens import __version__

ARTIFACTS = {
    "windows": "Lupin-{version}-Windows-x64-Setup.exe",
    "arch": "lupin-{version}-1-x86_64.pkg.tar.zst",
    "debian": "lupin_{version}-1_amd64.deb",
}
MIGRATION_VERSIONS = ("0.8.0", "0.9.0", "0.10.0")
PRIVATE_ROOT = "LUPIN_QA_PRIVATE_ROOT"
HOST_HOME = "LUPIN_QA_HOST_HOME"
SOFTWARE_ENV = {
    "QT_QPA_PLATFORM": "offscreen", "GDK_BACKEND": "x11",
    "LIBGL_ALWAYS_SOFTWARE": "1", "QT_OPENGL": "software",
    "QT_QUICK_BACKEND": "software", "PYTHONDONTWRITEBYTECODE": "1",
    "OMP_NUM_THREADS": "2", "RAYON_NUM_THREADS": "2",
    "RTEN_NUM_THREADS": "1", "GIO_USE_VFS": "local", "GVFS_DISABLE_FUSE": "1",
    "NO_AT_BRIDGE": "1", "GTK_USE_PORTAL": "0",
}
DESKTOP_ENV = (
    "DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET",
    "DBUS_SESSION_BUS_ADDRESS", "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE",
)
QA_MARKER = ".lupin-private-qa"


def version_parts(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", value):
        raise ValueError("Expected a numeric release version such as 1.0.2")
    return tuple(map(int, value.split(".")))


def add_release_arguments(parser):
    parser.add_argument("--version", default=__version__, help="Exact release to test (default: current source version)")
    parser.add_argument("--require-migrations", action="store_true", help="Fail before transactions if a historical migration baseline is missing")


def artifact_path(dist, platform, version):
    version_parts(version)
    path = Path(dist) / ARTIFACTS[platform].format(version=version)
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError("Required QA artifact missing: " + str(path))
    return path


def migration_packages(dist, platform, version, *, required=False, upgrade_from=(), report=print):
    current = version_parts(version)
    dist = Path(dist).resolve()
    found, missing = [], []
    for previous in MIGRATION_VERSIONS:
        if version_parts(previous) >= current:
            report(f"SKIP migration {previous}: not older than {version}")
            continue
        path = dist / ARTIFACTS[platform].format(version=previous)
        if path.is_file() and path.stat().st_size:
            found.append(path)
            report("Using migration baseline: " + path.name)
        else:
            missing.append(path)
            report("SKIP migration baseline missing: " + path.name)
    pattern = re.escape(ARTIFACTS[platform]).replace(re.escape("{version}"), r"(?P<version>[0-9]+\.[0-9]+\.[0-9]+)")
    for value in upgrade_from:
        path = Path(value).resolve()
        match = re.fullmatch(pattern, path.name)
        if not match:
            raise ValueError("Upgrade baseline must be a " + platform + " package: " + path.name)
        if version_parts(match['version']) >= current:
            raise ValueError("Upgrade baseline must be older than " + version + ": " + path.name)
        # DEB QA exposes this one directory read-only inside its OCI root.
        if path.parent != dist:
            raise ValueError("Keep explicit QA upgrade packages in " + str(dist))
        if not path.is_file() or not path.stat().st_size:
            raise FileNotFoundError("Explicit upgrade baseline missing: " + str(path))
        found.append(path)
        report("Using explicit upgrade baseline: " + path.name)
    if required and missing:
        raise FileNotFoundError("Required migration baselines missing: " + ", ".join(path.name for path in missing))
    return sorted(set(found), key=lambda path: version_parts(re.fullmatch(pattern, path.name)['version']))


def migration_installer(path, *, required=False, report=print):
    if path is None:
        if required:
            raise ValueError("--require-migrations needs --upgrade-from for Windows QA")
        report("SKIP historical Windows migration: --upgrade-from was not supplied")
        return None
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError("Windows migration baseline missing: " + str(path))
    report("Using migration baseline: " + path.name)
    return path


def wine_test_prefix(value, environ=None):
    env = os.environ if environ is None else environ
    prefix = Path(value).resolve()
    homes = {Path.home(), Path(env.get(HOST_HOME, str(Path.home())))}
    if prefix in {(home / ".wine").resolve() for home in homes}:
        raise ValueError("Use an isolated test prefix, never the default/game prefix")
    # Existing prefixes can keep absolute Wine known-folder links to the host
    # home even when this run has a private HOME. Inno writes shortcuts directly
    # through Desktop; disabling winemenubuilder does not prevent that write.
    allowed = [prefix]
    if env.get(PRIVATE_ROOT):
        allowed.append(Path(env[PRIVATE_ROOT]).resolve())
    users = prefix / "drive_c/users"
    if not users.resolve().is_relative_to(prefix):
        raise ValueError("Wine QA users directory escapes the test prefix: " + str(users))
    if users.is_dir():
        for profile in users.iterdir():
            if not profile.resolve().is_relative_to(prefix):
                raise ValueError("Wine QA user profile escapes the test prefix: " + str(profile))
            for name in ("Desktop", "Documents", "Downloads", "Music", "Pictures", "Videos",
                         "AppData", "AppData/Local", "AppData/LocalLow", "AppData/Roaming",
                         "Application Data", "Local Settings", "My Documents"):
                folder = profile / name
                if (folder.exists() or folder.is_symlink()) and not any(
                        folder.resolve().is_relative_to(root) for root in allowed):
                    raise ValueError("Wine QA known folder escapes the private desktop: " + str(folder))
    return prefix


def private_environment(folder, environ=None):
    folder = Path(folder)
    env = dict(os.environ if environ is None else environ)
    env[HOST_HOME] = env.get("HOME", str(Path.home()))
    for key in DESKTOP_ENV:
        env.pop(key, None)
    for key, relative in {
        "HOME": "home", "XDG_CONFIG_HOME": "config", "XDG_CACHE_HOME": "cache",
        "XDG_DATA_HOME": "data", "XDG_STATE_HOME": "state", "XDG_RUNTIME_DIR": "run",
        "TMPDIR": "tmp",
    }.items():
        path = folder / relative
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        env[key] = str(path)
    env.update(SOFTWARE_ENV)
    env["XDG_SESSION_TYPE"] = "x11"
    env[PRIVATE_ROOT] = str(folder)
    return env


def private_desktop_active(environ=None):
    env = os.environ if environ is None else environ
    try:
        root = Path(env[PRIVATE_ROOT]).resolve(strict=True)
        authority = Path(env["XAUTHORITY"]).resolve(strict=True)
        return (authority.is_relative_to(root / "tmp") and bool(env.get("DISPLAY"))
                and bool(env.get("DBUS_SESSION_BUS_ADDRESS"))
                and not env.get("WAYLAND_DISPLAY") and not env.get("WAYLAND_SOCKET")
                and all(env.get(key) == value for key, value in SOFTWARE_ENV.items())
                and all(Path(env[key]).resolve().is_relative_to(root) for key in
                        ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR")))
    except (KeyError, OSError, ValueError):
        return False


def desktop_process_environment(environ):
    """Keep fakeroot metadata emulation on pacman, not GUI/D-Bus clients."""
    env = dict(environ)
    for key in ("FAKEROOTKEY", "FAKED_MODE", "FAKEROOT_FD_BASE", "FAKEROOTDONTTRYCHOWN"):
        env.pop(key, None)
    preload = [value for value in re.split(r"[:\s]+", env.get("LD_PRELOAD", ""))
               if value and "libfakeroot" not in Path(value).name]
    if preload:
        env["LD_PRELOAD"] = ":".join(preload)
    else:
        env.pop("LD_PRELOAD", None)
    return env


def create_private_root():
    folder = Path(tempfile.mkdtemp(prefix="lupin-qa-"))
    token = secrets.token_hex(16)
    descriptor = os.open(folder / QA_MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(token)
    return folder, token


def _verify_cleanup_root(folder, token):
    folder = Path(os.path.abspath(folder))
    if not isinstance(token, str) or not re.fullmatch("[0-9a-f]{32}", token):
        raise ValueError("Invalid private QA ownership token")
    info = folder.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or folder.parent != Path(tempfile.gettempdir()).resolve()
            or not folder.name.startswith("lupin-") or folder.resolve() != folder):
        raise ValueError("Not an owned private QA root")
    marker = folder / QA_MARKER
    descriptor = os.open(marker, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "r") as stream:
        marker_info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(marker_info.st_mode) or marker_info.st_uid != os.getuid()
                or marker_info.st_size != 32 or not re.fullmatch("[0-9a-f]{32}", token)
                or not hmac.compare_digest(stream.read(33), token)):
            raise ValueError("Private QA ownership marker does not match")
    return folder


def _private_mounts(folder):
    result = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        before, separator, after = line.partition(" - ")
        fields, filesystem = before.split(), after.split()
        if not separator or len(fields) < 5 or len(filesystem) < 2:
            continue
        target = Path(re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[4]))
        if target == folder or target.is_relative_to(folder):
            result.append((target, filesystem[0], filesystem[1]))
    return result


def _allowed_qa_mount(folder, target, filesystem, source):
    if (target.relative_to(folder).as_posix() not in ("run/doc", "run/gvfs", "runtime/doc", "runtime/gvfs")
            or (filesystem, source) not in (("fuse.portal", "portal"), ("fuse.gvfsd-fuse", "gvfsd-fuse"))):
        return False
    parent = target.parent
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or parent.resolve() != parent:
        return False
    try:
        return not stat.S_ISLNK(target.lstat().st_mode)
    except OSError as error:
        # An exited private portal can leave its FUSE root disconnected.
        return error.errno == errno.ENOTCONN


def cleanup_private_root(folder, token, *, child_status=None, report=None):
    """Detach only known private FUSE mounts; never replace the child result."""
    if report is None:
        report = lambda message: print(message, file=sys.stderr, flush=True)
    try:
        folder = _verify_cleanup_root(folder, token)
        mounts = _private_mounts(folder)
        for target, filesystem, source in mounts:
            if not _allowed_qa_mount(folder, target, filesystem, source):
                raise ValueError("Unsupported mount retained: " + str(target))
        for target, _, _ in sorted(mounts, key=lambda entry: len(entry[0].parts), reverse=True):
            command = shutil.which("fusermount3") or shutil.which("fusermount")
            if not command:
                raise RuntimeError("Private FUSE cleanup requires fusermount3 or fusermount")
            result = subprocess.run([command, "-u", "-z", "--", str(target)],
                                    capture_output=True, text=True, timeout=10, check=False)
            if result.returncode:
                raise RuntimeError("Could not detach private FUSE mount: " + str(target))
            report("QA cleanup: detached " + str(target))
        if _private_mounts(folder):
            raise RuntimeError("Private mounts remain; temporary directory retained")
        shutil.rmtree(folder)
        return True
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report(f"QA CLEANUP FAILED (child exit {child_status} unchanged): {error}; retained {folder}")
        return False


def qa_entrypoint(main, script):
    """Re-exec Linux-host GUI QA with its own X server, bus, home and XDG paths."""
    if not sys.platform.startswith("linux") or "--help" in sys.argv or "-h" in sys.argv:
        return main()
    if PRIVATE_ROOT in os.environ:
        if not private_desktop_active():
            raise RuntimeError("Invalid private QA desktop; refusing to use the host desktop")
        return main()
    for command in ("xvfb-run", "dbus-run-session"):
        if not shutil.which(command):
            raise FileNotFoundError("Package QA requires " + command + "; nothing was installed or tested")
    folder, token = create_private_root()
    status = None
    try:
        env = private_environment(folder)
        command = ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24 -nolisten tcp",
                   "dbus-run-session", "--", sys.executable, "-B", str(Path(script).resolve()), *sys.argv[1:]]
        result = subprocess.run(command, env=env, check=False)
        status = result.returncode
    finally:
        cleanup_private_root(folder, token, child_status=status)
    raise SystemExit(result.returncode)


def guest_desktop_command(command):
    """The OCI root has its own /tmp; create all desktop state inside that root."""
    setup = """set -eu
task_qa_root=$(mktemp -d /tmp/lupin-qa.XXXXXX)
trap 'rm -rf -- "$task_qa_root"' EXIT
mkdir -m 700 "$task_qa_root/home" "$task_qa_root/config" "$task_qa_root/cache" "$task_qa_root/data" "$task_qa_root/state" "$task_qa_root/run" "$task_qa_root/tmp"
export HOME="$task_qa_root/home" XDG_CONFIG_HOME="$task_qa_root/config" XDG_CACHE_HOME="$task_qa_root/cache" XDG_DATA_HOME="$task_qa_root/data" XDG_STATE_HOME="$task_qa_root/state" XDG_RUNTIME_DIR="$task_qa_root/run" TMPDIR="$task_qa_root/tmp"
unset DISPLAY XAUTHORITY WAYLAND_DISPLAY WAYLAND_SOCKET DBUS_SESSION_BUS_ADDRESS DBUS_STARTER_ADDRESS DBUS_STARTER_BUS_TYPE
xvfb-run -a -s '-screen 0 1920x1080x24 -nolisten tcp' dbus-run-session -- env """
    assignments = [key + "=" + value for key, value in SOFTWARE_ENV.items()]
    # Values are fixed above; caller arguments travel separately through "$@".
    return ["sh", "-c", setup + " ".join(assignments) + ' "$@"\n', "lupin-qa", *map(str, command)]


def windows_python(runtime, *, module=None, arguments=(), code=None):
    """Set offscreen inside Windows Python before any QApplication can exist."""
    if (module is None) == (code is None):
        raise ValueError("Choose a Python module or inline code")
    bootstrap = "import os,runpy,sys; os.environ['QT_QPA_PLATFORM']='offscreen'; "
    if module is not None:
        bootstrap += f"sys.argv={[module, *arguments]!r}; runpy.run_module({module!r},run_name='__main__',alter_sys=True)"
    else:
        bootstrap += code
    return [str(runtime), "-B", "-c", bootstrap]
