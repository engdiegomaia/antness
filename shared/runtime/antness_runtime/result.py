"""Structured results.

Every tool prints one JSON object to stdout and nothing else. Human-readable
text goes to stderr. This means an agent never has to parse tool output with a
regex, and a failure carries the same shape as a success.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Result:
    status: str                                   # ok | error | blocked | confirmation_required
    action: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    parameter_context: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    duration_ms: Optional[int] = None
    backend: Optional[str] = None
    risk: Optional[str] = None
    validated_on: str = "host"                    # host | simulator | hardware

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "status": self.status,
            "action": self.action,
            "summary": self.summary,
        }
        if self.backend:
            out["backend"] = self.backend
        if self.risk:
            out["risk"] = self.risk
        out["validated_on"] = self.validated_on
        out["details"] = self.details
        if self.parameter_context:
            out["parameter_context"] = self.parameter_context
        if self.warnings:
            out["warnings"] = self.warnings
        if self.next_steps:
            out["next_steps"] = self.next_steps
        if self.duration_ms is not None:
            out["duration_ms"] = self.duration_ms
        return out


def ok(action: str, summary: str, **kw: Any) -> Result:
    return Result(status="ok", action=action, summary=summary, **kw)


def fail(action: str, summary: str, **kw: Any) -> Result:
    return Result(status="error", action=action, summary=summary, **kw)


def emit(result: Result, as_json: bool = True) -> int:
    """Print the result and return the process exit code."""
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        _human(result)
    return {"ok": 0, "confirmation_required": 3, "blocked": 4}.get(result.status, 1)


def _human(r: Result) -> None:
    mark = {"ok": "ok", "error": "FAIL", "blocked": "BLOCKED", "confirmation_required": "CONFIRM"}
    print("[{}] {}: {}".format(mark.get(r.status, r.status), r.action, r.summary))
    if r.backend:
        print("  backend: {}   validated on: {}".format(r.backend, r.validated_on))
    for key, value in r.details.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            print("  {}: {}".format(key, value))
    for warning in r.warnings:
        print("  warn: {}".format(warning), file=sys.stderr)
    for step in r.next_steps:
        print("  next: {}".format(step))
    if r.parameter_context:
        shown = ", ".join("{}<-{}".format(k, v) for k, v in sorted(r.parameter_context.items()))
        print("  parameters: {}".format(shown), file=sys.stderr)


class Timer:
    def __enter__(self) -> "Timer":
        self._t0 = time.monotonic()
        self.ms: Optional[int] = None
        return self

    def __exit__(self, *exc: Any) -> None:
        self.ms = int((time.monotonic() - self._t0) * 1000)
