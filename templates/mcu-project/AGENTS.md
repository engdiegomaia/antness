# AGENTS.md — <project name>

> Project-specific context. The shared environment is in `.agents/`; this file is the
> part only you can write. Agents read it before touching hardware.

## Hardware

```
MCU:              <part number, e.g. STM32H743ZIT6 / MIMXRT1062DVL6A / ESP32-S3>
Silicon revision: <rev, and the errata document version you are working from>
Board:            <name + revision>
Core:             <Cortex-M7 / RISC-V / Xtensa>, FPU: <yes/no>, MPU: <yes/no>, D-cache: <yes/no>
Flash:            <size, internal/external QSPI>
RAM:              <size, regions: ITCM/DTCM/SRAM1/PSRAM>
Main clock:       <source -> SYSCLK>
Debug probe:      <J-Link / ST-Link / CMSIS-DAP + serial number>
Console:          <UART, pins, baud, /dev/serial/by-id/...>
Recovery:         <DFU / serial download / JTAG / boot switches — how to unbrick>
```

## Software

```
RTOS:             <none / Zephyr <ver> / FreeRTOS <ver> / NuttX <ver> / ESP-IDF <ver>>
SDK:              <version, pinned where>
Toolchain:        <arm-none-eabi-gcc version, pinned where>
Track skill:      <mcu/skills/...>
```

## Commands

```bash
# Build (from a clean tree, one command)
<command>

# Flash — CONFIRM the board first
<command>

# Test (host)
<command>

# Test (hardware)
<command>

# Size report
<command>
```

## Budgets

```
Flash budget:     <used> / <total>
RAM budget:       <used> / <total>
Boot time:        <target>
Worst-case ISR latency: <target>
Power (if battery): <avg current target, sleep state residency target>
```

## Project decisions

- Generated files committed: <yes/no — CubeMX output, defconfig, sdkconfig>
- Dynamic allocation in steady state: <forbidden / allowed because ...>
- Logging: <backend, production level>
- Regulated scope: <none / IEC 61508 SIL? / IEC 62304 class? / EU CRA>

## Known hazards on this board

<Bodge wires, errata workarounds, fragile connectors, a peripheral that must be
powered before another. Anything that would surprise someone touching it.>
