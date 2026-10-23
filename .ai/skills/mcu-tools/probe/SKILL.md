---
name: probe
description: >-
  Flash and inspect an MCU over J-Link, OpenOCD, probe-rs or pyOCD through one command
  surface — enumerate probes, program firmware, reset, halt, read registers and memory.
  Every action carries a declared risk level and high-risk actions require explicit
  approval bound to the specific target. Use whenever the task is to program a board,
  reset it, or read its state — including when the user only says "grava aí", "flash it",
  "reseta a placa" or "lê a memória".
track: mcu
kind: executable
risk: flash=high erase=high reset=high write-mem=high read-mem=low regs=low info=low list=low
---

# probe — flashing and target inspection

Executable tool. Run it; do not reimplement it, and do not work around its gates.

```bash
python mcu/tools/probe/scripts/probe_cli.py <action> [options]
```

## Actions and risk

| Action | Does | Risk |
|--------|------|------|
| `list` | Enumerate probes visible to this host, across every installed tool | low |
| `info` | Connect and report target state | low |
| `regs` | Read CPU registers | low |
| `read-mem` | Read a memory range | low |
| `halt` / `go` | Stop / resume the core | low |
| `reset` | Reset the target | **high** |
| `flash` | Program firmware | **high** |
| `write-mem` | Write target memory | **high** |
| `erase` | Erase flash | **high** |

`reset` is high risk deliberately. On a running system a reset is an outage, and whatever
state you were trying to observe is gone.

## The approval gate

A high-risk action does not run just because a build succeeded. It returns:

```json
{
  "status": "confirmation_required",
  "risk": "high",
  "details": {
    "confirm_token": "1f258ed9",
    "what_is_at_stake": ["overwrites application flash on the target",
                         "if the image is wrong, recovery needs the probe to still enumerate",
                         "image: build/zephyr/zephyr.hex (51284 bytes)"],
    "recovery_path": "BOOT0 jumper + DFU over USB-C",
    "how_to_proceed": "… re-run the same command with --confirm 1f258ed9"
  }
}
```

**Show this to the user — the target, what is at stake, and the recovery path — and wait.**
Then re-run with `--confirm <token>`.

The token is derived from backend + device + probe serial. An approval for one board does
not carry to the board next to it on the bench. That is the point.

`operation_mode` in `local.json` sets how much is gated:

| | low | medium | high | irreversible |
|---|---|---|---|---|
| `1` bench board, recovery known | run | run | run + warn | confirm |
| `2` default | run | run + warn | confirm | confirm |
| `3` customer or production unit | run + warn | confirm | confirm | confirm |

Nothing is auto-approved at `irreversible`, at any mode. See
`.ai/rules/shared/10-hardware-safety.md` — that policy applies whether or not this tool is in
the call path.

## Backends

| Backend | Needs | Key config |
|---------|-------|------------|
| `jlink` | `JLinkExe` | `device`, `interface`, `speed` |
| `openocd` | `openocd` | `openocd_interface`, `openocd_target` |
| `probe-rs` | `probe-rs` | `chip` (see `probe-rs chip list`) |
| `pyocd` | `pyocd` | `pyocd_target` (see `pyocd list --targets`) |

Auto-detected from what is installed. Pin `probe.backend` in `project.json` when more than
one is present, or results stop being reproducible.

## Configuration

```jsonc
// project.json — hardware facts the team shares
{
  "probe": {
    "backend": "jlink",
    "device": "STM32H743ZI",
    "interface": "SWD",
    "speed": "4000",
    "recovery_path": "BOOT0 jumper + DFU over USB-C"
  }
}
```

```jsonc
// local.json — this bench only, gitignored
{
  "probe": {
    "jlink_exe": "/opt/SEGGER/JLink/JLinkExe",
    "serial_no": "600100123",
    "operation_mode": 2
  }
}
```

`recovery_path` belongs in `project.json`: it describes the hardware, and it is printed in
every approval request. A board whose recovery path nobody wrote down is a board nobody
should be flashing unattended.

## Examples

```bash
# What can this host see
python mcu/tools/probe/scripts/probe_cli.py list

# Flash the last build (the image comes from state.json if --file is omitted)
python mcu/tools/probe/scripts/probe_cli.py flash
python mcu/tools/probe/scripts/probe_cli.py flash --confirm 1f258ed9

# .bin needs a load address — the tool refuses to invent one
python mcu/tools/probe/scripts/probe_cli.py flash --file app.bin --address 0x08000000

# Inspect without touching anything
python mcu/tools/probe/scripts/probe_cli.py regs
python mcu/tools/probe/scripts/probe_cli.py read-mem --address 0x20000000 --length 64
```

## What it will not do

- Pick a probe when several are attached. On a shared bench the wrong pick is somebody
  else's board.
- Flash a `.bin` without a load address.
- Downgrade its own risk levels from config. A tool does not get to decide how dangerous
  its operations are.
- Carry an approval across targets.

## After a failed flash

The target may be partially programmed. Verify before power-cycling — a half-written image
that boots far enough to reconfigure the debug pins is how boards become unreachable.
