#!/usr/bin/env python3
"""Antness: hardware-aware embedded development CLI."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

VERSION = "0.1.0"
LOGO = """     .---.\n    /     \\\n   |  .-.  |\n   | (   ) |---o\n    \\ `-' /   o\n     `---'"""


def detect(root: Path) -> dict:
    checks = {
        "mcu": any((root / p).exists() for p in ("west.yml", "prj.conf", "sdkconfig", "FreeRTOSConfig.h", "platformio.ini")),
        "linux": any((root / p).exists() for p in ("conf/local.conf", "bblayers.conf", "buildroot", "Android.bp")),
    }
    frameworks = []
    for key, paths in {"zephyr": ("west.yml", "prj.conf"), "esp-idf": ("sdkconfig", "idf_component.yml"), "yocto": ("conf/local.conf", "bblayers.conf"), "buildroot": ("buildroot",)}.items():
        if any((root / p).exists() for p in paths): frameworks.append(key)
    return {"tracks": [t for t, found in checks.items() if found], "frameworks": frameworks}


def main() -> int:
    parser = argparse.ArgumentParser(prog="antness", description="Antness — hardware-aware embedded development framework\n" + LOGO, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".", help="project directory")
    parser.add_argument("--track", choices=("mcu", "linux"))
    parser.add_argument("--target")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("project", help="inspect project and detected workflows").add_argument("action", nargs="?", default="inspect", choices=("inspect",))
    sub.add_parser("doctor", help="diagnose project tools and setup")
    init = sub.add_parser("init", help="preview or create Antness project configuration")
    init.add_argument("--apply", action="store_true", help="write the displayed configuration")
    for cmd in ("build", "test"):
        action = sub.add_parser(cmd, help=f"run configured {cmd} command")
        action.add_argument("--args", nargs=argparse.REMAINDER, help="arguments passed to the existing tool")
    sub.add_parser("report", help="show latest operation evidence")
    args = parser.parse_args()
    root = Path(args.project).resolve()
    config = root / ".antness" / "project.json"
    detected = detect(root)
    data = {"project": root.name, **detected}
    if config.is_file():
        try: data["configuration"] = json.loads(config.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"Invalid {config}: {e}", file=sys.stderr); return 4
    if args.command in ("project", "doctor", "init"):
        if args.command == "doctor":
            data["tools"] = {name: shutil.which(name) for name in ("python3", "west", "idf.py", "bitbake", "cmake", "pytest")}
            data["status"] = "ok" if detected["tracks"] else "incomplete"
        if args.command == "init":
            proposed = {"schema_version": 1, "project": {"name": root.name}, "tracks": {t: {} for t in detected["tracks"]}, "evidence": {"directory": ".antness/results"}}
            data["proposed_configuration"] = proposed
            if args.apply:
                if config.exists(): print(f"Refusing to overwrite {config}", file=sys.stderr); return 4
                config.parent.mkdir(parents=True, exist_ok=True); config.write_text(json.dumps(proposed, indent=2) + "\n")
                data["created"] = str(config)
        if args.format == "json": print(json.dumps(data, indent=2))
        else:
            print(LOGO); print(f"Antness {VERSION}: {args.command} — {root}")
            print(json.dumps(data, indent=2))
        return 0 if args.command != "doctor" or data["status"] == "ok" else 5
    if args.command in ("build", "test"):
        track = args.track or (detected["tracks"][0] if len(detected["tracks"]) == 1 else None)
        if not track:
            print("Select --track mcu or --track linux (project detection is ambiguous or empty).", file=sys.stderr); return 4
        # MCU build operations remain delegated to the established, risk-aware CLI.
        if track == "mcu" and args.command == "build":
            tool = Path(__file__).parent / "mcu/tools/build/scripts/build_cli.py"
            if not tool.is_file(): print(f"Missing MCU build adapter: {tool}", file=sys.stderr); return 5
            command = [sys.executable, str(tool), "build", "--workspace", str(root)] + (args.args or [])
            return subprocess.run(command).returncode
        track_config = data.get("configuration", {}).get("tracks", {}).get(track, {})
        operation = track_config.get(args.command, {})
        command = operation.get("command") if isinstance(operation, dict) else None
        if not command:
            print(f"No {track}.{args.command}.command configured in {config}; Antness will not guess a command.", file=sys.stderr); return 4
        import shlex
        return subprocess.run(shlex.split(command), cwd=root).returncode
    print("This operation requires a configured Antness workflow; use 'antness init' and inspect the configuration first.", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
