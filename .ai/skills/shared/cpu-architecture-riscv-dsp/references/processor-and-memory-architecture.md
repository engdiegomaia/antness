# Processor and Memory Architecture

## Contents
- [Trace the instruction path](#trace-the-instruction-path)
- [Distinguish memory architectures](#distinguish-memory-architectures)
- [Understand address translation](#understand-address-translation)
- [Budget memory and I/O](#budget-memory-and-io)

## Trace the instruction path

A processor fetches instructions, decodes them, reads operands, executes operations, and commits results. The datapath, control unit, registers, ALU, and buses determine how instructions act. ISA specifies the software-visible contract; microarchitecture specifies one implementation. A single ISA can have many implementations with different latency, throughput, power, and pipeline behavior.

Instruction categories commonly include data movement, arithmetic/logic, branches, load/store, system control, and interrupt/exception operations. When diagnosing software behavior, distinguish architecture-defined effects from microarchitecture-specific timing.

## Distinguish memory architectures

Von Neumann designs share an instruction/data path; Harvard designs separate them; modified Harvard systems combine separate caches or paths with a shared address space or memory subsystem. This affects bandwidth and deterministic access, but exact behavior depends on the implementation.

## Understand address translation

Virtual memory maps process addresses to physical memory through page tables and an MMU. TLBs cache translations; misses and page faults have different meanings and costs. Privilege, permissions, and memory attributes govern access. Check architecture mode, page-table configuration, and OS behavior before interpreting an address or access fault.

Embedded systems may use an MMU, an MPU, or neither. Do not assume desktop-style paging or isolation on a small microcontroller.

## Budget memory and I/O

Memory latency, bandwidth, bus width, burst behavior, and I/O protocol can dominate compute time. Consider SRAM/DRAM organization, refresh, prefetch, peripheral transport, and DMA. Measure effective transfer behavior rather than inferring application throughput from a bus's nominal rate.

## Sources

- *Modern Computer Architecture and Organization*, 3rd ed., chapters 2–5 and 7.
- *RISC-V Architecture and DSP Processor Design*, chapters 3–5.
