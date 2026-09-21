# AGENTS.md — MCU Track

> Extends the root `AGENTS.md`. Load together with `shared/rules/*`.

## Scope

Bare-metal and RTOS firmware on microcontrollers: Zephyr, FreeRTOS (incl. NXP MCUXpresso),
ESP-IDF, STM32 HAL/LL, NuttX. Includes on-MCU inference (TFLite Micro, CMSIS-NN, eIQ).

## Skill routing

| Detected in repo | Skill |
|------------------|-------|
| `west.yml`, `prj.conf`, `boards/*.overlay`, `Kconfig` + zephyr | `skills/zephyr-development` |
| `sdkconfig`, `idf_component.yml`, `main/CMakeLists.txt` + idf | `skills/esp-idf-development` |
| `FreeRTOSConfig.h`, MCUXpresso SDK tree, `board/pin_mux.c` | `skills/freertos-mcuxpresso` |
| `*.ioc`, `stm32*_hal_conf.h`, `Core/Src/main.c` | `skills/stm32-hal-development` |
| `nuttx/`, `apps/`, `boards/*/configs/*/defconfig` | `skills/nuttx-development` |
| Model files, `tflite`, `CMSIS-NN`, `eiq`, `esp-dl` | `skills/mcu-edge-ai` |
| Test work | `skills/mcu-testing` |
| Fault/hang/hardfault debugging | `skills/mcu-debug-trace` |

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
