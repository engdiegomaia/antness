# FPGA Resources, Arithmetic, and Pipelines

## Contents
- [Estimate device resources](#estimate-device-resources)
- [Choose arithmetic structures](#choose-arithmetic-structures)
- [Balance throughput and latency](#balance-throughput-and-latency)
- [Inspect reports](#inspect-reports)

## Estimate device resources

An FPGA may provide lookup tables, flip-flops, block RAM, DSP slices, clocking resources, and high-speed transceivers. Availability and mapping rules are family-specific. Estimate logic, state, memory ports, arithmetic width, clock domains, and I/O needs, then compare against device capacity with integration margin.

Storage inference depends on coding style, reset requirements, port count, and access pattern. A reset on every memory element may prevent block RAM inference. Replicated memories can increase capacity use when extra read ports are required.

## Choose arithmetic structures

Parallel combinational arithmetic can reduce cycle count but increase area and routing delay. A pipelined implementation adds registers and latency while potentially increasing clock rate and sustained throughput. Resource sharing can save hardware at the cost of control and throughput. Use DSP blocks where the target architecture and synthesis flow can infer or instantiate them effectively.

For fixed-point DSP, define scale, signedness, rounding, saturation, and overflow behavior at each stage. Validate with numerical test vectors and account for quantization when selecting intermediate widths.

## Balance throughput and latency

Throughput is the rate at which new work can be accepted; latency is the time for one item to traverse the design. Pipelining can improve throughput without reducing latency. Calculate cycles per result, clock rate, initiation interval, and buffer requirements. Include stalls and downstream backpressure in the model.

## Inspect reports

Review resource utilization, inferred operators and memories, critical paths, high-fanout signals, and clock domain crossings. Compare estimates to implemented reports. A design that fits nominally may still fail because of routing, clock, transceiver, or package constraints.

## Sources

- *FPGA Programming Handbook*, 2nd ed., chapters 6–7 and 14.
- *Architecting and Building High-Speed SoCs*, chapters 5, 7, and 13.
