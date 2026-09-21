---
name: cross-compilation
description: Cross-compilation toolchains, sysroots, CMake toolchain files, ABI matching, and diagnosing host/target contamination. Applies to both MCU and Linux tracks.
track: both
---

# Cross-Compilation

## The three things that go wrong

1. **ABI mismatch** — objects compiled with different `-mfpu`/`-mfloat-abi`/`-march`
2. **Host contamination** — a host library, header or tool leaked into the target build
3. **Wrong sysroot** — headers from one version, libraries from another

All three produce errors that look like something else. Check them first.

## Triplets

```
arm-none-eabi-        bare metal / RTOS, no OS, newlib
arm-linux-gnueabihf-  32-bit Arm Linux, hard float
aarch64-linux-gnu-    64-bit Arm Linux
riscv64-unknown-elf-  bare metal RISC-V
xtensa-esp32s3-elf-   ESP32-S3
```
`none-eabi` has no OS and no syscalls — linking it against anything expecting libc
syscalls requires stubs (`_write`, `_sbrk`, ...). That is a deliberate decision, not
a workaround.

## CMake toolchain file

```cmake
set(CMAKE_SYSTEM_NAME       Generic)       # "Linux" for Linux targets
set(CMAKE_SYSTEM_PROCESSOR  arm)

set(CMAKE_C_COMPILER   arm-none-eabi-gcc)
set(CMAKE_CXX_COMPILER arm-none-eabi-g++)

# Compiler check without a full link — required for bare metal
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

set(CMAKE_C_FLAGS_INIT "-mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard -mthumb")

# For Linux cross builds with a sysroot
set(CMAKE_SYSROOT       /path/to/sysroot)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)   # tools from the host
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)    # libs ONLY from the sysroot
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
```
The `FIND_ROOT_PATH_MODE` lines are what prevent host contamination. Without them,
`find_package` happily returns `/usr/lib/x86_64-linux-gnu`.

## ABI flags must be identical everywhere

```
-mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard -mthumb
```
Every object, every static library, every prebuilt blob. A single soft-float object
linked into a hard-float image either fails to link with an obscure message or,
worse, links and computes wrong values.

Verify:
```bash
arm-none-eabi-readelf -A lib.a | grep -E "Tag_ABI_VFP_args|Tag_FP_arch"
arm-none-eabi-objdump -f firmware.elf
file myapp   # for Linux targets: confirms architecture and interpreter
```

## Linux cross builds

```bash
# Yocto SDK
source /opt/poky/4.0/environment-setup-aarch64-poky-linux
# sets CC, CXX, CFLAGS, LDFLAGS, PKG_CONFIG_PATH, CONFIGURE_FLAGS correctly

# Manual pkg-config discipline
export PKG_CONFIG_SYSROOT_DIR=$SYSROOT
export PKG_CONFIG_LIBDIR=$SYSROOT/usr/lib/pkgconfig:$SYSROOT/usr/share/pkgconfig
unset PKG_CONFIG_PATH        # must NOT point at host paths
```
Yocto/Buildroot SDKs are the right answer — they get the sysroot, flags and pkg-config
correct. Hand-assembled toolchains drift.

## Diagnosing contamination

```bash
# Did anything from the host end up linked?
aarch64-linux-gnu-readelf -d app | grep NEEDED
strings app | grep -E "/usr/include|/home/|/usr/lib/x86_64"

# Yocto: buildpaths QA error means exactly this
# Look for absolute host paths baked into the binary
```
Host paths in a binary also break reproducible builds — the QA check is doing its job.

## Static vs dynamic

- Bare metal: always static.
- Linux: dynamic against the target sysroot's libc. Statically linking glibc is a
  licensing and correctness hazard (NSS, locale); if static is required, use musl.
- Never copy a binary built against a different libc version onto the target and expect
  it to work.

## Rust / Go cross builds

```bash
rustup target add thumbv7em-none-eabihf aarch64-unknown-linux-gnu
cargo build --target aarch64-unknown-linux-gnu    # + linker in .cargo/config.toml

GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build    # CGO off = trivially portable
GOOS=linux GOARCH=arm64 CGO_ENABLED=1 CC=aarch64-linux-gnu-gcc go build   # needs the sysroot
```
`CGO_ENABLED=0` avoids the whole class of problems when no C dependency is needed.
