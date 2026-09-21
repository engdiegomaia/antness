"""Locate the runtime package from a tool script without installing anything.

Tools are run as `python mcu/tools/<tool>/scripts/<tool>_cli.py`, from any
working directory, in a repository that may have been trimmed to one track.
Searching upward for shared/runtime is the only assumption that survives all
of that.
"""
from __future__ import annotations

import sys
from pathlib import Path


def add_runtime_to_path(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        runtime = candidate / "shared" / "runtime"
        if (runtime / "embedded_agentic" / "__init__.py").is_file():
            if str(runtime) not in sys.path:
                sys.path.insert(0, str(runtime))
            return candidate
    raise SystemExit(
        "cannot find shared/runtime/embedded_agentic starting from {}.\n"
        "Run this script from inside an embedded-agentic repository.".format(start)
    )
