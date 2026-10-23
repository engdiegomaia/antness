# DDR and High-Speed Interfaces

## Contents
- [Plan DDR access](#plan-ddr-access)
- [Integrate high-speed links](#integrate-high-speed-links)
- [Measure end-to-end behavior](#measure-end-to-end-behavior)

## Plan DDR access

External DDR offers capacity but adds controller initialization, board routing, calibration, arbitration, refresh, and variable access latency. Specify topology, bus width, speed grade, address map, and bandwidth consumers. Consider whether on-chip memory is better for small deterministic buffers.

Burst length, alignment, bank behavior, and concurrent masters affect effective throughput. Include CPU, DMA, video, and accelerator traffic in the bandwidth budget and test contention. Memory controller IP and calibration procedures are device-specific; use the board and silicon documentation.

## Integrate high-speed links

PCIe, Ethernet, and other high-speed interfaces add protocol, clocking, transceiver, buffering, and software-stack requirements. Define link generation, lane count, topology, throughput, error handling, DMA behavior, and required endpoint/root-complex roles. Validate signal integrity and board constraints with the appropriate hardware flow.

For data exchange over PCIe or Ethernet, distinguish payload bandwidth from protocol overhead, interrupts, descriptor processing, and memory copies. Check coherency and IOMMU or protection requirements where present.

## Measure end-to-end behavior

Measure sustained rate and tail latency with representative traffic. Include initialization time, retries, arbitration, interrupt load, and software handling. A link's nominal bit rate is not application throughput. Recheck after changes to clocks, placement, bus width, DMA, or memory topology.

## Sources

- *Architecting and Building High-Speed SoCs*, chapters 4–5, 7, and 10.
- *FPGA Programming Handbook*, 2nd ed., chapters 8–9 and 12.
