#!/usr/bin/env python3
"""Flash and inspect an MCU through J-Link, OpenOCD, probe-rs or pyOCD.

One command surface over four probe stacks. Every action carries a declared
risk level and is gated by operation_mode, so an action that can brick a board
cannot run because a build happened to succeed.

    probe_cli.py info
    probe_cli.py list
    probe_cli.py flash --file build/zephyr/zephyr.hex
    probe_cli.py reset [--halt]
    probe_cli.py read-mem --address 0x20000000 --length 64
    probe_cli.py regs
    probe_cli.py erase          # high risk
    probe_cli.py rtt            # streaming, bounded by --timeout
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _bootstrap import setup  # noqa: E402

setup(__file__)

from antness_runtime import ConfigError, Resolver, emit, fail, ok, run, which_tool  # noqa: E402
from antness_runtime.result import Result, Timer  # noqa: E402
from antness_runtime.risk import ConfirmationRequired, check_operation  # noqa: E402

SECTION = "probe"

# Declared risk per action. These are not adjustable from config — a tool does
# not get to downgrade how dangerous its own operations are.
ACTION_RISK = {
    "list": "low",
    "info": "low",
    "regs": "low",
    "read-mem": "low",
    "rtt": "low",
    "halt": "low",
    "go": "low",
    "reset": "high",        # resets the running application; on a live system that is an outage
    "flash": "high",        # overwrites application flash
    "write-mem": "high",    # can corrupt a running system in ways that survive a reset
    "erase": "high",        # removes the application; recovery needs a working probe
}

RISK_REASONS = {
    "reset": ["restarts the target; any running process or captured state is lost"],
    "flash": ["overwrites application flash on the target",
              "if the image is wrong, recovery needs the probe to still enumerate"],
    "write-mem": ["writes directly to target memory, bypassing the running program's invariants"],
    "erase": ["erases flash; the device will not boot until something is programmed back"],
}

BACKENDS = ("jlink", "openocd", "probe-rs", "pyocd")


def confirmation_result(exc: ConfirmationRequired, backend: Optional[str]) -> Result:
    return Result(
        status="confirmation_required",
        action=exc.action,
        summary="{} needs explicit approval on this target".format(exc.action),
        backend=backend,
        risk=exc.risk,
        details=exc.details(),
        validated_on="hardware",
    )


# ------------------------------------------------------------- backend pick
def detect_backend(r: Resolver) -> Tuple[Optional[str], List[str]]:
    evidence = []
    for backend, exe in (("jlink", "JLinkExe"), ("probe-rs", "probe-rs"),
                         ("openocd", "openocd"), ("pyocd", "pyocd")):
        found = which_tool(exe) or (which_tool("JLink.exe") if backend == "jlink" else None)
        if found:
            evidence.append("{} found at {}".format(exe, found))
            return backend, evidence
    return None, ["none of JLinkExe, probe-rs, openocd, pyocd found on PATH"]


def enumerate_probes(r: Resolver, timeout: int = 20) -> Dict[str, Any]:
    """Ask every installed probe tool what it can see.

    Deliberately backend-independent: "which probes are attached" is a question
    about the host, and answering it only through the configured backend hides
    the adapter the operator actually plugged in.
    """
    found: Dict[str, Any] = {}
    queries = [
        ("probe-rs", r.resolve_tool("probe_rs_exe", None, ["probe-rs"]), ["list"]),
        ("pyocd", r.resolve_tool("pyocd_exe", None, ["pyocd"]), ["list"]),
        ("jlink", r.resolve_tool("jlink_exe", None, ["JLinkExe", "JLink.exe"]), None),
        ("openocd", r.resolve_tool("openocd_exe", None, ["openocd"]), None),
    ]
    for backend, exe, sub in queries:
        if not exe:
            continue
        entry: Dict[str, Any] = {"tool": exe}
        if sub:
            probe_result = run([exe] + sub, timeout=timeout)
            entry["output"] = probe_result.tail(20)
            entry["queried"] = probe_result.ok
        elif backend == "jlink":
            script = jlink_script(["ShowEmuList"])
            try:
                probe_result = run([exe, "-NoGui", "1", "-CommanderScript", str(script)], timeout=timeout)
                entry["output"] = probe_result.tail(20)
                entry["queried"] = probe_result.ok
            finally:
                script.unlink(missing_ok=True)
        else:
            # OpenOCD has no adapter enumeration that works without a target
            # config, so report presence only rather than inventing a result.
            entry["queried"] = False
            entry["output"] = "installed; OpenOCD cannot enumerate adapters without a target config"
        found[backend] = entry
    return found


# ------------------------------------------------------------------- J-Link
def jlink_script(commands: List[str]) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".jlink", delete=False, encoding="utf-8")
    handle.write("\n".join(commands + ["qc", ""]))
    handle.close()
    return Path(handle.name)


def jlink_run(r: Resolver, args: argparse.Namespace, commands: List[str]) -> Tuple[List[str], Optional[Path]]:
    exe = r.resolve_tool("jlink_exe", args.tool, ["JLinkExe", "JLink.exe"])
    if not exe:
        raise ConfigError("JLinkExe not found. Set probe.jlink_exe in .antness/local.json")
    device = r.resolve_project("device", args.device, required=True,
                               describe="J-Link device name, e.g. STM32H743ZI or GD32F470ZG")
    interface = str(r.resolve_project("interface", args.interface, default="SWD")).upper()
    speed = str(r.resolve_project("speed", args.speed, default="4000"))
    serial = r.resolve_tool("serial_no", args.serial)

    script = jlink_script(["connect"] + commands)
    argv = [exe, "-Device", str(device), "-If", interface, "-Speed", speed,
            "-NoGui", "1", "-ExitOnError", "1", "-AutoConnect", "1",
            "-CommanderScript", str(script)]
    if serial:
        argv += ["-SelectEmuBySN", str(serial)]
    return argv, script


def jlink_commands(action: str, args: argparse.Namespace) -> List[str]:
    if action == "info":
        return ["h", "regs"]
    if action == "flash":
        target = Path(args.file).resolve()
        if target.suffix.lower() == ".bin":
            if not args.address:
                raise ConfigError(".bin has no load address — pass --address, e.g. --address 0x08000000")
            return ["r", "h", "loadbin {} {}".format(target, args.address), "r", "g"]
        return ["r", "h", "loadfile {}".format(target), "r", "g"]
    if action == "erase":
        return ["r", "h", "erase"]
    if action == "reset":
        return ["r"] + ([] if args.halt else ["g"])
    if action == "halt":
        return ["h", "regs"]
    if action == "go":
        return ["g"]
    if action == "regs":
        return ["h", "regs"]
    if action == "read-mem":
        return ["h", "mem {} {}".format(args.address, hex(args.length))]
    if action == "write-mem":
        return ["h", "w4 {} {}".format(args.address, args.value)]
    raise ConfigError("action {} is not supported by the J-Link backend".format(action))


# ------------------------------------------------------------------ OpenOCD
def openocd_argv(r: Resolver, args: argparse.Namespace, commands: List[str]) -> List[str]:
    exe = r.resolve_tool("openocd_exe", args.tool, ["openocd"])
    if not exe:
        raise ConfigError("openocd not found. Set probe.openocd_exe in .antness/local.json")
    interface_cfg = r.resolve_project("openocd_interface", None, required=True,
                                      describe="e.g. interface/stlink.cfg or interface/cmsis-dap.cfg")
    target_cfg = r.resolve_project("openocd_target", None, required=True,
                                   describe="e.g. target/stm32h7x.cfg")
    argv = [exe, "-f", str(interface_cfg), "-f", str(target_cfg)]
    for command in commands:
        argv += ["-c", command]
    argv += ["-c", "shutdown"]
    return argv


def openocd_commands(action: str, args: argparse.Namespace) -> List[str]:
    if action in ("info", "regs"):
        return ["init", "reset halt", "reg"]
    if action == "flash":
        target = Path(args.file).resolve()
        if target.suffix.lower() == ".bin":
            if not args.address:
                raise ConfigError(".bin has no load address — pass --address")
            return ["init", "program {} {} verify reset".format(target, args.address)]
        return ["init", "program {} verify reset".format(target)]
    if action == "erase":
        return ["init", "reset halt", "flash erase_sector 0 0 last"]
    if action == "reset":
        return ["init", "reset halt" if args.halt else "reset run"]
    if action == "halt":
        return ["init", "halt", "reg"]
    if action == "go":
        return ["init", "resume"]
    if action == "read-mem":
        return ["init", "halt", "mdb {} {}".format(args.address, args.length)]
    if action == "write-mem":
        return ["init", "halt", "mww {} {}".format(args.address, args.value)]
    raise ConfigError("action {} is not supported by the OpenOCD backend".format(action))


# ----------------------------------------------------------------- probe-rs
def probers_argv(r: Resolver, args: argparse.Namespace, action: str) -> List[str]:
    exe = r.resolve_tool("probe_rs_exe", args.tool, ["probe-rs"])
    if not exe:
        raise ConfigError("probe-rs not found. Set probe.probe_rs_exe in .antness/local.json")
    chip = r.resolve_project("chip", args.device, required=True,
                             describe="probe-rs chip name, e.g. STM32H743ZITx (run `probe-rs chip list`)")
    base = [exe]
    common = ["--chip", str(chip)]
    serial = r.resolve_tool("serial_no", args.serial)
    if serial:
        common += ["--probe", str(serial)]

    if action == "list":
        return base + ["list"]
    if action == "info":
        return base + ["info"] + common
    if action == "flash":
        return base + ["download", "--chip", str(chip)] + (["--probe", str(serial)] if serial else []) + [str(Path(args.file).resolve())]
    if action == "erase":
        return base + ["erase"] + common
    if action == "reset":
        return base + ["reset"] + common
    if action == "rtt":
        return base + ["attach", "--chip", str(chip)] + (["--probe", str(serial)] if serial else [])
    raise ConfigError("action {} is not supported by the probe-rs backend".format(action))


# -------------------------------------------------------------------- pyOCD
def pyocd_argv(r: Resolver, args: argparse.Namespace, action: str) -> List[str]:
    exe = r.resolve_tool("pyocd_exe", args.tool, ["pyocd"])
    if not exe:
        raise ConfigError("pyocd not found. Set probe.pyocd_exe in .antness/local.json")
    target = r.resolve_project("pyocd_target", args.device, required=True,
                               describe="pyOCD target, e.g. stm32h743zitx (run `pyocd list --targets`)")
    common = ["-t", str(target)]
    serial = r.resolve_tool("serial_no", args.serial)
    if serial:
        common += ["-u", str(serial)]

    if action == "list":
        return [exe, "list"]
    if action == "info":
        return [exe, "cmd"] + common + ["-c", "status"]
    if action == "flash":
        return [exe, "flash"] + common + [str(Path(args.file).resolve())]
    if action == "erase":
        return [exe, "erase"] + common + ["--chip"]
    if action == "reset":
        return [exe, "reset"] + common + (["--halt"] if args.halt else [])
    if action == "regs":
        return [exe, "cmd"] + common + ["-c", "reg"]
    if action == "read-mem":
        return [exe, "cmd"] + common + ["-c", "read32 {} {}".format(args.address, args.length)]
    raise ConfigError("action {} is not supported by the pyOCD backend".format(action))


# -------------------------------------------------------------------- main
def build_argv(backend: str, action: str, r: Resolver, args: argparse.Namespace) -> Tuple[List[str], Optional[Path]]:
    if backend == "jlink":
        return jlink_run(r, args, jlink_commands(action, args))
    if backend == "openocd":
        return openocd_argv(r, args, openocd_commands(action, args)), None
    if backend == "probe-rs":
        return probers_argv(r, args, action), None
    if backend == "pyocd":
        return pyocd_argv(r, args, action), None
    raise ConfigError("unknown backend {}".format(backend))


def target_identity(backend: str, r: Resolver, args: argparse.Namespace) -> str:
    """The string a confirmation token is bound to.

    Includes the probe serial when known, so approving a flash on one board does
    not silently approve it on the board next to it.
    """
    serial = args.serial or r.local_value("serial_no") or "unspecified-probe"
    device = args.device or r.project_value("device") or r.project_value("chip") or "unknown-device"
    return "{}:{}:{}".format(backend, device, serial)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="probe", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=sorted(ACTION_RISK))
    parser.add_argument("--backend", choices=BACKENDS, help="override detection")
    parser.add_argument("--device", help="chip/device name for the backend")
    parser.add_argument("--serial", help="probe serial number (required when several are attached)")
    parser.add_argument("--interface", help="SWD or JTAG (J-Link)")
    parser.add_argument("--speed", help="interface speed in kHz")
    parser.add_argument("--file", help="image to flash (.elf/.hex/.bin)")
    parser.add_argument("--address", help="address for .bin flash, read-mem or write-mem")
    parser.add_argument("--length", type=int, default=32, help="bytes to read")
    parser.add_argument("--value", help="value for write-mem")
    parser.add_argument("--halt", action="store_true", help="halt after reset")
    parser.add_argument("--tool", help="explicit path to the probe tool")
    parser.add_argument("--timeout", type=int, default=120, help="seconds (default 120)")
    parser.add_argument("--confirm", help="confirmation token from a previous refusal")
    parser.add_argument("--workspace", help="workspace root (default: discovered)")
    parser.add_argument("--json", action="store_true", default=True)
    parser.add_argument("--text", dest="json", action="store_false")
    args = parser.parse_args(argv)

    try:
        r = Resolver(SECTION, Path(args.workspace) if args.workspace else None)
    except ConfigError as exc:
        return emit(fail("init", str(exc)), args.json)

    backend = args.backend or r.resolve_project("backend", None)
    evidence: List[str] = []
    if backend:
        r.provenance["backend"] = "cli" if args.backend else "project"
    else:
        backend, evidence = detect_backend(r)
        r.provenance["backend"] = "detected"

    if args.action == "list":
        probes = enumerate_probes(r)
        if not probes:
            return emit(
                fail("list", "no probe tool installed on this host",
                     details={"evidence": evidence},
                     next_steps=["Install one of: JLinkExe, probe-rs, openocd, pyocd",
                                 "Or set its path in .antness/local.json under probe"]),
                args.json,
            )
        return emit(
            ok("list", "{} probe tool(s) present".format(len(probes)),
               backend=backend, details={"tools": probes},
               parameter_context=r.parameter_context(),
               warnings=["more than one probe tool is installed; pin probe.backend in "
                         "project.json so results are reproducible"] if len(probes) > 1 else []),
            args.json,
        )

    if not backend:
        return emit(
            fail(args.action, "no probe tool found", details={"evidence": evidence},
                 next_steps=["Install one of: JLinkExe, probe-rs, openocd, pyocd",
                             "Or set its path in .antness/local.json under probe"]),
            args.json,
        )

    if args.action == "flash" and not args.file:
        from_state = r.state_value("last_build")
        if from_state:
            args.file = from_state
            r.provenance["file"] = "state"
        else:
            return emit(fail("flash", "--file is required and no previous build is recorded",
                             backend=backend,
                             next_steps=["build build", "then: probe flash"]), args.json)
    if args.file:
        candidate = Path(args.file)
        if not candidate.is_file():
            from_workspace = r.workspace / args.file
            if from_workspace.is_file():
                candidate = from_workspace
            else:
                return emit(
                    fail(args.action, "image not found: {}".format(args.file), backend=backend,
                         details={"looked_in": sorted(
                             {str(Path(args.file).resolve()), str(from_workspace)})},
                         next_steps=["build artifacts — list what the last build produced"]),
                    args.json,
                )
        args.file = str(candidate.resolve())

    if args.action in ("write-mem",) and not (args.address and args.value):
        return emit(fail(args.action, "--address and --value are required", backend=backend), args.json)
    if args.action == "read-mem" and not args.address:
        return emit(fail(args.action, "--address is required", backend=backend), args.json)

    identity = target_identity(backend, r, args)
    reasons = list(RISK_REASONS.get(args.action, []))
    if args.action == "flash" and args.file:
        reasons.append("image: {} ({} bytes)".format(args.file, Path(args.file).stat().st_size))
    recovery = str(r.resolve_project("recovery_path", None,
                                     default="not recorded — add probe.recovery_path to project.json"))

    try:
        warnings = check_operation(args.action, ACTION_RISK[args.action], r.operation_mode,
                                   target=identity, reasons=reasons, recovery=recovery,
                                   confirmed=args.confirm)
    except ConfirmationRequired as exc:
        return emit(confirmation_result(exc, backend), args.json)

    script: Optional[Path] = None
    try:
        cmd, script = build_argv(backend, args.action, r, args)
    except ConfigError as exc:
        return emit(fail(args.action, str(exc), backend=backend,
                         parameter_context=r.parameter_context()), args.json)

    try:
        with Timer() as timer:
            result = run(cmd, timeout=args.timeout)
    finally:
        if script and script.exists():
            script.unlink()

    details: Dict[str, Any] = result.as_details()
    details["target"] = identity
    details["recovery_path"] = recovery

    if not result.ok:
        summary = "{} timed out after {}s".format(args.action, args.timeout) if result.timed_out \
            else "{} failed (exit {})".format(args.action, result.returncode)
        return emit(
            fail(args.action, summary, backend=backend, risk=ACTION_RISK[args.action],
                 details=details, parameter_context=r.parameter_context(), warnings=warnings,
                 duration_ms=timer.ms, validated_on="hardware",
                 next_steps=["Check the probe is attached and the target is powered",
                             "probe list — confirm which probes this host can see",
                             "A failed flash may have left the target partially programmed; "
                             "verify before power-cycling"] if args.action == "flash" else []),
            args.json,
        )

    if args.action in ("flash", "info") and args.device:
        r.remember_project(device=args.device)
    r.commit(state={"last_action": args.action,
                    "last_image": args.file if args.action == "flash" else None,
                    "last_backend": backend})

    return emit(
        ok(args.action, "{} succeeded on {}".format(args.action, identity),
           backend=backend, risk=ACTION_RISK[args.action], details=details,
           parameter_context=r.parameter_context(), warnings=warnings,
           duration_ms=timer.ms, validated_on="hardware"),
        args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
