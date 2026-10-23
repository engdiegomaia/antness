# Dynamic Analysis and Crash Inspection

## Contents
- [Choose a controlled environment](#choose-a-controlled-environment)
- [Inspect a process with GDB](#inspect-a-process-with-gdb)
- [Analyze stack and memory faults](#analyze-stack-and-memory-faults)
- [Inspect kernel crashes](#inspect-kernel-crashes)

## Choose a controlled environment

Use a representative Arm device for hardware- and kernel-dependent behavior. QEMU user-mode emulation can run a compatible user-space binary under host-kernel services; full-system emulation models a broader machine but may not reproduce target peripherals, timing, or implementation details. Record the emulator machine model, CPU features, kernel, and root filesystem.

Prefer a disposable lab system for unknown binaries. Preserve the original file and hash, isolate networking, and collect logs. Dynamic analysis executes code and can alter persistent state.

## Inspect a process with GDB

Load the matching executable and symbols, stop at a known function or entry point, then inspect registers, disassembly, memory, and stack. Verify the current address mapping and shared-library symbols. For stripped programs, combine dynamic symbols and disassembly with runtime observations. GDB extensions are optional and version-dependent; core conclusions should rely on standard debugger state and architecture semantics.

## Analyze stack and memory faults

Inspect stack pointer, frame records, saved return addresses, and mapped stack bounds. A corrupted return address or impossible frame chain may indicate an earlier overwrite. Follow writes to the implicated buffer, structure, or stack region and check size calculations at each layer. A later crash location may be only where corrupted state was consumed.

Compiler and kernel mitigations such as address randomization, stack protection, or address sanitizers vary by build and platform. Verify enabled configuration and binary properties rather than assuming a mitigation is active. In a debugging workflow, use sanitizing builds when supported and preserve a non-instrumented reproduction for timing-sensitive behavior.

## Inspect kernel crashes

For a vmcore, use the matching kernel image, debug information, and configuration. Confirm the dump architecture and load context before interpreting addresses. `crash` and lower-level ELF tools can inspect task state, stack, registers, and kernel structures; structure layouts and utility support are release-sensitive. A dump records a post-failure state, so correlate it with logs and the triggering workload.

## Sources

- *Reverse Engineering Armv8-A Systems*, chapters 7–8, 11–12.
