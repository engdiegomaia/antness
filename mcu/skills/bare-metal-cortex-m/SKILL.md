---
name: bare-metal-cortex-m
description: >-
  Bare-metal firmware engineering on ARM Cortex-M microcontrollers (M0/M0+/M3/M4/M7/M23/M33/M55)
  without an RTOS or Linux. Use for register-level peripheral drivers (GPIO, SysTick, timers/PWM,
  input capture, UART/USART, SPI, I2C, ADC, RTC, IWDG/WWDG, EXTI, NVIC, DMA), CMSIS-Core and
  vendor device headers, linker scripts and startup code (vector table, .data copy, .bss zero,
  reset handler, VTOR, bootloaders), the GNU Arm toolchain (arm-none-eabi-gcc, objdump, nm, size,
  readelf, .map files, newlib-nano, Makefiles/CMake, OpenOCD, GDB), clock-tree and PLL bring-up,
  flash wait states, low-power modes (WFI/WFE, Sleep/Stop/Standby), MPU and TrustZone-M, caches
  and TCM, and firmware CI. Trigger on STM32, NUCLEO, LPC, nRF, RP2040, SAM, "HAL vs LL vs
  registers", HardFault, MemManage, BusFault, UsageFault, "undefined reference to _sbrk",
  "region FLASH overflowed", "section .data will not fit", "my register write does nothing",
  "ISR never fires", "firmware hangs after enabling the cache", volatile/RMW races, or any
  .ld / startup_*.s / system_*.c / *_hal_conf.h / CMSIS file.
track: mcu
---

# Bare-Metal Firmware on ARM Cortex-M

Bare metal means there is no operating system, no process isolation, and no one else to blame: a single image owns the vector table, the clock tree, every peripheral register and the whole address space, and it runs forever on hardware that will not be rebooted by a user. The mental model a senior firmware engineer brings is **the datasheet is the API**. Behaviour is not defined by a library contract but by the silicon's configuration sequences, reset values, flag semantics and timing. Code is correct when it matches the reference manual's required ordering, and most bugs are ordering bugs, not logic bugs.

Three consequences shape everything below:

1. **Nothing is implicit.** Clocks, pin muxing, interrupt enables, memory initialization — if your code did not do it, it did not happen. The hardware's reset state is the only thing you get for free, and it is often not what you want.
2. **The compiler does not know about hardware.** It will delete a spin on a status flag, reorder stores, cache a value in a register, and garbage-collect your vector table. `volatile`, barriers and `KEEP()` exist to tell it otherwise.
3. **There is no safety net.** A stack overflow quietly corrupts `.bss`; a null-pointer write lands on a real peripheral; a missed interrupt flag clear spins the CPU forever. Defences (MPU guard regions, stack painting, watchdog, fault handlers that record state) have to be designed in up front, because postmortem debugging is all you will have in the field.

## Workflow

### Bringing up a new board or peripheral

1. **Gather the three documents** — datasheet (pinout, base addresses, electrical limits), reference manual (register offsets, bit fields, configuration sequences), and the Arm core guide for NVIC/SysTick/SCB/MPU. See `references/register-access-and-cmsis.md`.
2. **Get a build before you get a blink.** Toolchain, linker script, startup file, Makefile, flashing and a GDB connection first. Verify you can halt at `main`, read a global, and single-step. Debugging a peripheral while unsure whether your image even loads correctly wastes the most time.
3. **Clock tree before anything else.** Sources, PLL, bus prescalers, flash wait states, `SystemCoreClock`. Prove it with an MCO pin on a scope or by timing a known delay — every baud rate, timer period and ADC prescaler downstream is wrong if this is wrong.
4. **Enable the peripheral clock, then configure pins, then configure the peripheral.** Register writes to an unclocked peripheral read back as zero and vanish. This is the first thing to check when "my register write does nothing".
5. **Poll first, interrupt second, DMA third.** Get a blocking polled version working, then add interrupts, then DMA. Each step adds a class of bugs; introducing all three at once makes them indistinguishable.
6. **Write a thin project-owned driver interface** (`init`, `read`, `write`, status return) over the register-level implementation, so the application never touches vendor types. See `references/architecture-patterns.md`.

### Debugging misbehaving firmware

Work down the stack, cheapest check first:

| Symptom | First things to check |
|---|---|
| Register write has no effect | Peripheral clock not enabled; register write-protected or only writable while the peripheral is disabled; wrong struct offset from miscounted reserved padding |
| ISR never fires | Handler name does not match the vector table symbol (falls through to the weak default); interrupt enabled at the peripheral but not the NVIC (or vice versa); EXTI port mux pointing at a different port |
| ISR fires forever | Peripheral flag not cleared; flag cleared with `\|=` on a write-1-to-clear register; clear still in the write buffer at `bx lr` (clear early or `__DSB()`) |
| Hard fault immediately | Stack pointer or reset vector wrong; Thumb bit missing on a function pointer; `.data`/`.bss` init missing; unaligned or null access |
| Works in debug, fails in release | Missing `volatile`; a delay loop optimized away; relying on uninitialized memory; a race the slower debug build hid |
| Works until the cache is enabled | DMA buffer coherency on M7 — clean before TX, invalidate after RX, or mark the region non-cacheable |
| Random corruption, no pattern | Stack overflow into `.bss`/heap; a read-modify-write race with an ISR; a DMA length in bytes where the hardware counts items |
| Correct value then garbage at higher clock | Flash wait states not raised before the frequency; derived dividers (baud, timer, ADC) not recomputed |

Then: read the fault status registers (`CFSR`, `HFSR`, `MMFAR`, `BFAR`) and the stacked `PC`/`LR` rather than staring at a `while(1)`; put a GPIO toggle on the path and look at it with a logic analyzer; and when software and hardware disagree, the scope is the ground truth.

### Reviewing or porting firmware

Port by *layer*, not by file: the application and middleware should compile unchanged, and only the HAL implementation and the linker/startup files should change. If application code must change to move parts, the layering has leaked. For a review, run the checklist at the bottom of this file.

## Decision rules

| Situation | Choose | Why |
|---|---|---|
| Need peripheral register definitions | Vendor CMSIS device header, vendored into the repo and version-pinned | Machine-generated offsets and masks; hand-typed addresses are the top bring-up bug source |
| Need core features (NVIC, SysTick, MPU, barriers, intrinsics) | CMSIS-Core | Standardized, correct, portable across vendors |
| Need a peripheral driver | Your own register-level driver behind a project-owned interface | Determinism, size, and you can read every wait loop |
| Complex stack (USB, Ethernet, SD/FS, BLE) | Vendor HAL or a proven third-party stack | Reimplementing is months of work for no differentiation |
| Mixing both on one peripheral | Never | The HAL's internal state desynchronizes from the hardware |
| Toggling a pin from >1 context | Atomic set/reset register (`BSRR`, SET/CLR) | One bus write, no read-modify-write race, and faster |
| Protecting a multi-register update | Save/restore `PRIMASK`, or `BASEPRI` on M3+ | A bare `__enable_irq()` breaks nesting; `BASEPRI` keeps high-priority ISRs alive |
| Timing a delay | SysTick tick counter with wraparound-safe comparison | A calibrated `for` loop changes with optimization level and clock |
| Sub-microsecond timing or precise periods | A hardware timer, not SysTick | SysTick is 24-bit, shared, and interrupt-latency-bound |
| Moving bulk data to/from a peripheral | DMA | Frees the CPU and makes servicing deterministic at high rates |
| Variable-length UART frames | Circular DMA + idle-line interrupt | Avoids per-byte interrupts and handles unknown lengths |
| Dynamic memory in firmware | Avoid; use static pools | Fragmentation and non-deterministic timing with no good failure path |
| Several independent timed activities, or a stack that assumes threads | Move to an RTOS | A super-loop hand-rolling blocking I/O becomes an RTOS, badly |
| "Run slowly to save power" vs "race to sleep" | Usually race to sleep | Dynamic energy per operation is roughly fixed while leakage and fixed overhead accrue with time — but verify the deep state is actually reachable |
| Need to sandbox untrusted/third-party code on M3/M4/M7 | MPU + unprivileged thread mode + SVC gate | TrustZone does not exist on Armv7-M |
| Need isolation of secrets/keys on M23/M33/M55 | TrustZone-M, and prefer TF-M over a hand-rolled secure world | Getting SAU, veneers and argument validation right by hand is a security liability |

## Pitfalls

**Clocks and ordering**

- Writing peripheral registers before enabling that peripheral's clock. Reads return 0, writes disappear, nothing faults. Always the first suspect.
- Raising the system clock before increasing flash wait states — the core fetches garbage instructions and hard-faults. On the way down, lower the clock first, then the wait states. Getting this backwards is a classic un-debuggable failure.
- Changing the system clock and not recomputing everything derived from it: SysTick reload, UART baud divisors, timer prescalers, ADC prescaler, SPI/I2C dividers. Presents as "I raised the clock and my UART turned to garbage".
- Waiting for an oscillator ready flag in an unbounded loop. A failed crystal then bricks the product in the field; use a bounded timeout and fall back to the internal RC.
- Waking from Stop mode and assuming the PLL is still running. On most parts the system clock reverts to the internal RC on wake and you must reconfigure it.

**Registers and the compiler**

- Missing `volatile` on a status-flag spin — the optimizer reads once and loops forever. Appears only in release builds.
- Assuming `volatile` means atomic, ordered against the hardware, or a barrier. It is none of those. Clearing an interrupt flag at the very end of an ISR can leave the write in the write buffer and re-enter the handler; clear early or `__DSB()`.
- `|=` on a write-1-to-clear register clears *every* pending bit, not the one you named. Assign, do not OR.
- OR-ing a value into a multi-bit field without clearing the field first. Works from the reset value, fails on reconfiguration.
- Miscounted reserved padding in a hand-written peripheral struct, shifting every later member. Assert `offsetof` at each gap.
- C bitfields for hardware registers — implementation-defined layout and access width.
- `1 << 31` without `UL`: signed overflow, undefined behaviour.
- Clobbering the MODER/pin-mux bits that reset to the debug-port alternate function, killing SWD on the next reset.

**Linker and startup**

- Forgetting `KEEP()` on the vector table section — `--gc-sections` discards it and the part does not boot.
- Taking the *value* of a linker-defined symbol instead of its address. `extern uint32_t _sdata; ... &_sdata` is the correct form; using `_sdata` directly reads whatever happens to be at that address.
- A reset vector whose value has the Thumb bit clear — immediate hard fault, because every Cortex-M branch target must be odd.
- Skipping `.bss` zeroing or `.data` copy and then being surprised that globals hold junk, or that initialized globals work in the debugger (which may load them) but not from a cold boot.
- Not running `.init_array` and wondering why C++ static constructors never executed.
- Sizing the stack by guesswork. Lazy FPU stacking adds an extra frame on M4F/M7, and the collision with the heap or `.bss` is silent. Paint the stack and check the high-water mark; put an MPU no-access guard below it.
- Forgetting to set `VTOR` after a bootloader jumps to the application — interrupts then vector into the bootloader. M0 has no `VTOR` at all and needs a RAM-remap trick or a fixed layout.

**Interrupts and DMA**

- A typo in an ISR name. The linker silently keeps the weak default handler and your interrupt "never fires".
- Cortex-M priority registers implement only the upper bits of a byte (typically 4 on M3/M4/M7, 2 on M0/M0+), so priority values must be shifted, and lower numeric value means higher priority. Writing raw small integers gives surprising priority inversions.
- Enabling an interrupt at only one of the two required places (the peripheral and the NVIC).
- Long ISRs, `printf`, `malloc` or floating point in an ISR. Defer work to the main loop via a flag or a ring buffer.
- DMA transfer counts expressed in bytes when the controller counts *items* of the configured width.
- Reconfiguring a DMA stream without disabling it and waiting for the enable bit to read back as 0, and without clearing all transfer flags first.
- DMA buffers in cached memory on M7 — clean before a memory-to-peripheral transfer, invalidate after a peripheral-to-memory one, with cache-line-aligned and size-rounded buffers. Or place them in a non-cacheable region. Also check the DMA engine can physically reach the RAM you chose; tightly-coupled memories often are not reachable.
- EXTI lines sharing one vector (e.g. 5–9, 10–15): the ISR must demultiplex via the pending register.

**Serial buses**

- Unbounded `while (!(SR & FLAG));` loops. Every hardware wait needs a timeout and an error return, or one unplugged sensor hangs the product.
- Disabling a UART or entering sleep on TXE instead of TC — the last character is still in the shift register and gets truncated.
- Dropping SPI chip-select on TXE rather than on BSY clearing, cutting the last byte.
- I2C address confusion between the 7-bit value and the shifted 8-bit value.
- No bus-recovery path for an I2C slave holding SDA low; the 9-clock recovery sequence is cheap insurance.
- Assuming the I2C driver ports across STM32 families — the older F1/F4-style event-flag peripheral and the newer `TIMINGR`/`NBYTES`/`AUTOEND` peripheral are completely different programming models.

**Analog, time and reliability**

- ADC sampling time too short for a high-impedance source, which shows up as wrong readings and apparent crosstalk from the previously converted channel.
- Leaving an ADC pin in digital input mode instead of analog mode.
- Running the RTC calendar from the internal low-speed RC (percent-level error) instead of a 32.768 kHz crystal.
- Forgetting a step of the backup-domain unlock sequence — RTC writes then silently do nothing.
- Re-initializing the RTC on every boot instead of detecting an already-running clock via a backup-register magic value.
- Kicking the watchdog from a timer ISR. That proves only that interrupts still run; kick it from the supervisory loop after each subsystem reports alive.
- Leaving debug-freeze bits enabled in production so the watchdog never fires on a real hang.
- Not reading and logging the reset-cause flags at boot, so field watchdog resets go unnoticed.

**Performance and portability**

- `double` arithmetic on an M4F, whose FPU is single-precision only — it silently falls back to slow software emulation. Use `float` and the `f` suffix on literals.
- Mismatched `-mfloat-abi` between objects and libraries, producing link errors or silent ABI breakage.
- Optimizing before measuring. Use the DWT cycle counter (not available on M0/M0+) or a GPIO toggle, on a warmed-up steady state.
- Assuming a feature exists on the whole family: bit-banding is M3/M4 only, caches and TCM are M7+, `VTOR` is absent on M0, TrustZone-M is Armv8-M only, the Armv7-M and Armv8-M MPUs have different programming models.

## Review checklist

**Build and image**
- [ ] Reproducible command-line build; no IDE-only step; toolchain and SDK versions pinned
- [ ] `-Wall -Wextra` clean; warnings not suppressed
- [ ] `-ffunction-sections -fdata-sections -Wl,--gc-sections` with `KEEP()` on the vector table
- [ ] Flash and RAM usage from `size` tracked as a metric; map file reviewed for unexpected library pull-ins
- [ ] Linker script bounds the heap and leaves a checked gap between stack and `.bss`/heap

**Startup and memory**
- [ ] Vector table complete, initial SP and reset vector correct, Thumb bit set
- [ ] `.data` copied, `.bss` zeroed, `.init_array` run, `SystemInit` called, trap on return from `main`
- [ ] Real fault handlers that capture the stacked frame and `CFSR`/`MMFAR`/`BFAR`, not bare `while(1)`
- [ ] Stack sized from worst-case depth including ISR nesting and lazy FPU frames; painting or MPU guard in place
- [ ] No dynamic allocation after init; none in any ISR

**Hardware access**
- [ ] All register accesses `volatile`-qualified, via CMSIS or asserted struct overlays
- [ ] Peripheral clock enabled before first access to every peripheral
- [ ] Write-1-to-clear registers assigned, not OR-ed; multi-bit fields cleared before being set
- [ ] Atomic set/reset registers used for outputs touched from multiple contexts
- [ ] Critical sections save and restore the previous mask

**Concurrency and timing**
- [ ] Every ISR name matches a vector table entry (verified in the map file, not by eye)
- [ ] Interrupt priorities shifted into the implemented bits and documented in one table
- [ ] All ISR/main shared state `volatile`, single-word, or guarded; ring buffers single-producer/single-consumer
- [ ] ISRs short; no blocking I/O, allocation or logging inside them
- [ ] Every hardware wait loop has a bounded timeout and returns an error

**Robustness**
- [ ] Watchdog enabled in production, kicked from a supervisory path that proves the system is alive
- [ ] Reset cause read and logged at boot
- [ ] Clock-source failure has a defined fallback
- [ ] Brown-out / power-loss behaviour considered for any flash write
- [ ] Error codes propagated; no silently swallowed failures

**Structure**
- [ ] Application and middleware free of vendor headers and register access; testable on a host with a mock HAL
- [ ] Pin map, interrupt priority table, clock tree and memory budget documented in-tree
- [ ] CI builds every target variant, runs host unit tests, and tracks size regressions

## Reference map

| File | Read it when |
|---|---|
| `references/register-access-and-cmsis.md` | Declaring registers, `volatile` and atomicity, struct overlays and padding, bit idioms, read-modify-write races, CMSIS components, integrating a vendor device pack, HAL vs LL vs raw registers |
| `references/toolchain-and-build.md` | Build stages and `arm-none-eabi-*` flags, `-mcpu`/`-mfloat-abi`/`--specs`, objcopy/size/nm/objdump/readelf and map-file forensics, Makefiles for firmware, OpenOCD + GDB, off-target testing and emulation, firmware CI |
| `references/linker-and-startup.md` | Writing or fixing a linker script, vector table and reset sequence, LMA vs VMA, linker symbols, stack/heap placement, fault handlers, bootloaders, `VTOR`, multi-stage images and secure boot |
| `references/architecture-patterns.md` | Source layering and HAL, super-loop vs RTOS, prototype/refactor/API-contract process, security design points, CI rationale, test tiers (host/virtual/hardware), CI flow levels |
| `references/peripherals-gpio-timers.md` | GPIO modes, pull/drive/speed, alternate functions, debouncing; SysTick; timer prescaler/ARR math, update events, PWM, input capture, timer-triggered peripherals |
| `references/peripherals-serial-uart-spi-i2c.md` | Choosing a bus; UART baud math and TXE/TC/ORE semantics, `printf` retargeting, RX ring buffers; SPI modes, flag discipline and CS handling; I2C sequences, clock stretching, bus recovery, pull-up sizing |
| `references/interrupts-and-dma.md` | Exception model and EXC_RETURN, NVIC enable/pending/priority and the implemented-bits trap, masking, EXTI, ISR design rules, DMA configuration order, DMA cache coherency, common DMA recipes |
| `references/adc-rtc-watchdog.md` | ADC bring-up order and sampling time, conversion modes and overrun, noise practice; RTC backup domain unlock, prescalers, BCD and shadow registers, alarms and wake; IWDG/WWDG timing and kick strategy |
| `references/power-and-clocks.md` | Clock tree and PLL constraints, the clock-up/clock-down ordering, flash wait states, clock security; low-power mode ladder, WFI/WFE and the lost-wakeup race, GPIO configuration for leakage, energy budgeting and measurement |
| `references/performance-and-memory.md` | Cortex-M memory map and memory types, barriers, DWT cycle counting, what actually makes code fast, FPU and the `double` trap, caches and TCM, compiler levers, stack sizing and overflow detection, heap and pools, ML on MCU |
| `references/security-trustzone-mpu.md` | Threat modeling and PSA goals, Armv7-M MPU programming and region plans, unprivileged sandboxing with SVC, TrustZone-M SAU/NSC/veneers, TF-M |
| `references/hardware-and-tool-selection.md` | Choosing a core and a part, sizing compute/memory/power, dev-board selection, bare metal vs RTOS vs HAL, compilers and IDEs, cloud/virtual targets |

## Sources

Synthesized from:

- *Bare-Metal Embedded C Programming* — register construction from memory addresses, the GNU toolchain and build process, linker scripts and startup files, Make, CMSIS, GPIO, SysTick, general-purpose timers, UART, ADC, SPI, I2C, EXTI, RTC, independent watchdog, DMA, and power management.
- *Insider's Guide to Arm Cortex-M Development* — hardware, software and tool selection; booting to main across several Cortex-M parts; performance optimization and cycle measurement; machine learning on microcontrollers; PSA and TrustZone-M security; cloud-based development; continuous integration for firmware.
- *Embedded Systems Architecture, 2nd Edition* — embedded-system constraints and workflow/toolchain (chapters 1–2), architectural patterns and source organization, the boot-up procedure, memory management and the MPU, general-purpose peripherals and clock configuration, local bus interfaces, power management, and the Trusted Execution Environment.
