# Static Analysis of AArch64 Programs

## Contents
- [Set a bounded goal](#set-a-bounded-goal)
- [Triage the artifact](#triage-the-artifact)
- [Read control flow and data flow](#read-control-flow-and-data-flow)
- [Analyze kernel binaries](#analyze-kernel-binaries)
- [Know the limits](#know-the-limits)

## Set a bounded goal

State the question before opening a disassembler: identify an input check, locate a call path, compare two builds, understand a crash site, or find a relevant kernel handler. Keep notes of observed facts separately from naming guesses. Use small address ranges and expand only when the call or data flow requires it.

## Triage the artifact

Use `file`, `readelf`, `strings`, and a hex viewer to establish format and obvious metadata. Verify that the file is not truncated, compressed, or wrapped in a vendor container. Compare header values with the expected architecture and build process. Disassembly tools can produce plausible but incorrect output when given the wrong ISA mode or a data region.

## Read control flow and data flow

Start at the entry point or a known function and identify prologue, register saves, argument use, calls, return paths, and stack adjustments. Track values through registers and memory. Use cross-references, relocations, strings, and imported symbols as clues, not proof of behavior. Compiler optimizations can merge, inline, or remove functions and transform source-level control flow.

For conditional code, pair compare/test operations with the branch they control. For loops, identify induction variables and exit conditions. For library calls, account for PLT/GOT resolution and ABI register clobbering.

## Analyze kernel binaries

Use the matching `vmlinux` and modules when possible. Inspect ELF sections, symbols, module metadata, system-register accesses, exception vectors, and code that reads per-task or exception state. Kernel structure layouts and macros depend on configuration and release; derive field offsets from the matching debug information or source, not a different kernel's headers.

## Know the limits

Static analysis cannot determine runtime values, all indirect branch targets, or behavior selected by hardware and kernel state. Obfuscation, LTO, stripped symbols, and compiler transformations reduce clarity. Confirm important claims with a controlled dynamic observation, source/build evidence, or independent analysis.

## Sources

- *Reverse Engineering Armv8-A Systems*, chapters 6, 9–10.
