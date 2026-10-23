# RISC-V ISA and Extensions

## Contents
- [Identify the ISA configuration](#identify-the-isa-configuration)
- [Understand base instruction sets](#understand-base-instruction-sets)
- [Check extension dependencies](#check-extension-dependencies)
- [Use toolchain evidence](#use-toolchain-evidence)

## Identify the ISA configuration

RISC-V is a modular ISA. Record XLEN, base integer ISA, implemented standard extensions, privilege specification, ABI, and any vendor-specific additions. A processor name or generic “RISC-V” label is insufficient to determine whether a binary or compiler option is supported.

## Understand base instruction sets

The base integer ISA provides control flow, arithmetic/logic, loads/stores, and system instructions. Compressed, multiplication/division, atomic, and floating-point capabilities are supplied by extensions. Privileged architecture defines execution modes and system control separately from the unprivileged instruction set.

## Check extension dependencies

Extension letters and names have versioned specifications and dependency rules. Verify assembler, compiler, linker, runtime libraries, and processor support together. Do not infer that an instruction is available because it appears in another RISC-V core or simulator.

## Use toolchain evidence

Inspect compiler target flags, ELF attributes where present, disassembly, and runtime capability reporting supported by the platform. Test fallback paths on a core without the optional extension when portability matters. Linker relaxation and compressed instruction selection can change final instruction layout and performance.

## Sources

- *Modern Computer Architecture and Organization*, 3rd ed., chapters 11–12.
- *RISC-V Architecture and DSP Processor Design*, chapter 2.
