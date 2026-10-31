"""Release preflights and QA isolation without builds or package transactions."""
import contextlib
import io
import json
import os
from pathlib import Path
import struct
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import build_windows_installer
import package_windows
import qa_common
import windows_stage


def reader_bytes(machine=0x8664, magic=0x20B, characteristics=0x0002):
    header = bytearray(64)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 60, 64)
    pe = bytearray(26)
    pe[:4] = b"PE\0\0"
    struct.pack_into("<H", pe, 4, machine)
    struct.pack_into("<H", pe, 20, 2)
    struct.pack_into("<H", pe, 22, characteristics)
    struct.pack_into("<H", pe, 24, magic)
    return bytes(header + pe)


class WindowsStageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def complete_stage(self):
        stage = self.root / "stage"
        for name in windows_stage.REQUIRED_STAGE_FILES:
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"Fixture resource")
        (stage / "bin/lupin-screen-reader.exe").write_bytes(reader_bytes())
        (stage / "runtime-trim.json").write_text(json.dumps(dict(platform="windows", removed=[])))
        return stage

    def test_windows_x64_reader_and_required_stage_resources_are_accepted(self):
        windows_stage.validate_windows_stage(self.complete_stage())

    def test_missing_reader_does_not_replace_an_existing_stage(self):
        stage = self.root / "stage"
        stage.mkdir()
        sentinel = stage / "keep.txt"
        sentinel.write_text("Existing reviewable stage")
        with patch.object(package_windows, "OUT", stage), patch.object(package_windows, "READER", self.root / "missing.exe"):
            with self.assertRaisesRegex(FileNotFoundError, "Compiled Windows x64 reader"):
                package_windows.main()
        self.assertEqual(sentinel.read_text(), "Existing reviewable stage")

    def test_linux_or_32_bit_reader_is_rejected_before_staging(self):
        reader = self.root / "reader.exe"
        for data in (b"\x7fELF" + bytes(100), reader_bytes(machine=0x14C), reader_bytes(magic=0x10B), reader_bytes(characteristics=0x2002)):
            with self.subTest(data=data[:4]):
                reader.write_bytes(data)
                with patch.object(package_windows, "READER", reader), patch.object(package_windows.shutil, "rmtree") as remove:
                    with self.assertRaises(ValueError):
                        package_windows.main()
                    remove.assert_not_called()

    def test_each_required_resource_is_checked(self):
        stage = self.complete_stage()
        for name in windows_stage.REQUIRED_STAGE_FILES:
            with self.subTest(name=name):
                path = stage / name
                data = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(FileNotFoundError, "required file missing"):
                    windows_stage.validate_windows_stage(stage)
                path.write_bytes(data)

    def test_old_shipped_reader_name_cannot_satisfy_the_stage(self):
        stage = self.complete_stage()
        (stage / "bin/lupin-screen-reader.exe").rename(stage / "bin/classic-screen-reader.exe")
        with self.assertRaisesRegex(FileNotFoundError, "lupin-screen-reader.exe"):
            windows_stage.validate_windows_stage(stage)

    def test_linux_runtime_report_cannot_satisfy_the_windows_stage(self):
        stage = self.complete_stage()
        (stage / "runtime-trim.json").write_text(json.dumps(dict(platform="linux", removed=[])))
        with self.assertRaisesRegex(ValueError, "Windows runtime-trim"):
            windows_stage.validate_windows_stage(stage)

    def test_installer_never_invokes_compiler_or_writes_cleanup_for_incomplete_stage(self):
        compiler = self.root / "ISCC.exe"
        compiler.write_bytes(b"Compiler fixture; never execute")
        stage = self.complete_stage()
        destination = self.root / "dist/Lupin-Windows-x64"
        destination.parent.mkdir()
        stage.rename(destination)
        (destination / "bin/lupin-screen-reader.exe").unlink()
        with patch.object(build_windows_installer, "ROOT", self.root), patch.object(sys, "argv", ["build_windows_installer.py", "--iscc", str(compiler)]):
            with patch.object(build_windows_installer.subprocess, "run") as run, patch.object(build_windows_installer.subprocess, "check_output") as output:
                with self.assertRaisesRegex(FileNotFoundError, "lupin-screen-reader.exe"):
                    build_windows_installer.main()
                run.assert_not_called()
                output.assert_not_called()
        self.assertFalse((self.root / "dist/windows-trim-delete.iss").exists())


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.dist = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def write(self, platform, version):
        path = self.dist / qa_common.ARTIFACTS[platform].format(version=version)
        path.write_bytes(b"Package fixture")
        return path

    def test_exact_version_wins_even_when_an_older_artifact_is_newer_on_disk(self):
        for platform in qa_common.ARTIFACTS:
            with self.subTest(platform=platform):
                current = self.write(platform, "1.0.2")
                old = self.write(platform, "0.18.0")
                os.utime(current, (1, 1))
                os.utime(old, (2, 2))
                self.assertEqual(qa_common.artifact_path(self.dist, platform, "1.0.2"), current)

    def test_missing_current_artifact_never_falls_back_to_another_release(self):
        self.write("windows", "0.18.0")
        with self.assertRaises(FileNotFoundError):
            qa_common.artifact_path(self.dist, "windows", "1.0.2")

    def test_version_cannot_be_a_path_or_shell_fragment(self):
        for value in ("../1.0.2", "1.0.2;echo", "1.0", "1.0.2-beta"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                qa_common.artifact_path(self.dist, "arch", value)

    def test_optional_migrations_report_every_missing_baseline(self):
        existing = self.write("arch", "0.9.0")
        reports = []
        result = qa_common.migration_packages(self.dist, "arch", "1.0.2", report=reports.append)
        self.assertEqual(result, [existing])
        self.assertEqual(len([line for line in reports if line.startswith("SKIP")]), 2)
        self.assertTrue(any("0.8.0" in line for line in reports))
        self.assertTrue(any("0.10.0" in line for line in reports))

    def test_release_migration_mode_requires_all_older_baselines(self):
        self.write("debian", "0.9.0")
        with self.assertRaisesRegex(FileNotFoundError, "0.8.0.*0.10.0"):
            qa_common.migration_packages(self.dist, "debian", "1.0.2", required=True, report=lambda _: None)

    def test_baselines_newer_than_the_selected_release_are_not_installed(self):
        self.write("arch", "0.8.0")
        self.write("arch", "0.10.0")
        result = qa_common.migration_packages(self.dist, "arch", "0.9.0", required=True, report=lambda _: None)
        self.assertEqual([path.name for path in result], ["lupin-0.8.0-1-x86_64.pkg.tar.zst"])

    def test_explicit_previous_release_is_used_and_missing_old_baselines_stay_visible(self):
        for platform in ("arch", "debian"):
            with self.subTest(platform=platform):
                previous = self.write(platform, "1.0.1")
                reports = []
                result = qa_common.migration_packages(self.dist, platform, "1.0.2",
                    upgrade_from=[previous], report=reports.append)
                self.assertEqual(result, [previous])
                self.assertEqual(len([line for line in reports if line.startswith("SKIP")]), 3)
                self.assertTrue(any("explicit upgrade" in line and "1.0.1" in line for line in reports))

    def test_explicit_upgrade_baselines_must_match_platform_and_be_older(self):
        for path in (self.write("arch", "1.0.1"), self.write("debian", "1.0.2"), self.write("debian", "1.0.3")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                qa_common.migration_packages(self.dist, "debian", "1.0.2", upgrade_from=[path], report=lambda _: None)

    def test_explicit_baselines_are_sorted_and_deduplicated(self):
        old = self.write("arch", "0.9.0")
        recent = self.write("arch", "1.0.1")
        result = qa_common.migration_packages(self.dist, "arch", "1.0.2",
            upgrade_from=[recent, old, recent], report=lambda _: None)
        self.assertEqual(result, [old, recent])

    def test_missing_explicit_baseline_fails_instead_of_becoming_an_optional_skip(self):
        missing = self.dist / qa_common.ARTIFACTS["debian"].format(version="1.0.1")
        with self.assertRaisesRegex(FileNotFoundError, "Explicit upgrade baseline"):
            qa_common.migration_packages(self.dist, "debian", "1.0.2", upgrade_from=[missing], report=lambda _: None)

    def test_explicit_baseline_must_be_inside_the_readonly_package_directory(self):
        with tempfile.TemporaryDirectory() as external:
            path = Path(external) / qa_common.ARTIFACTS["debian"].format(version="1.0.1")
            path.write_bytes(b"Package fixture")
            with self.assertRaisesRegex(ValueError, "Keep explicit QA upgrade packages"):
                qa_common.migration_packages(self.dist, "debian", "1.0.2", upgrade_from=[path], report=lambda _: None)

    def test_windows_historical_migration_is_explicitly_skipped_or_required(self):
        reports = []
        self.assertIsNone(qa_common.migration_installer(None, report=reports.append))
        self.assertTrue(reports[0].startswith("SKIP"))
        with self.assertRaisesRegex(ValueError, "--upgrade-from"):
            qa_common.migration_installer(None, required=True)
        with self.assertRaises(FileNotFoundError):
            qa_common.migration_installer(self.dist / "missing.exe")


class IsolationTests(unittest.TestCase):
    def test_temporary_home_does_not_remove_the_original_default_wine_prefix_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            host_home = Path(temporary) / "host-home"
            host_home.mkdir()
            prefix = host_home / ".wine"
            prefix.mkdir()
            alias = Path(temporary) / "alias"
            alias.symlink_to(prefix, target_is_directory=True)
            env = {qa_common.HOST_HOME: str(host_home)}
            for value in (prefix, alias):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "default/game prefix"):
                    qa_common.wine_test_prefix(value, env)

    def test_existing_wine_desktop_link_cannot_write_through_to_host_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "qa-prefix"
            profile = prefix / "drive_c/users/tester"
            profile.mkdir(parents=True)
            host_desktop = root / "host-home/Desktop"
            host_desktop.mkdir(parents=True)
            (profile / "Desktop").symlink_to(host_desktop, target_is_directory=True)
            private = root / "private"
            private.mkdir()
            env = {qa_common.PRIVATE_ROOT: str(private)}
            with self.assertRaisesRegex(ValueError, "known folder escapes"):
                qa_common.wine_test_prefix(prefix, env)
            self.assertEqual(list(host_desktop.iterdir()), [])

    def test_wine_known_folders_may_link_only_to_this_runs_private_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "qa-prefix"
            profile = prefix / "drive_c/users/tester"
            profile.mkdir(parents=True)
            private = root / "private"
            desktop = private / "home/Desktop"
            desktop.mkdir(parents=True)
            (profile / "Desktop").symlink_to(desktop, target_is_directory=True)
            env = {qa_common.PRIVATE_ROOT: str(private)}
            self.assertEqual(qa_common.wine_test_prefix(prefix, env), prefix.resolve())
            stale = root / "previous-private/home/Desktop"
            (profile / "Desktop").unlink()
            (profile / "Desktop").symlink_to(stale, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "known folder escapes"):
                qa_common.wine_test_prefix(prefix, env)

    def test_wine_user_directory_cannot_redirect_validation_to_host_profiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "qa-prefix"
            (prefix / "drive_c").mkdir(parents=True)
            host_users = root / "host-users"
            host_users.mkdir()
            (prefix / "drive_c/users").symlink_to(host_users, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "users directory escapes"):
                qa_common.wine_test_prefix(prefix, {})

    def test_private_environment_removes_host_desktop_and_uses_temporary_user_paths(self):
        host = dict(HOME="/host/home", DISPLAY=":0", XAUTHORITY="/host/auth",
                    WAYLAND_DISPLAY="wayland-0", WAYLAND_SOCKET="42",
                    DBUS_SESSION_BUS_ADDRESS="unix:path=/host/bus", XDG_CACHE_HOME="/host/cache")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = qa_common.private_environment(root, host)
            for key in qa_common.DESKTOP_ENV:
                self.assertNotIn(key, env)
            for key in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "TMPDIR"):
                self.assertTrue(Path(env[key]).is_relative_to(root), key)
                self.assertEqual(Path(env[key]).stat().st_mode & 0o777, 0o700)
            self.assertEqual(env[qa_common.HOST_HOME], "/host/home")
            self.assertEqual(env["LIBGL_ALWAYS_SOFTWARE"], "1")
        self.assertEqual(host["DISPLAY"], ":0")

    def test_host_entrypoint_runs_only_a_private_x_server_and_bus_then_cleans_up(self):
        main = Mock()
        captured = {}

        def run(command, *, env, check):
            captured.update(command=command, env=env.copy())
            self.assertTrue(Path(env[qa_common.PRIVATE_ROOT]).is_dir())
            self.assertNotIn("DISPLAY", env)
            self.assertNotIn("DBUS_SESSION_BUS_ADDRESS", env)
            return subprocess.CompletedProcess(command, 0)

        with patch.dict(os.environ, {"HOME": "/host/home", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}, clear=True):
            with patch.object(sys, "platform", "linux"), patch.object(sys, "argv", ["qa.py", "--version", "1.0.2"]):
                with patch.object(qa_common.shutil, "which", return_value="/fixture/tool"), patch.object(qa_common.subprocess, "run", side_effect=run):
                    with self.assertRaises(SystemExit) as result:
                        qa_common.qa_entrypoint(main, __file__)
        self.assertEqual(result.exception.code, 0)
        main.assert_not_called()
        self.assertEqual(captured["command"][0], "xvfb-run")
        self.assertIn("dbus-run-session", captured["command"])
        self.assertEqual(captured["command"][-2:], ["--version", "1.0.2"])
        self.assertFalse(Path(captured["env"][qa_common.PRIVATE_ROOT]).exists())

    def test_invalid_reentry_cannot_fall_back_to_the_host_display(self):
        main = Mock()
        with patch.dict(os.environ, {qa_common.PRIVATE_ROOT: "/missing", "DISPLAY": ":0"}, clear=True):
            with patch.object(sys, "platform", "linux"), patch.object(sys, "argv", ["qa.py"]):
                with self.assertRaisesRegex(RuntimeError, "host desktop"):
                    qa_common.qa_entrypoint(main, __file__)
        main.assert_not_called()

    def test_private_child_enters_main_without_starting_another_desktop(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = qa_common.private_environment(temporary, {})
            authority = Path(env["TMPDIR"]) / "Xauthority"
            authority.touch()
            env.update(DISPLAY=":99", XAUTHORITY=str(authority), DBUS_SESSION_BUS_ADDRESS="unix:path=/private/bus")
            main = Mock(return_value=42)
            with patch.dict(os.environ, env, clear=True), patch.object(sys, "platform", "linux"), patch.object(sys, "argv", ["qa.py"]):
                with patch.object(qa_common.subprocess, "run") as run:
                    self.assertEqual(qa_common.qa_entrypoint(main, __file__), 42)
                    main.assert_called_once_with()
                    run.assert_not_called()

    def test_gui_processes_leave_fakeroot_without_losing_the_private_desktop(self):
        source = dict(FAKEROOTKEY="fixture", FAKED_MODE="unknown-is-root", DISPLAY=":99",
                      DBUS_SESSION_BUS_ADDRESS="unix:path=/private/bus",
                      LD_PRELOAD="/fakeroot/libfakeroot.so:/other/library.so")
        result = qa_common.desktop_process_environment(source)
        self.assertNotIn("FAKEROOTKEY", result)
        self.assertNotIn("FAKED_MODE", result)
        self.assertEqual(result["LD_PRELOAD"], "/other/library.so")
        self.assertEqual(result["DISPLAY"], ":99")
        self.assertEqual(result["DBUS_SESSION_BUS_ADDRESS"], source["DBUS_SESSION_BUS_ADDRESS"])
        self.assertIn("libfakeroot", source["LD_PRELOAD"])

    def test_guest_arguments_are_separate_from_the_shell_setup(self):
        payload = ["/opt/lupin/bin/helper", "value with spaces", "$(never executed)"]
        command = qa_common.guest_desktop_command(payload)
        self.assertEqual(command[-3:], payload)
        self.assertNotIn(payload[-1], command[2])
        self.assertIn("unset DISPLAY XAUTHORITY WAYLAND_DISPLAY WAYLAND_SOCKET", command[2])
        self.assertIn("dbus-run-session", command[2])
        self.assertIn("XDG_RUNTIME_DIR=", command[2])
        self.assertIn("LIBGL_ALWAYS_SOFTWARE=1", command[2])

    def test_windows_bootstrap_sets_offscreen_before_import_and_preserves_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            module = Path(temporary) / "qa_probe.py"
            module.write_text("import json,os,sys\nprint(json.dumps([os.environ['QT_QPA_PLATFORM'],sys.argv[1:]]))\n")
            arguments = ["value with spaces", "$(literal)", 'a"quote']
            env = {**os.environ, "PYTHONPATH": temporary, "QT_QPA_PLATFORM": "xcb"}
            result = subprocess.run(qa_common.windows_python(sys.executable, module="qa_probe", arguments=arguments),
                                    env=env, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), ["offscreen", arguments])

    def test_inline_windows_python_also_sets_offscreen_inside_the_process(self):
        command = qa_common.windows_python(sys.executable, code="assert os.environ['QT_QPA_PLATFORM']=='offscreen'")
        subprocess.run(command, env={**os.environ, "QT_QPA_PLATFORM": "xcb"}, check=True, capture_output=True)


@unittest.skipUnless(sys.platform.startswith("linux"), "Private FUSE cleanup is Linux-only")
class PrivateCleanupTests(unittest.TestCase):
    def setUp(self):
        self.root, self.token = qa_common.create_private_root()
        self.addCleanup(lambda: shutil.rmtree(self.root) if self.root.exists() else None)

    def portal(self):
        target = self.root / "run/doc"
        target.mkdir(parents=True)
        return target

    def test_only_known_owned_private_fuse_mount_is_detached(self):
        target = self.portal()
        with patch.object(qa_common, "_private_mounts", side_effect=[[(target, "fuse.portal", "portal")], []]):
            with patch.object(qa_common.shutil, "which", return_value="/fixture/fusermount3"), patch.object(qa_common.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
                self.assertTrue(qa_common.cleanup_private_root(self.root, self.token, report=lambda _: None))
                self.assertEqual(run.call_args.args[0], ["/fixture/fusermount3", "-u", "-z", "--", str(target)])
        self.assertFalse(self.root.exists())

    def test_external_or_unknown_mount_is_never_detached_or_deleted(self):
        for target, filesystem in ((Path('/run/user/1000/doc'), 'fuse.portal'),
                                   (self.root / 'home/unknown', 'fuse.portal'),
                                   (self.root / 'run/doc', 'tmpfs')):
            with self.subTest(target=target), patch.object(qa_common, "_private_mounts", return_value=[(target, filesystem, 'portal')]):
                with patch.object(qa_common.subprocess, "run") as run:
                    self.assertFalse(qa_common.cleanup_private_root(self.root, self.token, report=lambda _: None))
                    run.assert_not_called()
                    self.assertTrue((self.root / qa_common.QA_MARKER).is_file())

    def test_symlink_runtime_or_mount_target_cannot_escape_the_private_root(self):
        with tempfile.TemporaryDirectory() as external:
            target = self.root / 'run/doc'
            (self.root / 'run').symlink_to(external, target_is_directory=True)
            with patch.object(qa_common, "_private_mounts", return_value=[(target, 'fuse.portal', 'portal')]), patch.object(qa_common.subprocess, "run") as run:
                self.assertFalse(qa_common.cleanup_private_root(self.root, self.token, report=lambda _: None))
                run.assert_not_called()
            (self.root / 'run').unlink()
            target.parent.mkdir()
            target.symlink_to(external, target_is_directory=True)
            with patch.object(qa_common, "_private_mounts", return_value=[(target, 'fuse.portal', 'portal')]), patch.object(qa_common.subprocess, "run") as run:
                self.assertFalse(qa_common.cleanup_private_root(self.root, self.token, report=lambda _: None))
                run.assert_not_called()
            self.assertTrue(Path(external).is_dir())

    def test_wrong_token_or_root_symlink_never_deletes_the_root(self):
        self.assertFalse(qa_common.cleanup_private_root(self.root, '0'*32, report=lambda _: None))
        with tempfile.TemporaryDirectory() as temporary:
            link = Path(temporary) / 'lupin-qa-link'
            link.symlink_to(self.root, target_is_directory=True)
            self.assertFalse(qa_common.cleanup_private_root(link, self.token, report=lambda _: None))
        self.assertTrue(self.root.is_dir())

    def test_failed_unmount_reports_cleanup_and_preserves_data(self):
        target = self.portal()
        reports = []
        with patch.object(qa_common, "_private_mounts", return_value=[(target, 'fuse.portal', 'portal')]):
            with patch.object(qa_common.shutil, "which", return_value="/fixture/fusermount3"), patch.object(qa_common.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)):
                self.assertFalse(qa_common.cleanup_private_root(self.root, self.token, child_status=17, report=reports.append))
        self.assertTrue(self.root.is_dir())
        self.assertTrue(any('child exit 17 unchanged' in line for line in reports))

    def test_cleanup_failure_cannot_replace_the_actual_child_result(self):
        for status in (0, 9):
            reports = io.StringIO()
            with self.subTest(child_status=status), patch.dict(os.environ, {'HOME':'/host/home'}, clear=True), patch.object(sys, 'argv', ['qa.py']):
                with patch.object(qa_common, 'create_private_root', return_value=(self.root, self.token)):
                    with patch.object(qa_common, '_private_mounts', return_value=[(self.root/'home/unknown','fuse.portal','portal')]):
                        with patch.object(qa_common.shutil, 'which', return_value='/fixture/tool'), patch.object(qa_common.subprocess, 'run', return_value=subprocess.CompletedProcess([], status)):
                            with contextlib.redirect_stderr(reports), self.assertRaises(SystemExit) as result:
                                qa_common.qa_entrypoint(lambda: None, __file__)
            self.assertEqual(result.exception.code, status)
            self.assertIn(f'QA CLEANUP FAILED (child exit {status} unchanged)', reports.getvalue())


if __name__ == "__main__":
    unittest.main()
