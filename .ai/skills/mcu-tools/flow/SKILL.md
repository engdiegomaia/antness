---
name: flow
description: >-
  Chain build -> flash -> observe and aggregate the results, or report what is missing
  before the loop can close. Use when the task is the whole cycle rather than one step:
  "compila e grava", "build and flash", "sobe o firmware e vê se bootou", "por que o loop
  não fecha". Implements no build or probe logic of its own.
track: mcu
kind: executable
risk: inherited from the stage being run
---

# flow — closing the build/flash/observe loop

Executable orchestration. It calls `build`, `probe` and `serial` and joins their
structured output, so a failure is attributed to a **stage** rather than to "the flow".

```bash
python mcu/tools/flow/scripts/flow_cli.py <action> [options]
```

## Actions

| Action | Stages |
|--------|--------|
| `plan` | none — reports what would run, with which backends |
| `diagnose` | none — read-only: what is present, what is missing, and why |
| `build-flash` | build → flash |
| `verify` | build → flash → wait for a boot pattern |
| `observe` | capture or wait on the console only |

## Start with diagnose

```bash
python mcu/tools/flow/scripts/flow_cli.py diagnose
```

Answers the question that actually blocks people: *what is stopping the loop from
closing?* It reports the detected build backend, the probe tools present, the visible
serial devices, the current `operation_mode`, and a `missing` list. It also runs the
configuration layer lint and reports values sitting in the wrong file.

## The gate is inherited, not bypassed

Chaining is not a way around an approval. If flashing needs confirmation, the flow stops
at that stage and hands back the token, with the build already done:

```json
{
  "status": "confirmation_required",
  "summary": "stopped at 'flash': it needs explicit approval",
  "details": {
    "stages": [{"stage": "build", "status": "ok"},
               {"stage": "flash", "status": "confirmation_required"}],
    "confirm_token": "1f258ed9",
    "recovery_path": "BOOT0 jumper + DFU over USB-C"
  }
}
```

Show the user the target, the stakes and the recovery path. Then:

```bash
python mcu/tools/flow/scripts/flow_cli.py build-flash --confirm 1f258ed9
```

## The full cycle

```bash
python mcu/tools/flow/scripts/flow_cli.py verify \
    --board nucleo_h743zi \
    --pattern "Booting Zephyr" \
    --out boot.log
```

build → flash → wait for the banner. A result with three `ok` stages is the closest thing
to "it works on hardware" that a command can produce, and it says
`"validated_on": "hardware"` so nobody has to assume.

## Reading the result

Every result carries `stages`. On failure, `failed_stage` names where it stopped and the
failing stage's own `next_steps` are preserved. A build error never gets reported as a
flash problem.

## What it will not do

- Reimplement build or probe logic. Fix behaviour in the tool that owns it.
- Skip a confirmation because an earlier stage succeeded.
- Continue past a failed stage.
