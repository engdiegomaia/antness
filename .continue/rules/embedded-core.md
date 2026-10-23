---
name: embedded-core
alwaysApply: true
---

# AGENTS.md — Embedded Agentic Development Environment

> Canonical, vendor-neutral instruction file. Edit this file and the scoped track files;
> generated harness adapters are compatibility outputs, never sources of truth.

## 1. What this repository is

An agent-ready development environment for embedded systems, split into two tracks:

| Track | Path | Targets |
|-------|------|---------|
| **MCU** | `mcu/` | Zephyr, FreeRTOS/MCUXpresso, ESP-IDF, STM32 HAL, NuttX |
| **Embedded Linux** | `linux-embedded/` | Yocto/OE, Torizon OS, Buildroot, kernel/drivers, AOSP |
| **Shared** | `shared/` | Rules, roles and skills valid for both tracks |

Both tracks cover **AI as a development tool** (agents writing/reviewing firmware and BSP)
and **AI on the device** (edge inference: TFLite Micro, CMSIS-NN, eIQ, ONNX Runtime, NPU/VPU).

## 2. Track selection (do this first)

Before any work, determine the track from the repository under development:

```
Has west.yml / prj.conf / CMakeLists.txt with zephyr   -> mcu/ + zephyr-development
Has sdkconfig / idf_component.yml                      -> mcu/ + esp-idf-development
Has FreeRTOSConfig.h + MCUXpresso SDK                  -> mcu/ + freertos-mcuxpresso
Has .ioc / stm32?xx_hal_conf.h                         -> mcu/ + stm32-hal-development
Has nuttx/ or defconfig with CONFIG_NUTTX              -> mcu/ + nuttx-development
Has conf/local.conf, bblayers.conf, *.bb, kas*.yml     -> linux-embedded/ + yocto-openembedded
Has docker-compose.yml on a Toradex module / tcb*.yaml -> linux-embedded/ + torizon-os
Has buildroot/ or configs/*_defconfig                  -> linux-embedded/ + buildroot-development
Has Kconfig + Makefile with obj-m / *.dts              -> linux-embedded/ + kernel-driver-development
Has Android.bp / device/<vendor>/                      -> linux-embedded/ + android-aosp
```

Then load: `shared/rules/*` + the track's `<track>/AGENTS.md` + the matching skill.

## 3. Non-negotiable rules

These override any generic coding advice. Full text in `shared/rules/`.

1. **Hardware is not undoable.** Never execute a command that writes to flash, eMMC,
   fuses (OTP/eFuse), bootloader environment, or secure boot keys without explicit,
   per-command user confirmation. See `shared/rules/10-hardware-safety.md`.
2. **Determinism over convenience.** Toolchain, SDK and layer revisions are pinned.
   Never bump a revision as a side effect of another task.
3. **Constrained resources are a correctness property.** Flash/RAM/stack budgets, ISR
   latency and power are requirements, not optimizations.
4. **No blocking in interrupt or atomic context.** Applies to MCU ISRs and to kernel
   code alike (`may_sleep` discipline).
5. **Reproducible builds.** Every build must be reproducible from a clean tree with a
   single documented command. Record it in the project's `AGENTS.md`.
6. **Validate on target, state where you validated.** Always report explicitly whether a
   result came from host build, simulator (QEMU/Renode), or real hardware.
7. **Never fabricate register values, pin numbers, or datasheet facts.** If a value is not
   in the repo, the datasheet, or the vendor docs you read, say you need it.

## 4. Roles

Personas in `shared/roles/`. Adopt the one matching the task; state which one you adopted.

| Role | Use for |
|------|---------|
| `firmware-engineer` | MCU application and driver code |
| `bsp-engineer` | Yocto/Buildroot layers, kernel config, boot chain |
| `hardware-bringup-engineer` | New board, first boot, signal-level debug |
| `edge-ai-engineer` | Model conversion, quantization, on-device inference |
| `embedded-security-engineer` | Secure boot, keys, attack surface, CRA/IEC 62443 |
| `embedded-qa-engineer` | HIL tests, coverage, regression on target |
| `release-engineer` | Images, OTA/Torizon Cloud updates, rollback |

## 5. Agents (subagent definitions)

Portable agent definitions live in `shared/agents/`, `mcu/agents/`, `linux-embedded/agents/`.
Each is a markdown file with YAML frontmatter (`name`, `description`, `tools`, `model`) —
the Claude Code subagent format, which Codex/Cursor/Continue read as plain prompt files.

Invoke proactively:
- Code written or modified in firmware -> `firmware-reviewer`
- Build failure on MCU toolchain -> `mcu-build-resolver`
- Build failure in BitBake/Buildroot -> `bsp-build-resolver`
- New/changed device tree -> `device-tree-auditor`
- Concurrency, ISR, or RTOS primitive changes -> `rtos-concurrency-auditor`
- Anything touching keys, boot, or update -> `embedded-security-reviewer`

## 6. Skills

Skills are `SKILL.md` files with YAML frontmatter under `<track>/skills/<name>/`.
They are loaded on demand — read the one matching the task before acting, not after.
`docs/skill-index.md` lists all of them with trigger conditions.

## 6a. Executable tools (MCU track)

`mcu/tools/` holds tools that **act on hardware** rather than describe it: compile,
flash, read the console, and chain the three. Run them; do not reimplement what they do
with ad-hoc shell commands.

```bash
python mcu/tools/flow/scripts/flow_cli.py diagnose    # what is missing before the loop closes
python mcu/tools/build/scripts/build_cli.py build
python mcu/tools/probe/scripts/probe_cli.py flash     # high risk — returns a token first
python mcu/tools/serial/scripts/serial_cli.py wait-for --pattern "Booting"
```

Each prints one JSON object, declares a risk level per action, and reports
`validated_on` as `host`, `simulator` or `hardware`. See `mcu/tools/README.md`.

**A high-risk action returns `status: "confirmation_required"` with a token.** Show the
user the target, what is at stake and the recovery path, then re-run with
`--confirm <token>`. The token is bound to that specific device — an approval for one
board never carries to another. Chaining through `flow` does not bypass this.

## 6b. Machine-readable project context

```
.embedded-agentic/project.json   versioned   board, chip, interface, recovery path, budgets
.embedded-agentic/local.json     gitignored  tool paths, probe serial, operation_mode
.embedded-agentic/state.json     gitignored  last successful run — a fallback, never truth
```

`project.json` is the same hardware context described in this file's project section, in
a form the tools can read and write back to. When a tool confirms a value it persists it,
so the context fills itself in through use instead of depending on someone remembering.

Precedence: `CLI > project > local > state > PATH > default`. Tool paths are never read
from `project.json`; project facts are never read from `local.json`. A value in the wrong
file breaks a colleague's clone — `flow diagnose` reports these.

## 7. Workflow

```
1. Identify track + skill (section 2)
2. Read the target's constraints: memory map, clock tree, power states, boot chain
3. Plan: state the change, the risk to the boot chain, and the rollback path
4. Implement smallest coherent change
5. Verify: host build -> static analysis -> unit test -> simulator -> hardware
6. Review with the matching agent
7. Report where each result was obtained (host/sim/hardware)
```

Never skip step 2. Most embedded agent failures are missing-context failures, not
reasoning failures.

## 8. Commit convention

```
<type>(<scope>): <description>

type:  feat fix refactor perf docs test chore ci bsp dts driver boot security
scope: board name, driver name, layer name, or subsystem (e.g. verdin-imx8mp, spi, meta-app)
```

Always state in the body which hardware the change was validated on, or that it was not.

## 9. Harness compatibility

| Harness | Entry point | Mechanism |
|---------|-------------|-----------|
| Claude Code | `AGENTS.md` (v2.1.277+) | Native fallback; no `CLAUDE.md` may exist on the repo path; skills/agents auto-discovered |
| OpenAI Codex | `AGENTS.md` | Native |
| Cursor | `.cursor/rules/*.mdc` | Generated from this file |
| Gemini CLI | `GEMINI.md` | Pointer file |
| DeepSeek / generic | `AGENTS.md` | Native (open standard) |
| GitHub Copilot | `.github/copilot-instructions.md` | Generated |
| Continue | `.continue/rules/` | Generated |

Regenerate native harness adapters with `./scripts/sync-agent-configs.sh` after editing
this file. `CLAUDE.md` is intentionally absent so Claude Code loads `AGENTS.md` directly.
Other harness-specific files are generated artifacts — changes to them are lost on the next sync.
