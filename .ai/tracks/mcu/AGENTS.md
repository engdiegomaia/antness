# AGENTS.md — MCU Track

> Extends the root `AGENTS.md`. Load together with `.ai/rules/shared/*`.

## Scope

Bare-metal and RTOS firmware on microcontrollers: Zephyr, FreeRTOS (incl. NXP MCUXpresso),
ESP-IDF, STM32 HAL/LL, NuttX. Includes on-MCU inference (TFLite Micro, CMSIS-NN, eIQ).

## Skill routing

| Detected in repo | Skill |
|------------------|-------|
| `west.yml`, `prj.conf`, `boards/*.overlay`, `Kconfig` + zephyr | `.ai/skills/mcu/zephyr-development/SKILL.md` |
| `sdkconfig`, `idf_component.yml`, `main/CMakeLists.txt` + idf | `.ai/skills/mcu/esp-idf-development/SKILL.md` |
| `FreeRTOSConfig.h`, MCUXpresso SDK tree, `board/pin_mux.c` | `.ai/skills/mcu/freertos-mcuxpresso/SKILL.md` |
| `*.ioc`, `stm32*_hal_conf.h`, `Core/Src/main.c` | `.ai/skills/mcu/stm32-hal-development/SKILL.md` |
| `nuttx/`, `apps/`, `boards/*/configs/*/defconfig` | `.ai/skills/mcu/nuttx-development/SKILL.md` |
| Cortex-M firmware without an RTOS; startup, linker script, registers, CMSIS | `.ai/skills/mcu/bare-metal-cortex-m/SKILL.md` |
| Embedded C++ firmware, templates, compile-time design, C interop | `.ai/skills/mcu/embedded-cpp/SKILL.md` |
| AUTOSAR Classic/Adaptive, ARXML, SWC/RTE, BSW, COM stack | `.ai/skills/mcu/autosar/SKILL.md` |
| Model files, `tflite`, `CMSIS-NN`, `eiq`, `esp-dl` | `.ai/skills/mcu/mcu-edge-ai/SKILL.md` |
| Test work | `.ai/skills/mcu/mcu-testing/SKILL.md` |
| Fault/hang/hardfault debugging | `.ai/skills/mcu/mcu-debug-trace/SKILL.md` |

## Executable tools — prefer them over ad-hoc shell

| Task | Tool |
|------|------|
| Compile, clean, footprint | `python mcu/tools/build/scripts/build_cli.py` |
| Flash, reset, read memory/registers | `python mcu/tools/probe/scripts/probe_cli.py` |
| Console capture, send, wait for a banner | `python mcu/tools/serial/scripts/serial_cli.py` |
| The whole cycle, or "why won't it work" | `python mcu/tools/flow/scripts/flow_cli.py` |

Start an unfamiliar workspace with `flow diagnose`. It reports the detected build backend,
available probes, visible serial devices and what is missing — in one call, read-only.

These tools enforce the risk gate described in `.ai/rules/shared/10-hardware-safety.md` at the
point of execution. Running `openocd` or `west flash` directly bypasses it. Do not.

## Before you touch firmware

State these, from the repo or by asking:

```
MCU:            part number + silicon revision
Core:           Cortex-M?/RISC-V/Xtensa, FPU present?, MPU present?
Memory:         flash size, RAM size, external PSRAM/QSPI?
Clock:          source, target SYSCLK
RTOS:           none / Zephyr / FreeRTOS / NuttX, tick rate
Debug probe:    SWD/JTAG adapter, or DFU/serial bootloader only
Build command:  the single command that builds from clean
```

## MCU hard rules

1. **No dynamic allocation after init.** Static, pool, or stack. If `malloc` exists in
   steady state, justify it or remove it.
2. **ISRs are short, non-blocking, and allocation-free.** No mutex take, no `printf`,
   no `k_sleep`, no FP without lazy stacking. Defer to a work queue/task.
3. **Every wait has a timeout.** `while (!(REG & FLAG));` is a hang in production.
4. **Shared data between ISR and task** is protected by a critical section, an atomic,
   or a lock-free queue — `volatile` alone is not protection.
5. **Stack sizes are calculated, not guessed.** Use worst-case analysis plus runtime
   high-water marks; leave documented headroom.
6. **Peripheral init is explicit.** Never rely on reset defaults you did not verify
   in the reference manual.
7. **Watchdog is fed from a health check, not from a timer.** Feeding unconditionally
   defeats the watchdog.
8. **Report flash/RAM delta** for every change that adds code or data.

## Concurrency review triggers

Invoke `rtos-concurrency-auditor` when a change touches: ISR handlers, priority
assignments, semaphores/mutexes/queues, DMA completion paths, shared buffers,
critical sections, low-power entry/exit, or `configTICK_RATE`/`CONFIG_SYS_CLOCK_TICKS`.

## Build-failure routing

MCU toolchain/linker/Kconfig errors -> `mcu-build-resolver` agent. Typical classes:
undefined reference from a missing Kconfig symbol, region overflow in the linker script,
devicetree binding mismatch, SDK component not added to the build, ABI mismatch
(hard-float vs soft-float), missing `-mcpu`/`-mfpu` consistency across objects.
