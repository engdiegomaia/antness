# Armv8-A Security Features in Binary Analysis

## Contents
- [TrustZone](#trustzone)
- [PAN and privileged access](#pan-and-privileged-access)
- [PAC and pointer integrity](#pac-and-pointer-integrity)
- [BTI and indirect branches](#bti-and-indirect-branches)
- [MTE and memory tags](#mte-and-memory-tags)

## TrustZone

TrustZone provides Secure and Non-secure states. On common Armv8-A systems, EL3 firmware handles Secure Monitor Calls and configures transitions and access controls. When analyzing firmware, identify the SMC convention, caller/callee register use, exception level, and resource ownership. Secure-world isolation depends on monitor, trusted OS, memory, and interconnect configuration; a call site alone does not prove an operation is protected.

## PAN and privileged access

Privileged Access Never restricts selected privileged accesses to user memory. Inspect the kernel's configuration and initialization path and distinguish architectural support from active policy. The PAN system register and related control fields are architecture-specific details; verify exact behavior for the target revision.

## PAC and pointer integrity

Pointer Authentication Code instructions create or check authentication codes associated with pointers, commonly to harden return addresses or function pointers. Look for compiler-generated instruction patterns, build properties, and runtime support. Missing PAC instructions do not prove the system is vulnerable, and present instructions do not protect uninstrumented paths or arbitrary data.

## BTI and indirect branches

Branch Target Identification constrains valid targets for certain indirect branches. Analyze landing-pad instructions together with executable mappings, ELF properties, compiler/linker output, and kernel enforcement. A marker in one function does not establish complete process coverage.

## MTE and memory tags

Memory Tagging Extension associates allocation and pointer tags with memory and detects mismatches in supported access modes. Check processor capability, kernel support, process controls, allocator behavior, and binary/runtime configuration. MTE can aid debugging and mitigation, but coverage and fault mode determine what a particular observation means.

## Sources

- *Reverse Engineering Armv8-A Systems*, chapters 14–15.
