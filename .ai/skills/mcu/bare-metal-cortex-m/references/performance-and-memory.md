# Performance and Memory on Cortex-M

Read this when firmware is too slow, the memory map or barriers are biting you, or you need to size, protect and reason about stack and heap on a bare-metal Cortex-M target.

## Contents

- [The memory map is an architectural contract](#the-memory-map-is-an-architectural-contract)
- [Memory types, ordering and barriers](#memory-types-ordering-and-barriers)
- [Measure before you optimize](#measure-before-you-optimize)
- [What actually makes code fast on Cortex-M](#what-actually-makes-code-fast-on-cortex-m)
- [Floating point and the double trap](#floating-point-and-the-double-trap)
- [DSP, SIMD and Helium](#dsp-simd-and-helium)
- [Caches on M7 and M55](#caches-on-m7-and-m55)
- [Compiler levers, in order of payoff](#compiler-levers-in-order-of-payoff)
- [Algorithm and source-level levers](#algorithm-and-source-level-levers)
- [The execution stack](#the-execution-stack)
- [The heap](#the-heap)
- [Machine learning on an MCU](#machine-learning-on-an-mcu)
- [Checklists](#checklists)

## The memory map is an architectural contract

Every Cortex-M has no MMU and no virtual addressing. Every symbol is reached through its physical
address, and the 4 GB space is carved into fixed architectural regions. The split is defined by Arm,
not by the vendor; the vendor only decides what hardware actually sits inside each window.

| Region | Base | Typical contents | Default type | Execute |
|---|---|---|---|---|
| Code | 0x0000_0000 | Internal flash (XIP), `.text`, `.rodata`, vector table, flash init images | Normal | yes |
| SRAM | 0x2000_0000 | Internal SRAM: `.data`, `.bss`, heap, stack | Normal | yes |
| Peripheral | 0x4000_0000 | On-chip peripheral registers | Device | no |
| External RAM | 0x6000_0000 | Off-chip SDRAM/SRAM via an external memory controller | Normal | yes |
| External device | 0xA000_0000 | Off-chip memory-mapped devices, FIFOs | Device | no |
| Private Peripheral Bus | 0xE000_0000 | SCB, NVIC, SysTick, MPU, DWT, ITM, FPB | Strongly-Ordered | no |
| Vendor / system | 0xE010_0000 | Vendor-defined system space | Vendor | no |

Practical consequences:

- **Only small windows inside each region are backed by hardware.** Touching an unmapped address
  faults. Know your part's real flash/SRAM bases and lengths before writing the linker script.
- **Vendors move the code region.** Flash often lives at a vendor base (STM32: 0x0800_0000) with an
  alias at 0x0000_0000 so the vector table is reachable from address zero. Because reading address 0
  usually succeeds, a NULL dereference silently returns the initial stack pointer instead of faulting.
  Do not rely on NULL dereference to trap; use the MPU if you want that.
- **SRAM is often non-contiguous and heterogeneous.** A part may expose one SRAM bank at
  0x2000_0000 and a second tightly-coupled bank elsewhere (CCM/DTCM, zero wait state from the core).
  These are separate `MEMORY` entries in the linker script and should be used deliberately: hot data
  and the stack in TCM, bulk buffers in general SRAM, DMA buffers where the DMA engine can actually
  reach them (many DMA controllers cannot see CCM at all — a classic silent-failure bug).
- **RAM keeps execute permission.** That is what makes `.ramfunc` and flash self-programming possible.
  It also means a stack overflow into a data region can turn into arbitrary code execution. Treat
  executable RAM as a liability unless you need it.

## Memory types, ordering and barriers

The architecture does not promise that memory transactions complete in program order. Normal memory
may be reordered, merged and buffered; Device and Strongly-Ordered memory are kept in order relative
to each other. The peripheral and system regions default to Device/Strongly-Ordered, which is why
most naive register code happens to work. The traps are at the edges.

- **`volatile` is about the compiler, barriers are about the hardware.** `volatile` stops the compiler
  from caching, reordering or eliminating an access. It says nothing about whether the write has
  actually reached the peripheral. Every memory-mapped register access needs `volatile`; some also
  need a barrier.
- **`__DMB()`** orders memory accesses either side of it without waiting. **`__DSB()`** stalls until
  all pending transactions have completed. **`__ISB()`** additionally flushes the pipeline so later
  instructions are re-fetched under the new state.
- Use `__DSB()` followed by `__ISB()` after any change that alters how instructions are fetched or
  decoded: writing VTOR, enabling/disabling the MPU, enabling or invalidating caches, enabling the
  FPU via CPACR, remapping memory, or self-modifying code.
- **The write-buffer-at-ISR-exit bug.** A write that clears a peripheral interrupt flag may still be
  sitting in a write buffer when the handler returns. The NVIC then sees the flag still set and
  re-enters the handler — a spurious double interrupt that looks like a race. Fix: `__DSB()` after the
  flag-clearing write, before returning. Some vendors instead recommend a dummy read-back of the same
  register, which has the same effect.
- **The same bug at sleep entry.** `__WFI()` can execute while a peripheral write (e.g. the one that
  was supposed to arm the wake-up source) is still buffered, and the part sleeps forever. Put a
  `__DSB()` before `__WFI()`/`__WFE()`.
- Shared state between an ISR and the main loop needs `volatile` *and* usually a critical section;
  `volatile` alone does not give you atomicity for anything wider than a naturally-aligned word, and
  gives you nothing for read-modify-write.

## Measure before you optimize

Guessing where the cycles go is wrong more often than not. Pick the cheapest instrument that answers
the question.

**DWT CYCCNT — the default choice.** A free-running 32-bit core-cycle counter in the Data Watchpoint
and Trace unit. Non-intrusive, exact, usable from application code.

```c
/* Enable once at init. */
CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;   /* power up trace */
DWT->LAR = 0xC5ACCE55;    /* unlock; required on some parts, harmless elsewhere */
DWT->CYCCNT = 0;
DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

uint32_t t0 = DWT->CYCCNT;
work();
uint32_t cycles = DWT->CYCCNT - t0;   /* unsigned math handles wraparound */
```

Pitfalls: forgetting TRCENA (CYCCNT stays zero), forgetting the lock-access write on parts that
implement it, and **DWT being optional or absent**. M0 has no DWT; M0+ typically implements DWT
without CYCCNT. On those parts fall back to SysTick or a vendor timer. DWT also exposes counters for
folded instructions, load/store cycles, sleep cycles, extra CPI cycles and exception-handling cycles —
use EXCCNT to prove interrupts polluted a measurement, LSUCNT to show a loop is memory-bound.

**SysTick — the portable fallback.** Present on every Cortex-M. Free-running 24-bit *down*-counter;
clock it from the core clock, load the reload register with its maximum, and take the difference.
The 24-bit limit is the catch: it wraps after roughly 16.7 million core cycles, which at typical
MCU clocks is a fraction of a second. Check the COUNTFLAG bit and treat any wrap as an invalid
measurement, or split the region under test.

**GPIO toggle plus logic analyzer.** Set a pin high on entry, low on exit. The only honest way to see
interrupt latency, jitter and tail distributions over thousands of events, and the only method that
survives when the core is asleep or the debugger is detached. Cost is a couple of cycles per edge.

**ITM/SWO and ETM.** ITM gives low-overhead `printf`-style and event trace over one SWO pin; ETM gives
full instruction trace and true profiling, but needs a trace-capable probe and pins the board may not
route. Newer parts (M33, M55, M85) may include a PMU that counts cache misses, branch mispredicts and
memory events directly.

**Measurement discipline:**

1. Measure a warmed-up steady state, not the first iteration (flash prefetch, caches, branch
   predictors all need warming).
2. Control interrupts: either disable them around the region, or record EXCCNT and discard polluted
   runs. Do not silently average over sporadic ISRs.
3. Run the same input repeatedly and report min and median, not a single sample.
4. Measure on the real part at the real clock with the real flash wait states. A benchmark on a
   different board, a simulator or a virtual platform tells you about relative algorithm cost, not
   about your system.
5. Re-measure after every change. Optimizations that "obviously" help regularly make things slower.

## What actually makes code fast on Cortex-M

**Instruction fetch usually dominates.** Above roughly 30–40 MHz on most parts, flash cannot keep up
with the core and the controller inserts wait states. Clock the core twice as fast and you may gain
far less than 2x, because every fetch now costs more cycles. Before blaming the algorithm, check:

- **Flash wait states** are set correctly for the current clock *and* supply voltage. Setting them too
  low is a hang or hard fault; too high is silent lost performance. Many HAL clock-setup routines get
  this right only if you call them in the right order.
- **Prefetch buffer / instruction cache / ART-style accelerator** is enabled. On parts that have one,
  this is usually the single largest free win and costs one register write.
- **Hot loops in RAM.** Placing a critical function in SRAM or ITCM removes flash wait states entirely.
  Use a linker section plus an attribute, and copy it at startup alongside `.data`:
  `__attribute__((section(".ramfunc"), noinline)) void isr_hot_path(void);`
  Budget the RAM cost; this trades the scarcest resource for speed.
- **Alignment.** Keep hot loops and functions aligned, keep data naturally aligned. Unaligned accesses
  are unsupported on M0/M0+/M23 (they fault) and merely slow on M3/M4/M7/M33. Never assume a packed
  struct field can be read as a word.

**Data placement matters as much as code placement.** Ordered fastest to slowest: TCM (DTCM/CCM,
zero wait state), internal SRAM, cached external RAM, uncached external RAM. Put the working set of a
hot loop in the fastest memory that the required bus masters can reach.

## Floating point and the double trap

- M0/M0+/M3/M23 have **no FPU**. All floating point is software emulation — tens to hundreds of cycles
  per operation. On these parts, fixed point is not an optimization, it is the design.
- M4F and M33 with FPU implement **single precision only** (FPv4-SP / FPv5-SP). M7 may have a
  double-precision FPU; M55/M85 vary by configuration. Check the part, not the core family.
- **The single most common real-world firmware performance bug:** writing `double` on a single-precision
  part. `float x = a * 0.5;` promotes to double because `0.5` is a double literal, and the whole
  expression silently falls back to software emulation, often an order of magnitude slower. So do
  `sqrt()`, `sin()`, `cos()` and friends — the unsuffixed names are the double versions. Write `0.5f`,
  call `sqrtf()`/`sinf()`, and consider `-Wdouble-promotion` to make the compiler tell you.
- Build with `-mfloat-abi=hard -mfpu=fpv4-sp-d16` (adjust the fpu name per core) so arguments pass in
  FPU registers. **Every object file and every prebuilt library in the link must agree** on float ABI
  and FPU — mismatches either fail to link or, worse, produce silently wrong results. This includes
  the C library variant you select.
- The FPU must be enabled (CPACR) before the first floating-point instruction, followed by
  `__DSB()`/`__ISB()`. Startup code that uses float before that point hard-faults.
- Lazy FPU stacking is the default: the exception frame reserves space for FPU registers but defers
  the save. It cuts latency but means **every interrupt frame is ~100 bytes instead of ~32** — size
  the stack for the reserved case.

## DSP, SIMD and Helium

- The **DSP extension** (M4, M7, M33, M35P, M55, M85) adds saturating arithmetic, SIMD on packed
  8/16-bit lanes within 32-bit registers, and single-cycle MAC. It is what makes filters, PID loops
  and fixed-point math fast.
- **CMSIS-DSP** ships hand-optimized implementations of filters, transforms, matrix and vector
  operations that pick the best available instructions per core. The measured lesson from benchmarking:
  a single purpose-built CMSIS routine beats naive C, but *composing* two CMSIS primitives to do one
  job can be slower than plain C, because of the data movement between them. Use the function that
  matches your operation, not a chain of library calls.
- **Helium (MVE)** on M55/M85 is a true vector extension (Armv8.1-M) and is the reason ML inference is
  viable on those parts. It also brings low-overhead loop instructions that remove branch overhead
  from tight loops.
- The processor choice itself is a performance lever: the same C source can run several times faster on
  an M33 than an M0+. But faster is not automatically better — if an M0+ meets the deadline, it is the
  cheaper, lower-power answer.

## Caches on M7 and M55

Only some cores have caches (M7, M55, M85, and M35P variants). Where they exist:

- **I-cache is nearly free.** Enable it, measure, keep it. There is no coherency problem for
  instruction fetch unless you write code at runtime (bootloader, flash programming) — then invalidate.
- **D-cache is where projects break.** The core sees cached data; a DMA engine sees main memory. The
  two disagree, and the bug presents as "it worked until I enabled the cache."
  - **Before a DMA transmit:** clean (write back) the buffer so the DMA reads what the core wrote.
  - **After a DMA receive:** invalidate the buffer so the core reloads what the DMA wrote.
  - Maintenance operates on **whole cache lines** (typically 32 bytes — confirm on your part). Align
    DMA buffers to the line size and round the length up, or you will clean/invalidate a neighbour's
    data and corrupt it. A DMA buffer sharing a cache line with an unrelated variable is a latent bug.
  - The robust alternative: carve a **non-cacheable MPU region** for all DMA buffers and skip
    maintenance entirely. Slightly slower accesses, dramatically fewer bugs. Prefer this unless you
    have measured that it costs too much.
- **Write-back** (default, fastest) delays writes to memory, so a peripheral or second master sees
  stale data until you clean. **Write-through** keeps memory current at a bandwidth cost and removes
  the clean-before-TX problem, not the invalidate-after-RX problem.
- Cache maintenance operations need `__DSB()`/`__ISB()` afterwards.
- Enabling caches makes timing less deterministic. For hard-real-time paths, either lock the data in
  TCM (which is never cached and always deterministic) or budget for the miss case.

## Compiler levers, in order of payoff

1. **Optimization level.** `-O0` is for stepping in a debugger and nothing else; it is routinely
   several times slower than optimized code. `-Og` keeps debugging usable with most of the win. `-O2`
   is the default production choice. `-O3` adds aggressive inlining and vectorization and sometimes
   *loses* to `-O2` on flash-bound parts because the bigger code costs more fetches. `-Os`/`-Oz`
   optimize size and, on a wait-stated flash part, sometimes win on speed too. **Benchmark all four
   on the real part.**
2. **Link-time optimization** (`-flto`). Enables cross-module inlining and dead-code elimination; real
   gains on multi-file projects. Costs: much worse debugging, longer links, and it exposes latent
   undefined behaviour and missing `volatile`/barriers as new runtime bugs. Adopt it deliberately and
   re-run your full test suite.
3. **Section garbage collection.** `-ffunction-sections -fdata-sections` with `-Wl,--gc-sections`
   removes unreferenced functions and data. Nearly free, pure flash savings. Make sure the linker
   script `KEEP`s the vector table and any section referenced only from assembly, or it will be
   garbage-collected and the part will not boot.
4. **`restrict`** on pointer parameters that genuinely do not alias. This is often the difference
   between a loop the compiler can software-pipeline and one it cannot. Lying about aliasing is
   undefined behaviour and produces bugs that appear only at high optimization levels.
5. **`static` and `const`.** `static` on file-local functions and data lets the compiler inline,
   constant-fold and discard. `const` on tables puts them in flash instead of consuming RAM for a
   second initialized copy. Both are free and both are routinely forgotten.
6. **Loop unrolling.** Leave it to the compiler first (`-funroll-loops`, implied by `-O3`). Measure;
   on flash-bound parts the extra code can cost more than the saved branches. Hand-unroll only after
   the compiler's attempt has been measured and found wanting.
7. **`-ffast-math`.** Relaxes IEEE semantics (reassociation, no NaN/Inf handling, flush-to-zero). Can
   be a large win for DSP-style code and is **wrong** for anything that depends on exact rounding,
   NaN propagation or summation order. Enable per translation unit, never globally by reflex.
8. **`volatile` discipline.** `volatile` forces a memory access per read and blocks every optimization.
   Correct for registers and ISR-shared flags; a serious speed loss on a loop variable. Copy a
   `volatile` into a local, work on the local, write back once.
9. **Inlining.** `static inline` removes call overhead for small helpers; forcing inline on large
   functions bloats flash and can slow things down. `-Winline` tells you when the compiler declined.
10. **The compiler itself.** The same C source can vary by a large factor across toolchains and flag
    sets, and vendor-aligned commercial compilers often lead on newly released cores until the
    optimizations reach GCC/LLVM. If performance is make-or-break, benchmark the alternative toolchain
    before redesigning the algorithm.

## Algorithm and source-level levers

- **Fixed point beats float** on any part without an FPU, and often beats it on an M4F for integer-ish
  workloads because the DSP SIMD lanes process two or four values per instruction. Q15/Q31 formats
  plus CMSIS-DSP are the well-trodden path.
- **Lookup tables vs computation.** A `const` table in flash replaces a transcendental call with an
  index. Weigh it against flash wait states and cache pressure — a table that misses every access can
  be slower than computing. Small tables in RAM/TCM are the sweet spot.
- **Integer width.** The core is 32-bit: `int32_t`/`uint32_t` is the natural size. Narrower types do
  *not* automatically run faster — on a 32-bit register file, `int8_t` and `int16_t` arithmetic may
  cost extra sign-extension or masking instructions. Use narrow types to save *memory* and to feed
  SIMD lanes, not reflexively for speed. Avoid `char` of unspecified signedness in arithmetic.
- **Avoid division and modulo.** M0/M0+ have no hardware divide at all (library call, tens of cycles);
  M3 and above have `SDIV`/`UDIV` but still multi-cycle. Replace division by constants with
  multiply-and-shift, `% 2^n` with a mask, and ring-buffer wrapping with a power-of-two mask.
- **Structure of arrays over array of structures** when a loop touches one field across many elements:
  better locality and a shape SIMD can use.
- **Minimize memory traffic.** Fuse passes so data is loaded once; keep accumulators in locals so the
  compiler keeps them in registers; hoist invariant loads out of loops. On a flash-bound part, loads
  and stores are frequently the real cost, and DWT's LSUCNT will tell you.

## The execution stack

Bare-metal firmware is normally single-stack. The core has two stack pointers: **MSP**, used by reset
and all exception handlers, and **PSP**, intended for thread/task stacks. Without an RTOS you usually
run everything on MSP and never touch PSP; an RTOS switches threads onto PSP and keeps handlers on MSP.

**Placement.** The initial MSP value is the first word of the vector table, so the linker script
decides it. Two viable layouts:

- *Separate region* (best, when the part offers one): put the stack in its own bank — a TCM/CCM block,
  for example. An overflow then runs off the end of a mapped region and hard-faults immediately, and
  the stack gets zero-wait-state access as a bonus.
- *Top of the single RAM region* (the common case): `_estack = ORIGIN(RAM) + LENGTH(RAM);` and let it
  grow down toward `.bss` and the heap, which grow up. Efficient use of every byte, and dangerous:
  the two fronts collide silently and corrupt each other.

**Sizing.** There is no runtime check, so compute it:

- Worst-case call-chain depth of locals and spills. `-Wstack-usage=N` warns per function; it does
  *not* sum nested calls, so it finds fat functions, not deep chains. `-fstack-usage` emits per-function
  `.su` files a script can walk over the call graph.
- Plus the deepest **ISR nesting** you permit, each frame being at minimum the 8-register hardware
  frame plus whatever the handler itself uses.
- Plus the **lazy FPU stack frame** (~100 bytes instead of ~32) for every frame that may touch float.
- Plus headroom. A stack that is exactly big enough today is a field failure tomorrow.
- **Ban recursion**, or bound its depth explicitly. Unbounded recursion is unanalyzable.
- Never put large buffers or long strings in locals; make them `static` or pass in a caller-owned
  buffer. A 1 KB local in an ISR on a 2 KB stack is an immediate overflow.

**Symptoms of overflow.** Inexplicable variable corruption, a hard fault with a nonsensical PC, a
return into garbage, faults that move when unrelated code changes. These look like compiler bugs and
almost never are.

**Detection — stack painting.** Fill the unused stack with a recognizable pattern at reset, then scan
for the surviving pattern later to get a high-water mark.

```c
/* In the reset handler, before main(), using no locals. */
extern uint32_t _estack, _stack_limit;
register uint32_t *sp __asm__("sp");
for (uint32_t *p = &_stack_limit; p < sp; p++)
    *p = 0xDEADC0DEu;

/* Later, from the main loop or a diagnostic command: */
uint32_t unused = 0;
for (uint32_t *p = &_stack_limit; p < &_estack && *p == 0xDEADC0DEu; p++)
    unused += 4;
```

Report the high-water mark over a long soak run covering every mode and every interrupt. Painting
measures what actually happened, not the theoretical worst case — use it to validate your analysis,
not to replace it.

**Other guards:**

- **MPU guard region.** Configure a small no-access region just below the stack limit. An overflow
  then faults precisely, with the faulting PC intact. The cheapest way to turn silent corruption into
  a debuggable event on cores without stack-limit hardware.
- **MSPLIM / PSPLIM** on Armv8-M (M23, M33, M55, M85): hardware stack-limit registers that fault on
  overflow with no MPU region consumed and no runtime cost. Set them at startup. If your part has
  them, use them; there is no reason not to.
- Enable the configurable fault handlers (UsageFault/BusFault/MemManage) and write a fault handler
  that captures the stacked PC, LR and the fault status registers rather than spinning in a `while(1)`.

## The heap

**Default position: no dynamic allocation in bare-metal firmware.** The reasons are not stylistic:

- **Fragmentation is unrecoverable.** With physical addressing there is no way to compact the heap.
  Alternating allocations of different sizes will eventually fail even with plenty of free bytes.
- **Timing is non-deterministic.** `malloc` walks a free list; its cost depends on history. That is
  incompatible with a hard deadline.
- **There is no good failure path.** On a single-threaded device there is no process to kill and
  nothing to swap. Out of memory usually means reset.
- Safety-critical standards generally forbid it outright.

**When it is acceptable:** allocate everything once during initialization and never free. You get the
convenience of sizing at startup without fragmentation. Fail loudly and reset if an init-time
allocation fails — that is a configuration bug, not a runtime condition.

**The right answer when you need dynamism: fixed-block pools.** A static array of N blocks of fixed
size plus a free list. Allocation and release are O(1) and deterministic, fragmentation is impossible
by construction, exhaustion is detectable and local, and the worst-case memory footprint is known at
link time. Use **several pools** for different block sizes (small messages, packet buffers, DMA
descriptors) so one subsystem cannot starve another, and place a DMA pool in memory the DMA engine
can reach and, where caches exist, in a non-cacheable region.

**newlib and `_sbrk`.** If you link the toolchain C library and anything calls `malloc` (directly or
via `printf`, `sprintf`, string functions), newlib needs you to supply `_sbrk`. A correct `_sbrk`:

1. Starts the heap pointer at the linker-exported `_end`/`_start_heap`.
2. Rounds the increment up to the word size.
3. **Checks the new break against a hard upper bound** and returns `(void *)-1` on failure so `malloc`
   returns NULL. The bound is either a linker-exported `_heap_end` or the current stack pointer minus
   a safety margin.
4. Never silently grows past that bound.

A `_sbrk` without the collision check is the default in far too many vendor templates: the heap grows
straight into the stack and the failure appears as corruption somewhere unrelated. **Export an explicit
`_heap_end` in the linker script and enforce it**, so a leak fails loudly at the allocation site
instead of quietly eating the stack.

**Classic errors, and what to do about them:**

| Error | Why it is deadly here | Mitigation |
|---|---|---|
| Assuming `malloc` succeeded | NULL deref on a part where address 0 is readable may not even fault | Check every return; define the out-of-memory strategy up front |
| Use after free | No MMU, no detection; the block may already be reissued | Null the pointer at every free site; prefer pools with ownership rules |
| Double free | Corrupts allocator metadata, fails arbitrarily later | Signature/magic word per block, breakpoint on mismatch |
| Returning a pointer to a local | Stack reused immediately; works until a different call path | Compiler warnings on, review every returned pointer |
| `malloc` inside an ISR | newlib's allocator is not reentrant; locks or corrupts | Ban allocation in interrupt context, no exceptions |
| Leak | Small heaps exhaust in minutes | Track allocation counts; break in the debugger and look for repeated same-size allocations |
| Hidden allocation | `printf`, `sprintf`, `strdup` pull in `malloc` and a large library | Use a minimal/nano printf, or a bespoke formatter |

Instrumenting the allocator is expensive. Analyzing each object's lifetime and keeping ownership
explicit is cheaper than hunting heap bugs at system level.

## Machine learning on an MCU

A short orientation, not a tutorial.

- **TensorFlow Lite for Microcontrollers (TFLite Micro)** is the de facto C++ inference runtime for
  Cortex-M: no OS, no standard C++ library, and **no dynamic allocation** required. You train in
  TensorFlow on a host, convert, and link the model in as a C array.
- **CMSIS-NN** supplies Cortex-M-optimized kernels that TFLite Micro dispatches to. It is what turns
  a nominally-running model into a usefully fast one, and it is why the **DSP extension (M4 and up)
  and Helium/MVE (M55/M85)** matter: without SIMD MACs, inference on an MCU is rarely viable.
- **Quantize to int8.** Post-training int8 quantization typically cuts model size roughly 4x versus
  float32 and maps directly onto the SIMD lanes. Accuracy loss is usually small but must be measured
  on a held-out set, per model.
- **The tensor arena is a statically sized buffer** you declare yourself: a single block the runtime
  carves up for activations. Too small and the interpreter fails to allocate at init; too large and
  you have wasted the RAM you did not have. Find the minimum empirically by shrinking until init
  fails, then add margin — and re-check whenever the model changes.
- **Budget the memory first.** Model weights in flash plus the arena in RAM usually dominate the
  firmware's footprint, and the arena competes directly with your stack and buffers. Evaluate a
  candidate model on three axes — accuracy, inference time measured on the real part, and total
  flash+RAM — and reject on any one of them before integrating.

## Checklists

**Before optimizing:**

- [ ] Flash wait states correct for the clock and voltage
- [ ] Prefetch / instruction cache / accelerator enabled
- [ ] Optimization level is not `-O0`; `-ffunction-sections --gc-sections` on
- [ ] FPU enabled and used; no accidental `double` (`-Wdouble-promotion` clean)
- [ ] A measurement harness exists (DWT CYCCNT or SysTick or GPIO toggle) and is trusted
- [ ] You know which function actually costs the time, from measurement, not from reading code

**Memory review:**

- [ ] Every memory-mapped register access is `volatile`
- [ ] `__DSB()` after clearing an interrupt flag before ISR return, and before `__WFI()`
- [ ] `__DSB()` + `__ISB()` after VTOR, MPU, cache or CPACR changes
- [ ] DMA buffers are in memory the DMA master can reach, cache-line aligned and size-rounded, or in
      a non-cacheable region
- [ ] Stack size derived from worst-case depth + ISR nesting + lazy FPU frames, with headroom
- [ ] Stack painting or MSPLIM/PSPLIM or an MPU guard region in place; high-water mark measured on a
      soak run
- [ ] No recursion, no large locals, no VLAs
- [ ] `_sbrk` enforces an explicit `_heap_end`; heap is bounded in the linker script
- [ ] No allocation after init, no allocation in an ISR; pools used where dynamism is genuinely needed
- [ ] Fault handlers capture stacked PC/LR and fault status registers instead of spinning

Sources: see the Sources section of ../SKILL.md (Bare-Metal Embedded C Programming; Insider's Guide to Arm Cortex-M Development; Embedded Systems Architecture, 2nd ed.). Per-chapter attribution was not recorded for this file.
