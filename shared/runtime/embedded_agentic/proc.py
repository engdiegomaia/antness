"""Subprocess execution with the guarantees embedded tooling needs.

Every external command has a timeout. A hung probe or a build waiting on stdin
must not stall an agent session forever.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

DEFAULT_TIMEOUT = 300
MAX_CAPTURE = 200_000  # bytes of output kept per stream


@dataclass
class CommandResult:
    argv: List[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def tail(self, lines: int = 40) -> str:
        combined = (self.stdout + "\n" + self.stderr).strip().splitlines()
        return "\n".join(combined[-lines:])

    def as_details(self, full_output: bool = False) -> Dict[str, object]:
        return {
            "command": " ".join(shlex.quote(a) for a in self.argv),
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "output": (self.stdout + self.stderr) if full_output else self.tail(),
        }


def run(
    argv: Sequence[str],
    cwd: Optional[Path] = None,
    timeout: int = DEFAULT_TIMEOUT,
    env: Optional[Dict[str, str]] = None,
    stdin_text: Optional[str] = None,
) -> CommandResult:
    argv = [str(a) for a in argv]
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    # Keep tool output parseable and locale-independent.
    merged_env.setdefault("LC_ALL", "C")
    merged_env.setdefault("PYTHONUNBUFFERED", "1")

    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env=merged_env,
            input=stdin_text if stdin_text is not None else "",
        )
        return CommandResult(
            argv=argv,
            returncode=proc.returncode,
            stdout=proc.stdout[:MAX_CAPTURE],
            stderr=proc.stderr[:MAX_CAPTURE],
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            argv=argv,
            returncode=124,
            stdout=(exc.stdout or "")[:MAX_CAPTURE] if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr or "")[:MAX_CAPTURE] if isinstance(exc.stderr, str) else "",
            duration_ms=int((time.monotonic() - start) * 1000),
            timed_out=True,
        )
    except FileNotFoundError:
        return CommandResult(
            argv=argv,
            returncode=127,
            stdout="",
            stderr="executable not found: {}".format(argv[0]),
            duration_ms=int((time.monotonic() - start) * 1000),
        )
