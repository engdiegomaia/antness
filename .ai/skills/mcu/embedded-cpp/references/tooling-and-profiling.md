Toolchain choice, static analysis, host and target testing, A-B timing and profiling for C++ firmware.

## Contents

- [Choosing a compiler](#choosing-a-compiler)
- [GCC facts worth knowing](#gcc-facts-worth-knowing)
- [Static analysis](#static-analysis)
- [Unit testing](#unit-testing)
- [Measuring timing](#measuring-timing)
- [Build and environment](#build-and-environment)
- [Pitfalls](#pitfalls)

## Choosing a compiler

- Start from the functional-safety requirement. If a qualified compiler is required (IEC 61508 and its
  industry derivatives such as ISO 26262, EN 50128, IEC 62304), only commercial toolchains that ship a
  safety edition qualify, and those are typically available only in their top product tier.
- Commercial toolchains (Arm Compiler for Embedded, IAR) lag behind the standard. The book reports C++17
  as the newest standard in the commercial compilers it reviewed and C++14 in one safety edition. Check
  current versions before planning to use C++20 or C++23 features.
- GCC (arm-none-eabi) is the common free choice for non-critical work. GCC can itself be qualified by
  compiling and running test programs, documenting every issue and putting a mitigation process in place.
- Vendor IDEs (STM32CubeIDE, MCUXpresso) are Eclipse plus GCC plus GDB with configuration generators; some
  vendors use VS Code instead.

## GCC facts worth knowing

- `g++` is a driver: preprocess, compile, assemble, link. `-E` stops after preprocessing; the preprocessed
  `<cstdio>` alone adds hundreds of lines.
- The final output is an ELF file; flashing tools use binary or hex converted from it.
- Compiler Explorer (godbolt) with an `arm-none-eabi` compiler is a quick way to inspect generated code for
  a language feature.
- Useful flags: `-fno-exceptions`, `-fno-rtti`, `-Wall -Wextra -Wpedantic`, `-Werror`, `-fanalyzer` (GCC 10
  and later), `-finstrument-functions`.

## Static analysis

- Analyzers find undefined behaviour and, in commercial products, check MISRA or AUTOSAR rule compliance.
- GCC `-fanalyzer` caught an uninitialized variable and an out-of-bounds index that plain `-Wall -Wextra` did
  not. `-Wuninitialized` only fires when optimization is enabled.
- Tools differ in what they find, so run more than one: GCC analyzer, clang (and clang-tidy), cppcheck, and a
  commercial analyzer if rules compliance is required. Analysis is slower on large code bases.
- Analyzers do not prove the program does what it should; that is the job of tests.

## Unit testing

- A unit is a unit of work (what happens when a button is pressed or a packet arrives), tested in isolation.
- Most C++ test frameworks pull in `ostream` and are too large for small targets, so tests usually run on
  the host. Concerns: different type sizes (use fixed-width integers) and compiler differences (use the same
  compiler version where possible). Complement with target-side and system tests.
- Common frameworks: GoogleTest and others. GoogleTest registers tests through macros, so no manual
  registration.
- Writing for testability pushes toward loose coupling and supports TDD.

## Measuring timing

Real-time safety needs measured worst-case execution time, not reasoning.

| Technique | Notes |
|---|---|
| GPIO toggle plus oscilloscope or logic analyzer | Simple, accurate, one pin per measurement |
| MCU timer plus UART output | Uses a timer and slows the system |
| DWT and ITM (Cortex-M) | Cycle counter and data trace; ITM sends printf-style output via SWO |
| `-finstrument-functions` | Compiler inserts entry and exit hooks (`__cyg_profile_func_enter/exit`, declared `extern "C"`); log the cycle count and timestamps, map addresses with the linker map |
| ETM instruction trace | Accurate function times and call graph without modifying code, on cores that have it |
| PC sampling | Less intrusive, finds hotspots only |
| Trace formats and tools | CTF with barectf, Babeltrace, TraceCompass, SEGGER SystemView over RTT |

A-B timing measures duration from point A to point B for given inputs. If duration and result repeat for
the same inputs, the code is deterministic; heap allocation is the typical source of non-determinism.
Instrumentation costs performance, so decide whether to keep it in release.

## Build and environment

- The book builds a containerized toolchain (compiler, CMake, debugger, Renode simulator) and attaches VS
  Code to it. That makes builds reproducible across machines and CI.
- CMake needs the C, C++ and assembler compilers set explicitly when the project mixes vendor C HAL, C++
  code and an assembly start-up file. It defines the target, compile flags (C++-specific flags separate),
  linker script, CPU flags, specs (newlib-nano) and map file.

## Pitfalls

- Selecting a free compiler and discovering late that certification needs a qualified one.
- Planning around C++20 features and finding the vendor compiler stops at C++17.
- Relying on one analyzer.
- Unit tests with `int` assumptions that differ between host and target.
- Leaving heavy instrumentation in a timing-critical build.

Sources: C++ in Embedded Systems, ch 2 (measuring performance, instrumentation), ch 3 (ecosystem: compilers, analyzers, testing, profiling), ch 4 (development environment).
