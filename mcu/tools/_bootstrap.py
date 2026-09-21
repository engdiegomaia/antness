"""Importable shim so every tool script starts the same way.

    from _bootstrap import setup
    WORKSPACE = setup(__file__)
"""
from __future__ import annotations

import sys
from pathlib import Path


def setup(script_file: str) -> Path:
    start = Path(script_file).resolve()
    for candidate in (start, *start.parents):
        runtime = candidate / "shared" / "runtime"
        if (runtime / "embedded_agentic" / "__init__.py").is_file():
            if str(runtime) not in sys.path:
                sys.path.insert(0, str(runtime))
            return candidate
    raise SystemExit(
        "cannot find shared/runtime/embedded_agentic starting from {}".format(start)
    )
