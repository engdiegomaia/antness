---
name: fpga-soc-design
description: Use when designing FPGA or FPGA-based SoC hardware and software, including HDL/SystemVerilog/VHDL, synthesis, timing constraints, DSP slices, pipelines, AXI/AXI-Stream, DDR/MIG, DMA, MicroBlaze/Zynq-class SoCs, hardware/software partitioning, verification, or FPGA acceleration.
track: shared
---

# FPGA and SoC Design

Treat an FPGA design as a hardware/software system. Define interfaces, timing, data rates, memory movement, reset behavior, verification strategy, and debug access before filling the fabric with logic. Keep architecture decisions independent of a particular vendor; translate them into the selected toolchain's IP and constraint terminology only after checking the device documentation.

## Design workflow

1. **Specify behavior and performance.** Define inputs, outputs, clock domains, throughput, latency, resource budget, and fault behavior.
2. **Choose the partition.** Decide what runs in programmable logic, processor software, or fixed SoC hardware. Estimate data movement and control overhead as well as compute cost.
3. **Define interfaces and ownership.** Specify protocol, widths, address map, clock/reset, interrupts, DMA buffers, coherency, and error handling for every boundary.
4. **Build incrementally.** Simulate a small block, synthesize, inspect inferred hardware, add constraints, implement, and check timing and resource reports before integration.
5. **Verify at multiple levels.** Use unit testbenches, protocol assertions, integration tests, emulation or simulation, and board-level tests. Test reset, backpressure, stalls, overflow, and invalid transactions.
6. **Measure the implemented design.** Inspect timing paths, utilization, memory bandwidth, interrupt and DMA behavior, and end-to-end performance on the target board.
7. **Preserve reproducibility.** Version HDL, constraints, IP configuration, generated files where appropriate, tool versions, software/BSP, and bitstream provenance.

## Architecture decisions

| Question | Design consequence |
|---|---|
| Is work sequential control or wide regular data processing? | Software on a processor often suits control; pipelined or parallel logic can suit FPGA fabric. Measure interface and development costs. |
| Is the data stream continuous? | Define backpressure, buffering depth, clock crossing, and sustained bandwidth before choosing AXI-Stream or equivalent. |
| Does a processor and fabric share memory? | Define cache coherency, DMA ownership, cache maintenance, and synchronization explicitly. |
| Is external DDR needed? | Account for controller initialization, calibration, arbitration, burst efficiency, and worst-case access latency. |
| Is timing closure at risk? | Register long paths, pipeline arithmetic, constrain clocks and I/O, and inspect setup/hold reports after implementation. |

## Reference map

- [FPGA logic and implementation flow](references/logic-and-implementation.md) — HDL, simulation, synthesis, constraints, timing closure, and resource reports.
- [Resources, arithmetic, and pipelines](references/resources-and-pipelines.md) — logic cells, DSP blocks, parallelism, latency, and throughput.
- [SoC architecture and partitioning](references/soc-architecture-and-partitioning.md) — processor/fabric roles, hardware/software split, and early modeling.
- [Buses, DMA, and coherency](references/buses-dma-and-coherency.md) — AXI protocols, interconnect, address maps, data movement, and cache coherency.
- [DDR and high-speed interfaces](references/ddr-and-high-speed-interfaces.md) — memory controllers, PCIe/Ethernet links, throughput, and integration risks.
- [Embedded software, verification, and acceleration](references/software-verification-and-acceleration.md) — BSP/software integration, emulation, DSP/video workloads, and security boundaries.

## Review checklist

- [ ] Requirements include rate, latency, timing, reset, and error behavior.
- [ ] Interfaces specify clock/reset domains, widths, handshakes, address map, and ownership.
- [ ] DMA and shared-memory paths define coherency and cache maintenance.
- [ ] Testbenches cover stalls, backpressure, boundary values, and reset/recovery.
- [ ] Timing constraints match real clocks and I/O; implementation reports have no unexplained violations.
- [ ] Resource and bandwidth estimates include buffering and integration overhead.
- [ ] The bitstream, software, constraints, IP configuration, and tool versions are traceable.

## Sources

- *FPGA Programming Handbook*, 2nd ed., chapters 1–14.
- *Architecting and Building High-Speed SoCs*, chapters 1–13.

The examples are strongly tied to particular FPGA families and tool releases. Verify primitives, IP names, timing constraint syntax, board wiring, and generated software interfaces against the selected device and tool version.
