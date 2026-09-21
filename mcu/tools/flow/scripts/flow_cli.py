#!/usr/bin/env python3
"""Chain build -> flash -> observe, and aggregate the results.

A thin orchestration layer. It implements no build or probe logic of its own —
it calls the other tools and joins their structured output, so a failure is
attributed to a stage rather than to "the flow".

    flow_cli.py plan          what would run, and with what, without running it
    flow_cli.py build-flash   build, then flash the produced artifact
    flow_cli.py observe       capture the console after a reset
    flow_cli.py verify        build, flash, reset, and wait for a boot pattern
    flow_cli.py diagnose      read-only: what is present, what is missing

The confirmation model is inherited, not bypassed: if flashing needs approval,
the flow stops at that stage and reports the token. A chained command is not a
way around a gate.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _bootstrap import setup  # noqa: E402

REPO = setup(__file__)

from embedded_agentic import ConfigError, Resolver, emit, fail, ok  # noqa: E402
from embedded_agentic.config import lint_layers  # noqa: E402
from embedded_agentic.result import Result, Timer  # noqa: E402

SECTION = "flow"

TOOLS = {
    "build": REPO / "mcu" / "tools" / "build" / "scripts" / "build_cli.py",
    "probe": REPO / "mcu" / "tools" / "probe" / "scripts" / "probe_cli.py",
    "serial": REPO / "mcu" / "tools" / "serial" / "scripts" / "serial_cli.py",
}


def call(tool: str, argv: List[str], workspace: Optional[str], timeout: int = 1800) -> Dict[str, Any]:
    """Invoke another tool and return its parsed result."""
    script = TOOLS[tool]
    if not script.is_file():
        return {"status": "error", "action": tool, "summary": "tool not found: {}".format(script)}
    cmd = [sys.executable, str(script)] + argv
    if workspace:
        cmd += ["--workspace", workspace]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "error", "action": tool,
                "summary": "{} timed out after {}s".format(tool, timeout)}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "action": tool,
                "summary": "{} produced unparseable output".format(tool),
                "details": {"stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}}


def stage(name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "stage": name,
        "status": result.get("status"),
        "summary": result.get("summary"),
        "backend": result.get("backend"),
        "risk": result.get("risk"),
        "details": result.get("details", {}),
        "warnings": result.get("warnings", []),
    }


def halted(stages: List[Dict[str, Any]], action: str, last: Dict[str, Any]) -> Result:
    """Stop the chain, preserving whatever the failing stage reported."""
    status = last.get("status", "error")
    if status == "confirmation_required":
        return Result(
            status="confirmation_required",
            action=action,
            summary="stopped at '{}': it needs explicit approval".format(stages[-1]["stage"]),
            risk=last.get("risk"),
            details={"stages": stages, "blocked_stage": stages[-1]["stage"],
                     **last.get("details", {})},
        )
    return Result(
        status="error",
        action=action,
        summary="stopped at '{}': {}".format(stages[-1]["stage"], last.get("summary")),
        details={"stages": stages, "failed_stage": stages[-1]["stage"]},
        next_steps=last.get("next_steps", []),
    )


# ------------------------------------------------------------------- stages
def do_build(args: argparse.Namespace, stages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    argv = ["build"]
    if args.board:
        argv += ["--board", args.board]
    if args.pristine:
        argv.append("--pristine")
    result = call("build", argv, args.workspace)
    stages.append(stage("build", result))
    return result


def do_flash(args: argparse.Namespace, image: Optional[str],
             stages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    argv = ["flash"]
    if image:
        argv += ["--file", image]
    if args.confirm:
        argv += ["--confirm", args.confirm]
    if args.serial_no:
        argv += ["--serial", args.serial_no]
    result = call("probe", argv, args.workspace, timeout=args.timeout)
    stages.append(stage("flash", result))
    return result


def do_observe(args: argparse.Namespace, stages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    argv = ["wait-for", "--pattern", args.pattern, "--timeout", str(args.observe_timeout)] \
        if args.pattern else ["capture", "--duration", str(args.observe_timeout)]
    if args.port:
        argv += ["--port", args.port]
    if args.out:
        argv += ["--out", args.out]
    result = call("serial", argv, args.workspace, timeout=int(args.observe_timeout) + 30)
    stages.append(stage("observe", result))
    return result


def artifact_from(result: Dict[str, Any]) -> Optional[str]:
    """The absolute path. The relative one is for humans to read, not to pass on:
    the next tool has its own working directory."""
    artifacts = (result.get("details") or {}).get("artifacts") or []
    if not artifacts:
        return None
    return artifacts[0].get("absolute") or artifacts[0].get("path")


# --------------------------------------------------------------------- main
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="flow", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["plan", "build-flash", "observe", "verify", "diagnose"])
    parser.add_argument("--board", help="board or target passed to build")
    parser.add_argument("--serial-no", dest="serial_no", help="probe serial number")
    parser.add_argument("--port", help="serial device or stable id")
    parser.add_argument("--pattern", help="boot pattern to wait for, e.g. 'Booting Zephyr'")
    parser.add_argument("--out", help="write the console capture here")
    parser.add_argument("--pristine", action="store_true")
    parser.add_argument("--observe-timeout", dest="observe_timeout", type=float, default=30.0)
    parser.add_argument("--timeout", type=int, default=300, help="per-stage seconds")
    parser.add_argument("--confirm", help="confirmation token, passed through to the gated stage")
    parser.add_argument("--workspace", help="workspace root (default: discovered)")
    parser.add_argument("--json", action="store_true", default=True)
    parser.add_argument("--text", dest="json", action="store_false")
    args = parser.parse_args(argv)

    try:
        r = Resolver(SECTION, Path(args.workspace) if args.workspace else None)
    except ConfigError as exc:
        return emit(fail("init", str(exc)), args.json)

    lint = lint_layers(r.workspace)

    # -------------------------------------------------------------- plan
    if args.action in ("plan", "diagnose"):
        build_info = call("build", ["detect"], args.workspace)
        probe_info = call("probe", ["list"], args.workspace, timeout=30)
        ports = call("serial", ["list"], args.workspace, timeout=30)

        missing: List[str] = []
        if build_info.get("status") != "ok":
            missing.append("build backend: {}".format(build_info.get("summary")))
        if probe_info.get("status") != "ok":
            missing.append("probe backend: {}".format(probe_info.get("summary")))
        if not (ports.get("details", {}).get("ports")):
            missing.append("no serial device visible on this host")
        if not r.project:
            missing.append(".embedded-agentic/project.json is absent — every parameter "
                           "will have to be passed on the command line")

        details = {
            "workspace": str(r.workspace),
            "build": {"backend": build_info.get("backend"),
                      "artifacts": build_info.get("details", {}).get("artifacts", [])},
            "probe": {"backend": probe_info.get("backend"), "status": probe_info.get("status")},
            "serial": {"ports": ports.get("details", {}).get("ports", [])},
            "operation_mode": r.operation_mode,
            "missing": missing,
        }
        status_ok = not missing
        result = (ok if status_ok else fail)(
            args.action,
            "ready: {} -> {}".format(build_info.get("backend"), probe_info.get("backend"))
            if status_ok else "{} thing(s) missing before a closed loop works".format(len(missing)),
            details=details, warnings=lint,
            next_steps=["flow build-flash --pattern '<boot banner>'"] if status_ok else
                       ["Fill the gaps listed in details.missing"],
        )
        return emit(result, args.json)

    stages: List[Dict[str, Any]] = []

    # ------------------------------------------------------------ observe
    if args.action == "observe":
        result = do_observe(args, stages)
        if result.get("status") != "ok":
            return emit(halted(stages, args.action, result), args.json)
        return emit(ok("observe", result.get("summary", "captured"),
                       details={"stages": stages}, warnings=lint,
                       validated_on="hardware"), args.json)

    # ------------------------------------------- build-flash and verify
    with Timer() as timer:
        build_result = do_build(args, stages)
        if build_result.get("status") != "ok":
            return emit(halted(stages, args.action, build_result), args.json)

        image = artifact_from(build_result)
        flash_result = do_flash(args, image, stages)
        if flash_result.get("status") != "ok":
            return emit(halted(stages, args.action, flash_result), args.json)

        if args.action == "verify":
            observe_result = do_observe(args, stages)
            if observe_result.get("status") != "ok":
                return emit(halted(stages, args.action, observe_result), args.json)

    size = (build_result.get("details") or {}).get("size", {})
    return emit(
        ok(args.action,
           "{} stage(s) completed; flashed {}".format(len(stages), image or "the previous build"),
           details={"stages": stages, "image": image, "size": size},
           warnings=lint + [w for s in stages for w in s.get("warnings", [])],
           duration_ms=timer.ms, validated_on="hardware",
           next_steps=["flow observe --pattern '<expected banner>'"] if args.action != "verify" else []),
        args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
