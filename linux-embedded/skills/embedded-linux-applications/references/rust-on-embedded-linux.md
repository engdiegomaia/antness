# Rust on embedded Linux

Rust can be used for Linux user-space applications and, with additional toolchain and kernel support, for selected kernel components. Choose it based on product requirements, team capability, dependency availability, and the target's compiler/runtime constraints rather than assuming it removes all memory or concurrency risks.

## User-space cross-compilation

- Select a Rust target triple compatible with the CPU, endianness, ABI, and C library used by the root filesystem.
- Configure the linker and target sysroot deliberately. Native dependencies and build scripts may execute on the host while producing target artifacts; inspect which tools run where.
- Keep dependency versions controlled and verify crates that require C libraries, bindgen, or target-specific code.
- Test the produced ELF on the target or a matching emulator; inspect architecture and shared-library requirements when startup fails.

## Kernel use

Rust-for-Linux support depends on the exact upstream kernel version, configuration, toolchain, and subsystem integration. It is not equivalent to compiling an ordinary Cargo project as a loadable module. Confirm current kernel documentation and supported abstractions before designing a Rust kernel component; keep experimental integration separate from a product's supported BSP baseline.

Prefer user-space Rust when the hardware is already represented by a stable kernel interface. Use kernel code only when the required operation belongs in the kernel and the target's supported tree provides a maintainable path.

Sources: *Embedded Linux Essentials Handbook*, ch 14 (Rust applications, cross-compilation and kernel support). Verify current Rust target and Rust-for-Linux requirements for the selected releases.
