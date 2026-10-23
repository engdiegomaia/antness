# Virtualization and Processor Isolation

## Contents
- [Separate virtualization models](#separate-virtualization-models)
- [Reason about privilege and traps](#reason-about-privilege-and-traps)
- [Map memory and device isolation](#map-memory-and-device-isolation)
- [Review embedded tradeoffs](#review-embedded-tradeoffs)

## Separate virtualization models

Virtualization can mean system virtual machines, process-level virtual environments, or ISA emulation. Identify which layer is virtualized and what is shared. A hypervisor may multiplex CPUs and memory; emulation translates instruction behavior; containers share a kernel and do not virtualize the ISA.

## Reason about privilege and traps

Privilege modes control access to system state and resources. Guest operations may trap to a more privileged layer for emulation or mediation. Review trap causes, context save/restore, interrupt routing, and timing overhead. RISC-V privileged architecture and extension support must match the processor's implemented specification.

## Map memory and device isolation

Address translation and protection separate guest or process memory, while IOMMU or bus protection may be needed for DMA-capable devices. Verify that peripheral masters cannot bypass CPU page-table protections. Shared memory requires explicit ownership and ordering.

## Review embedded tradeoffs

Virtualization can improve separation and deployment flexibility but adds memory, performance, complexity, and validation costs. Decide whether the isolation requirement justifies those costs. Test real-time deadlines, device passthrough, reset recovery, and secure boot composition on the target system.

## Sources

- *Modern Computer Architecture and Organization*, 3rd ed., chapters 5 and 13.
- *RISC-V Architecture and DSP Processor Design*, chapters 2 and 5.
