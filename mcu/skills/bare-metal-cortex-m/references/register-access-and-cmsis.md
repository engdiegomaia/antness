# Register Access and CMSIS

Read this when writing or reviewing the lowest layer of a bare-metal driver: how peripheral registers are declared, accessed, bit-manipulated, and how CMSIS device headers fit in.

## Contents

- [Reading the reference manual](#reading-the-reference-manual)
- [Three ways to declare a register](#three-ways-to-declare-a-register)
- [Why `volatile`, and what `volatile` does not give you](#why-volatile-and-what-volatile-does-not-give-you)
- [Struct overlays: the rules that make them correct](#struct-overlays-the-rules-that-make-them-correct)
- [Bit manipulation idioms](#bit-manipulation-idioms)
- [Read-modify-write hazards](#read-modify-write-hazards)
- [CMSIS: what it is and which parts you actually use](#cmsis-what-it-is-and-which-parts-you-actually-use)
- [Using a vendor CMSIS device pack](#using-a-vendor-cmsis-device-pack)
- [HAL vs LL vs raw registers](#hal-vs-ll-vs-raw-registers)
- [Checklist](#checklist)

## Reading the reference manual

Three documents, three jobs. Confusing them wastes hours:

| Document | Who writes it | What it answers |
|---|---|---|
| Datasheet | Silicon vendor | Pinout, packages, electrical limits, **peripheral base addresses**, alternate-function mapping table, timing specs |
| Reference manual | Silicon vendor | **Register offsets, bit fields, reset values, configuration sequences** per peripheral |
| Core generic user guide / Armv7-M or Armv8-M ARM | Arm | NVIC, SysTick, SCB, MPU, DWT, instruction set, exception model — anything inside the core |

A register's address is always `peripheral_base + offset`. The base comes from the datasheet's memory-map table, the offset from the reference manual's register description. Every register description also gives:

- **Reset value** — the state after reset. If your code depends on a bit being cleared, check whether reset already does it instead of writing a redundant clear. Conversely, some reset values are *not* zero (on STM32F4, `GPIOA_MODER` resets to `0xA8000000` because the SWD pins are pre-configured as alternate function — clobbering those bits kills your debugger connection, which is a classic self-inflicted "my board bricked itself" bug).
- **Access type** — some registers are read-only, write-only, write-1-to-clear, or only support certain access widths. A byte write to a word-only register may be silently dropped or may fault.
- **Access conditions** — "writable only when the peripheral is disabled", "requires an unlock key sequence", "reads return 0 until the clock is enabled".

Before writing any peripheral code, read the manual's *configuration sequence* prose, not just the register tables. Most peripherals have a mandatory ordering (disable, configure, enable, wait for a ready flag) and the register tables do not show it.

## Three ways to declare a register

### 1. Address-cast macro

```c
#define RCC_AHB1ENR  (*(volatile uint32_t *)(0x40023800UL + 0x30UL))
RCC_AHB1ENR |= (1UL << 0);          /* enable GPIOA clock */
```

Fine for a one-off or for teaching. It scales badly: every register needs its own macro, and nothing ties related registers together.

Note the `UL` suffix on both the address and the bit masks. Without it, `1 << 31` is undefined behaviour on a 32-bit `int` (signed overflow), and address constants above `0x7FFFFFFF` become negative `int`. Always write register constants as `1UL << n` or `UINT32_C(1) << n`.

### 2. Struct overlay (the standard approach, and what CMSIS does)

```c
typedef struct {
    volatile uint32_t MODER;    /* 0x00 */
    volatile uint32_t OTYPER;   /* 0x04 */
    volatile uint32_t OSPEEDR;  /* 0x08 */
    volatile uint32_t PUPDR;    /* 0x0C */
    volatile uint32_t IDR;      /* 0x10 */
    volatile uint32_t ODR;      /* 0x14 */
    volatile uint32_t BSRR;     /* 0x18 */
    volatile uint32_t LCKR;     /* 0x1C */
    volatile uint32_t AFR[2];   /* 0x20, 0x24 */
} GPIO_TypeDef;

#define GPIOA  ((GPIO_TypeDef *)0x40020000UL)

GPIOA->MODER |= (1UL << 10);
```

One struct describes the whole peripheral; one pointer per instance. `GPIOA`, `GPIOB`, `GPIOC` share the type, so a driver can take a `GPIO_TypeDef *` and work with any port — the single biggest practical win, because it turns copy-pasted per-port code into one function.

### 3. Bitfields — do not use for hardware

C bitfield layout (allocation order, straddling, padding) is implementation-defined. Two compilers, or two `-m` flags, can lay the same struct out differently, and the compiler is free to access the underlying storage at whatever width it likes — which breaks write-1-to-clear and write-only registers. Use explicit masks and shifts.

## Why `volatile`, and what `volatile` does not give you

`volatile` tells the compiler that every read and write in the source must appear in the generated code, in source order relative to other volatile accesses, and that the value may change outside the program's control. Without it, the optimizer legitimately deletes a spin on a status flag (`while (!(SPI1->SR & RXNE));` becomes an infinite loop reading the register once), collapses repeated writes, or hoists a read out of a loop.

What `volatile` does **not** do:

- **It is not atomic.** `reg |= BIT` is a load, an OR, and a store. An interrupt between the load and the store loses the other writer's change.
- **It is not a memory barrier against the hardware.** The core may still have the write sitting in a write buffer. Writes to Device memory are not reordered against each other, but a write to a peripheral is not guaranteed to have *reached* the peripheral when the next instruction executes. If you clear an interrupt flag and immediately return from the ISR, the write may still be in flight and the NVIC re-enters the handler. Either clear the flag early in the ISR, or issue `__DSB()` before returning. The same applies before entering sleep.
- **It does not order volatile accesses against non-volatile ones.** Handing a buffer to DMA needs `__DMB()`, not `volatile`.
- **It is not thread/ISR synchronization.** For a multi-word shared structure you still need a critical section or a lock-free single-producer/single-consumer design.

CMSIS spells the intent with qualifiers: `__I` (`volatile const`, read-only), `__O` (write-only), `__IO` (`volatile`, read/write). Use them when writing a device header; they also make a misuse like writing to a status-only register a compile error.

## Struct overlays: the rules that make them correct

1. **Member order and width must mirror the memory map exactly.** Each 32-bit register is a `uint32_t`; a 16-bit register is a `uint16_t` only if the manual says half-word access is correct for it.
2. **Fill gaps explicitly.** Peripherals have reserved holes. Pad with a named reserved array so the offsets of everything after the gap stay right:
   ```c
   typedef struct {
       __IO uint32_t CR;            /* 0x00 */
       __IO uint32_t CFGR;          /* 0x04 */
       uint32_t      RESERVED0[10]; /* 0x08 .. 0x2C */
       __IO uint32_t AHB1ENR;       /* 0x30 */
   } RCC_TypeDef;
   ```
   Counting the padding wrong shifts every subsequent member and produces writes to the wrong register — which often look like "the peripheral does nothing" or like a random unrelated peripheral misbehaving. When you hand-write a device struct, verify it with a static assertion rather than by eye:
   ```c
   _Static_assert(offsetof(RCC_TypeDef, AHB1ENR) == 0x30, "RCC layout");
   ```
   Add one assertion per non-contiguous boundary. This catches the error at compile time instead of on the bench.
3. **No padding surprises.** All-`uint32_t` structs on Cortex-M have natural alignment and no implicit padding, which is why device headers use uniform word members. Mixing widths invites compiler-inserted padding — avoid it or assert the offsets.
4. **Use an array for indexed register banks** (`AFR[2]`, `DIER`-style per-channel arrays) so driver code can compute the index instead of branching.
5. **Cast once, in the header.** `#define GPIOA ((GPIO_TypeDef *)GPIOA_BASE)` keeps the cast out of driver code and gives the compiler a typed pointer it can reason about.

## Bit manipulation idioms

```c
reg |=  MASK;                      /* set bits */
reg &= ~MASK;                      /* clear bits */
reg ^=  MASK;                      /* toggle bits */
if (reg & MASK) { ... }            /* test any bit in MASK set */
reg = (reg & ~FIELD_MASK) | (value << FIELD_POS);   /* write a multi-bit field */
```

The multi-bit field case is the one people get wrong. A two-bit mode field cannot be set with `|=` alone — if the field currently holds `11` and you OR in `01`, you get `11`. **Always clear the field before OR-ing the new value**, in a single read-modify-write so the register is only written once:

```c
#define MODER_POS(pin)   (2U * (pin))
#define MODER_MSK(pin)   (0x3UL << MODER_POS(pin))
#define MODE_OUTPUT      0x1UL

GPIOA->MODER = (GPIOA->MODER & ~MODER_MSK(5)) | (MODE_OUTPUT << MODER_POS(5));
```

Writing the field as two separate statements (`|= (1<<10); &= ~(1<<11);`) happens to work for this case but puts the register through an intermediate state. On a peripheral where a write triggers an action, the intermediate state is a real glitch. Prefer the single-write form.

Derive bit positions from the pin/channel number with a formula rather than hand-expanding them — two-bit fields are at `2*n`, four-bit alternate-function fields at `4*(n % 8)` in the low/high register pair. Hand-expanded magic numbers are where off-by-one bugs live.

Write-1-to-clear flag registers (pending registers, interrupt status registers on many parts) must be **assigned, not OR-ed**:

```c
EXTI->PR  = (1UL << 5);   /* correct: clears line 5 only */
EXTI->PR |= (1UL << 5);   /* wrong: reads all pending bits and writes them back,
                             clearing every pending line */
```

This is one of the most common real bugs in hand-written EXTI/DMA/timer code, and it presents as "interrupts occasionally go missing".

## Read-modify-write hazards

`reg |= BIT` from the main loop while an ISR does `reg |= OTHER_BIT` loses one of the two updates. Three fixes, in order of preference:

1. **Use the hardware's atomic register if there is one.** Output set/reset registers (`BSRR` on STM32, separate SET/CLR/XOR registers on RP2040, NXP, Nordic) perform the operation in one bus write with no read. `GPIOA->BSRR = (1UL << 5)` sets PA5; `GPIOA->BSRR = (1UL << (5 + 16))` clears it. This is both race-free and faster than a read-modify-write on `ODR`. Use it for anything touched from more than one context, and prefer it generally.
2. **Partition ownership.** Decide that a given register is written only from one context. Most configuration registers are written once at init and never again, which makes the race vacuous.
3. **Critical section**, saving and restoring the previous mask rather than blindly re-enabling:
   ```c
   uint32_t pm = __get_PRIMASK();
   __disable_irq();
   reg |= BIT;
   __set_PRIMASK(pm);
   ```
   A bare `__enable_irq()` at the end re-enables interrupts even when the caller had them disabled — a nesting bug that only shows up under load.

Bit-banding (M3/M4 only, aliased SRAM and peripheral regions) gives atomic single-bit writes without a critical section. It does not exist on M0/M0+/M7/M23/M33, so code that relies on it does not port. Treat it as a niche optimization, not a default.

## CMSIS: what it is and which parts you actually use

CMSIS is Arm's vendor-independent standardization layer for Cortex-M. It is a set of specifications and header files, not a runtime you link against. The parts that matter for bare-metal work:

| Component | What it gives you | Use it? |
|---|---|---|
| **CMSIS-Core(M)** | Core register definitions (NVIC, SCB, SysTick, MPU, DWT, ITM), intrinsics (`__NOP`, `__WFI`, `__DSB`, `__disable_irq`), NVIC helper functions, `SystemCoreClock` | Yes, always. Hand-rolling NVIC access is pure risk. |
| **CMSIS device headers** (`<Device>.h`, from the silicon vendor) | Peripheral structs, base-address pointers, every bit mask and position as `PERIPH_REG_FIELD_Msk` / `_Pos` | Yes. Hand-typing register offsets is the single largest source of bring-up bugs. |
| **CMSIS-DSP** | Optimized filters, transforms, matrix/vector math using DSP/SIMD instructions | Yes, when you need DSP — it is far better than hand-written C. |
| **CMSIS-NN** | Quantized neural-network kernels | Only for ML on MCU. |
| **CMSIS-SVD** | XML description of every peripheral register | Indirectly — your debugger reads it to render peripheral views. Worth checking your debugger has the right SVD loaded; it turns register inspection from hex guessing into named fields. |
| **CMSIS-Driver** | Generic peripheral driver API for middleware | Only if you are consuming middleware that requires it. |
| **CMSIS-Pack** | Packaging/delivery format for device support | Indirectly, via your IDE or `cpackget`. |
| **CMSIS-RTOS2** | Common RTOS API | Not bare metal. |

CMSIS code is C99/C++03, uses `<stdint.h>` types, and follows MISRA C:2012 with documented deviations (it does not claim full compliance).

The practical rule: **use the vendor's CMSIS device header for register definitions, and write your own drivers on top of it.** That gives you correct, machine-generated register definitions without the weight and indirection of a vendor HAL.

## Using a vendor CMSIS device pack

What you need in the project, and where it comes from:

| File | Source | Modify? |
|---|---|---|
| `core_cm<n>.h`, `cmsis_gcc.h`, `cmsis_compiler.h`, `mpu_armv7.h`/`mpu_armv8.h` | Arm (shipped inside the vendor pack) | Never |
| `<Device>.h` (e.g. `stm32f4xx.h` + `stm32f411xe.h`) | Silicon vendor | Never |
| `system_<Device>.c` / `.h` | Silicon vendor | Yes — this is where clock setup and `SystemCoreClock` live |
| `startup_<device>.s` or `.c` | Silicon vendor | Yes — vector table, reset handler |
| `partition_<Device>.h` | Silicon vendor (Armv8-M only) | Yes — SAU regions and interrupt target states |

Integration steps that trip people up:

1. **Define the exact part macro.** Device header families are one umbrella header that `#include`s a part-specific header selected by a preprocessor symbol (`STM32F411xE`, `LPC55S69_cm33_core0`, …). Forget it and you get a "please select the target device" `#error`, or worse, a silently wrong memory map. Put it in the build (`-DSTM32F411xE`), not in a source file.
2. **Vendor the headers into the repo** rather than pointing at an SDK installed on someone's machine. Toolchain and SDK version drift silently changes register definitions and code size. Pin the version.
3. **Add both include paths**: the Arm core includes and the device includes. They are separate directories in every vendor pack.
4. **Strip what you do not need.** Vendor packs ship HAL sources, middleware, and every part in the family. Keep the `Include` directories; drop the rest, or the repo grows by hundreds of megabytes.
5. **Call `SystemInit()` from the reset handler** before `main()` if you use the vendor `system_<Device>.c`, and be aware that the stock version may only set up the vector table offset and a default clock — check what it actually does rather than assuming your clock is configured.

Bit definitions in CMSIS device headers come in `_Pos` / `_Msk` pairs plus a bare convenience macro. Prefer `_Pos`/`_Msk` for field writes, since they make the shift explicit:

```c
TIM3->CCMR1 = (TIM3->CCMR1 & ~TIM_CCMR1_OC1M_Msk)
            | (0x6UL << TIM_CCMR1_OC1M_Pos);   /* PWM mode 1 */
```

## HAL vs LL vs raw registers

| Layer | Code size & speed | Determinism | Portability | When it is the right choice |
|---|---|---|---|---|
| Vendor HAL | Largest, slowest, deep call chains, internal state machines and handle structs | Poor — hidden blocking loops with internal timeouts | Good within one vendor family, zero across vendors | Rapid prototyping; complex peripherals (USB, Ethernet, SDMMC) where reimplementing is not worth it |
| Vendor LL / register-level API | Thin inline wrappers over registers | Good | Same as HAL | A reasonable default: you keep register semantics but skip typing masks |
| CMSIS device header + your own driver | Smallest, fastest | Full — you can see every wait loop | Portable *design*, per-part implementation | Production bare metal; anything timing-critical, size-constrained, or safety-relevant |
| Hand-defined addresses | Same as above but error-prone | Full | None | Learning, or a part with no header available |

Mixing HAL and direct register writes on the same peripheral is the worst of both worlds: the HAL's internal state no longer matches the hardware, and its next call will "fix" your configuration. If you need register access on a HAL-managed peripheral, take over that peripheral entirely.

The pragmatic production structure is a **project-owned interface** (`uart_init`, `uart_write`, returning status codes) with a register-level implementation per target, so that the application never sees a vendor type and the implementation can be swapped when the part changes.

## Checklist

- [ ] Every register access goes through a `volatile`-qualified declaration
- [ ] Peripheral structs have explicit reserved padding, verified with `_Static_assert` on `offsetof` at each gap
- [ ] No C bitfields used to describe hardware registers
- [ ] Register constants use `UL` / `UINT32_C` suffixes; no bare `1 << 31`
- [ ] Multi-bit fields are written clear-then-set in a single store, not OR-ed in
- [ ] Write-1-to-clear registers are assigned (`=`), never read-modify-written (`|=`)
- [ ] Output pins toggled from more than one context use the atomic set/reset register
- [ ] Critical sections save and restore `PRIMASK` instead of unconditionally enabling
- [ ] Peripheral clock is enabled before the first register write to that peripheral
- [ ] Reset values checked — especially pins pre-assigned to the debug port
- [ ] The part-selection macro is set in the build system, and CMSIS headers are vendored and version-pinned
- [ ] Application code contains no vendor header types; register access is confined to the driver layer

Sources: see the Sources section of ../SKILL.md (Bare-Metal Embedded C Programming; Insider's Guide to Arm Cortex-M Development; Embedded Systems Architecture, 2nd ed.). Per-chapter attribution was not recorded for this file.
