"""Shared runtime for antness executable tools.

Standard library only. Every tool in mcu/tools/ imports from here so that
configuration resolution, risk gating and result formatting are identical
across tools.
"""
from __future__ import annotations

__version__ = "1.0.0"

from .config import (
    Resolver,
    ConfigError,
    project_config_path,
    local_config_path,
    state_path,
    find_workspace,
)
from .result import Result, emit, fail, ok
from .risk import RISK_LEVELS, ConfirmationRequired, check_operation
from .proc import CommandResult, run
from .discover import which_tool, list_serial_ports, resolve_serial_port

__all__ = [
    "Resolver",
    "ConfigError",
    "project_config_path",
    "local_config_path",
    "state_path",
    "find_workspace",
    "Result",
    "emit",
    "fail",
    "ok",
    "RISK_LEVELS",
    "ConfirmationRequired",
    "check_operation",
    "CommandResult",
    "run",
    "which_tool",
    "list_serial_ports",
    "resolve_serial_port",
]
