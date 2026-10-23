# mcu/tools — executable tools

The knowledge skills in `.ai/skills/mcu/` tell an agent how to reason about a stack. These
tools let it **act**: compile, flash, and read the console, then feed the result back into
the next decision.

```
build   →  probe  →  serial
   └──────  flow  ──────┘
```

| Tool | Covers | Entry point |
|------|--------|-------------|
| [`build`](../../.ai/skills/mcu-tools/build/SKILL.md) | west, ESP-IDF, CMake, Make, NuttX | `build/scripts/build_cli.py` |
| [`probe`](../../.ai/skills/mcu-tools/probe/SKILL.md) | J-Link, OpenOCD, probe-rs, pyOCD | `probe/scripts/probe_cli.py` |
| [`serial`](../../.ai/skills/mcu-tools/serial/SKILL.md) | console capture, send, wait-for | `serial/scripts/serial_cli.py` |
| [`flow`](../../.ai/skills/mcu-tools/flow/SKILL.md) | build → flash → observe | `flow/scripts/flow_cli.py` |

## Contract

Every tool:

- takes an action plus flags, and prints **one JSON object** on stdout, nothing else
- declares a **risk level per action**, which config cannot downgrade
- resolves parameters through the shared layers and reports **where each one came from**
- has a **timeout on every external command** — a hung probe must not stall a session
- says **`validated_on`**: `host`, `simulator`, or `hardware`
- writes confirmed facts back to `project.json`, so context fills itself in through use

Exit codes: `0` ok, `1` error, `3` confirmation required, `4` blocked.

## Dependencies

Python 3.9+, standard library only. `pyserial` is optional and only for serial capture.
The actual toolchains (west, idf.py, openocd, JLinkExe, …) are found on `PATH` or pinned
per machine in `local.json` — this layer never installs or pins a toolchain, because that
decision belongs to the project (`.ai/rules/shared/20-toolchain-determinism.md`).

## Configuration

```
.embedded-agentic/project.json   versioned    board, device, interface, recovery path
.embedded-agentic/local.json     gitignored   tool paths, probe serial, operation_mode
.embedded-agentic/state.json     gitignored   last successful run — a fallback, never truth
```

Precedence: `CLI > project > local > state > PATH > default`, with tool paths never read
from `project.json` and project facts never read from `local.json`. `flow diagnose` lints
for values in the wrong file.

## Quick start

```bash
python mcu/tools/flow/scripts/flow_cli.py diagnose      # what is missing
python mcu/tools/build/scripts/build_cli.py detect      # which build system
python mcu/tools/probe/scripts/probe_cli.py list        # which probes
python mcu/tools/flow/scripts/flow_cli.py verify --pattern "Booting"
```

## Safety

`.ai/rules/shared/10-hardware-safety.md` is the policy. These tools enforce a subset of it at
the point of execution, and `.ai/hooks/guard-destructive-hardware.sh` enforces another subset
at the tool-call and commit boundary. Neither is complete on its own, and neither replaces
a human deciding what gets flashed.
