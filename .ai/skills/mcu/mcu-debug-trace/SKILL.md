---
name: mcu-debug-trace
description: Debugging firmware faults — Cortex-M hard fault decoding, stack analysis, RTT/SWO tracing, SystemView, GDB/OpenOCD/pyOCD workflows, and intermittent-bug methodology.
track: mcu
---

# MCU Debugging & Tracing

## Method before tools

1. **Characterize**: reproducible or intermittent? boot, steady state, or under load?
   correlated with an event (radio TX, flash write, temperature, power)?
2. **Bisect the system**, not just the code: does it happen with peripherals disabled?
   with the RTOS scheduler not started? on a second board?
3. **Preserve evidence** before changing anything: the full fault register dump, the
   image hash, the exact build command.
4. Only then change one thing at a time.

An intermittent bug that "disappeared" after a rebuild did not disappear.

## Cortex-M fault decoding

On a HardFault, capture and decode these before anything else:

```
CFSR  (0xE000ED28)  -> UsageFault | BusFault | MemManage sub-registers
HFSR  (0xE000ED2C)  -> FORCED bit means an escalated configurable fault: read CFSR
MMFAR (0xE000ED34)  -> faulting data address (valid if CFSR.MMARVALID)
BFAR  (0xE000ED38)  -> faulting data address (valid if CFSR.BFARVALID)
```

Stacked frame (from MSP or PSP per EXC_RETURN bit 2): `R0 R1 R2 R3 R12 LR PC xPSR`.
**PC in that frame is the faulting instruction** — resolve it with
`arm-none-eabi-addr2line -e app.elf <pc>`.

```c
/* Minimal but sufficient handler */
void HardFault_Handler(void) {
    __asm volatile (
        "tst lr, #4      \n"
        "ite eq          \n"
        "mrseq r0, msp   \n"
        "mrsne r0, psp   \n"
        "b hard_fault_c  \n");
}
void hard_fault_c(uint32_t *frame) {
    /* frame[6] == PC. Persist frame + CFSR/HFSR/MMFAR/BFAR to a noinit region,
       then reset. Print on the next boot. */
}
```

Quick interpretation:
| Bit | Meaning | Usual cause |
|-----|---------|-------------|
| CFSR.IACCVIOL | instruction access violation | jumped to a bad function pointer |
| CFSR.PRECISERR | precise bus error, BFAR valid | dereferenced invalid/unclocked peripheral |
| CFSR.IMPRECISERR | imprecise bus error | buffered write to bad address; enable `-O0` or a DSB to localize |
| CFSR.UNALIGNED | unaligned access | packed struct cast, or `__attribute__((packed))` pointer |
| CFSR.UNDEFINSTR | undefined instruction | FPU not enabled, or corrupted flash/wrong ISA |
| CFSR.STKERR | stacking fault on exception entry | stack overflow |

Accessing a peripheral whose clock is not enabled is the single most common
`PRECISERR` on STM32/NXP.

## Stack overflow

- Enable the RTOS check (`configCHECK_FOR_STACK_OVERFLOW 2`, `CONFIG_THREAD_ANALYZER`).
- Enable the MPU stack guard where available.
- Paint stacks at init and scan for the high-water mark periodically during soak.
- A corrupted variable "for no reason" adjacent to a task stack is an overflow until
  proven otherwise.

## Non-intrusive tracing

| Mechanism | Cost | Use |
|-----------|------|-----|
| SEGGER RTT | ~1 µs per message, no pin | printf-style logging without a UART, works in ISRs |
| SWO / ITM | one pin, hardware FIFO | timestamped event trace, `printf` retargeting |
| ETM/ETB | trace port | full instruction trace — the only way to see what preceded a corruption |
| GPIO toggle + scope | ~10 ns | the most honest latency measurement available |
| SEGGER SystemView | RTT-based | RTOS task/ISR timeline, scheduling and priority inversion |
| Zephyr tracing / Percepio | build option | same, vendor-neutral |

For timing questions, GPIO + scope beats any software timestamp. For "which task ran
when", SystemView beats reasoning.

## GDB workflows

```bash
openocd -f interface/cmsis-dap.cfg -f target/stm32h7x.cfg &
arm-none-eabi-gdb build/app.elf -ex "target extended-remote :3333"

# or
pyocd gdbserver --target stm32h743xx
JLinkGDBServer -device STM32H743ZI -if SWD -speed 4000
```

Useful in-session:
```
monitor reset halt
info registers
x/16xw $sp                  # inspect the stack
p/x *(uint32_t*)0xE000ED28  # CFSR live
thread apply all bt         # with RTOS awareness enabled
watch g_counter             # data watchpoint — finds the writer of a corrupted variable
```
A hardware watchpoint on a corrupted variable identifies the culprit in one run. Reach
for it before adding logging.

## Intermittent and environmental bugs

Correlate against: power supply ripple under load, brownout during radio TX, temperature
(freeze spray / heat gun), EMI, a specific peripheral's DMA, and flash write operations.
An "impossible" bug that only happens on battery is a power design issue, not a software
one — measure the rail with a scope, not a DMM.

## Postmortem on the field device

Ship a crash handler that persists the fault context in a `__attribute__((section(".noinit")))`
region, resets, and reports it on the next boot (log, NVS, or telemetry). A device that
reboots silently teaches you nothing.
