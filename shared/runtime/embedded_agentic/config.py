"""Layered configuration resolution.

Precedence, highest first:

  1. CLI         explicit argument for this invocation
  2. project     .embedded-agentic/project.json  — versioned, shared with the team
  3. local       .embedded-agentic/local.json    — this machine only, gitignored
  4. state       .embedded-agentic/state.json    — last successful run, gitignored
  5. PATH        active discovery of a tool executable
  6. default     the tool's documented fallback

What belongs in each layer is not a style preference — it is what keeps a
repository clone-able by a colleague.

  project.json  hardware and project facts: board, soc, stack, device name,
                debug interface, speed, build preset, artifact paths.
                MUST NOT contain absolute tool paths or anything tied to one
                operator's bench.

  local.json    this machine: absolute paths to JLink.exe / openocd / west,
                the probe serial number on this desk, the serial adapter id,
                and operation_mode. MUST NOT contain chip or project facts —
                those belong in project.json where the team can see them.

  state.json    never a source of truth. The last values that actually worked,
                used only as a fallback so a second invocation needs fewer
                arguments. Safe to delete at any time.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONFIG_DIR = ".embedded-agentic"
PROJECT_FILE = "project.json"
LOCAL_FILE = "local.json"
STATE_FILE = "state.json"

# Keys that must never appear in project.json (they are machine-specific and
# break the moment a colleague clones the repository).
#
# `_path` is deliberately NOT a hint: recovery_path describes the hardware and
# belongs in project.json. The reliable signal for a machine-local value is an
# absolute path in the value, which is checked separately.
LOCAL_ONLY_HINTS = ("_exe",)
LOCAL_ONLY_KEYS = frozenset({"serial_no", "port", "operation_mode", "probe_serial", "adapter"})

# Keys that must never appear in local.json (they are project facts the team
# needs to see and review).
PROJECT_ONLY_HINTS = ("board", "soc", "device", "stack", "interface", "speed")


class ConfigError(Exception):
    """Raised when a required parameter cannot be resolved from any layer."""


def find_workspace(start: Optional[Path] = None) -> Path:
    """Walk upward looking for .embedded-agentic/, a VCS root, or AGENTS.md."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / CONFIG_DIR).is_dir():
            return candidate
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists() or (candidate / "AGENTS.md").is_file():
            return candidate
    return here


def project_config_path(workspace: Optional[Path] = None) -> Path:
    return (workspace or find_workspace()) / CONFIG_DIR / PROJECT_FILE


def local_config_path(workspace: Optional[Path] = None) -> Path:
    return (workspace or find_workspace()) / CONFIG_DIR / LOCAL_FILE


def state_path(workspace: Optional[Path] = None) -> Path:
    return (workspace or find_workspace()) / CONFIG_DIR / STATE_FILE


def _read(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError("cannot read {}: {}".format(path, exc))
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError("{} is not valid JSON: {}".format(path, exc))
    if not isinstance(data, dict):
        raise ConfigError("{} must contain a JSON object".format(path))
    return data


def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _get(section_data: Dict[str, Any], section: str, key: str) -> Any:
    """Look up key in data[section] first, then at the top level."""
    scoped = section_data.get(section)
    if isinstance(scoped, dict) and key in scoped:
        return scoped[key]
    return section_data.get(key)


def lint_layers(workspace: Optional[Path] = None) -> List[str]:
    """Report values sitting in the wrong layer. Advisory, not fatal."""
    ws = workspace or find_workspace()
    warnings: List[str] = []

    def walk(data: Any, prefix: str = "") -> List[Tuple[str, Any]]:
        out: List[Tuple[str, Any]] = []
        if isinstance(data, dict):
            for k, v in data.items():
                path = "{}.{}".format(prefix, k) if prefix else k
                if isinstance(v, dict):
                    out.extend(walk(v, path))
                else:
                    out.append((path, v))
        return out

    for key, value in walk(_read(project_config_path(ws))):
        leaf = key.rsplit(".", 1)[-1]
        if leaf in LOCAL_ONLY_KEYS or any(leaf.endswith(h) for h in LOCAL_ONLY_HINTS):
            warnings.append(
                "project.json holds a machine-specific value '{}'; move it to local.json "
                "or the repository stops working for a colleague".format(key)
            )
        elif isinstance(value, str) and (value.startswith("/home/") or ":\\" in value):
            warnings.append(
                "project.json holds an absolute path '{}' = {!r}; move it to local.json".format(key, value)
            )

    for key, _ in walk(_read(local_config_path(ws))):
        leaf = key.rsplit(".", 1)[-1]
        if leaf in PROJECT_ONLY_HINTS:
            warnings.append(
                "local.json holds the project fact '{}'; move it to project.json so the "
                "team shares it".format(key)
            )
    return warnings


class Resolver:
    """Resolves parameters across the layers and records where each came from.

    Provenance is not a debugging nicety. A build that silently used a stale
    value from state.json looks identical to one that used the reviewed project
    config, until it does not.
    """

    def __init__(self, section: str, workspace: Optional[Path] = None) -> None:
        self.section = section
        self.workspace = workspace or find_workspace()
        self.project = _read(project_config_path(self.workspace))
        self.local = _read(local_config_path(self.workspace))
        self.state = _read(state_path(self.workspace))
        self.provenance: Dict[str, str] = {}
        self._pending_project: Dict[str, Any] = {}

    # -- lookups ---------------------------------------------------------
    def project_value(self, key: str) -> Any:
        return _get(self.project, self.section, key)

    def local_value(self, key: str) -> Any:
        return _get(self.local, self.section, key)

    def state_value(self, key: str) -> Any:
        return _get(self.state, self.section, key)

    # -- resolution ------------------------------------------------------
    def resolve(
        self,
        key: str,
        cli: Any = None,
        default: Any = None,
        layers: Tuple[str, ...] = ("cli", "project", "local", "state", "default"),
        required: bool = False,
        describe: str = "",
    ) -> Any:
        """Resolve one parameter. `layers` restricts which layers may supply it."""
        for layer in layers:
            value = None
            if layer == "cli":
                value = cli
            elif layer == "project":
                value = self.project_value(key)
            elif layer == "local":
                value = self.local_value(key)
            elif layer == "state":
                value = self.state_value(key)
            elif layer == "default":
                value = default
            if value not in (None, "", []):
                self.provenance[key] = layer
                return value

        if required:
            hint = " ({})".format(describe) if describe else ""
            raise ConfigError(
                "'{}'{} is not set and cannot be guessed.\n"
                "Provide it explicitly, or add it to {}:\n"
                '  {{"{}": {{"{}": <value>}}}}'.format(
                    key, hint, project_config_path(self.workspace), self.section, key
                )
            )
        self.provenance[key] = "unset"
        return None

    def resolve_project(self, key: str, cli: Any = None, default: Any = None, **kw: Any) -> Any:
        """A project fact. Never read from local.json — that would hide it from the team."""
        return self.resolve(key, cli, default, layers=("cli", "project", "state", "default"), **kw)

    def resolve_tool(self, key: str, cli: Any = None, candidates: Optional[List[str]] = None) -> Optional[str]:
        """A tool executable. Never read from project.json — paths are machine-local."""
        from .discover import which_tool

        for layer, value in (("cli", cli), ("local", self.local_value(key)), ("state", self.state_value(key))):
            if value:
                self.provenance[key] = layer
                return str(value)
        for name in candidates or []:
            found = which_tool(name)
            if found:
                self.provenance[key] = "PATH"
                return found
        self.provenance[key] = "unset"
        return None

    # -- write-back ------------------------------------------------------
    def remember_project(self, **values: Any) -> None:
        """Queue confirmed project facts for write-back after a successful run."""
        for key, value in values.items():
            if value not in (None, "", []):
                self._pending_project[key] = value

    def commit(self, state: Optional[Dict[str, Any]] = None) -> None:
        """Persist confirmed facts and run state. Call only after success."""
        if self._pending_project:
            section = self.project.setdefault(self.section, {})
            if not isinstance(section, dict):
                section = {}
                self.project[self.section] = section
            changed = False
            for key, value in self._pending_project.items():
                if section.get(key) != value:
                    section[key] = value
                    changed = True
            if changed:
                _write(project_config_path(self.workspace), self.project)

        if state:
            section = self.state.setdefault(self.section, {})
            if not isinstance(section, dict):
                section = {}
                self.state[self.section] = section
            section.update({k: v for k, v in state.items() if v not in (None, "", [])})
            _write(state_path(self.workspace), self.state)

    def parameter_context(self) -> Dict[str, str]:
        return dict(self.provenance)

    @property
    def operation_mode(self) -> int:
        """1 execute, 2 execute with a risk summary, 3 require confirmation."""
        raw = os.environ.get("EMBEDDED_AGENTIC_OPERATION_MODE")
        if raw is None:
            raw = _get(self.local, self.section, "operation_mode")
        if raw is None:
            raw = self.local.get("operation_mode")
        try:
            mode = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 2
        return mode if mode in (1, 2, 3) else 2
