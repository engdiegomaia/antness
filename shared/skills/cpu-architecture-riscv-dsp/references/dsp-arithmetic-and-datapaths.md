# DSP Arithmetic and Data Paths

## Contents
- [Choose fixed or floating point](#choose-fixed-or-floating-point)
- [Use MAC and saturation deliberately](#use-mac-and-saturation-deliberately)
- [Match memory to the algorithm](#match-memory-to-the-algorithm)
- [Optimize end-to-end signal processing](#optimize-end-to-end-signal-processing)

## Choose fixed or floating point

Fixed-point arithmetic can offer compact, deterministic operations on suitable cores but requires explicit scaling, range analysis, rounding, and overflow handling. Floating point simplifies dynamic range for some algorithms but has different hardware, latency, power, and determinism costs. Select based on precision requirements and the actual target implementation.

## Use MAC and saturation deliberately

Multiply-accumulate units support common filtering and transform operations. Analyze accumulator width, intermediate precision, saturation, and rounding to avoid wraparound or bias. Hardware may implement adders, multipliers, shifters, and dividers with different area/timing tradeoffs; the number of cycles and supported formats are core-specific.

## Match memory to the algorithm

DSP workloads benefit from predictable data access, sufficient bandwidth, and effective reuse. Harvard-style paths, banked memories, and ping-pong buffers can overlap compute and transfer. DMA can reduce copy overhead but introduces buffer ownership, alignment, and coherency requirements.

## Optimize end-to-end signal processing

Identify whether the bottleneck is sampling, data movement, arithmetic, control, or output. For convolution, filters, and FFTs, check algorithm complexity, coefficient/data layout, vectorization, and memory reuse. Compare output against a reference with tolerances before optimizing. Measure full pipeline latency and sustained input/output rate.

## Sources

- *Modern Computer Architecture and Organization*, 3rd ed., chapter 6.
- *RISC-V Architecture and DSP Processor Design*, chapters 1, 3, 6, and 10.
