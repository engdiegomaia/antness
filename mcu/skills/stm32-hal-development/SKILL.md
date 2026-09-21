---
name: stm32-hal-development
description: STM32 development with HAL/LL drivers, CubeMX, CMake/Makefile builds, DMA, and low-power modes. Use when a .ioc file or stm32*_hal_conf.h is present.
track: mcu
---

# STM32 HAL / LL Development

## Orient first

```
*.ioc                       -> CubeMX project: MCU, clocks, pinmux, middleware
Core/Inc/stm32*_hal_conf.h  -> which HAL modules are compiled in
Core/Src/main.c             -> generated init, USER CODE sections
Drivers/STM32*_HAL_Driver/  -> HAL version
*.ld                        -> memory regions, section placement
```

Identify the exact part (`STM32H743ZIT6`) and family. H7/F7 have D-cache; F4/L4 do not.
G0/C0 have no FPU. This changes DMA and ISR rules.

## The CubeMX contract

Generated code is regenerated. **All hand-written code goes inside the markers:**

```c
/* USER CODE BEGIN 2 */
app_init();
/* USER CODE END 2 */
```

Code outside the markers is destroyed on the next generation. If a change cannot be
expressed inside a marker, change the `.ioc` and regenerate — do not hand-patch
`main.c`, `stm32*_hal_msp.c`, or the clock config.

Commit the `.ioc`. Whether generated sources are committed is a project decision —
state it in the project AGENTS.md.

## HAL vs LL

| Use | When |
|-----|------|
| HAL | Application-level, portability across families, complex peripherals (USB, SD, Ethernet) |
| LL | Time-critical paths, tiny footprint, register-level control |

Mixing is allowed and common: HAL for setup, LL in the hot path
(`LL_GPIO_SetOutputPin` instead of `HAL_GPIO_WritePin`).

## Transfer modes

```c
HAL_UART_Transmit(&huart2, buf, len, 100);       /* blocking — never in a task loop */
HAL_UART_Transmit_IT(&huart2, buf, len);         /* interrupt-driven */
HAL_UART_Transmit_DMA(&huart2, buf, len);        /* DMA, preferred for bulk */
```

DMA rules on this platform:
- Buffer must live in a memory region the DMA controller can reach. On H7, DMA1/2
  **cannot** access DTCM RAM — a buffer in `.dtcmram` silently fails. Place DMA buffers
  in `RAM_D1`/`SRAM1` explicitly via the linker script or `__attribute__((section(...)))`.
- With D-cache enabled (H7/F7): clean before TX (`SCB_CleanDCache_by_Addr`), invalidate
  after RX (`SCB_InvalidateDCache_by_Addr`), 32-byte aligned and sized. Or mark the
  region non-cacheable in the MPU.
- Always implement the error callback (`HAL_UART_ErrorCallback`), not just the complete
  callback. Overrun errors stop reception permanently if unhandled.

## Interrupts and callbacks

- HAL callbacks (`HAL_UART_RxCpltCallback`) run in ISR context — all ISR rules apply.
- `HAL_Delay` uses SysTick and blocks; it deadlocks if called from an ISR at a priority
  above SysTick.
- With an RTOS, `HAL_GetTick` must be backed by the RTOS tick, and the HAL tick
  priority must be the lowest — configured in CubeMX under SYS.

## Clock configuration

`SystemClock_Config()` is generated from the `.ioc`. Never hand-edit it. If a peripheral
runs at an unexpected rate, check the peripheral clock source in CubeMX's clock tree,
not the code. Verify at runtime with `HAL_RCC_GetPCLK1Freq()` and friends.

## Build

```bash
# CMake (CubeMX can generate a CMake project)
cmake -B build -DCMAKE_TOOLCHAIN_FILE=cmake/gcc-arm-none-eabi.cmake && cmake --build build
arm-none-eabi-size build/app.elf

# Flashing — CONFIRM the target first
STM32_Programmer_CLI -c port=SWD -w build/app.hex -v -rst
openocd -f interface/stlink.cfg -f target/stm32h7x.cfg -c "program build/app.elf verify reset exit"
```

Keep `-mcpu`, `-mfpu`, `-mfloat-abi` identical across every object and every library, or
the link silently produces a broken binary or fails with an ABI mismatch.

## Low power

`HAL_PWR_EnterSTOPMode` / `STANDBY` — verify which peripherals retain state and which
clocks stop. Debug is lost in Stop/Standby unless `DBGMCU` low-power debug bits are set
(dev only, disable in production). Wake sources must be configured before entry.

## Common failure modes

| Symptom | Cause |
|---------|-------|
| DMA transfer completes but data is stale/garbage | D-cache not maintained, or buffer in DTCM on H7 |
| UART RX stops after a while | overrun error not handled in `HAL_UART_ErrorCallback` |
| HardFault immediately on a float operation | FPU not enabled (`SCB->CPACR`) or `-mfpu` mismatch |
| `HAL_BUSY` forever | previous transfer never completed; error callback missing |
| Works with debugger, fails standalone | timing dependency, or a peripheral left enabled by the debugger |
| Hangs in `HAL_Delay` | called from an ISR above SysTick priority |
