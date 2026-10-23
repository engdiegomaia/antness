# Interrupts and DMA on Cortex-M

Read this when wiring up NVIC interrupts, pin/EXTI interrupts, ISR-to-main-loop handoff, or any DMA-driven peripheral on a bare-metal Cortex-M target.

## Contents

- [Exception model](#exception-model)
- [NVIC programming](#nvic-programming)
- [Masking and critical sections](#masking-and-critical-sections)
- [Pin interrupts (EXTI)](#pin-interrupts-exti)
- [ISR design rules](#isr-design-rules)
- [DMA fundamentals](#dma-fundamentals)
- [DMA configuration order](#dma-configuration-order)
- [DMA and cache coherency](#dma-and-cache-coherency)
- [DMA recipes](#dma-recipes)
- [Debugging checklist](#debugging-checklist)

---

## Exception model

Cortex-M has a single unified exception mechanism. "Exception" is the architectural word; "interrupt"
is an exception sourced from a peripheral. They share the vector table, the stacking behaviour and the
NVIC priority machinery.

**Exception number vs IRQ number.** The vector table is an array of function pointers at the start of the
vector table region. Entry 0 holds the *initial stack pointer*, not code. Entry 1 is Reset. System
exceptions occupy entries 2..15. Peripheral IRQ *n* lives at vector index **16 + n**. So IRQ 0 is exception
number 16. Vendor headers expose the IRQ number (`EXTI0_IRQn = 6`) and the NVIC API takes that; the
architectural exception number only matters when you read IPSR, decode a fault, or hand-build a table.

| Exc # | Name | Notes |
|---|---|---|
| 1 | Reset | Entry point; also loads MSP from entry 0 |
| 2 | NMI | Cannot be masked by PRIMASK/BASEPRI |
| 3 | HardFault | Catch-all; also where escalated faults land |
| 4 | MemManage | MPU violation (M3/M4/M7; needs enabling) |
| 5 | BusFault | Bad bus transaction, often a bad DMA/peripheral address |
| 6 | UsageFault | Undefined instruction, unaligned access, div-by-zero |
| 11 | SVC | `svc` instruction — RTOS syscall entry |
| 14 | PendSV | Software-pended, lowest priority — RTOS context switch |
| 15 | SysTick | Core timer tick |
| 16+n | IRQ n | Peripheral interrupts via NVIC |

M0/M0+ implement only Reset, NMI, HardFault, SVC, PendSV, SysTick — the configurable faults all escalate
to HardFault.

**Automatic stacking.** On exception entry the core pushes R0-R3, R12, LR, the return address and xPSR
onto the active stack, so an ISR can be a plain C function with no assembly wrapper. Callee-saved
registers (R4-R11) are preserved by normal C calling conventions. Consequence: every nesting level costs
at least 32 bytes of stack, more with FPU state.

**EXC_RETURN.** On entry, LR is loaded with a magic value (upper bits all ones) instead of a real address.
Branching to it triggers the unstacking sequence. Its low bits tell you what was interrupted:

- bit 2: which stack was in use — 0 = MSP (interrupted handler or pre-RTOS code), 1 = PSP (thread/task).
- bit 3: 0 = returning to Handler mode (you preempted another ISR), 1 = returning to Thread mode.
- bit 4 (M4F/M7): 0 = extended frame, FPU registers were stacked; 1 = basic frame.

When you land in HardFault, read this value to decide whether the faulting frame is on MSP or PSP before
you go digging for the stacked PC.

**Tail-chaining and late arrival.** If a second exception is pending when one finishes, the core skips the
unstack/restack pair and jumps straight to the next handler — cheaper than back-to-back entry on
architectures without it. "Late arrival" is the mirror case: a higher-priority exception that shows up
during the stacking of a lower one gets serviced first, reusing the same stack frame. Both are automatic;
you only need to know they exist because they make ISR *entry* latency non-constant.

**Lazy FPU stacking (M4F, M7).** By default the core reserves space for the FPU registers in the exception
frame but does not actually write them until an ISR executes an FP instruction. This keeps latency low
while still being safe. Two practical consequences:

1. Budget stack for the *extended* frame (roughly 100+ bytes per nesting level), not the basic one.
2. A single stray float in a deeply nested ISR suddenly makes the stack writes real. Size stacks for the
   worst case, or disable FP in ISRs entirely.

## NVIC programming

The NVIC registers are arrays of 32-bit words; interrupt *n* is bit `n % 32` in word `n / 32`.

| Register | Effect |
|---|---|
| `ISER[]` | Write 1 to **enable** IRQ n. Writing 0 does nothing. |
| `ICER[]` | Write 1 to **disable** IRQ n. |
| `ISPR[]` | Write 1 to force IRQ n **pending** (useful for software-triggered work). |
| `ICPR[]` | Write 1 to **clear** a pending IRQ. |
| `IABR[]` | Read-only: which IRQs are currently active. |
| `IPR[]` | Per-IRQ priority, one **byte** each. |

Use CMSIS (`NVIC_EnableIRQ`, `NVIC_SetPriority`, `NVIC_ClearPendingIRQ`) rather than hand-rolling the
index arithmetic; it is the one abstraction that costs nothing and removes a whole class of typos.

**Priority is the thing people get wrong.** Each IRQ has an 8-bit priority field, but silicon only
implements the **upper N bits**. Typically 4 bits on M3/M4/M7 (16 levels) and 2 bits on M0/M0+ (4 levels).
The unimplemented low bits read as zero and ignore writes. So the raw register value is
`priority << (8 - N)`. Two rules follow:

- **Lower numeric value = higher urgency.** Priority 0 preempts priority 5. This is the opposite of most
  RTOS task priorities, and it trips everyone at least once.
- Never write a priority directly into `IPR` without shifting. `NVIC_SetPriority()` does the shift for you
  using `__NVIC_PRIO_BITS` from the device header — use it.

Because the low bits are dropped, priorities 0 and 1 are *distinct* on a 4-bit part but *identical* on a
2-bit part. Code ported from an M4 to an M0+ can silently lose its priority ordering.

**Priority grouping.** `SCB->AIRCR.PRIGROUP` splits the implemented priority bits into a *preempt
priority* field (decides who can interrupt whom) and a *sub-priority* field (only breaks ties between
simultaneously-pending interrupts of equal preempt priority). Sub-priority never causes preemption.
Writing AIRCR requires the `VECTKEY` value in the upper half-word or the write is ignored.

Decision rule: **use all bits as preempt priority and leave sub-priority empty**, unless you have a
concrete reason. Sub-priority buys very little and makes reasoning about preemption harder. Assign a small
number of named levels (e.g. 0 = hard-deadline motor/fault, 1 = comms, 2 = timers, 3 = everything else)
rather than scattering magic numbers across drivers.

## Masking and critical sections

| Mechanism | Effect |
|---|---|
| `PRIMASK` | Masks all configurable-priority exceptions. `__disable_irq()` / `__enable_irq()`. NMI and HardFault still fire. |
| `BASEPRI` | Masks everything with priority numerically **>=** the value written. 0 disables masking. Not present on M0/M0+. |
| `FAULTMASK` | Like PRIMASK but also masks HardFault. Cleared automatically on exception return. Avoid. |

Use PRIMASK for short, unconditional critical sections (a handful of instructions updating a shared
struct). Use BASEPRI when you have genuinely hard-real-time interrupts that must stay live through a
critical section — set BASEPRI to the lowest latency-critical level and anything above it keeps running.

Always save and restore rather than blindly re-enabling, so nested critical sections don't unmask early:

```c
uint32_t primask = __get_PRIMASK();
__disable_irq();
/* ... touch shared state ... */
__set_PRIMASK(primask);
```

Keep critical sections to a few instructions. Time spent with interrupts masked is added directly to the
worst-case latency of every interrupt in the system.

**Two enables, one flag.** An interrupt only reaches the CPU if it is enabled in **both** places:

1. In the peripheral (e.g. the UART's RXNEIE bit, the EXTI interrupt mask).
2. In the NVIC (`ISER`).

Forgetting either gives silence. And on the way out, the **peripheral status flag must be cleared inside
the ISR** — the NVIC pending bit is re-asserted as long as the peripheral line is high, so an uncleared
flag makes the ISR re-enter forever and the main loop never runs again. Some flags are cleared by writing
1 (EXTI pending, most DMA flag registers), some by reading a data register, some by a read-then-write
sequence. Check the reference manual for each peripheral; the semantics are not uniform even within one
vendor.

**The write-buffer hazard.** The store that clears a peripheral flag can still be sitting in the write
buffer when the ISR returns, so the core sees the interrupt as still asserted and re-enters once
spuriously. Two fixes, pick one:

- Clear the flag **early** in the ISR, so later work covers the latency. Preferred.
- Clear it last and follow with `__DSB()` before returning.

**Handler names must match the vector table symbol exactly.** The startup file defines weak aliases
(`EXTI15_10_IRQHandler`, `DMA1_Stream5_IRQHandler`, …) pointing at an infinite-loop default handler.
A typo or wrong case compiles cleanly, links cleanly, and your ISR is simply never called — the weak
default wins. If an interrupt "does nothing", check the spelling against the startup file *first*. For
C++ sources, the handler must be `extern "C"` or name mangling produces the same silent failure.

## Pin interrupts (EXTI)

STM32 names below; most vendors have an equivalent block, sometimes integrated into the GPIO peripheral.

The EXTI controller provides a set of independent interrupt/event lines. Lines 0..15 come from GPIO pins;
the remainder are internal wake-up sources (RTC alarm, USB wake-up, PVD, …) that vary per family.

**Port selection mux.** Line *n* is fed by pin *n* of exactly one port, selected by the SYSCFG EXTI
configuration registers (`SYSCFG->EXTICR[]`; on some families this lives in a different block — on L0/G0
and friends check the name). The mux is per line number, not per port, so **PA5 and PB5 cannot both be
pin interrupts** — they share line 5. This is a design constraint on pin assignment, not something you can
work around in software. SYSCFG needs its own clock enabled before the mux is writable.

**Trigger selection.** `RTSR` and `FTSR` are independent bitmasks: set the rising bit, the falling bit, or
both for an either-edge interrupt. Setting neither means the line never triggers, which is an easy way to
configure a pin that does nothing.

**Interrupt mask vs event mask.** `IMR` unmasks a line as an *interrupt* — the NVIC line asserts and the
ISR runs. `EMR` unmasks it as an *event* — the signal reaches the core's wake-up logic and brings it out
of WFE/sleep, but **no handler executes**. Use the event path for pure low-power wake-up where the main
loop just needs to resume; use the interrupt path when you need code to run. Setting both is legal but
usually means you meant one of them.

**Shared vectors.** Lines 0..4 have dedicated NVIC vectors; lines 5..9 share `EXTI9_5_IRQHandler` and lines
10..15 share `EXTI15_10_IRQHandler`. A shared handler must demultiplex by testing the pending register and
must clear only the line it handled:

```c
void EXTI15_10_IRQHandler(void)
{
    if (EXTI->PR & (1U << 13)) {
        EXTI->PR = (1U << 13);   /* write 1 to clear — assign, do not OR */
        button_pressed = 1;
    }
    if (EXTI->PR & (1U << 14)) {
        EXTI->PR = (1U << 14);
        alert_flag = 1;
    }
}
```

**Write-1-to-clear semantics.** `EXTI->PR` is W1C. Use a plain assignment of the single bit. A read-modify-
write (`PR |= bit`) reads back *every* currently pending bit and writes them all as ones, clearing
unrelated lines you had not serviced yet. The same trap applies to every W1C status register, including
the DMA flag-clear registers.

**Debounce anyway.** An interrupt does not fix contact bounce — it makes it worse, because every bounce
edge is now an ISR entry. Handle it by ignoring further edges for a fixed window (timestamp in the ISR,
compare against a tick counter) or by sampling the pin again in the main loop after a delay. Do not put a
blocking delay in the ISR.

## ISR design rules

- **ISRs are short.** Acknowledge the hardware, grab the data, set a flag or push to a queue, return. All
  interpretation, formatting, filesystem and network work belongs in the main loop or a task.
- **`volatile` on every variable shared with an ISR.** Without it the compiler may cache the variable in a
  register and your `while (!flag) {}` spins forever at -O2. Mark pointers correctly:
  `volatile uint8_t *p` (pointee is volatile) is what you almost always want.
- **`volatile` is not atomicity and not a memory barrier.** It only forbids the compiler from eliding or
  reordering accesses *to that object*. It does not make a 32-bit read-modify-write atomic, does not order
  it against other variables, and does nothing about the write buffer. For atomic updates use a critical
  section, or `LDREX`/`STREX` (via CMSIS `__LDREXW`/`__STREXW`) on M3 and up.
- **Atomic access widths.** Aligned single loads and stores up to the bus width (8/16/32-bit) are atomic
  on Cortex-M. A 64-bit value, a struct, or any `x++` is not. If the ISR and the main loop share a counter,
  either make the ISR the only writer and the main loop the only reader, or guard it.
- **Lock-free SPSC ring buffer** is the standard producer/consumer pattern. One writer (the ISR), one
  reader (the main loop), power-of-two size, and each index written by exactly one side:

```c
#define RB_SIZE 64                     /* power of two */
static volatile uint8_t  rb[RB_SIZE];
static volatile uint16_t rb_head;      /* written by ISR only  */
static volatile uint16_t rb_tail;      /* written by main only */

/* ISR side */
static inline void rb_push(uint8_t b) {
    uint16_t next = (rb_head + 1u) & (RB_SIZE - 1u);
    if (next != rb_tail) { rb[rb_head] = b; rb_head = next; }  /* else drop */
}

/* main-loop side */
static inline int rb_pop(uint8_t *out) {
    if (rb_tail == rb_head) return 0;
    *out = rb[rb_tail];
    rb_tail = (rb_tail + 1u) & (RB_SIZE - 1u);
    return 1;
}
```

  Decide explicitly what happens on overflow — dropping the newest byte and incrementing an error counter
  is usually better than overwriting unread data silently.

- **Reentrancy.** No `printf`, no `malloc`/`free`, no shared static scratch buffers, no library call whose
  reentrancy you have not verified. `printf` in particular pulls in locks, heap and (on some libcs)
  floating point, and will either deadlock against a main-loop `printf` or blow the stack. If you must
  trace from an ISR, write a byte to a ring buffer or toggle a GPIO.
- **No floating point in ISRs** unless you understand the FPU context handling on your part — see lazy
  stacking above. If an RTOS is involved, check that it saves FP context for the tasks that use it.
- **Measure, don't guess.** Set a GPIO high on ISR entry and low on exit, then look at the scope: pulse
  width is execution time, the gap from the trigger edge to the rising edge is latency, and the spread
  across many triggers is jitter. For finer resolution use the DWT cycle counter (`DWT->CYCCNT`, after
  enabling the trace unit) and record min/max deltas into variables the debugger can read.

## DMA fundamentals

DMA solves two problems: it moves bulk data without spending CPU cycles per word, and it services fast
peripherals with hardware determinism that an ISR cannot match. For a 1 Mbit/s UART or a continuously
sampling ADC, per-byte interrupts can consume most of the CPU; with DMA the cost drops to one interrupt
per buffer.

**Structure.** A DMA *controller* contains several *streams* (STM32F2/F4/F7/H7 terminology) or *channels*
(F0/F1/F3/L0/L4/G0/G4 and most other vendors). Each stream is one unidirectional path with its own source
address, destination address, transfer count and control register. An arbiter resolves simultaneous
requests using a software priority (typically four levels) with the stream/channel number breaking ties.

**Request mapping is a hard constraint.** A given peripheral request line is not wired to every stream.
On older STM32 parts (F1/F4/F7 and similar) the mapping is **fixed in silicon**: USART2_RX can only be
served by one specific stream/channel combination, and you must look it up in the DMA request mapping
table in the reference manual before you write any code. On F4-class parts you pick the stream and then
select the channel within it via the `CHSEL` field; only one channel per stream is active at a time.
Newer families (L4, G0, G4, H7, WB, U5 and most non-ST modern parts) add a **DMAMUX** that routes any
request to any channel, removing the constraint — but check which your part has rather than assuming.
Picking an unmapped stream produces a transfer that configures perfectly and never triggers.

**Direction modes.**

| Mode | Use |
|---|---|
| Peripheral-to-memory | ADC results, UART/SPI RX, timer capture |
| Memory-to-peripheral | UART/SPI TX, DAC output, display refresh |
| Memory-to-memory | Large block copies; needs no peripheral request, runs flat out |

Memory-to-memory is the odd one out: it is usually **not allowed with circular mode**, it often requires
the FIFO rather than direct mode, and on some controllers it is supported by only one of the two DMA
instances. Check your reference manual before relying on it.

**Normal vs circular.** In normal mode the stream stops when the transfer count reaches zero and must be
reconfigured to run again. In circular mode the count is automatically reloaded and the address pointer
wraps to the start of the buffer, so the transfer runs forever — the right choice for continuous ADC
sampling, audio and always-on receive paths.

**Half-transfer and transfer-complete interrupts.** Both can be enabled. With circular mode they give you
free ping-pong buffering: on the half-transfer interrupt you process the first half of the buffer while
DMA fills the second, and on the transfer-complete interrupt you process the second half while DMA
refills the first. You must finish processing each half before DMA laps you; if not, make the buffer
bigger, not the ISR longer. Some controllers also offer an explicit double-buffer mode with two memory
address registers that it swaps between automatically.

**FIFO vs direct mode.** In direct mode each peripheral request moves one item immediately. In FIFO mode
the controller buffers items (four words on STM32F4 streams) and drains at a configurable threshold,
which reduces bus contention and is *required* for burst transfers and for source/destination widths
that differ. If you enable bursts, the burst size times the data width must not cross the FIFO threshold
boundary, and memory addresses should be naturally aligned — a mismatch produces a FIFO error rather
than a silent slowdown. When in doubt, start in direct mode with no bursts and only add FIFO/burst once
the basic transfer works.

**Widths and increment flags.** Configure peripheral data size and memory data size independently (8/16/32
bits) and set the increment flags to match the shape of the transfer. For an ADC filling an array:
peripheral width 16-bit with increment **off** (the data register does not move), memory width 16-bit with
increment **on**. Getting the memory width wrong relative to the C array type gives you correctly-sized
transfers landing at the wrong stride — classic symptom is every other array element being garbage.

## DMA configuration order

The ordering constraints are where most DMA bugs live.

1. Enable the DMA controller's clock. (Also the peripheral's clock, and the peripheral's DMA-request
   enable bit — e.g. the UART's DMAT/DMAR bits, the ADC's DMA bit.)
2. **Disable the stream** by clearing its enable bit, then **poll until the bit reads back 0**. The
   controller may need to finish an in-flight transfer; writes to the configuration registers while EN is
   still set are ignored or produce undefined behaviour. The `while (DMAx_Streamy->CR & EN) {}` spin is not
   optional.
3. **Clear all the transfer flags** for that stream in the interrupt-flag-clear register — transfer
   complete, half transfer, transfer error, FIFO error, direct-mode error. A leftover flag fires your ISR
   the instant you enable the stream.
4. Program the peripheral address, memory address and the transfer count (`NDTR` on STM32 — number of
   *data items*, not bytes).
5. Program the control register: channel/request selection, direction, circular, increments, widths,
   priority, and the interrupt enables you want.
6. Program the FIFO register if you are using FIFO mode or bursts.
7. Enable the NVIC line for the stream.
8. Enable the stream, then start the peripheral.

Reconfiguring a running stream means going back to step 2. For circular receive, you generally do not
reconfigure at all — you read `NDTR` to find out how far the controller has got.

**Error flags.** A transfer error almost always means a bad address: a peripheral register address that
was never taken (`&(USARTx->DR)` written as `USARTx->DR`), a buffer in a memory region this DMA master
cannot reach, or a null pointer. A FIFO error means a burst/threshold/width combination the controller
cannot satisfy. A direct-mode error means the peripheral requested faster than the stream could serve it.
Always enable the transfer-error interrupt during bring-up, even if you drop it later — a silent DMA
failure looks exactly like a dead peripheral.

## DMA and cache coherency

This applies to Cortex-M7 and any part with a data cache. On M0/M3/M4 there is no D-cache and this section
is moot (though the memory-reachability point below still applies).

DMA masters bypass the CPU's data cache. Two failure modes:

- **Memory-to-peripheral:** you fill a buffer, the writes sit in the D-cache, DMA reads stale RAM and
  transmits garbage. Fix: `SCB_CleanDCache_by_Addr()` **before** enabling the transfer.
- **Peripheral-to-memory:** DMA writes RAM, the CPU reads a stale cached copy. Fix:
  `SCB_InvalidateDCache_by_Addr()` **after** the transfer completes, before reading.

Rules for doing this safely:

- Cache maintenance operates on whole 32-byte cache lines. **Align the buffer to 32 bytes and round its
  size up to a multiple of 32**, or an invalidate will discard a neighbouring variable that shares the
  line — a corruption bug that moves whenever you recompile.
- Never place a DMA buffer in the same cache line as unrelated data. Give DMA buffers their own section.

The alternative, and usually the better one: **put DMA buffers in a non-cacheable region** — an MPU region
configured as Device or Normal non-cacheable, or a linker section placed in SRAM the vendor marks
non-cacheable. Then no maintenance calls are needed and no one can forget one.

**Reachability trap (part-specific).** Not all RAM is reachable by all bus masters. The classic case is
tightly-coupled memory — DTCM on M7 parts, CCM RAM on STM32F3/F4 — which the CPU reaches at full speed but
which some DMA controllers cannot address at all. Since the linker usually puts `.bss` and `.data` in the
default RAM region, this only bites when someone "optimises" a buffer into TCM/CCM and the transfer starts
failing with a transfer error. On H7-class parts with multiple SRAM banks and multiple DMA controllers,
check the bus matrix in the reference manual: which master can see which bank is a per-part answer.

## DMA recipes

**ADC scan + circular DMA to an array.** Configure the ADC for scan mode across N channels, continuous
conversion, and enable its DMA request (plus the "DMA requests continue after last transfer" bit if your
part has one — without it the ADC stops requesting after the first sequence). Set the stream
peripheral-to-memory, circular, peripheral address = ADC data register with increment off, memory address
= your `uint16_t[N]` with increment on, both widths 16-bit, `NDTR` = N. Start the stream, then start the
ADC. From then on the array always holds the latest sample set with zero CPU cost. Declare the array
`volatile` and be aware a read can race a DMA write mid-array; for coherent sets, use half/full-transfer
interrupts with a double-length buffer.

**UART TX via DMA.** Memory-to-peripheral, normal mode, memory increment on, `NDTR` = message length.
**Caveat:** the DMA transfer-complete interrupt fires when the last byte has been handed to the UART's
data register, *not* when it has left the wire. If you need to know transmission is finished — before
disabling the UART, switching an RS-485 driver-enable line, or entering sleep — wait on the UART's own
transmission-complete flag, not on the DMA flag. Also do not reuse or free the source buffer until the
transfer really completes; a stack-local string is a common cause of garbled output.

**UART RX via circular DMA + idle-line interrupt.** The standard solution for variable-length frames.
Set up a circular peripheral-to-memory stream into a buffer comfortably larger than the longest frame, and
separately enable the UART's IDLE-line interrupt. The IDLE interrupt fires when the line has been quiet
for one character time — i.e. at the end of a frame. In that ISR, compute how many bytes arrived from
`buffer_size - NDTR`, compare against where you last read to, and hand that span to the main loop. Add
the half-transfer and transfer-complete interrupts if frames can be long enough to wrap. This gives you
framing with no per-byte interrupts and no fixed message size. Remember the IDLE flag has its own clear
sequence (read SR then DR on older parts, write to ICR on newer ones).

**SPI full-duplex.** SPI shifts in a byte for every byte it shifts out, so full-duplex **needs two
streams**: memory-to-peripheral for TX and peripheral-to-memory for RX, both the same length. Configure
and enable the RX stream *first*, then TX, then enable SPI — otherwise the first received byte lands
before the RX path is armed and you get a one-byte offset through the whole transfer. If you only care
about receiving, you still need a TX stream feeding dummy bytes to generate the clock; point it at a
single constant with memory increment off. Completion is signalled by the RX stream, not the TX one.

## Debugging checklist

ISR never runs:

1. Handler name spelled exactly as in the startup file (and `extern "C"` in C++)?
2. Peripheral interrupt enable bit set?
3. NVIC enable set for the right IRQ number?
4. For EXTI: SYSCFG clock enabled, port mux pointing at the right port, at least one of RTSR/FTSR set?
5. Global interrupts re-enabled after init?

ISR runs once then hangs, or runs forever:

1. Peripheral flag cleared inside the ISR?
2. W1C register written with a plain assignment of one bit, not `|=`?
3. Flag cleared early, or `__DSB()` before return?
4. Shared vector handler demultiplexing correctly and not falling through?

DMA configured but nothing moves:

1. Does this peripheral request actually map to this stream/channel on this part?
2. Peripheral's own DMA-request-enable bit set?
3. Did EN read back 0 before you reconfigured?
4. Stale flags cleared before enabling?
5. Peripheral address is the *address of* the data register?

DMA moves wrong data:

1. Memory width matches the C array element type, increments set correctly?
2. `NDTR` counts items, not bytes?
3. On M7: buffer cleaned before TX / invalidated after RX, 32-byte aligned and size-rounded?
4. Is the buffer in RAM this DMA controller can reach?

Sources: see the Sources section of ../SKILL.md (Bare-Metal Embedded C Programming; Insider's Guide to Arm Cortex-M Development; Embedded Systems Architecture, 2nd ed.). Per-chapter attribution was not recorded for this file.
