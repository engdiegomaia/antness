# Skill Index

Every skill, with the condition that should make an agent load it. Skills are loaded
**before** acting, not after a mistake.

## Shared (`shared/skills/`)

| Skill | Load when |
|-------|-----------|
| `cross-compilation` | Toolchain, sysroot, CMake toolchain file, ABI mismatch, host contamination |
| `serial-console-debug` | No console output, garbage output, setting up a new board's console |
| `hardware-lab-safety` | **Before instructing any physical procedure** — power, probing, irreversible ops |
| `requirements-traceability` | The product is in a regulated scope (safety, medical, automotive, CRA, 62443) |

## MCU (`mcu/skills/`)

| Skill | Load when |
|-------|-----------|
| `zephyr-development` | `west.yml`, `prj.conf`, `*.overlay` present |
| `esp-idf-development` | `sdkconfig`, `idf_component.yml` present |
| `freertos-mcuxpresso` | `FreeRTOSConfig.h`, MCUXpresso SDK tree present |
| `stm32-hal-development` | `*.ioc`, `stm32*_hal_conf.h` present |
| `nuttx-development` | `nuttx/` + `apps/`, NuttX `defconfig` present |
| `mcu-edge-ai` | TFLite Micro, CMSIS-NN, eIQ, ESP-DL, Ethos-U, any on-MCU model |
| `mcu-testing` | Writing or fixing firmware tests; setting up CI or a board farm |
| `mcu-debug-trace` | Hard fault, hang, corruption, intermittent failure, latency measurement |

## MCU executable tools (`mcu/tools/`)

These are not reference skills — they are CLIs with a `SKILL.md` describing how to drive
them. Prefer them over raw shell for anything that touches a board.

| Tool | Load when |
|------|-----------|
| `build` | Compiling firmware, checking size, locating artifacts |
| `probe` | Talking to a debug probe: enumerate, inspect, halt, reset, flash, erase |
| `serial` | Reading the console, waiting for a boot pattern, sending a command |
| `flow` | You want the whole loop — diagnose the setup, build, flash, verify, observe |

Start with `flow diagnose`; it reports exactly which piece of the loop is missing.

## Embedded Linux (`linux-embedded/skills/`)

| Skill | Load when |
|-------|-----------|
| `yocto-openembedded` | `bblayers.conf`, `*.bb`, `*.bbappend`, `kas*.yml` present |
| `torizon-os` | Toradex module with containers, `tcbuild.yaml`, TorizonCore Builder |
| `buildroot-development` | `configs/*_defconfig`, `package/*/Config.in` present |
| `kernel-driver-development` | Kernel source, out-of-tree module, `obj-m` |
| `device-tree` | Any `*.dts`, `*.dtsi`, `*.dtso` change; a peripheral that will not enumerate |
| `android-aosp` | `Android.bp`, `device/<vendor>/` present |
| `linux-edge-ai` | ONNX Runtime, TFLite delegate, NPU/GPU/VPU inference on the target |
| `board-bringup` | New board or new SoM, first boot, no console, DDR issues |
| `linux-testing` | `testimage`, ptest, kselftest, Labgrid, boot-time or soak testing |

## Selection order

1. Determine the track from the repository (root `AGENTS.md` section 2)
2. Load `shared/rules/*` — always
3. Load the track's `AGENTS.md`
4. Load the one skill that matches the task
5. Load a second skill only if the task genuinely spans two (e.g. a device tree change
   for an NPU used by `linux-edge-ai`)

Loading every skill is not thoroughness — it is context waste that degrades the work.
