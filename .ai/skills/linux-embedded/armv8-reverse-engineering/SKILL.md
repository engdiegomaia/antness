---
name: armv8-reverse-engineering
description: Use when inspecting AArch64 ELF executables, shared libraries, Linux kernels or modules; analyzing Arm64 disassembly, registers, calling conventions, exception levels, GDB state, vmcore dumps, stack corruption, control flow, uftrace output, or Armv8-A security mitigations.
track: linux-embedded
---

# Armv8-A Reverse Engineering

Use this skill to form and test hypotheses about an AArch64 binary. Begin with the artifact and its execution context, then combine ELF metadata, instruction semantics, control flow, runtime state, and kernel or platform knowledge. Reverse engineering supports debugging, compatibility analysis, and defensive security review; treat conclusions as evidence-based hypotheses until confirmed.

## Analysis workflow

1. **Identify the artifact.** Record source/provenance, hash, architecture, endianness, ABI, file type, build ID, and whether it is stripped or compressed.
2. **Set the goal.** Choose one question: identify entry point, trace a call, recover a structure layout, explain a crash, or understand a security boundary.
3. **Map execution context.** Determine user vs kernel, process vs module, exception level, loaded address, ASLR/KASLR state, and symbols available.
4. **Start broad, then narrow.** Inspect ELF headers and segments, imports/relocations and strings; then follow AArch64 calling convention, data flow, branches, and memory accesses.
5. **Use runtime evidence when needed.** Inspect registers, mappings, stack, syscalls, or trace output under GDB, QEMU, a lab device, crash tools, or `uftrace` where appropriate.
6. **Correlate and record.** Resolve addresses with the matching image and load base. Record commands, tool versions, assumptions, and evidence supporting each conclusion.

## Essential cautions

- Architecture defines instruction and exception behavior; the Cortex implementation and SoC determine many optional features and system details.
- Optimized code may inline, reorder, merge, or remove source constructs. Do not assume one source statement maps to one instruction.
- Kernel internals, structure layouts, symbol addresses, and tracing facilities vary by release and configuration. Match `vmlinux`, modules, source, and configuration.
- Static analysis cannot establish runtime values; dynamic analysis observes only the exercised path and can alter execution.
- Security mitigations such as PAC, BTI, PAN, MTE, and TrustZone depend on hardware, kernel, compiler, and binary support. Verify actual coverage.

## Reference map

- [AArch64 fundamentals](references/aarch64-fundamentals.md) — registers, PSTATE, AAPCS, exception levels, and vectors.
- [ELF and Linux binaries](references/elf-and-linux-binaries.md) — headers, sections, segments, relocations, modules, and address mapping.
- [AArch64 instruction analysis](references/a64-instruction-analysis.md) — data processing, memory access, branches, conditions, and system calls.
- [Static analysis](references/static-analysis.md) — artifact triage, control-flow reading, kernel binaries, and limitations.
- [Dynamic analysis](references/dynamic-analysis.md) — GDB, QEMU, stack and crash analysis, vmcore, and runtime correlation.
- [Execution tracing with uftrace](references/uftrace.md) — function instrumentation and call, argument, and return analysis.
- [Armv8-A security features](references/armv8-security-features.md) — TrustZone, PAN, PAC, BTI, and MTE analysis.

## Review checklist

- [ ] The binary architecture, ABI, load address, and build provenance are known.
- [ ] The analysis uses matching symbols and kernel/module artifacts where available.
- [ ] Register roles, stack state, and exception level match the observed context.
- [ ] Branches and memory accesses are traced from actual instruction semantics.
- [ ] Address randomization, relocation, and optimization effects are accounted for.
- [ ] Findings distinguish static evidence, observed runtime behavior, and inference.

## Sources

- *Reverse Engineering Armv8-A Systems*, chapters 1–15.

Use current Arm Architecture Reference Manuals and kernel/tool documentation to verify details for the specific architecture revision, kernel version, compiler, and analysis tools.
