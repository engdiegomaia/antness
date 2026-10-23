# On-Chip Buses, DMA, and Coherency

## Contents
- [Choose the transaction model](#choose-the-transaction-model)
- [Specify AXI-style interfaces](#specify-axi-style-interfaces)
- [Design DMA ownership](#design-dma-ownership)
- [Handle cache coherency](#handle-cache-coherency)

## Choose the transaction model

Use memory-mapped transactions for control and addressable storage; use streaming handshakes for continuous data where the protocol fits. Bus choice affects throughput, latency, buffering, arbitration, and verification. Define the expected bandwidth and transaction sizes rather than selecting an interface by name alone.

## Specify AXI-style interfaces

AXI separates address, data, and response channels; AXI-Stream uses a data handshake with optional sideband information. Verify the specific protocol revision and vendor IP behavior. Handle valid/ready backpressure, burst boundaries, response errors, alignment, IDs, and outstanding transactions. Do not assume an accepted address means data has completed.

Use protocol checkers or assertions to exercise stalls and simultaneous channel activity. For bridges between protocols, state what buffering and ordering guarantees are preserved.

## Design DMA ownership

DMA moves data without processor copies but introduces shared-state and lifetime hazards. Define buffer alignment, size, ownership transitions, descriptor format, completion/error signaling, and what software may access while transfer is active. Include timeout, cancellation, reset, and partial-transfer behavior.

## Handle cache coherency

If CPU and device do not share coherent access, software must perform cache maintenance and memory barriers according to the OS, architecture, and DMA API. A coherent interconnect does not eliminate ordering, ownership, or lifetime rules. Use platform-supported DMA mapping APIs in software and verify the actual hardware path; do not substitute guessed physical addresses or raw cache operations for the supported interface.

Atomicity matters when multiple agents share descriptors or status. Define which agent writes each field and how ownership is published and consumed.

## Sources

- *Architecting and Building High-Speed SoCs*, chapters 3–4, 8, and 10.
- *FPGA Programming Handbook*, 2nd ed., chapters 8–9.
