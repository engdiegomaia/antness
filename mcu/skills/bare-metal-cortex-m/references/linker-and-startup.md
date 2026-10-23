# Linker Scripts, Startup Code and Boot on Cortex-M

Read this when the image does not reach `main()`, when globals have the wrong value before the first line of code runs, or when you are splitting flash between a bootloader and an application.

## Contents

- [The reset sequence](#the-reset-sequence)
- [The vector table](#the-vector-table)
- [Linker script anatomy](#linker-script-anatomy)
- [LMA vs VMA and why `.data` has both](#lma-vs-vma-and-why-data-has-both)
- [Linker-defined symbols and the address gotcha](#linker-defined-symbols-and-the-address-gotcha)
- [Directives that matter: KEEP, ALIGN, PROVIDE, NOLOAD, `.`](#directives-that-matter-keep-align-provide-noload-)
- [The reset handler, in order](#the-reset-handler-in-order)
- [Stack and heap placement](#stack-and-heap-placement)
- [Fault handlers worth having](#fault-handlers-worth-having)
- [Multi-stage boot: bootloader plus application](#multi-stage-boot-bootloader-plus-application)
- [Image building, update slots and secure boot](#image-building-update-slots-and-secure-boot)
- [Debugging a two-stage image](#debugging-a-two-stage-image)
- [Position-independent code and shared code on MCUs](#position-independent-code-and-shared-code-on-mcus)
- [Checklists](#checklists)

Vendor note: addresses like `0x08000000` (flash) and `0x20000000` (SRAM) are STM32. NXP LPC, Nordic nRF, TI, Renesas and RP2040 put flash and SRAM elsewhere, and Arm Compiler uses *scatter files* with load/execution regions instead of GNU `ld` scripts. The architectural rules below — word 0 is the stack pointer, word 1 is the reset vector, `.data` is copied, `.bss` is zeroed — hold everywhere in the Cortex-M family (M0/M0+/M3/M4/M7/M23/M33/M55).

## The reset sequence

On reset the Cortex-M core does something unusual: **hardware, not software, loads the stack pointer**. The sequence is fixed — fetch the word at the base of the vector table into **MSP**, fetch the next word (base + 4) into **PC** with bit 0 masked off, then begin executing in Thumb state, Thread mode, privileged, with no NVIC interrupt yet enabled.

Consequences you must design around:

- **The initial SP is a constant in flash.** It cannot be computed at runtime, because the table lives in read-only memory. Whatever the linker computes for the top of stack is baked into the image.
- **A valid C stack exists before your first instruction.** You can write the reset handler in C. You do *not* have to set SP yourself (though a bootloader-launched image must — see below).
- **Word 1 must be odd.** Cortex-M executes only Thumb; bit 0 of every vector is the Thumb bit and must be 1, and the core masks it off to form the address. Taking the address of a C function gets this right automatically. It goes wrong in hand-written assembly tables where the handler symbol was never marked as a function: with GNU `as`, use `.thumb_func` (or `.type name, %function`) before each label, or `.word name` emits an even address and the core faults or locks up immediately at reset. Symptom: the debugger stops at address 0 or in lockup, with no stack and no symbols.
- Where the table lives at reset is implementation-defined. Classic Cortex-M fetches it from `0x00000000`, and vendors alias flash there (STM32 maps `0x08000000` to `0x00000000` under the default BOOT pin configuration). Some ARMv8-M parts take the initial base from a vendor boot ROM. Check the reference manual.

## The vector table

The table is an array of 32-bit function pointers. The first 16 entries are architectural and fixed; everything from index 16 on is device-specific.

| Index | Offset | Entry |
|---|---|---|
| 0 | 0x00 | Initial MSP value (data, not a pointer to code) |
| 1–3 | 0x04–0x0C | Reset, NMI, HardFault |
| 4–6 | 0x10–0x18 | MemManage, BusFault, UsageFault (ARMv7-M / v8-M mainline; reserved on M0/M0+/M23) |
| 7 | 0x1C | SecureFault on ARMv8-M with TrustZone; otherwise reserved |
| 8–10 | 0x20–0x28 | Reserved |
| 11 | 0x2C | SVCall |
| 12 | 0x30 | DebugMonitor (reserved on baseline cores) |
| 13 | 0x34 | Reserved |
| 14, 15 | 0x38, 0x3C | PendSV, SysTick |
| 16+ | 0x40+ | Device IRQ0, IRQ1, … in the order the silicon vendor defines |

**The ordering constraint is absolute.** Position *is* the identity of the handler — nothing in the file links a name to a slot. Reserved slots must be present (write `0`), or every entry after them shifts by one word and a UART interrupt lands in the DMA handler. Likewise, a device may not implement every IRQ number; the unimplemented ones still occupy their slot. Get the list from the vendor's vector-table section in the reference manual or from the vendor's CMSIS `startup_*.s`, not from a similar part in the same family.

Build the table as a C array in its own input section:

```c
extern uint32_t _estack;                 /* linker symbol, see below */
void NMI_Handler(void)       __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
/* ...one per vector... */

__attribute__((section(".isr_vector"), used))
void (* const g_vectors[])(void) = {
    (void (*)(void))&_estack,    /* word 0: initial MSP */
    Reset_Handler,               /* word 1: Thumb bit set by the compiler */
    NMI_Handler, HardFault_Handler,
    /* ... 0 for each reserved slot ... */
};
```

`weak, alias("Default_Handler")` gives every vector a definition while letting a driver override one by defining a non-weak function of the same name — no startup-file edit, no registration call. If a handler name is misspelled in the driver, the weak default silently wins, so make that default a spin-forever you can recognize in a debugger.

**Alignment.** The table must be aligned to a power of two at least as large as the table itself, and never less than 128 bytes on ARMv7-M/v8-M (VTOR's low bits are reserved) — a part with 100+ IRQs needs 512- or 1024-byte alignment. Do not rely on `.text`'s default alignment; align explicitly and verify the address in the map file.

## Linker script anatomy

A GNU `ld` script for a Cortex-M target has three parts: entry point, `MEMORY`, `SECTIONS`.

```ld
ENTRY(Reset_Handler)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 512K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 128K
}

_estack      = ORIGIN(RAM) + LENGTH(RAM);   /* top of stack, grows down */
_min_heap    = 0x200;
_min_stack   = 0x800;

SECTIONS
{
    .isr_vector : { . = ALIGN(512); KEEP(*(.isr_vector)) } >FLASH

    .text : {
        *(.text .text*)
        *(.rodata .rodata*)
        KEEP(*(.init_array))                /* C++ / constructor attribute */
        . = ALIGN(4); _etext = .;
    } >FLASH

    .data : {
        . = ALIGN(4); _sdata = .;
        *(.data .data*)
        *(.RamFunc .RamFunc*)               /* code that must execute from RAM */
        . = ALIGN(4); _edata = .;
    } >RAM AT> FLASH                        /* VMA in RAM, LMA in flash */
    _sidata = LOADADDR(.data);              /* where the initial values live */

    .bss (NOLOAD) : {
        . = ALIGN(4); _sbss = .;
        *(.bss .bss*) *(COMMON)
        . = ALIGN(4); _ebss = .;
    } >RAM

    .noinit (NOLOAD) : { *(.noinit .noinit*) } >RAM

    ._heap_stack (NOLOAD) : {               /* link fails if RAM is overcommitted */
        . = ALIGN(8); . = . + _min_heap; . = . + _min_stack; . = ALIGN(8);
    } >RAM
}
```

Syntax notes, because a wrong guess here produces a silently wrong image rather than an error:

- `MEMORY` attributes (`r`, `w`, `x`) are advisory for placement warnings — they do **not** program the MPU. Memory protection is a runtime job.
- Constants: leading `0` is octal, `0x` is hex, `K` is ×1024, `M` is ×1024². `4K`, `4096` and `0x1000` are the same number; `0400` is 256, which is probably not what you meant.
- Order matters: output sections are placed in script order within a region, so `.isr_vector` must come first in `FLASH`. Input-section wildcards are greedy and first-match-wins, and with `-ffunction-sections` almost everything lands in `.text.<name>`, so the `*` forms do the real work.
- Verify unusual syntax against your linker version. `AT>` (region) and `AT(addr)` (address) both work; `LOADADDR()` works in GNU `ld` and LLD, but check a vendor-forked toolchain.

## LMA vs VMA and why `.data` has both

Every allocatable output section has two addresses: the **VMA**, where it is *accessed* at runtime (on a no-MMU MCU, the physical runtime address), and the **LMA**, where its bytes are *stored* in the image — where the flash programmer puts them.

For `.text`, `.rodata` and the vector table these are the same: code executes in place from flash (XIP). For `.bss` there is no LMA at all — it has no contents, only a reservation.

`.data` is the exception, and it is the reason startup code exists. Initialized globals must be writable, so their VMA is in RAM; RAM is volatile, so the initial values must be stored in flash, giving them an LMA in flash. `>RAM AT> FLASH` expresses exactly this. Without it the linker puts the initial values at RAM addresses in the image, the programmer tries to write RAM, and every initialized global comes up as garbage. The same mechanism places functions that must run from RAM (`.RamFunc`) — flash self-programming routines that cannot execute from the flash they are erasing, and latency-critical ISRs on parts with slow flash.

## Linker-defined symbols and the address gotcha

A linker symbol has a name and a *value that is an address*, and occupies no storage. This is the most common bug in hand-written startup code:

```c
extern uint32_t _sdata;      /* NOT a variable. There is no object here. */
uint32_t wrong = _sdata;     /* reads whatever bytes happen to be at that address */
uint32_t *right = &_sdata;   /* the address itself — this is what you want */
```

Always take the address. Some codebases declare them as `extern char _sdata[]`, which makes array-to-pointer decay do the right thing and removes the temptation to dereference; either convention is fine if used consistently. The conventional set, in GNU/ST spelling (CMSIS and other vendors use `__data_start__`, `__bss_end__`, `__StackTop`; match whatever your startup file expects):

| Symbol | Meaning |
|---|---|
| `_sidata` / `_stored_data` | LMA of `.data` — source of the copy, in flash |
| `_sdata` / `_edata` | VMA start/end of `.data` in RAM — destination of the copy |
| `_sbss` / `_ebss` | Start/end of `.bss` in RAM — range to zero |
| `_estack` / `_stack_top` | Initial MSP, word 0 of the vector table |
| `_etext` | End of `.text` in flash. Equals the `.data` LMA only if `.data` immediately follows with no alignment gap — prefer `LOADADDR(.data)`, correct by construction |

Keep all of these and the `.data` LMA 4-byte aligned, because the startup loops copy words. An unaligned boundary gives an unaligned access (a UsageFault with `UNALIGN_TRP` set) or a one-word overrun into whatever follows.

## Directives that matter: KEEP, ALIGN, PROVIDE, NOLOAD, `.`

**`.` — the location counter**, the current output address. Reading it gives the address; assigning to it moves forward (never backward) and leaves a gap. `. = ALIGN(8);` rounds up; `. = . + 0x400;` reserves 1 KiB; `. = 0x400;` inside a section places the next item at offset 0x400 from the section start, which is how you put a fixed-address table just past the vectors.

**`KEEP(...)` — garbage-collection immunity.** With `-ffunction-sections -fdata-sections -Wl,--gc-sections` (which you want — often 20–40% of image size on a vendor-SDK build) the linker discards every section not reachable from the entry point. **The vector table is reachable only by hardware, not by any call chain**, so without `KEEP(*(.isr_vector))` it is collected and you ship an image with code but no vectors, which boots to a lockup with no clue why. Same for `.init_array`, for vendor option-byte or config-word sections (RP2040 `.boot2`, NXP flash configuration field, Nordic UICR), and for any table found by address rather than by symbol. When in doubt, `KEEP` it.

**`ALIGN(n)`** (power of two) at section boundaries for word-copy correctness, at the vector table for VTOR, and to 8 for the stack as AAPCS requires. **`PROVIDE(sym = expr)`** defines `sym` only if nothing else does, giving an overridable default; a plain `=` always wins and collides with a C definition of the same name.

**`(NOLOAD)`** marks a section allocated but with no contents in the image. Essential for `.bss`, stack and heap reservations, and `.noinit` (data deliberately preserved across a warm reset — reset-cause latches, crash logs, bootloader handoff flags). Without it some toolchains emit zeros into the binary, inflating the image by the size of your RAM and making the startup code wipe data you meant to survive. **`ASSERT(cond, "msg")`** is the cheapest guardrail in the file — fail the link instead of the field:

```ld
ASSERT(_ebss + _min_heap + _min_stack <= ORIGIN(RAM) + LENGTH(RAM),
       "RAM overflow: statics + heap + stack exceed available SRAM")
```

## The reset handler, in order

The order of these steps is a real constraint, not a style preference:

```c
void Reset_Handler(void)
{
    /* 0. bootloader-launched images only: set SP explicitly            */
    /* 1. optional, chip-dependent: minimal clock + flash wait states   */
    SystemInit();                /* only if it does NOT touch initialized globals */

    uint32_t *src = (uint32_t *)&_sidata;                        /* 2. copy .data */
    uint32_t *dst = (uint32_t *)&_sdata;
    while (dst < (uint32_t *)&_edata) { *dst++ = *src++; }

    dst = (uint32_t *)&_sbss;                                    /* 3. zero .bss  */
    while (dst < (uint32_t *)&_ebss) { *dst++ = 0u; }

    __libc_init_array();         /* 4. C++ ctors / constructor attribute */
    main();                      /* 5. hand over                         */
    for (;;) { }                 /* 6. main() must not return            */
}
```

- **Nothing before step 2 may read or write an initialized global, and nothing before step 3 may rely on a zero-initialized one.** This is the trap in `SystemInit()`. CMSIS startup files traditionally call it *first*, assuming it only pokes clock registers. The moment someone adds `SystemCoreClock = 16000000;` or a cached calibration global, that write is overwritten by step 2 and silently reverts. Decide explicitly: keep `SystemInit()` global-free and call it first, or move it after step 3 — do not leave it ambiguous.
- **Flash wait states may have to come first.** If the part boots on a slow internal RC and you intend to run the copy loop fast, raise flash latency before raising the clock. On most parts the reset clock is slow enough that doing all clock work after step 3 is simpler and safer; prefer that unless boot time is critical.
- **`__libc_init_array` must follow both copy and zero**, because constructors run arbitrary application code. **`main()` returning is a bug** — there is no OS to return to, so the trailing `for(;;)` turns an undefined jump into a findable hang. Better still, do not feed the watchdog there, so the device resets.

**Pitfall: byte count versus word count.** `for (i = 0; i < size; i++) *dst++ = *src++;` with `size = (uint32_t)&_edata - (uint32_t)&_sdata` iterates a *byte* count over *word* pointers, copying four times too much and trampling whatever follows `.data` — usually `.bss`, which step 3 then re-zeros, hiding the damage until the overrun reaches the stack. Divide by 4, or use the pointer-comparison form above, which cannot get this wrong.

**Pitfall: optimizers recognize these loops.** At `-O2` GCC may rewrite the copy into `memcpy` and the zero into `memset` — which do not exist if you built `-nostdlib`. Use `-fno-tree-loop-distribute-patterns` (or `__attribute__((optimize("O0")))` on the handler) if you hit it.

## Stack and heap placement

The classic layout, low address to high: `.data`, `.bss`, heap growing up, a gap, then the stack growing down from `_estack` at the top of RAM.

That gap is the whole safety margin, and nothing checks it. **Stack overflow and heap exhaustion meet silently in the middle**: the stack writes into the heap or into `.bss`, and the failure surfaces later as a corrupted variable in unrelated code. This is the hardest class of bug on a bare-metal MCU.

Mitigations, in increasing order of cost:

- **Link-time `ASSERT`** on statics + minimum heap + minimum stack, as above. Catches overcommitment, not runtime depth.
- **Avoid the heap entirely.** Most firmware should — static allocation turns a runtime failure into a link-time one. If you do not use `malloc`, set the heap reservation to 0 and stub `_sbrk` to trap.
- **Stack painting.** Fill the unused stack with a known pattern (`0xA5A5A5A5`) early in the reset handler, then at runtime scan from the low end for the first non-pattern word to get a high-water mark and report it. This is the standard way to size a stack with evidence instead of guesswork. The fill must stop a safe margin below the current SP so it does not clobber the reset handler's own frame.
- **MPU guard region.** An unwritable MPU region immediately below the stack's lower limit turns an overflow into a MemManage fault at the point of overflow. Available on M3/M4/M7/M23/M33/M55 with an MPU; the region base must satisfy MPU alignment rules, so reserve the guard explicitly in the linker script.
- **Hardware stack limit registers.** ARMv8-M (M23/M33/M55) adds `MSPLIM`/`PSPLIM`: set them and overflow becomes a UsageFault with an exact PC. Strictly better than painting — and absent on ARMv6-M and ARMv7-M.

**Inverted layout.** Putting the stack at the *bottom* of RAM (below `.data`) makes an overflow run off the start of SRAM, which faults on most parts. Free, and converts silent corruption into a fault — worth it when there is no MPU and no stack-limit register.

**MSP vs PSP.** At reset only MSP is in use (`CONTROL.SPSEL` = 0), and a bare-metal main loop stays on MSP forever. An RTOS runs threads on PSP and keeps MSP for exception handling so a thread overflow cannot corrupt the handler stack. Even without an RTOS, moving the main loop to PSP and reserving MSP for exceptions is a cheap robustness win — the linker script then needs two stack reservations.

## Fault handlers worth having

The default `while(1)` handler is widely mocked and still much better than nothing: it stops execution at the fault instead of letting the core lock up, run off into garbage, or reset and lose all evidence — attach a debugger and the call stack is sometimes still readable. But the cheap upgrade pays for itself. On entry to any exception the core has already stacked eight words — **R0, R1, R2, R3, R12, LR, PC, xPSR** — onto the stack that was active before the fault. The stacked PC is the faulting instruction (or close to it), which is the one piece of information you actually need. Recover it like this:

```c
__attribute__((naked)) void HardFault_Handler(void)
{
    __asm volatile(                  /* ITE is ARMv7-M; on ARMv6-M use branches */
        "tst lr, #4         \n"      /* EXC_RETURN bit 2: 0 = MSP, 1 = PSP */
        "ite eq             \n"
        "mrseq r0, msp      \n"
        "mrsne r0, psp      \n"
        "b hardfault_report \n");
}

void hardfault_report(uint32_t *frame)
{
    volatile uint32_t pc = frame[6], lr = frame[5], xpsr = frame[7];
    volatile uint32_t cfsr  = *(volatile uint32_t *)0xE000ED28;   /* fault class   */
    volatile uint32_t hfsr  = *(volatile uint32_t *)0xE000ED2C;   /* escalation    */
    volatile uint32_t mmfar = *(volatile uint32_t *)0xE000ED34;   /* fault address */
    volatile uint32_t bfar  = *(volatile uint32_t *)0xE000ED38;
    (void)pc; (void)lr; (void)xpsr; (void)cfsr; (void)hfsr; (void)mmfar; (void)bfar;
    for (;;) { }                     /* breakpoint here; or log and reset */
}
```

**CFSR** splits into MemManage, BusFault and UsageFault status bytes — it tells you the *class* of fault (unaligned access, divide by zero, undefined instruction, precise or imprecise bus error, stacking error). **HFSR** bit 30 (`FORCED`) means a configurable fault escalated to HardFault because its handler was disabled or it faulted during handling; read CFSR for the real cause. **MMFAR**/**BFAR** hold the offending data address, but only when the corresponding valid bit (`MMARVALID`/`BFARVALID`) in CFSR is set.

Caveats:

- On **ARMv6-M (M0/M0+) and baseline M23**, CFSR/HFSR/MMFAR/BFAR do not exist and every fault is a bare HardFault. The stacked frame is all you get — which makes capturing the stacked PC *more* important there, not less.
- With the FPU active, the frame is longer; the integer frame is still the first eight words, so the indices above hold, and EXC_RETURN bit 4 says whether FP state was stacked.
- An **imprecise** BusFault (`IMPRECISERR`) means the stacked PC is *not* the faulting instruction — the write was buffered. Set `ACTLR.DISDEFWBUF` while debugging to force precise faults; remove it for production.
- Enable the configurable faults (`SHCSR` MEMFAULTENA / BUSFAULTENA / USGFAULTENA) so you get a specific handler instead of universal escalation to HardFault.
- In production, log the frame to `.noinit` RAM or a flash page and reset through the watchdog rather than hanging. A field device that hangs is indistinguishable from a dead one.

## Multi-stage boot: bootloader plus application

A bootloader buys field updates, image verification before boot, and failover to a known-good image. The standard arrangement is two independently linked images in two flash partitions.

**Separate linker scripts, not one script with two regions.** Build two complete `.elf` files, each with its own vector table, `.data`/`.bss` and entry point. They may freely reuse section and symbol names — they are never linked together. The scripts differ only in the `FLASH` region:

```ld
/* bootloader.ld */   FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 32K
/* app.ld       */    FLASH (rx) : ORIGIN = 0x08008000, LENGTH = 480K
```

RAM is shared in time, not space: the bootloader uses it, the application re-initializes it. Anything that must survive the handoff goes in a `.noinit` region at a fixed address that *both* scripts reserve identically.

**The handoff, in order** — each step exists for a reason:

```c
#define APP_BASE 0x08008000u

static void jump_to_app(void)
{
    uint32_t app_sp    = *(volatile uint32_t *)(APP_BASE);
    void (*app_reset)(void) = (void (*)(void))(*(volatile uint32_t *)(APP_BASE + 4));

    __disable_irq();                            /* 1 */
    /* 2. de-initialize every peripheral and DMA stream the bootloader started;
          disable and clear each NVIC IRQ (NVIC_ICER / NVIC_ICPR); stop SysTick */
    SCB->VTOR = APP_BASE;                       /* 3 */
    __DSB(); __ISB();
    __set_MSP(app_sp);                          /* 4 */
    __enable_irq();                             /* 5 */
    app_reset();                                /* 6, never returns */
}
```

1. **Disable interrupts first.** If the bootloader enabled a timer or UART, an interrupt arriving mid-handoff vectors through a half-updated table into code that no longer exists. `cpsid i` masks everything except NMI and HardFault; keep the window short.
2. **De-initialize what you started.** The step people skip, and the most common cause of "the application works standalone but not after the bootloader". A DMA stream still running, a peripheral still asserting its interrupt line, a pending NVIC bit left set — any of these fires the instant the application enables interrupts, into an uninitialized handler. Clearing the NVIC enable is not enough if the peripheral keeps asserting; disable the peripheral too. Cheapest robust alternative on many parts: trigger a system reset and have the bootloader skip itself on the second pass, so the application starts from true reset state.
3. **Relocate the vector table via VTOR** (`0xE000ED08`). The written value must satisfy the table's alignment requirement; `DSB`/`ISB` after the write.
4. **Set MSP to the application's word 0.** Nothing else does — hardware loaded MSP only at real reset, and MSP currently points into the bootloader's stack. Skip this and the application runs on the bootloader's stack with its own `_estack` unused: it works for a while, then overflows mysteriously.
5. Re-enable interrupts, or leave them masked for the application's early code to enable — pick one and document it.
6. Jump to the application's reset handler, which redoes `.data`/`.bss` init for its own layout.

**The M0 / ARMv6-M case: there is no VTOR.** On Cortex-M0 and many M0+ parts the table is fixed at address 0. Options, best first: (a) **vendor SRAM remap** — many M0+ parts can remap `0x00000000` onto SRAM via a syscon register (STM32's `SYSCFG_CFGR1.MEM_MODE`), so the application copies its table to SRAM and remaps; confirm in the reference manual, not by family. (b) **Shared table with dispatch** — the bootloader owns the only table and each handler tail-calls a function pointer read from a fixed address in the application partition, costing a few cycles per interrupt and an ABI nothing checks. (c) **Skip the bootloader** — do updates from the application itself, self-programming the other bank.

**Flash erase granularity dictates the partition boundary.** Flash erases in sectors or pages, and sector sizes are often non-uniform (STM32F4's first sectors are 16 KiB, then 64 KiB, then 128 KiB). If the application partition does not start on a sector boundary, you cannot erase the application without erasing part of the bootloader — which is the one thing that must never happen. Size the bootloader partition up to the next sector boundary, not to the next round number.

## Image building, update slots and secure boot

**Concatenating two images** — pad the bootloader binary to exactly the partition size, then append:

```sh
arm-none-eabi-objcopy -O binary --pad-to=0x8000 --gap-fill=0xFF bootloader.elf bootloader.bin
arm-none-eabi-objcopy -O binary app.elf app.bin
cat bootloader.bin app.bin > factory.bin
```

Fill with `0xFF`, not `0x00` — `0xFF` is the erased state of NOR flash, so programming it is a no-op. Use the combined image for factory programming; for field updates flash the partitions separately so the bootloader is never touched.

**A/B (dual-slot) updates.** Reserve two application slots plus the bootloader. Write the new image into the inactive slot, verify it, mark it active and reset; if it fails to confirm itself within N boots, the bootloader reverts to the previous slot. This is the only scheme that survives a power cut mid-write. It costs slightly more than twice the application size in flash — budget for it at project start, because retrofitting it means re-partitioning a fleet. Parts with **dual-bank flash** make it cheaper: both banks are mapped, the inactive one can be programmed while executing from the active one, and a bank-swap bit makes the switch atomic at reset. Without dual bank the self-programming routine must execute from RAM (`.RamFunc`), because the flash controller stalls reads during an erase.

**Image headers and signature verification.** Put a fixed-layout header at the start of each application slot — magic number, header version, image length, image version, CRC or hash of the payload, and a signature. The boot decision is then: magic matches, length is sane, hash over the payload matches the header, signature over the header verifies against a public key in the bootloader's own read-only partition. Only then jump. For **secure boot**, the properties that actually matter:

- The root of trust must be immutable — public key or key hash in a write-protected sector, OTP/fuses, or a vendor boot ROM. A key in erasable flash protects nothing.
- Verify over the whole payload, every boot, *before* jumping. A CRC proves integrity against corruption, not against an attacker; use a real signature (ECDSA P-256, Ed25519) when tampering is in the threat model.
- Put the image version in the signed header and reject downgrades, or an attacker reinstalls a version whose bug you already fixed. Lock the debug port in production (usually irreversible) or the whole chain is bypassable.
- Prefer an audited implementation (MCUboot and similar) over hand-rolling verification and slot management. The format is fiddly and the failure modes are silent.

## Debugging a two-stage image

The two images have separate symbol tables in separate `.elf` files — load both. `file` *replaces* the symbol table; `add-symbol-file` *adds* to it, which is what you want, and it takes the address where the application's `.text` actually starts (from the map file, not the partition base, if anything precedes `.text`):

```gdb
file bootloader.elf
add-symbol-file app.elf 0x08008000
```

Duplicate names across the two images are legal and GDB handles them: `break main` sets a breakpoint at both locations and `info breakpoints` shows them as `<MULTIPLE>`.

Practical tips: step the handoff instruction by instruction — the two failure points are the MSP write and the first instruction after the jump, and a wrong SP shows immediately in `info registers`. Check `x/x 0xE000ED08` after the jump to confirm the VTOR relocation took. `arm-none-eabi-objdump -S app.elf > app.mix` gives mixed source and assembly; searching that listing for a stacked PC is often faster than coaxing GDB into unwinding a corrupted stack. And keep the `.map` file for every release — section addresses, sizes and the symbol listing answer most "where did this come from" questions without running anything.

## Position-independent code and shared code on MCUs

Two separate wishes get conflated here. **Truly position-independent images** (one binary runs from either A/B slot without relinking) are possible but awkward. Arm toolchains offer ROPI (PC-relative read-only) and RWPI (static-base-register read-write); GCC offers `-fPIC` with `-msingle-pic-base`. Costs: a register is consumed as the static base, every global access gains an indirection, the vector table cannot be position-independent (it holds absolute addresses), and function pointers in initialized data need runtime relocation. For most projects, building two slot-specific images — or relocating at install time — is cheaper and far less surprising. Confirm what your toolchain version supports before designing around it.

**Sharing code between boot stages** is the more common wish: both stages want the same CRC routine or flash driver, but the images are not linked together so the application cannot call bootloader functions by symbol. The workaround is an explicit jump table at a fixed address: the bootloader places an array of function pointers in its own `KEEP`-ed section at a known offset past the vector table, and the application declares a pointer to that address and calls through inline wrappers that supply the signatures.

It works and saves flash, but **the signatures are checked by nothing — not the linker, not the loader, not runtime**. If the bootloader's `crc32()` gains a parameter and the application is not rebuilt, the call corrupts the stack with no diagnostic. Version the interface: a version word and entry count at the head of the table, and an application that refuses to run against an incompatible bootloader. In most projects, duplicating a few kilobytes of utility code is the better trade; reach for the shared table only when flash pressure is real. A side benefit of fully separated stages: sharing no linked code, they may carry **incompatible licenses** — a GPL bootloader and a proprietary application in separate partitions are two programs, not one.

## Checklists

**Linker script**

- [ ] `ENTRY()` names the reset handler; `MEMORY` origins/lengths match this exact part, not a sibling
- [ ] `.isr_vector` is first in flash, explicitly aligned (≥128 bytes, more for large tables), wrapped in `KEEP()`
- [ ] `.data` is `>RAM AT> FLASH`; `_sidata` comes from `LOADADDR(.data)`, not `_etext`
- [ ] `.bss`, `.noinit` and the stack/heap reservation are `(NOLOAD)`; copy/zero boundaries are `ALIGN(4)`, stack top `ALIGN(8)`
- [ ] `.init_array` and any vendor config section (boot2, flash config field, UICR) are placed and `KEEP`-ed
- [ ] An `ASSERT` fails the link on RAM overcommitment, and the map file has been read once end to end

**Startup code**

- [ ] Word 0 is `&_estack`; word 1 is the reset handler at an *odd* address in the map/disassembly
- [ ] Reserved vector slots are present as zeros; the IRQ order came from this part's reference manual
- [ ] Every vector has a weak default aliased to a recognizable spin-forever handler
- [ ] The copy loop compares pointers (or divides the byte count by 4), and linker symbols are used by address
- [ ] Whether `SystemInit()` runs before or after `.data`/`.bss` init is explicit and matches whether it touches globals
- [ ] `__libc_init_array()` runs after both copy and zero; a return from `main()` is trapped
- [ ] Fault handlers capture stacked PC/LR/xPSR, plus CFSR/HFSR/MMFAR/BFAR on mainline cores

**Boot and update**

- [ ] Partition boundaries land on flash sector boundaries
- [ ] Handoff order: mask interrupts → de-init peripherals/DMA/NVIC → set VTOR (+DSB/ISB) → set MSP → jump
- [ ] On a part without VTOR, the remap or dispatch strategy is chosen and documented
- [ ] Handoff state in RAM lives in a `.noinit` region reserved identically by both linker scripts
- [ ] The bootloader verifies length and hash before jumping — and a signature if the threat model needs one, rooted in immutable storage, with downgrades rejected
- [ ] A/B slots exist, or power loss mid-update has a documented recovery path
- [ ] Both `.elf` files and both map files are archived per release, so a field fault decodes against the exact image

Sources: see the Sources section of ../SKILL.md (Bare-Metal Embedded C Programming; Insider's Guide to Arm Cortex-M Development; Embedded Systems Architecture, 2nd ed.). Per-chapter attribution was not recorded for this file.
