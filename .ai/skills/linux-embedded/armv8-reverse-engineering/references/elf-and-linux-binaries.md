# ELF and Linux AArch64 Binaries

## Contents
- [Classify the ELF](#classify-the-elf)
- [Sections and segments](#sections-and-segments)
- [Map addresses](#map-addresses)
- [Kernel images and modules](#kernel-images-and-modules)

## Classify the ELF

Use `file` for an initial classification, then `readelf -h` to inspect class, endianness, machine, type, entry point, and table offsets. AArch64 executables use ELF64 and the AArch64 machine identifier, but the file may be relocatable, dynamically linked, position independent, or a kernel-specific image. Check rather than infer from a filename.

Inspect symbol and string tables when present. A stripped binary can still retain dynamic symbols, relocations, and strings, but those do not provide complete source-level names. Record build ID and hash so analysis can be tied to the exact artifact.

## Sections and segments

Sections organize link-time content such as `.text`, `.rodata`, `.data`, `.bss`, `.dynamic`, `.got`, and `.plt`. Program headers describe runtime loadable segments and permissions. The loader follows segments, not a simple concatenation of named sections. Use `readelf -S` and `readelf -l` together to connect file offsets, virtual addresses, sizes, and permissions.

Relocations and dynamic linking can mean that the on-disk value differs from the value after loading. PLT/GOT indirection is common in dynamically linked code; do not mistake a stub or unresolved entry for the final implementation.

## Map addresses

For a process, compare ELF virtual addresses with `/proc/<pid>/maps` and the executable's load bias. ASLR changes mappings between runs. For a kernel, account for KASLR, image relocation, and whether addresses are physical, virtual, or symbol-relative. Resolve offsets only against the exact matching artifact and runtime base.

## Kernel images and modules

`vmlinux` is the ELF kernel image useful for symbols and disassembly; the bootable `Image` may be compressed or wrapped. A `.ko` module is relocatable ELF with section and module metadata. Inspect module vermagic and dependencies as well as code. The module's final runtime address may differ because the kernel relocates it when loaded.

## Sources

- *Reverse Engineering Armv8-A Systems*, chapters 2, 8, and 10.
