#!/usr/bin/env python3
"""Generate .antness/project.json for a newly scaffolded project.

Takes the template, fills in what init-project.sh already knows, and drops the
sections that do not apply to the chosen stack. A Yocto project has no probe
backend, and leaving an empty one in the file invites somebody to fill it in
with something meaningless.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# Stacks whose work happens through mcu/tools/. The other stacks get a project
# config with hardware and compliance only.
TOOLED_STACKS = {"zephyr", "esp-idf", "freertos", "stm32", "nuttx"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--board", default="")
    parser.add_argument("--stack", required=True)
    parser.add_argument("--build-backend", dest="build_backend", default="")
    parser.add_argument("--template", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    template = pathlib.Path(args.template)
    if not template.is_file():
        print("template not found: {}".format(template), file=sys.stderr)
        return 1

    data = json.loads(template.read_text(encoding="utf-8"))

    data["_comment"] = [
        "Project context for {}. Versioned and shared with the team.".format(args.name),
        "Agents read this file, and so do the tools in mcu/tools/.",
        "Machine-specific values — tool paths, probe serial numbers, serial ports,",
        "operation_mode — belong in local.json, which is gitignored. A value in the",
        "wrong file breaks a colleague's clone; run `flow diagnose` to check.",
    ]

    board = args.board if args.board and args.board != "<fill in>" else ""
    data.setdefault("hardware", {})["board"] = board

    if args.stack in TOOLED_STACKS:
        data.setdefault("build", {})["backend"] = args.build_backend
        if args.stack in ("zephyr", "esp-idf"):
            data["build"]["board"] = board
    else:
        for section in ("build", "probe", "serial"):
            data.pop(section, None)
        data["_comment"].append(
            "The build/probe/serial sections were removed: the {} stack is driven by its "
            "own tooling, not by mcu/tools/.".format(args.stack)
        )

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
