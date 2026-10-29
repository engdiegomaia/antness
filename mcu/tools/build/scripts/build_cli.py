#!/usr/bin/env python3
"""Build embedded firmware across west, ESP-IDF, CMake, Make and NuttX.

One command surface over five build systems. The backend is detected from the
repository unless it is pinned in project.json, and every result reports the
artifact path and the flash/RAM figures so the next step does not have to
go looking for them.

    build_cli.py detect
    build_cli.py build [--board B] [--pristine] [--jobs N]
    build_cli.py clean
    build_cli.py size
    build_cli.py artifacts
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _bootstrap import setup  # noqa: E402

setup(__file__)

from antness_runtime import ConfigError, Resolver, emit, fail, ok, run, which_tool  # noqa: E402
from antness_runtime.result import Result, Timer  # noqa: E402
from antness_runtime.risk import ConfirmationRequired, check_operation  # noqa: E402

SECTION = "build"

# risk per action — clean removes work, build does not touch the target
ACTION_RISK = {"detect": "low", "build": "low", "clean": "medium", "size": "low", "artifacts": "low"}


def confirmation_result(exc: ConfirmationRequired, backend: Optional[str]) -> Result:
    return Result(
        status="confirmation_required",
        action=exc.action,
        summary="{} needs explicit approval".format(exc.action),
        backend=backend,
        risk=exc.risk,
        details=exc.details(),
    )


# --------------------------------------------------------------- detection
def detect_backend(workspace: Path) -> Tuple[Optional[str], List[str]]:
    """Return (backend, evidence). Evidence is what the agent should report."""
    evidence: List[str] = []

    if (workspace / ".west").is_dir() or (workspace / "west.yml").is_file():
        evidence.append("west workspace marker present")
        return "west", evidence
    for manifest in workspace.glob("*/west.yml"):
        evidence.append("west manifest at {}".format(manifest.relative_to(workspace)))
        return "west", evidence

    if (workspace / "sdkconfig").is_file() or (workspace / "sdkconfig.defaults").is_file():
        evidence.append("ESP-IDF sdkconfig present")
        return "idf", evidence
    if (workspace / "main" / "idf_component.yml").is_file():
        evidence.append("idf_component.yml under main/")
        return "idf", evidence

    if (workspace / "nuttx").is_dir() and (workspace / "apps").is_dir():
        evidence.append("nuttx/ and apps/ side by side")
        return "nuttx", evidence
    if (workspace / "tools" / "configure.sh").is_file():
        evidence.append("NuttX tools/configure.sh present")
        return "nuttx", evidence

    if (workspace / "CMakeLists.txt").is_file():
        text = (workspace / "CMakeLists.txt").read_text(encoding="utf-8", errors="replace")
        if "find_package(Zephyr" in text:
            evidence.append("CMakeLists.txt calls find_package(Zephyr)")
            return "west", evidence
        if "$ENV{IDF_PATH}" in text or "idf_component_register" in text:
            evidence.append("CMakeLists.txt references IDF_PATH")
            return "idf", evidence
        evidence.append("CMakeLists.txt present")
        return "cmake", evidence

    if (workspace / "Makefile").is_file():
        evidence.append("Makefile present")
        return "make", evidence

    return None, ["no build system marker found in {}".format(workspace)]


# ----------------------------------------------------------------- helpers
ELF_SUFFIXES = (".elf", ".hex", ".bin", ".uf2")


def find_artifacts(workspace: Path, backend: str) -> List[Dict[str, Any]]:
    roots = {
        "west": ["build/zephyr", "build"],
        "idf": ["build"],
        "cmake": ["build", "out"],
        "make": ["build", "out", "."],
        "nuttx": ["nuttx"],
    }.get(backend, ["build"])

    found: List[Dict[str, Any]] = []
    seen = set()
    for rel in roots:
        base = workspace / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() not in ELF_SUFFIXES or not path.is_file():
                continue
            # skip bootloader/partition side artifacts unless nothing else exists
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(
                {
                    "path": str(path.relative_to(workspace)),
                    "absolute": str(resolved),
                    "bytes": path.stat().st_size,
                    "suffix": path.suffix.lower(),
                }
            )
    found.sort(key=lambda a: (a["suffix"] != ".elf", a["path"]))
    return found[:20]


_SIZE_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([0-9a-fA-F]+)\s+(\S+)\s*$", re.M)


def read_size(elf: Path, size_exe: Optional[str]) -> Dict[str, Any]:
    """Flash and RAM from `size`. Reported as numbers, never as an estimate."""
    if not size_exe:
        return {"error": "no `size` tool found; install arm-none-eabi-binutils or set build.size_exe"}
    result = run([size_exe, "-B", str(elf)], timeout=30)
    if not result.ok:
        return {"error": result.tail(5)}
    match = _SIZE_RE.search(result.stdout)
    if not match:
        return {"raw": result.stdout.strip()}
    text, data, bss, total = (int(match.group(i)) for i in (1, 2, 3, 4))
    return {
        "text_bytes": text,
        "data_bytes": data,
        "bss_bytes": bss,
        "flash_bytes": text + data,
        "ram_bytes": data + bss,
        "total_bytes": total,
        "note": "flash = .text + .data; ram = .data + .bss. Stack and heap are not included.",
    }


# ---------------------------------------------------------------- backends
def cmd_west(action: str, r: Resolver, args: argparse.Namespace, ws: Path) -> Tuple[List[str], Path]:
    west = r.resolve_tool("west_exe", args.tool, ["west"]) or "west"
    app = r.resolve_project("app_dir", args.app, default=".")
    if action == "clean":
        return [west, "build", "-t", "pristine"], ws
    board = r.resolve_project(
        "board", args.board, required=True,
        describe="Zephyr board name, e.g. nucleo_h743zi or esp32s3_devkitm",
    )
    argv = [west, "build", "-b", str(board), str(app)]
    argv += ["-p", "always" if args.pristine else "auto"]
    extra = r.resolve_project("extra_args", None, default=[])
    if isinstance(extra, list):
        argv += [str(a) for a in extra]
    return argv, ws


def cmd_idf(action: str, r: Resolver, args: argparse.Namespace, ws: Path) -> Tuple[List[str], Path]:
    idf = r.resolve_tool("idf_exe", args.tool, ["idf.py"]) or "idf.py"
    if action == "clean":
        return [idf, "fullclean"], ws
    argv = [idf]
    # `idf.py set-target` regenerates sdkconfig and is never a build side effect.
    # The target is recorded in project.json and verified, not silently applied.
    target = r.resolve_project("target", args.board)
    if target:
        r.remember_project(target=str(target))
    argv += ["build"]
    if args.jobs:
        argv += ["-j", str(args.jobs)]
    return argv, ws


def cmd_cmake(action: str, r: Resolver, args: argparse.Namespace, ws: Path) -> Tuple[List[str], Path]:
    cmake = r.resolve_tool("cmake_exe", args.tool, ["cmake"]) or "cmake"
    build_dir = str(r.resolve_project("build_dir", args.build_dir, default="build"))
    if action == "clean":
        return [cmake, "--build", build_dir, "--target", "clean"], ws

    preset = r.resolve_project("preset", args.preset)
    if preset:
        argv = [cmake, "--build", "--preset", str(preset)]
    else:
        argv = [cmake, "--build", build_dir]
    if args.jobs:
        argv += ["-j", str(args.jobs)]
    return argv, ws


def cmd_make(action: str, r: Resolver, args: argparse.Namespace, ws: Path) -> Tuple[List[str], Path]:
    make = r.resolve_tool("make_exe", args.tool, ["make"]) or "make"
    if action == "clean":
        return [make, "clean"], ws
    argv = [make]
    if args.jobs:
        argv += ["-j", str(args.jobs)]
    target = r.resolve_project("make_target", None)
    if target:
        argv.append(str(target))
    return argv, ws


def cmd_nuttx(action: str, r: Resolver, args: argparse.Namespace, ws: Path) -> Tuple[List[str], Path]:
    make = r.resolve_tool("make_exe", args.tool, ["make"]) or "make"
    nuttx_dir = ws / "nuttx" if (ws / "nuttx").is_dir() else ws
    if action == "clean":
        return [make, "distclean"], nuttx_dir
    argv = [make]
    if args.jobs:
        argv += ["-j", str(args.jobs)]
    return argv, nuttx_dir


BACKENDS = {"west": cmd_west, "idf": cmd_idf, "cmake": cmd_cmake, "make": cmd_make, "nuttx": cmd_nuttx}


# -------------------------------------------------------------------- main
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="build", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=sorted(ACTION_RISK))
    parser.add_argument("--backend", choices=sorted(BACKENDS), help="override detection")
    parser.add_argument("--board", help="board or target name")
    parser.add_argument("--app", help="application directory (west)")
    parser.add_argument("--preset", help="CMake preset")
    parser.add_argument("--build-dir", dest="build_dir", help="build directory")
    parser.add_argument("--tool", help="explicit path to the build tool")
    parser.add_argument("--jobs", type=int, help="parallel jobs")
    parser.add_argument("--pristine", action="store_true", help="force a from-scratch build")
    parser.add_argument("--timeout", type=int, default=1800, help="seconds (default 1800)")
    parser.add_argument("--confirm", help="confirmation token from a previous refusal")
    parser.add_argument("--workspace", help="workspace root (default: discovered)")
    parser.add_argument("--json", action="store_true", default=True)
    parser.add_argument("--text", dest="json", action="store_false", help="human-readable output")
    args = parser.parse_args(argv)

    try:
        r = Resolver(SECTION, Path(args.workspace) if args.workspace else None)
    except ConfigError as exc:
        return emit(fail("init", str(exc)), args.json)
    ws = r.workspace

    backend = args.backend or r.resolve_project("backend", None)
    evidence: List[str] = []
    if backend:
        r.provenance["backend"] = "cli" if args.backend else "project"
    else:
        backend, evidence = detect_backend(ws)
        r.provenance["backend"] = "detected"

    if args.action == "detect":
        artifacts = find_artifacts(ws, backend) if backend else []
        if not backend:
            return emit(
                fail("detect", "no build system detected",
                     details={"workspace": str(ws), "evidence": evidence},
                     next_steps=[
                         "Pin it explicitly: {\"build\": {\"backend\": \"west|idf|cmake|make|nuttx\"}} "
                         "in .antness/project.json",
                     ]),
                args.json,
            )
        return emit(
            ok("detect", "backend: {}".format(backend), backend=backend,
               details={"workspace": str(ws), "evidence": evidence,
                        "artifacts": artifacts, "tool": which_tool(
                            {"west": "west", "idf": "idf.py", "cmake": "cmake",
                             "make": "make", "nuttx": "make"}[backend])},
               parameter_context=r.parameter_context()),
            args.json,
        )

    if not backend:
        return emit(fail(args.action, "no build system detected", details={"evidence": evidence}), args.json)

    if args.action == "artifacts":
        found = find_artifacts(ws, backend)
        return emit(
            ok("artifacts", "{} artifact(s)".format(len(found)), backend=backend,
               details={"artifacts": found},
               next_steps=["probe flash --file <path>"] if found else ["build first"]),
            args.json,
        )

    if args.action == "size":
        elf_arg = r.resolve_project("elf", None) or (
            find_artifacts(ws, backend)[0]["absolute"] if find_artifacts(ws, backend) else None
        )
        if not elf_arg:
            return emit(fail("size", "no ELF found — build first", backend=backend), args.json)
        size_exe = r.resolve_tool(
            "size_exe", None,
            ["arm-none-eabi-size", "riscv64-unknown-elf-size", "xtensa-esp32s3-elf-size", "size"],
        )
        return emit(
            ok("size", "size of {}".format(Path(elf_arg).name), backend=backend,
               details={"elf": elf_arg, **read_size(Path(elf_arg), size_exe)},
               parameter_context=r.parameter_context()),
            args.json,
        )

    # build / clean
    try:
        warnings = check_operation(
            args.action, ACTION_RISK[args.action], r.operation_mode,
            target=str(ws),
            reasons=["removes build outputs; a from-scratch rebuild can take a long time"]
            if args.action == "clean" else [],
            recovery="rebuild from source",
            confirmed=args.confirm,
        )
    except ConfirmationRequired as exc:
        return emit(confirmation_result(exc, backend), args.json)

    try:
        cmd, cwd = BACKENDS[backend](args.action, r, args, ws)
    except ConfigError as exc:
        return emit(fail(args.action, str(exc), backend=backend,
                         parameter_context=r.parameter_context()), args.json)

    with Timer() as timer:
        result = run(cmd, cwd=cwd, timeout=args.timeout)

    details: Dict[str, Any] = result.as_details()
    details["workspace"] = str(ws)

    if not result.ok:
        summary = "build timed out after {}s".format(args.timeout) if result.timed_out \
            else "{} failed (exit {})".format(args.action, result.returncode)
        return emit(
            fail(args.action, summary, backend=backend, details=details,
                 parameter_context=r.parameter_context(), warnings=warnings,
                 duration_ms=timer.ms,
                 next_steps=["Read the tail of `output` above — the first error is the real one",
                             "mcu-build-resolver agent handles toolchain/linker/Kconfig failures"]),
            args.json,
        )

    artifacts = find_artifacts(ws, backend)
    details["artifacts"] = artifacts
    if artifacts and args.action == "build":
        size_exe = r.resolve_tool(
            "size_exe", None,
            ["arm-none-eabi-size", "riscv64-unknown-elf-size", "xtensa-esp32s3-elf-size", "size"],
        )
        details["size"] = read_size(Path(artifacts[0]["absolute"]), size_exe)

    if args.action == "build":
        r.remember_project(backend=backend, **({"board": args.board} if args.board else {}))
        r.commit(state={"last_build": artifacts[0]["path"] if artifacts else None,
                        "last_backend": backend})

    return emit(
        ok(args.action, "{} succeeded".format(args.action), backend=backend, details=details,
           parameter_context=r.parameter_context(), warnings=warnings, duration_ms=timer.ms,
           next_steps=["probe flash --file {}".format(artifacts[0]["path"])] if artifacts and args.action == "build" else []),
        args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
