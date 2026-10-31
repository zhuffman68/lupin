"""Read-only preflight checks for Windows release staging and Setup inputs."""
import json
from pathlib import Path
import struct

REQUIRED_STAGE_FILES = (
    "runtime/python.exe", "runtime/pythonw.exe", "bin/lupin-screen-reader.exe",
    "bin/libunwind.dll", "bin/lupin-market-fetch.exe", "bin/WebView2Loader.dll",
    "MicrosoftEdgeWebview2Setup.exe", "price_lens/__init__.py", "price_lens/__main__.py",
    "price_lens/resources/update-windows.ps1", "price_lens/resources/update-keys.json",
    "models/korean-chat/manifest.json", "models/english-korean/manifest.json",
    "lupin-scaled.ico", "run-windows.bat", "selftest-windows.bat", "runtime-trim.json",
)


def require_windows_reader(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("Compiled Windows x64 reader required: " + str(path))
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise ValueError("Reader must be a Windows x64 executable: " + str(path))
        offset = struct.unpack_from("<I", header, 60)[0]
        if not 64 <= offset <= 1024 * 1024:
            raise ValueError("Invalid Windows reader PE header: " + str(path))
        stream.seek(offset)
        pe = stream.read(26)
    if (len(pe) != 26 or pe[:4] != b"PE\0\0"
            or struct.unpack_from("<H", pe, 4)[0] != 0x8664
            or struct.unpack_from("<H", pe, 20)[0] < 2
            or not struct.unpack_from("<H", pe, 22)[0] & 0x0002
            or struct.unpack_from("<H", pe, 22)[0] & 0x2000
            or struct.unpack_from("<H", pe, 24)[0] != 0x20B):
        raise ValueError("Reader must be a Windows x64 PE32+ executable: " + str(path))


def validate_windows_stage(stage):
    stage = Path(stage)
    for name in REQUIRED_STAGE_FILES:
        path = stage / name
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError("Incomplete Windows stage, required file missing: " + str(path))
    require_windows_reader(stage / "bin/lupin-screen-reader.exe")
    report = json.loads((stage / "runtime-trim.json").read_text())
    if not isinstance(report, dict) or report.get("platform") != "windows" or not isinstance(report.get("removed"), list):
        raise ValueError("Windows stage requires a Windows runtime-trim report")
