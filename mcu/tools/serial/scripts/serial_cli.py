#!/usr/bin/env python3
"""Serial console operations: enumerate, capture, send, and monitor for patterns.

Devices are addressed by stable id. /dev/ttyUSB0 is whichever adapter
enumerated first; on a bench with three boards that is a coin flip, and the
coin decides whose board you just talked to. This tool refuses to pick when
several candidates match.

    serial_cli.py list
    serial_cli.py capture --duration 10 --out boot.log
    serial_cli.py send --data "help\\r\\n" --expect "uart:~$"
    serial_cli.py wait-for --pattern "Booting Zephyr" --timeout 30
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _bootstrap import setup  # noqa: E402

setup(__file__)

from antness_runtime import ConfigError, Resolver, emit, fail, ok  # noqa: E402
from antness_runtime.discover import list_serial_ports, resolve_serial_port  # noqa: E402
from antness_runtime.result import Result, Timer  # noqa: E402
from antness_runtime.risk import ConfirmationRequired, check_operation  # noqa: E402

SECTION = "serial"

# Reading is harmless. Writing is not: a console command can reset a board,
# erase configuration, or enter a bootloader.
ACTION_RISK = {"list": "low", "capture": "low", "wait-for": "low", "send": "medium"}

MAX_CAPTURE_BYTES = 1_000_000


def require_pyserial() -> Any:
    try:
        import serial  # type: ignore

        return serial
    except ImportError:
        raise ConfigError(
            "pyserial is not installed. Install it with `pip install pyserial`.\n"
            "`serial list` works without it by reading /dev/serial/by-id."
        )


def open_port(serial_mod: Any, device: str, baud: int, timeout: float) -> Any:
    try:
        return serial_mod.Serial(device, baudrate=baud, timeout=timeout)
    except Exception as exc:  # pyserial raises several unrelated types
        raise ConfigError(
            "cannot open {} at {} baud: {}\n"
            "If this is a permission error, add yourself to the dialout group "
            "and log out and back in. Do not run the tool as root — the capture "
            "files end up root-owned and the real problem stays.".format(device, baud, exc)
        )


def decode(chunk: bytes) -> str:
    return chunk.decode("utf-8", errors="replace")


def read_until(port: Any, deadline: float, pattern: Optional[re.Pattern], sink: List[str]) -> Optional[str]:
    """Read until the deadline or until `pattern` matches. Returns the matching line."""
    buffer = ""
    total = 0
    while time.monotonic() < deadline:
        waiting = getattr(port, "in_waiting", 0) or 1
        chunk = port.read(max(1, min(waiting, 4096)))
        if not chunk:
            continue
        text = decode(chunk)
        total += len(chunk)
        sink.append(text)
        if total > MAX_CAPTURE_BYTES:
            sink.append("\n[capture truncated at {} bytes]\n".format(MAX_CAPTURE_BYTES))
            return None
        if pattern:
            buffer += text
            match = pattern.search(buffer)
            if match:
                return match.group(0)
            buffer = buffer[-8192:]
    return None


def unescape(data: str) -> bytes:
    """Interpret \\r \\n \\t \\xNN in a shell-supplied string."""
    return data.encode("utf-8").decode("unicode_escape").encode("latin-1")


def confirmation_result(exc: ConfirmationRequired) -> Result:
    return Result(status="confirmation_required", action=exc.action,
                  summary="{} needs explicit approval".format(exc.action),
                  risk=exc.risk, details=exc.details(), validated_on="hardware")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="serial", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=sorted(ACTION_RISK))
    parser.add_argument("--port", help="device path or stable id (or a substring of one)")
    parser.add_argument("--baud", type=int, help="baud rate (default 115200)")
    parser.add_argument("--duration", type=float, default=10.0, help="capture seconds")
    parser.add_argument("--timeout", type=float, default=30.0, help="wait-for seconds")
    parser.add_argument("--pattern", help="regex to wait for")
    parser.add_argument("--expect", help="regex expected after send")
    parser.add_argument("--data", help="text to send; \\r \\n \\xNN are interpreted")
    parser.add_argument("--out", help="write the capture to this file as well")
    parser.add_argument("--confirm", help="confirmation token from a previous refusal")
    parser.add_argument("--workspace", help="workspace root (default: discovered)")
    parser.add_argument("--json", action="store_true", default=True)
    parser.add_argument("--text", dest="json", action="store_false")
    args = parser.parse_args(argv)

    try:
        r = Resolver(SECTION, Path(args.workspace) if args.workspace else None)
    except ConfigError as exc:
        return emit(fail("init", str(exc)), args.json)

    if args.action == "list":
        ports = list_serial_ports()
        return emit(
            ok("list", "{} serial device(s)".format(len(ports)),
               details={"ports": ports},
               warnings=["some devices have no by-id entry; addressing them is not stable"]
               if any(not p["stable_id"] for p in ports) else [],
               next_steps=["serial capture --port <stable_id> --duration 10"] if ports else
                          ["no devices — check the cable, the adapter, and dialout group membership"]),
            args.json,
        )

    requested = r.resolve("port", args.port, layers=("cli", "local", "state"))
    baud = int(r.resolve("baud", args.baud, default=115200, layers=("cli", "project", "state", "default")))

    resolution = resolve_serial_port(requested if isinstance(requested, str) else None)
    if not resolution.get("resolved"):
        return emit(
            fail(args.action, str(resolution.get("error")),
                 details={"candidates": resolution.get("candidates", [])},
                 parameter_context=r.parameter_context(),
                 next_steps=["Name the device: --port <stable id from `serial list`>",
                             "Or pin it for this machine in .antness/local.json: "
                             '{"serial": {"port": "/dev/serial/by-id/..."}}']),
            args.json,
        )
    device = str(resolution["resolved"])
    stable = resolution.get("port", {}).get("stable_id") or device

    try:
        warnings = check_operation(
            args.action, ACTION_RISK[args.action], r.operation_mode, target=stable,
            reasons=["console input can reset the board, change its configuration, "
                     "or enter a bootloader"] if args.action == "send" else [],
            recovery="power-cycle the board",
            confirmed=args.confirm,
        )
    except ConfirmationRequired as exc:
        return emit(confirmation_result(exc), args.json)

    try:
        serial_mod = require_pyserial()
        port = open_port(serial_mod, device, baud, timeout=0.2)
    except ConfigError as exc:
        return emit(fail(args.action, str(exc),
                         details={"device": device, "baud": baud}), args.json)

    sink: List[str] = []
    matched: Optional[str] = None
    try:
        with Timer() as timer:
            if args.action == "send":
                if not args.data:
                    return emit(fail("send", "--data is required"), args.json)
                port.reset_input_buffer()
                port.write(unescape(args.data))
                port.flush()
                pattern = re.compile(args.expect) if args.expect else None
                matched = read_until(port, time.monotonic() + args.timeout, pattern, sink)
            elif args.action == "capture":
                matched = read_until(port, time.monotonic() + args.duration, None, sink)
            elif args.action == "wait-for":
                if not args.pattern:
                    return emit(fail("wait-for", "--pattern is required"), args.json)
                matched = read_until(port, time.monotonic() + args.timeout,
                                     re.compile(args.pattern), sink)
    finally:
        try:
            port.close()
        except Exception:
            pass

    captured = "".join(sink)
    if args.out:
        try:
            Path(args.out).write_text(captured, encoding="utf-8")
        except OSError as exc:
            warnings.append("could not write {}: {}".format(args.out, exc))

    details: Dict[str, Any] = {
        "device": device,
        "stable_id": stable,
        "baud": baud,
        "bytes": len(captured),
        "matched": matched,
        "output": captured[-8000:],
    }
    if args.out:
        details["log_file"] = args.out

    expecting = args.pattern or args.expect
    if expecting and not matched:
        return emit(
            fail(args.action, "pattern {!r} not seen within the timeout".format(expecting),
                 details=details, parameter_context=r.parameter_context(), warnings=warnings,
                 duration_ms=timer.ms, validated_on="hardware",
                 next_steps=["Garbage instead of text usually means a baud mismatch, which "
                             "usually means a clock configuration problem",
                             "Silence usually means wrong pin, no power, or a reset loop",
                             "See .ai/skills/shared/serial-console-debug"]),
            args.json,
        )

    r.commit(state={"port": device, "baud": baud})
    summary = "matched {!r}".format(matched) if matched else "captured {} bytes".format(len(captured))
    return emit(
        ok(args.action, summary, details=details, parameter_context=r.parameter_context(),
           warnings=warnings, duration_ms=timer.ms, validated_on="hardware"),
        args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
