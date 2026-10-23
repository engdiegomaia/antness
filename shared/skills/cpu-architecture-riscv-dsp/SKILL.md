---
name: cpu-architecture-riscv-dsp
description: Use when reasoning about processor and memory architecture, RISC-V ISA/extensions, instruction pipelines and hazards, caches and coherence, MMUs/virtual memory, atomics and ordering, processor virtualization, DSP arithmetic, SIMD, MAC units, or CPU/DSP performance tradeoffs.
track: shared
---

# CPU Architecture, RISC-V, and DSP

Use this skill to connect software-visible behavior to processor, memory, and accelerator structure. Begin with the architecture and implementation actually present; similar instruction sets and processor families can differ in supported extensions, privilege behavior, cache topology, and performance.

## Analysis workflow

1. **Identify the target.** Record ISA revision, XLEN, privilege model, extensions, microarchitecture, cache topology, memory map, and compiler/toolchain.
2. **State the workload.** Identify control flow, data types, memory access pattern, throughput, latency, power, and determinism requirements.
3. **Follow the data path.** Trace instruction fetch/decode/execute, register and memory dependencies, cache behavior, and I/O or DMA movement.
4. **Select the right optimization level.** Consider algorithm/data layout first, then compiler and ISA features, then microarchitecture or custom hardware.
5. **Check correctness constraints.** Include memory ordering, atomicity, cache coherency, alignment, overflow, fixed-point precision, and exception behavior.
6. **Measure on the target.** Compare baseline and optimized code with repeatable workloads and suitable counters; account for warm/cold caches, contention, and power state.

## Reference map

- [Processor and memory architecture](references/processor-and-memory-architecture.md) — ISA, datapath, memory hierarchy, MMU, and virtual memory.
- [Pipelines and performance](references/pipelines-and-performance.md) — hazards, branch behavior, renaming, SIMD, and profiling tradeoffs.
- [Caches and coherence](references/caches-and-coherence.md) — geometry, locality, write policies, DMA maintenance, and memory ordering.
- [RISC-V ISA and extensions](references/riscv-isa-and-extensions.md) — base instruction sets, modular extensions, privilege, and toolchain checks.
- [DSP arithmetic and data paths](references/dsp-arithmetic-and-datapaths.md) — fixed/floating point, MAC, saturation, filters, and data movement.
- [Virtualization and isolation](references/virtualization-and-isolation.md) — execution modes, address translation, traps, and resource partitioning.

## Review checklist

- [ ] ISA revision, implemented extensions, privilege modes, and ABI are verified.
- [ ] Performance claims distinguish latency, throughput, and worst-case behavior.
- [ ] Cache, DMA, coherency, and memory-ordering responsibilities are explicit.
- [ ] Arithmetic widths, overflow, rounding, and saturation are specified.
- [ ] Benchmarks use representative data and report target conditions.
- [ ] Hardware-specific claims are checked against the processor manual and actual implementation.

## Sources

- *Modern Computer Architecture and Organization*, 3rd ed., chapters 1–9, 11–14.
- *RISC-V Architecture and DSP Processor Design*, chapters 1–10.

RISC-V extensions, privileged architecture, processor cores, and toolchains evolve independently. Confirm the target specification revision and implementation documentation; the SpringCore examples in the DSP book are a particular design, not universal RISC-V behavior.
