Choosing libraries for C++ firmware (standard library, ETL, Pigweed, CIB) and designing for portability and testability.

## Contents

- [Standard library: what suits firmware](#standard-library-what-suits-firmware)
- [Embedded Template Library](#embedded-template-library)
- [Pigweed](#pigweed)
- [Compile-time initialization and build (CIB)](#compile-time-initialization-and-build-cib)
- [Portability and SOLID](#portability-and-solid)
- [Testability](#testability)
- [Pitfalls](#pitfalls)

## Standard library: what suits firmware

The standard defines hosted and freestanding implementations. Bare-metal GCC projects often mix them: a
custom entry point and no OS, but hosted headers available. `-ffreestanding` requests the freestanding
library. Check which headers your toolchain really provides; for example `std::function` is not part of the
freestanding set.

| Generally fine | Notes |
|---|---|
| `<cstdint>` | Fixed-width integers for registers and protocols |
| `<limits>` | `std::numeric_limits` replaces magic constants |
| `<array>`, `<span>`, `<algorithm>`, `<numeric>`, iterators | No heap; `.at()` checks bounds |
| `<type_traits>`, `<concepts>` | Compile-time only |
| `<cmath>` | Costly without an FPU; consider fixed-point or approximations |
| `std::priority_queue` | Swap the default `std::vector` for a fixed-capacity vector |

| Avoid or restrict | Why |
|---|---|
| `std::vector`, `std::list`, `std::string`, `std::map` | Dynamic allocation (see [myths-and-feature-policy.md](myths-and-feature-policy.md)) |
| `<iostream>` | Large footprint and heap use; use `printf` family or a tiny logger |
| `std::function` | May allocate for large captures; not freestanding |

## Embedded Template Library

ETL mirrors standard containers and algorithms with a compile-time maximum size and no run-time allocation:
`etl::vector`, `etl::list`, `etl::string`, `etl::array` (for pre-C++11), `etl::delegate` (callable holder;
non-owning, no capturing lambdas, so watch for dangling), plus a message framework (routers, buses, FSMs),
CRC, checksums and hashes. Containers work with most standard algorithms and adapters. Error handling is
configurable (throw or call a user handler). Check overflow behaviour for each container against your safety
policy.

## Pigweed

Google's Pigweed is a modular collection and a development ecosystem: hardware interfaces already
implemented for several targets, logging, assertions, RPC (Protocol Buffers via nanopb), build and host
simulation. Its Sense tutorial runs the same application on a simulator and on hardware thanks to interface
design. It has a steep learning curve and is better suited to larger projects and teams. Modules vary in
maturity, so evaluate each one and its memory cost. Embedded Proto is a pure C++, static-allocation
Protocol Buffers alternative developed with MISRA C++ in mind.

## Compile-time initialization and build (CIB)

Intel's CIB builds on compile-time Observer wiring: components declare which services they extend (such as
`runtime_init`, `main_loop`) and a project struct lists the components. Adding or removing a component is a
declarative change, and `main` just runs the services. Wiring is resolved at build time so run-time overhead
is minimal. It also has logging, interrupt, message and string-constant libraries. It is a header library that
was not available in Compiler Explorer at the time; evaluate the toolchain requirement (modern C++) first.

## Portability and SOLID

Hardware changes (the 2020-2022 supply crisis forced component swaps), so firmware should survive replacing
sensors, drivers or the MCU. Write application code against interfaces and implement them per platform; the
same code then runs on the host in tests.

- **Single responsibility:** each class has one reason to change (an `accelerometer` interface, the `adxl_345`
  protocol class, the `i2c` bus interface, its STM32 implementation, the tap-detection algorithm).
- **Open/closed:** a new MCU needs only a new `i2c` implementation; a new sensor only a new `accelerometer`
  implementation.
- **Liskov substitution:** a derived class must honour the base contract; silently ignoring an unsupported
  sampling rate breaks it (return an error instead).
- **Interface segregation:** do not force an accelerometer to implement gyroscope and magnetometer calls
  because they share a broad IMU interface.
- **Dependency inversion:** high-level code depends on abstractions. Use runtime interfaces where the type
  varies at run time, or templates and concepts where it is fixed at build time (see
  [templates-and-compile-time.md](templates-and-compile-time.md)).

Readability first; optimize for performance only where measurement shows it matters.

## Testability

Interface-based design lets you substitute a fake. Example: a `fake_accel` returns a scripted sequence of
samples, and a GoogleTest case checks that the tap detector reports no tap for the first two samples and a
tap on a sudden change. No hardware, vendor code or timing is involved. This is also why the static-class
and adapter techniques in [hal-and-c-interop.md](hal-and-c-interop.md) matter.

## Pitfalls

- Assuming a library is allocation-free without reading its configuration.
- Adopting Pigweed or CIB for a small project and paying the learning and memory cost.
- Interfaces that are too broad and force stub methods.
- Hiding platform assumptions (register layout, endianness) in "portable" classes.
- Using `etl::delegate` with a callable that has gone out of scope.

Sources: C++ in Embedded Systems, ch 17 (libraries and frameworks), ch 18 (cross-platform development, SOLID, testability), ch 14 and ch 2 (ETL and standard-library background).
