---
name: serial
description: >-
  Serial console operations — enumerate adapters by stable id, capture boot logs, send
  console commands, and wait for a pattern with a bounded timeout. Use whenever the task
  involves the target's UART console: reading boot output, checking a banner appeared,
  driving a shell, or diagnosing silence and garbage. Triggers on "abre o console",
  "captura o boot", "monitor serial", "o que a placa está imprimindo".
track: mcu
kind: executable
risk: list=low capture=low wait-for=low send=medium
---

# serial — console capture and interaction

Executable tool.

```bash
python mcu/tools/serial/scripts/serial_cli.py <action> [options]
```

Reading needs nothing but the OS. `capture`, `send` and `wait-for` need `pyserial`
(`pip install pyserial`); `list` works without it by reading `/dev/serial/by-id`.

## Actions

| Action | Does | Risk |
|--------|------|------|
| `list` | Enumerate serial devices with their stable ids | low |
| `capture` | Read for `--duration` seconds; optionally tee to a file | low |
| `wait-for` | Read until `--pattern` matches or `--timeout` expires | low |
| `send` | Write to the console, optionally wait for `--expect` | **medium** |

`send` is not low risk. A console command can reset the board, rewrite its configuration,
or drop it into a bootloader. It is gated at `operation_mode` 3.

## Stable ids, not ttyUSB0

`/dev/ttyUSB0` is whichever adapter enumerated first. On a bench with three boards that is
a coin flip, and the coin decides whose board you just talked to.

```bash
python mcu/tools/serial/scripts/serial_cli.py list
```

```json
{"ports": [{"device": "/dev/ttyUSB0",
            "stable_id": "/dev/serial/by-id/usb-FTDI_TTL232R_FT9K2LMR-if00-port0",
            "vid_pid": "0403:6001"}]}
```

Use the `stable_id`. When several devices match and none was named, the tool **refuses to
choose** and lists the candidates — it does not guess which board is yours.

Pin yours for this machine:
```jsonc
// local.json
{ "serial": { "port": "/dev/serial/by-id/usb-FTDI_TTL232R_FT9K2LMR-if00-port0" } }
```
The baud rate is a project fact and goes in `project.json`:
```jsonc
{ "serial": { "baud": 115200 } }
```

## Examples

```bash
# Capture 10 seconds of boot output to a file
python mcu/tools/serial/scripts/serial_cli.py capture --duration 10 --out boot.log

# Assert the firmware actually booted
python mcu/tools/serial/scripts/serial_cli.py wait-for --pattern "Booting Zephyr" --timeout 30

# Drive a shell and check the response
python mcu/tools/serial/scripts/serial_cli.py send --data "kernel version\r\n" --expect "Zephyr version"
```

`--data` interprets `\r`, `\n`, `\t` and `\xNN`. Most embedded shells want `\r\n`.

## Diagnosing no output

The tool reports what it saw; the interpretation is in
[`.ai/skills/shared/serial-console-debug`](../../shared/serial-console-debug/SKILL.md).
The short version:

| Symptom | Usually means |
|---------|---------------|
| Garbage at every baud | level mismatch or floating ground |
| Readable at a *different* baud | the system clock is not what the firmware thinks it is |
| Total silence | wrong pin, no power, reset loop, or TX/RX swapped |
| Permission denied | add yourself to `dialout`, log out and back in |

Do not run the tool under `sudo` to get past a permission error. The capture files end up
root-owned and the real problem is still there tomorrow.

## What it will not do

- Choose between several attached adapters.
- Run unbounded. Every read has a deadline and captures are truncated at 1 MB.
- Treat `send` as harmless.
