---
name: build
description: >-
  Build embedded firmware across west (Zephyr), ESP-IDF, CMake, Make and NuttX through one
  command surface. Detects the backend from the repository, reports the artifact path and
  the flash/RAM figures, and records what worked. Use whenever the task is to compile,
  rebuild, clean, or find out how big the firmware is — including when the user only says
  "compila aí", "build it", "quanto ficou o binário" or "roda o build de novo".
track: mcu
kind: executable
risk: build=low clean=medium detect=low size=low artifacts=low
---

# build — firmware compilation

Executable tool. Run it; do not reimplement it.

```bash
python mcu/tools/build/scripts/build_cli.py <action> [options]
```

## Actions

| Action | Does | Risk |
|--------|------|------|
| `detect` | Identify the build system and report the evidence | low |
| `build` | Compile; report artifacts and flash/RAM delta | low |
| `clean` | Remove build outputs | medium |
| `size` | Flash and RAM from the ELF, via `size` | low |
| `artifacts` | List `.elf/.hex/.bin/.uf2` produced by the last build | low |

## Backends

Detected in this order, from markers in the workspace:

| Backend | Marker | Command it runs |
|---------|--------|-----------------|
| `west` | `.west/`, `west.yml`, `find_package(Zephyr)` | `west build -b <board> <app> -p auto` |
| `idf` | `sdkconfig`, `main/idf_component.yml`, `IDF_PATH` in CMakeLists | `idf.py build` |
| `nuttx` | `nuttx/` + `apps/`, `tools/configure.sh` | `make` in `nuttx/` |
| `cmake` | `CMakeLists.txt` | `cmake --build <dir>` or `--preset` |
| `make` | `Makefile` | `make` |

Override with `--backend`, or pin it in `project.json` so detection is not part of the
build's behaviour.

## Configuration

```jsonc
// .antness/project.json — versioned, shared with the team
{
  "build": {
    "backend": "west",
    "board": "nucleo_h743zi",      // Zephyr board / IDF target
    "app_dir": "app",
    "preset": "debug",             // CMake preset
    "build_dir": "build",
    "extra_args": ["--", "-DCONF_FILE=prj_debug.conf"]
  }
}
```

```jsonc
// .antness/local.json — this machine only, gitignored
{
  "build": {
    "west_exe": "/home/you/.local/bin/west",
    "size_exe": "/opt/gcc-arm-none-eabi/bin/arm-none-eabi-size"
  }
}
```

Tool paths never go in `project.json`: a colleague's clone would break on the first build.
Board and preset never go in `local.json`: the team cannot review what it cannot see.

## Examples

```bash
# What am I even looking at
python mcu/tools/build/scripts/build_cli.py detect

# Build, with the board supplied once and remembered afterwards
python mcu/tools/build/scripts/build_cli.py build --board nucleo_h743zi

# Build from scratch when incremental state is suspect
python mcu/tools/build/scripts/build_cli.py build --pristine

# Footprint
python mcu/tools/build/scripts/build_cli.py size
```

## Output

One JSON object on stdout. On success `details` carries `artifacts` and `size`:

```json
{
  "status": "ok",
  "action": "build",
  "backend": "west",
  "validated_on": "host",
  "details": {
    "artifacts": [{"path": "build/zephyr/zephyr.elf", "absolute": "/…", "bytes": 184320}],
    "size": {"flash_bytes": 51284, "ram_bytes": 8192,
             "note": "flash = .text + .data; ram = .data + .bss. Stack and heap are not included."}
  },
  "parameter_context": {"board": "project", "west_exe": "PATH"},
  "next_steps": ["probe flash --file build/zephyr/zephyr.elf"]
}
```

`parameter_context` says which layer supplied each value. A build that silently used a
stale value from `state.json` looks identical to one that used the reviewed project
config — until it does not.

## When a build fails

The tool returns `status: "error"` with the command, the exit code and the output tail.
**Read the first error, not the last** — the rest is cascade. Then hand it to the
`mcu-build-resolver` agent, which fixes toolchain, linker-region, Kconfig and devicetree
failures with minimal changes.

## What it will not do

- Guess a board name. `west build` without `-b` is a different build; the tool asks.
- Run `idf.py set-target` as a side effect. That regenerates `sdkconfig` and is a
  deliberate act, not a consequence of typing "build".
- Report a size it did not measure. If `size` is missing, it says so instead of estimating.
