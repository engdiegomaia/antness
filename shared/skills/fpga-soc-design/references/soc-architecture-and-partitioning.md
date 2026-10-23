# FPGA SoC Architecture and Hardware/Software Partitioning

## Contents
- [Explore requirements early](#explore-requirements-early)
- [Partition computation and control](#partition-computation-and-control)
- [Define processor/fabric integration](#define-processorfabric-integration)
- [Model before committing](#model-before-committing)

## Explore requirements early

Identify processor, memory, communication, accelerator, and real-time requirements before selecting a SoC FPGA. Map which functions are fixed in the processing system, which are programmable in the fabric, and which are external. Include boot, debug, reset, clock, power, and safety/security constraints.

## Partition computation and control

Move computation into programmable logic when data parallelism, sustained throughput, deterministic pipeline behavior, or specialized interfaces justify the hardware cost. Keep orchestration, configuration, and irregular control in software when a processor is a better fit. Include communication, DMA setup, cache maintenance, and verification effort in the comparison; a fast accelerator may not improve end-to-end performance if data movement dominates.

Define ownership at each boundary: who allocates and frees buffers, starts and stops the accelerator, reports errors, handles reset, and validates descriptors. Specify interrupt behavior and timeout recovery.

## Define processor/fabric integration

Document address maps, bus widths, clock/reset sources, interrupt routing, DMA masters, and coherent/non-coherent paths. Distinguish control-plane register access from high-bandwidth data paths. Ensure software and hardware agree on register semantics, endianness, alignment, and versioning.

## Model before committing

Use a golden functional model or transaction-level model to validate algorithms and estimate performance before detailed RTL. Simulate data rates and communication overhead; use emulation or QEMU only for the portions it models. Update estimates with measured implementation and board results.

## Sources

- *Architecting and Building High-Speed SoCs*, chapters 1, 6–9, and 12.
- *FPGA Programming Handbook*, 2nd ed., chapters 11 and 13.
