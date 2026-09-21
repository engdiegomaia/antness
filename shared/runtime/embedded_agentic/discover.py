"""Active discovery of tools and devices.

Two rules drive this module:

  Find tools before running them. Reporting "openocd is not installed" beats
  handing the agent a shell error it has to interpret.

  Address devices by stable id. /dev/ttyUSB0 is whichever adapter enumerated
  first. On a bench with three boards that is a coin flip, and the coin decides
  which board gets flashed.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

IS_WINDOWS = sys.platform.startswith("win")


def which_tool(name: str, extra_dirs: Optional[List[str]] = None) -> Optional[str]:
    """Resolve an executable from PATH, then from well-known install locations."""
    found = shutil.which(name)
    if found:
        return found

    candidates: List[Path] = []
    for directory in extra_dirs or []:
        candidates.append(Path(directory) / name)
    for directory in _well_known_dirs(name):
        candidates.append(directory / name)
        if IS_WINDOWS:
            candidates.append(directory / (name + ".exe"))

    for candidate in candidates:
        if candidate.is_file() and os.access(str(candidate), os.X_OK):
            return str(candidate)
    return None


def _well_known_dirs(name: str) -> List[Path]:
    lowered = name.lower()
    dirs: List[Path] = []
    if IS_WINDOWS:
        program_files = [Path(os.environ.get(v, "")) for v in ("ProgramFiles", "ProgramFiles(x86)")]
        for base in [p for p in program_files if str(p)]:
            if "jlink" in lowered:
                dirs.append(base / "SEGGER" / "JLink")
            if "openocd" in lowered:
                dirs += [base / "OpenOCD" / "bin", base / "openocd" / "bin"]
            if "uv4" in lowered:
                dirs.append(base / "Keil_v5" / "UV4")
    else:
        dirs += [Path("/usr/local/bin"), Path("/opt/SEGGER/JLink"), Path("/opt/openocd/bin")]
        home = Path.home()
        dirs += [home / ".local" / "bin", home / ".cargo" / "bin"]
        if "arm-none-eabi" in lowered:
            dirs.append(Path("/opt/gcc-arm-none-eabi/bin"))
    return [d for d in dirs if d.is_dir()]


def list_serial_ports() -> List[Dict[str, str]]:
    """Enumerate serial devices, preferring stable by-id paths.

    Uses pyserial when available for richer metadata, and falls back to the
    /dev/serial/by-id tree, which is present on any modern Linux with udev.
    """
    ports: List[Dict[str, str]] = []

    try:  # optional, not a hard dependency
        from serial.tools import list_ports  # type: ignore

        for info in list_ports.comports():
            if _is_legacy_uart(info):
                # /dev/ttyS0..31 are the chipset's 8250 ports. On a typical PC all
                # 32 exist and none has anything attached. Listing them buries the
                # one adapter the operator actually cares about.
                continue
            ports.append(
                {
                    "device": info.device,
                    "stable_id": _stable_id_for(info.device) or "",
                    "description": info.description or "",
                    "manufacturer": getattr(info, "manufacturer", "") or "",
                    "serial_number": getattr(info, "serial_number", "") or "",
                    "vid_pid": (
                        "{:04x}:{:04x}".format(info.vid, info.pid)
                        if getattr(info, "vid", None) and getattr(info, "pid", None)
                        else ""
                    ),
                    "source": "pyserial",
                }
            )
        if ports:
            return ports
    except ImportError:
        pass

    by_id = Path("/dev/serial/by-id")
    if by_id.is_dir():
        for link in sorted(by_id.iterdir()):
            try:
                target = link.resolve()
            except OSError:
                continue
            ports.append(
                {
                    "device": str(target),
                    "stable_id": str(link),
                    "description": link.name,
                    "manufacturer": "",
                    "serial_number": "",
                    "vid_pid": "",
                    "source": "by-id",
                }
            )
    if not ports:
        for pattern in ("ttyUSB*", "ttyACM*", "ttyAMA*"):
            for node in sorted(Path("/dev").glob(pattern)):
                ports.append(
                    {
                        "device": str(node),
                        "stable_id": "",
                        "description": "unstable node — no by-id entry",
                        "manufacturer": "",
                        "serial_number": "",
                        "vid_pid": "",
                        "source": "glob",
                    }
                )
    return ports


def _is_legacy_uart(info: Any) -> bool:
    import re as _re

    if getattr(info, "vid", None) or getattr(info, "pid", None):
        return False
    return bool(_re.match(r"^/dev/ttyS\d+$", getattr(info, "device", "") or ""))


def _stable_id_for(device: str) -> Optional[str]:
    by_id = Path("/dev/serial/by-id")
    if not by_id.is_dir():
        return None
    for link in by_id.iterdir():
        try:
            if link.resolve() == Path(device).resolve():
                return str(link)
        except OSError:
            continue
    return None


def resolve_serial_port(requested: Optional[str]) -> Dict[str, object]:
    """Resolve a port request into a concrete device, or explain the ambiguity.

    Never picks for the user when several candidates match. On a shared bench
    the wrong pick is somebody else's board.
    """
    ports = list_serial_ports()

    if requested:
        for port in ports:
            if requested in (port["device"], port["stable_id"]):
                return {"resolved": port["device"], "port": port, "candidates": ports}
        for port in ports:
            if requested in port["stable_id"] or requested in port["description"]:
                return {"resolved": port["device"], "port": port, "candidates": ports}
        return {
            "resolved": None,
            "error": "no serial device matches {!r}".format(requested),
            "candidates": ports,
        }

    if not ports:
        return {"resolved": None, "error": "no serial devices found", "candidates": []}
    if len(ports) == 1:
        return {"resolved": ports[0]["device"], "port": ports[0], "candidates": ports}
    return {
        "resolved": None,
        "error": (
            "{} serial devices present — name the one you mean. Choosing for you risks "
            "talking to somebody else's board.".format(len(ports))
        ),
        "candidates": ports,
    }
