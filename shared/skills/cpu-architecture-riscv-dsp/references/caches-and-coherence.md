# Caches, Coherence and Memory Ordering

How cache geometry, write policies, coherence and memory-ordering models change what firmware, driver and DSP-kernel code has to do.

## Contents

- [Cache geometry and the address split](#cache-geometry-and-the-address-split)
- [Conflict misses, 2^n strides and thrashing](#conflict-misses-2n-strides-and-thrashing)
- [False sharing](#false-sharing)
- [Write policies and what they mean for DMA](#write-policies-and-what-they-mean-for-dma)
- [Cache maintenance around DMA](#cache-maintenance-around-dma)
- [Coherent vs non-coherent interconnect](#coherent-vs-non-coherent-interconnect)
- [Memory consistency models](#memory-consistency-models)
- [Where fences and atomics actually belong](#where-fences-and-atomics-actually-belong)
- [Compiler reordering vs hardware reordering](#compiler-reordering-vs-hardware-reordering)
- [Pitfalls](#pitfalls)

## Cache geometry and the address split

A cache is an array of **sets**. Each set holds one or more **ways**; each way holds one
**cache line** (the fixed-size block transferred between adjacent memory levels), plus a
**tag** and a **valid** bit. A data cache adds a **dirty** bit per line. Line sizes vary by
architecture and cache level; query the target's cache geometry rather than assuming a common size.

Derive the geometry yourself before reasoning about any access pattern:

```
sets        = cache_size / (line_size * ways)
offset_bits = log2(line_size)
index_bits  = log2(sets)
tag_bits    = addr_bits - index_bits - offset_bits

index  = (addr >> offset_bits) & (sets - 1)
```

Worked example — 32 KiB, 64 B lines, 4-way:
`sets = 32768 / (64*4) = 128`; offset = bits [5:0]; index = bits [12:6]; tag = bits [31:13].
Address `0x2000_1A40` → index `(0x1A40 >> 6) & 127 = 0x69 & 0x7F = 105`.

| Organization | Ways | Behaviour |
|---|---|---|
| Direct-mapped | 1 | One possible home per address. Cheapest, highest conflict-miss rate. A direct-mapped cache *is* a one-way set-associative cache. |
| N-way set-associative | 2–16 typical | N lines with the same index coexist. All N tags are compared in parallel on every access. |
| Fully associative | = number of lines | Any line anywhere; one set. Best hit rate, worst area/power. Rare for I/D caches; normal for the TLB. |

Associativity costs die area and power on *every* access, because all tags in the set are
compared simultaneously. That is why fully associative I/D caches are effectively absent from
battery-powered parts, while the TLB — small enough that the win dominates — is fully
associative in practically every processor with paged virtual memory.

**Why you care:** the index bits are the *only* thing that decides where an address lands.
Two addresses with identical index bits fight for the same N ways regardless of how far apart
they are in memory.

### Level hierarchy

| Level | Typical shape | Note |
|---|---|---|
| L1 | Split I-cache + D-cache, fastest SRAM, physically closest to the core | Split L1 gives Harvard-style parallel instruction and operand access in the same cycle |
| L2 | Unified I+D, 4–8x the combined L1 capacity, 2–3x the latency | May be *inclusive* of L1 (always holds L1's lines) or not — architecture-specific |
| L3 | Unified, megabytes, 3–4x L2 latency | Often shared across cores |

Each level implements its own write policy: L1-D decides when to push to L2, L2 decides when
to push to DRAM. Cache maintenance that only reaches one level is a classic driver bug.

Tags may be virtual or physical, and a design can mix the two across levels. Virtual tagging
skips the TLB lookup on access but opens aliasing problems (the same virtual address naming
different physical addresses across contexts). This is why some SoCs require cache maintenance
on context switch — check the TRM rather than assuming.

## Conflict misses, 2^n strides and thrashing

Thrashing is not "the working set is too big". It is "too many live addresses share an index".

The pathological stride is any multiple of `sets * line_size` — the *way size*. For the
32 KiB/4-way/64 B cache above, that is 8 KiB. Walk an array with an 8192-byte stride and every
single access maps to index 0; you get 4 usable lines out of 512.

| Symptom | Likely cause | Fix |
|---|---|---|
| Hit rate collapses when a buffer dimension becomes a power of two | Row stride is a multiple of the way size | Pad the row: allocate `width + line_size` and stride by the padded value |
| FIR/FFT kernel much slower than its operation count suggests | Input, coefficient and output buffers are all page- or 64 KiB-aligned, so they collide at the same indices | Offset one or more buffers by one or two lines |
| Performance varies run to run with identical data | Allocator alignment changed the index bits | Pin alignment explicitly in the linker script or allocator |

Instruction caches thrash the same way. A loop whose body exceeds the cache size evicts its own
head on every pass: each line is still read once and reused for the instructions inside it, so
caching still helps, but every iteration now pays DRAM-latency misses. Sizing the inner loop
(and its data) to fit the anticipated L1/L2 capacity is one of the few cache-aware things source
code can do directly. The cost asymmetry is what makes it worth doing — a DRAM access can be on
the order of 25x an L1 access, and DRAM latency has improved far more slowly than core clocks.

Interrupt handlers and RTOS context switches evict lines too. A measured ISR latency number on an
idle system is optimistic; the realistic figure includes refilling what the switch destroyed.

**Do not infer cache behaviour from first principles — benchmark.** Too many factors
(prefetchers, replacement policy, other levels, OS activity) interact for analysis alone to
pick between viable implementations.

### Replacement policy

| Policy | Cost | Behaviour |
|---|---|---|
| LRU | Needs per-set age tracking hardware | Evicts the way idle longest; relies on the temporal-locality heuristic |
| Round-robin / alternating | Trivial | Can evict a hot line arbitrarily; cheaper silicon, slightly worse hit rate |

Neither is predictable enough to build hard real-time guarantees on. If you need bounded
worst-case access time for a control loop, put that data in tightly coupled memory (SRAM
mapped as non-cacheable or locked down) rather than hoping for hits.

## False sharing

Coherence is maintained per **line**, not per variable. Two cores writing two distinct variables
that happen to land in the same 64-byte line will ping-pong that line between their private
L1-Ds — every write invalidates the other core's copy, and every subsequent read goes back out
to the interconnect. The code is functionally correct and up to an order of magnitude slow.

Checklist:
- Pad per-core counters, statistics and lock-free queue head/tail indices to a full line.
- A producer index and a consumer index in the same struct is the canonical offender — separate
  them by `alignas(64)` (verify the real line size for your core).
- Arrays indexed by core ID need line-sized elements, not word-sized ones.
- Same hazard between a core and a DMA-visible descriptor field.

## Write policies and what they mean for DMA

| Policy | On a store | Consequence |
|---|---|---|
| Write-through | Updates the next level immediately on every store | DRAM is always current; write bandwidth is high |
| Write-back | Updates only the cached line, sets the dirty bit; writes out on eviction | Repeated stores to one line cost one DRAM write instead of many; DRAM is stale until eviction |

Write-back is the usual default and is the direct cause of the DMA-buffer class of bugs: a
dirty line in the core's cache holds the only correct copy of the data, while DRAM — which is
what a non-coherent DMA engine reads — still holds the old copy. The same staleness is what
makes multi-core coherence hard in the first place.

Write-through removes the stale-DRAM-on-TX problem but **not** the stale-cache-on-RX problem:
after a device writes DRAM, the core's cached copy is still wrong and must be invalidated.

Many SoCs offer a third attribute, non-cacheable or device memory, for descriptor rings and
MMIO. Trading throughput for the removal of all maintenance is often the right call for small,
infrequently touched structures. The region type is a hardware property of the address range
(see PMA below), not something the C code can choose.

## Cache maintenance around DMA

The two operations, whatever your vendor calls them:

- **Clean / flush / write-back**: push dirty lines out to the point the device sees. Needed
  *before* the device reads.
- **Invalidate**: drop cached copies so the next read refetches. Needed *before* the core reads
  what the device wrote.

Ordering is the whole game:

| Direction | Step | Order |
|---|---|---|
| CPU → device (TX) | Fill buffer → **clean** buffer range → memory barrier → write the "go" register | Clean must complete before the start trigger is visible to the device, or it DMAs stale bytes |
| Device → CPU (RX) | **Invalidate** buffer range → start DMA → wait for completion → **invalidate** again → read | The pre-start invalidate kills speculatively prefetched lines; the post-completion invalidate kills anything refetched while DMA was in flight |

Rules that save debugging time:
- Maintain by address range, not whole-cache. Whole-cache operations are slow and evict
  everything the rest of the system needed.
- Range operations round to line granularity. If a DMA buffer shares a line with an unrelated
  variable, an invalidate discards that variable's cached value — align and size DMA buffers to
  whole lines.
- Invalidate-before-start *and* invalidate-after-completion on RX. Speculative prefetch and
  hardware prefetchers can pull a line in at any point during the transfer.
- Never clean an RX buffer after the transfer: you would write the core's stale copy over the
  data the device just delivered.
- The barrier between the clean and the register write is separate from the clean itself.
  Cache maintenance completing does not imply the MMIO store is ordered after it.
- In a multi-level hierarchy, confirm the maintenance operation reaches the level the
  interconnect snoops. An L1-only clean on a system where the device sees post-L2 memory is a
  silent corruption bug.

## Coherent vs non-coherent interconnect

| | Non-coherent | Coherent (snooping / directory) |
|---|---|---|
| Who keeps copies consistent | Software, by explicit clean/invalidate | Hardware |
| DMA buffer handling | Full maintenance dance above | Allocate normal cacheable memory; no maintenance |
| Cost | Driver complexity, easy to get wrong | Interconnect area, power, snoop traffic |
| Scaling | n/a | Snooping works for a few cores; it does not scale to dozens, since every core must watch every other core's writes |

Snooping means a cache watches other masters' writes. On a write to an address it holds, it
either **invalidates** its line (next access refetches) or **updates** it in place. Larger
systems replace broadcast snooping with directory-based protocols; the specific protocol and
state names (MESI, MOESI and relatives) are implementation details — read your SoC TRM rather
than assuming.

Practical bring-up questions for a new SoC:
1. Is the DMA master on a coherent port, a non-coherent port, or configurable per-channel?
2. Do accelerators (DSP core, GPU, crypto, CLA-style control accelerators) sit inside or outside
   the coherency domain? Many SoCs are coherent for CPU clusters and non-coherent for
   accelerators — the same buffer then needs different treatment depending on which peer touches it.
3. Which memory regions are even eligible for caching? Local/tightly coupled memories are often
   private to one core or deliberately invisible to external masters, which both isolates them
   and makes them unusable as a shared handoff buffer.

**Coherence is not ordering.** A coherent interconnect guarantees everyone eventually agrees on
each address's value. It says nothing about the order in which two different addresses become
visible. Fences are still required.

## Memory consistency models

A consistency model is the contract defining the legal orders of shared-memory operations.
Models are classified by which of the four orderings — RAW, RAR, WAR, WAW — the hardware
preserves without being asked:

| Model | Relaxes | Typical implementation artifact |
|---|---|---|
| Sequential consistency | nothing | Every access in program order; no store buffering |
| Total store ordering | RAW (a load may pass an earlier store) | A store FIFO: stores are queued so loads, which stall the pipeline, get memory bandwidth first |
| Partial store ordering | RAW + WAW | Stores retire out of order with respect to each other |
| Weak ordering | all four | Software inserts barriers where it actually needs order |

RISC-V defines two: **RVWMO** (RISC-V Weak Memory Ordering, the weak model, requiring explicit
`FENCE`/atomics) and **RVTSO** (RISC-V Total Store Ordering, upheld in hardware, e.g. by a
global store FIFO). A core may apply different models to different address ranges.

This is part of the **Physical Memory Attributes (PMA)** of each address range. PMA are fixed
hardware properties of a region — not something the running program selects — covering:

1. **Region type**: main memory, I/O device, or unused "hole" (inaccessible).
2. **Access methods**: legal widths (byte through burst), alignment support,
   read/write/execute permission.
3. **Atomicity and ordering**: which atomics the region supports (AMO, LR/SC) and which
   ordering model applies.

PMA get fixed at three different times — chip design (on-chip ROM), board design (off-chip
devices on an external bus), or runtime configuration (an on-chip SRAM used as a private
per-core buffer in one mode and as shared non-cached memory in another). A region's attributes
are therefore a *system integration* fact, not an ISA fact.

Typical split: main memory uses the weak model (RVWMO) for throughput; I/O regions use strong
or program-order access, because peripheral register sequences must not be reordered. If a
region has strong ordering by PMA you do not need a fence between two accesses *within* it —
but you do need one between an I/O access and a main-memory access.

Side note on store buffers: a FIFO-queued store that has not yet reached memory is still
visible to that core's own loads through store-to-load forwarding on address match. Single-core
code never sees the buffer; other masters do.

## Where fences and atomics actually belong

RISC-V `fence` takes a predecessor set and a successor set drawn from `r`, `w`, `i`, `o`
(memory reads/writes, device input/output). `fence rw,rw` orders all prior loads and stores
before all subsequent ones. The fence is **global in scope** — it can order across main memory
and I/O regions, which is exactly what an atomic's address-scoped guarantee cannot do.

| Situation | What you need |
|---|---|
| Lock-free SPSC queue, producer | Write the payload, then `fence w,w`, then publish the index. Without it the index can become visible first and the consumer reads garbage. |
| Lock-free SPSC queue, consumer | Read the index, then `fence r,r`, then read the payload. |
| Mutex / spinlock | `amoswap` to take the lock, with acquire semantics on the acquiring access (`.aq` suffix) and release semantics on the release (`.rl`). Spin on a plain load first and only issue the atomic when the lock looks free — hammering the bus with atomics starves everyone. |
| Compare-and-swap, multi-word update | `LR`/`SC` pair: `LR` reserves the address, `SC` stores only if no other core wrote it in between and reports success in the destination register. Always loop on `SC` failure, and keep the reservation window tiny — any eviction or interrupt can break it. |
| Atomic counter | A single `AMOADD`. Cheaper and more robust than LR/SC retry loops; AMO instructions do the whole read-modify-write atomically in hardware. |
| Device register write before start | `fence w,o` (or the strongest the region needs) so the configuration stores land before the trigger. |
| Reading a status register after a write | A fence or, on strongly ordered I/O PMA, nothing — but read back the register if the write must be known to have landed. |
| Multi-core handoff of a buffer | Clean (if non-coherent) → fence → set the ownership flag with a release-ordered store. The other core reads the flag with acquire ordering, then invalidates, then reads. |
| Self-modifying code, JIT output, loading a firmware image to run | `fence.i` after the stores to instruction memory. Normal data fences do not reach the instruction path; writes went through the D-side and the I-cache/fetch pipeline must be told. |

Costs worth knowing: an AMO may lock the bus for its duration, blocking other masters and
raising their worst-case latency — a real concern for an ISR or control loop sharing the bus.
An LR/SC retry loop can livelock under contention. Neither belongs on a hot path if a per-core
variable plus a single handoff fence would do.

## Compiler reordering vs hardware reordering

Two independent reorderings, needing two independent remedies:

| | Compiler | Hardware |
|---|---|---|
| When | Build time | Run time |
| What it does | Hoists loads out of loops, sinks stores, merges or deletes accesses, caches a variable in a register | Store buffering, speculative loads, out-of-order issue, write combining, prefetching |
| Visible under | A debugger stepping through disassembly | Only another observer — another core, a DMA engine, a peripheral |
| Fixed by | `volatile`, compiler barriers (`asm volatile("" ::: "memory")`), atomics with the right memory order | `fence` / `fence.i` / the `.aq`/`.rl` suffixes on atomics |

`volatile` stops the compiler from eliding or reordering accesses to that object. It does not
emit a single barrier instruction, so it is sufficient for MMIO on a strongly ordered region
and insufficient for cross-core synchronization. Conversely, a bare inline `fence` with no
memory clobber lets the compiler move accesses across it. Use a C11/C++11 atomic with explicit
ordering, or an OS/vendor barrier macro that combines both — those macros are written to emit
the compiler barrier and the hardware fence together.

A single-core RTOS is not exempt. Preemption at an arbitrary instruction boundary exposes
compiler reordering between a task and its ISR exactly the way a second core would, which is
why shared ISR/task flags need `volatile` plus (on weak-ordered hardware) a real fence.

## Pitfalls

- Allocating a DMA buffer with `malloc`: not line-aligned, not line-sized, and neighbouring heap
  metadata shares the end line — an invalidate corrupts the allocator.
- Cleaning instead of invalidating on the RX path, overwriting freshly received data.
- Omitting the pre-start invalidate on RX and blaming the peripheral when a speculatively
  prefetched line hides the new data.
- Assuming a coherent CPU cluster means the DSP/accelerator or DMA master is also coherent.
- Padding only the producer index and not the consumer index, leaving false sharing in place.
- Benchmarking a kernel with a power-of-two stride and concluding the algorithm is slow, when it
  is the way-size collision.
- Using `volatile` as a substitute for a memory barrier between cores.
- Forgetting `fence.i` after writing code into RAM — the data store succeeded and the fetch path
  never heard about it.
- Interpreting a cache-maintenance API name literally; vendor "flush" sometimes means
  clean+invalidate and sometimes clean only. Read the implementation.
- Relying on an LR/SC loop inside an interrupt-disabled critical section whose length is
  unbounded; reservations are broken by eviction, not just by other cores.

Sources: Modern Computer Architecture and Organization, 3rd Edition, ch. 8 (cache memory,
multilevel caches, associativity, write policies, coherence and snooping) and ch. 12 (RISC-V
memory access and fence instructions); RISC-V Architecture and DSP Processor Design, ch. 5
(memory access architecture, physical memory attributes, memory consistency models, fence and
atomic instructions).
