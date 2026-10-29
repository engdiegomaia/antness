#!/usr/bin/env python3
"""Track small implementation steps and require evidence at every gate.

This tool records workflow evidence; it does not execute build, test, review,
or hardware commands. Those remain explicit operator/agent actions.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone


STATE_PATH = pathlib.Path(".antness/implementation.json")
STAGES = ("ready", "implemented", "verified", "reviewed")


class GateError(Exception):
    """A requested workflow transition is unsafe or incomplete."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_state(path: pathlib.Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError("No implementation session. Start one with `implementation_gate.py start`.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"Cannot read implementation state at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GateError(f"Invalid implementation state: {path}")
    steps = data.get("steps")
    if data.get("version") != 1 or not isinstance(steps, list) or not isinstance(data.get("task"), str):
        raise GateError(f"Unsupported or invalid implementation state: {path}")
    for item in steps:
        if (not isinstance(item, dict) or item.get("stage") not in STAGES
                or not isinstance(item.get("history"), list)):
            raise GateError(f"Invalid step record in implementation state: {path}")
    return data


def write_state(path: pathlib.Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="implementation.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def active_step(state: dict) -> dict:
    if not state["steps"]:
        raise GateError("No implementation step exists. Start one first.")
    return state["steps"][-1]


def emit(status: str, summary: str, **fields: object) -> None:
    print(json.dumps({"status": status, "summary": summary, **fields}, ensure_ascii=False))


def run(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.state_file)
    if args.command == "start":
        if path.exists():
            state = read_state(path)
            if state["steps"] and state["steps"][-1]["stage"] != "reviewed":
                raise GateError("The current step is not reviewed. Resolve or document it before starting another step.")
        else:
            state = {"version": 1, "task": args.task, "created_at": now(), "steps": []}
        if state["steps"] and state["task"] != args.task:
            raise GateError("A session already exists for another task; finish it before starting a new task.")
        step = {
            "number": len(state["steps"]) + 1,
            "title": args.step,
            "acceptance": args.acceptance,
            "stage": "ready",
            "history": [{"stage": "ready", "at": now(), "evidence": "Acceptance criteria recorded."}],
        }
        state["task"] = args.task
        state["steps"].append(step)
        write_state(path, state)
        emit("ok", "Step started; implement only this bounded change.", file=str(path), step=step)
        return 0

    state = read_state(path)
    step = active_step(state)
    if args.command == "status":
        emit("ok", "Current implementation gate state.", file=str(path), task=state["task"], step=step)
        return 0

    target = args.to
    current_index = STAGES.index(step["stage"])
    if current_index >= len(STAGES) - 1 or STAGES[current_index + 1] != target:
        expected = STAGES[current_index + 1] if current_index + 1 < len(STAGES) else "start a new step"
        raise GateError(f"Invalid transition {step['stage']} -> {target}; next allowed action: {expected}.")

    if target == "verified":
        step["checks"] = step.get("checks", [])
        check = {"command": args.check, "result": args.result, "at": now()}
        step["checks"].append(check)
        if args.result != "passed":
            write_state(path, state)
            emit("blocked", "Verification failed; stop and fix this step before proceeding.", file=str(path), step=step, next_actions=["Fix the failure", "Rerun the check", "Record passed evidence only after it succeeds"])
            return 2
        evidence = f"Check passed: {args.check}"
    else:
        evidence = args.evidence

    step["stage"] = target
    step["history"].append({"stage": target, "at": now(), "evidence": evidence})
    write_state(path, state)
    summary = "Step reviewed; start the next small step when ready." if target == "reviewed" else f"Step moved to {target}."
    emit("ok", summary, file=str(path), step=step)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--state-file", default=str(STATE_PATH), help="local progress file (default: %(default)s)")
    commands = result.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="start a bounded step or the next step after review")
    start.add_argument("--task", required=True, help="overall task name")
    start.add_argument("--step", required=True, help="one small implementation change")
    start.add_argument("--acceptance", required=True, help="observable completion criteria")
    advance = commands.add_parser("advance", help="record evidence and move exactly one gate")
    advance.add_argument("--to", choices=STAGES[1:], required=True)
    advance.add_argument("--evidence", help="implementation or review evidence")
    advance.add_argument("--check", help="validation command, required for verified")
    advance.add_argument("--result", choices=("passed", "failed"), help="validation outcome, required for verified")
    commands.add_parser("status", help="show the current step and gate")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "advance":
        if args.to == "verified":
            if not args.check or not args.result or args.evidence:
                emit("error", "verified requires --check and --result passed|failed; do not use --evidence.")
                return 2
        elif not args.evidence or args.check or args.result:
            emit("error", f"{args.to} requires --evidence and accepts no check result.")
            return 2
    try:
        return run(args)
    except GateError as exc:
        emit("error", str(exc), next_actions=["Inspect status and resolve the current gate before continuing"])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
