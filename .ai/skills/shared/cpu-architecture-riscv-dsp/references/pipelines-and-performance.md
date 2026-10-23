# Pipelines and Processor Performance

## Contents
- [Measure useful performance](#measure-useful-performance)
- [Understand pipeline hazards](#understand-pipeline-hazards)
- [Branches and speculation](#branches-and-speculation)
- [SIMD and parallel work](#simd-and-parallel-work)

## Measure useful performance

Separate instruction latency, initiation interval, throughput, and total application time. A faster clock does not guarantee lower task time if memory stalls, branches, synchronization, or I/O dominate. Measure on the actual processor with representative code and data.

## Understand pipeline hazards

Pipelining overlaps instruction stages. Structural hazards occur when operations compete for a resource; data hazards arise from operand dependencies; control hazards follow branches and exceptions. Implementations may forward results, stall, replay, or predict branches. These mechanisms are microarchitecture-specific and often invisible in ISA semantics.

In-order embedded cores and larger out-of-order processors behave differently under dependency chains and independent instruction streams. Avoid assuming that assembly instruction count alone predicts cycles.

## Branches and speculation

Conditional control flow can disrupt fetch and pipeline occupancy. Branch predictors and speculative execution reduce average cost on some processors but affect timing predictability. For real-time work, use implementation documentation and measure worst-case paths; do not rely only on average branch behavior.

## SIMD and parallel work

SIMD executes one operation across multiple data elements when data layout and instruction support align. Parallelism can improve throughput but increases register pressure, memory traffic, and tail handling. Verify alignment, vector width, ISA extension support, and compiler output. For DSP-style workloads, vectorization is only useful when data dependencies permit it.

## Sources

- *Modern Computer Architecture and Organization*, 3rd ed., chapters 3, 6, 8–10.
- *RISC-V Architecture and DSP Processor Design*, chapters 3–4.
