# antness

```text
     .---.       Antness
    /     \\
   |  .-.  |
   | (   ) |---o
    \\ `-' /   o
     `---'
```

Antness is the hardware-aware embedded development CLI taking shape in this repository.
The initial command entry point is `python3 antness.py`; it can inspect and diagnose a
project, preview or create `.antness/project.json`, and delegate MCU builds to the existing
build CLI. Use `--format json` for machine-readable inspection. `init` only writes when
passed `--apply`, and refuses to overwrite an existing configuration. Linux build/test
commands can run when explicitly declared in the Antness project configuration.

```bash
python3 antness.py --help
python3 antness.py project inspect
python3 antness.py doctor
python3 antness.py init                 # preview; no files written
python3 antness.py init --apply         # create configuration after review
```

[![template](https://img.shields.io/badge/GitHub-use%20this%20template-2ea44f?logo=github)](https://github.com/micron-iot/antness/generate)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**A GitHub template for starting embedded projects that AI coding agents can work in
safely.** Two tracks — **MCU** and **embedded Linux** — with rules, roles, skills, review
agents, safety hooks and configuration for every major agent harness.

Uses `AGENTS.md` as the canonical instruction file for Claude Code 2.1.277+, OpenAI Codex,
and other native readers. Generated adapters support Cursor, Gemini CLI, GitHub Copilot,
and Continue without maintaining separate sources of truth.

---

## Start a project

**Click ["Use this template" → "Create a new repository"](https://github.com/micron-iot/antness/generate)**, then:

```bash
git clone https://github.com/<you>/<your-project>.git
cd <your-project>
./scripts/init-project.sh
```

Or entirely from the CLI:

```bash
gh repo create my-project --template micron-iot/antness --private --clone
cd my-project && ./scripts/init-project.sh
```

The script asks for your project name, stack and board, then:

- writes an `AGENTS.md` with a prefilled **Project context** section and the right
  build/flash/test commands for your stack
- removes the track you are not using, so agents are not loading irrelevant context
- installs the git `pre-commit` hook (secret scan, quality gate, artifact reject)
- generates the config for every agent harness
- replaces the template CI with project CI

Non-interactive:

```bash
./scripts/init-project.sh --non-interactive \
  --name thermal-gateway --stack torizon --board "Verdin iMX8MP Quad 4GB WB IT"
```

| Stack | Track | Primary skill loaded |
|-------|-------|----------------------|
| `zephyr` | MCU | Zephyr RTOS — west, devicetree, Kconfig, twister |
| `esp-idf` | MCU | ESP32 family — idf.py, components, NVS, OTA |
| `freertos` | MCU | FreeRTOS + NXP MCUXpresso — i.MX RT, LPC, Kinetis |
| `stm32` | MCU | STM32 HAL/LL — CubeMX, DMA, low power |
| `nuttx` | MCU | Apache NuttX — POSIX API, board ports, NSH |
| `yocto` | Linux | Yocto/OpenEmbedded — layers, recipes, bbappends, kas |
| `torizon` | Linux | Torizon OS — containers, TorizonCore Builder, overlays |
| `buildroot` | Linux | Buildroot — defconfigs, BR2_EXTERNAL, packages |
| `kernel` | Linux | Kernel and driver development — subsystems, debugging |
| `android` | Linux | AOSP — Soong, HALs, SELinux, board config |

**Then fill in the Project context section of `AGENTS.md`.** Part number, memory map,
console, recovery path, real build command. This single step does more for agent output
quality than everything else in this repository.

### Adding it to an existing project

```bash
git clone https://github.com/micron-iot/antness ~/tools/antness
~/tools/antness/install.sh /path/to/existing-project --track linux
```

Installs the environment alongside your code instead of scaffolding a new repository.
Use `--mode copy` for a self-contained install, `--mode link` (default) to symlink back
here so improvements propagate.

---

## Why this exists

Embedded work breaks general-purpose coding agents in specific ways:

- **Hardware operations are irreversible.** A wrong `dd`, a burned fuse, an overwritten
  bootloader — none of these is a `git revert`.
- **The context is outside the repository.** Datasheets, schematics, errata, memory maps,
  pinmux tables. An agent without them produces confident, wrong answers.
- **Resource budgets are correctness properties.** Flash, RAM, stack, ISR latency, power
  are requirements, not optimizations.
- **"It compiles" says almost nothing.** Whether a result came from a host build, a
  simulator, or real silicon is part of the result.

This template encodes those constraints so any agent working in the repository operates
under them.

## What you get

```
AGENTS.md                  canonical universal entrypoint
.ai/                       shared and track-specific agents, roles, rules, skills, adapters
  tracks/                  MCU and Linux scoped AGENTS.md instructions
mcu/tools/                 executable build, probe, serial and flow CLIs
.ai/hooks/                     destructive-command guard, quality gate, secret scan, pre-commit
.ai/mcp/                       MCP server catalogue for embedded work
shared/runtime/            antness_runtime — config resolution, risk gating,
                           structured results (stdlib only, Python 3.9+)
.antness/         machine-readable project context (project.json versioned,
                           local.json gitignored)
scripts/                   init-project, sync-agent-configs, validate, update-from-upstream
docs/                      getting started, skill index, multi-harness guide
.devcontainer/             host tooling (no SDKs — those are pinned per project)
```

### MCU track

Zephyr, FreeRTOS + NXP MCUXpresso, ESP-IDF, STM32 HAL/LL, NuttX — plus TinyML on-device
inference (TFLite Micro, CMSIS-NN, eIQ, ESP-DL, Ethos-U).

Review agents: `firmware-reviewer`, `rtos-concurrency-auditor`, `mcu-build-resolver`,
`memory-footprint-optimizer`, `hal-driver-writer`

Executable tools under `mcu/tools/` — agents call these rather than improvising shell,
so that every build, flash and capture is risk-gated and returns structured JSON:

| Tool | Does |
|------|------|
| `build` | detect backend, build, clean, size, artifacts — west / idf / cmake / make / nuttx |
| `probe` | list, info, regs, read-mem, rtt, halt, go, reset, flash, write-mem, erase — J-Link / OpenOCD / probe-rs / pyOCD |
| `serial` | list, capture, wait-for, send |
| `flow` | plan, diagnose, build-flash, verify, observe — the closed loop over the three above |

Anything that changes the device (`reset`, `flash`, `write-mem`, `erase`) requires a
confirmation token bound to backend + device + probe serial, so an approval for one board
on the bench cannot be replayed against another.

### Embedded Linux track

Yocto/OpenEmbedded, Torizon OS, Buildroot, kernel and driver development, device tree,
AOSP — plus edge inference on NPU/GPU/VPU (ONNX Runtime, TFLite delegates, i.MX8MP NPU).

Review agents: `yocto-recipe-reviewer`, `bsp-build-resolver`, `kernel-driver-reviewer`,
`device-tree-auditor`, `torizon-container-reviewer`

Full list with load conditions: [`docs/skill-index.md`](docs/skill-index.md)

## Multi-harness by design

AGENTS.md is the canonical entrypoint. All skills, agents, roles and rules live in the
vendor-neutral .ai/ tree. Run the sync script to refresh thin Gemini and Copilot pointer
files:

```bash
./scripts/sync-agent-configs.sh
```

The script does not create .claude, .codex, .cursor, or .continue directories. Harnesses
read AGENTS.md and follow its references to .ai/. Hardware safety relies on executable
tools, hooks, pre-commit, and CI, not vendor-specific discovery.

Details: [docs/multi-harness.md](docs/multi-harness.md)

## Safety posture

[`.ai/rules/shared/10-hardware-safety.md`](.ai/rules/shared/10-hardware-safety.md) defines
operations an agent must never run autonomously: fuse and eFuse burning, secure boot
enablement, bootloader overwrite on the only boot medium, partition table changes, mass
erase, boot environment edits, fleet update pushes. Each requires the agent to state the
target device, what becomes irreversible, and the recovery path — then wait.

`.ai/hooks/guard-destructive-hardware.sh` enforces a subset at the tool-call and commit
boundary, and CI tests that it actually blocks. It is a safety net, not the policy —
pattern matching always misses cases.

> **This does not make an agent safe to point at production hardware.** It removes a
> class of failures. A human still decides what gets flashed.

## Keeping up to date

Projects started from this template can pull environment improvements without touching
their own code or hardware context:

```bash
./scripts/update-from-upstream.sh --dry-run    # see what would change
./scripts/update-from-upstream.sh
```

`AGENTS.md` is never overwritten — it holds your project's hardware context. Upstream
changes to the environment sections are reported for you to merge.

## Contributing

New ecosystems, better failure-mode tables, and support for more harnesses are all
welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) — the bar for skill content is that
commands must be real and failure modes must come with their causes.

## License

MIT — see [`LICENSE`](LICENSE).
