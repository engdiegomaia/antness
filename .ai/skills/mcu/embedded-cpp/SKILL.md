---
name: embedded-cpp
description: Write, review and migrate C++ for microcontroller firmware (Cortex-M, bare metal or RTOS). Use whenever the user asks about C++ in embedded systems, whether to use C++ instead of C, -fno-exceptions, -fno-rtti, new/delete or std::vector on an MCU, std::function heap allocation, std::pmr, constexpr lookup tables, consteval, templates or concepts or CRTP for drivers, a type-safe register HAL, strong types, std::span, std::expected or error handling without exceptions, wrapping a vendor C HAL (adapter, RAII, extern "C"), a sequencer or observer or state machine in C++, ETL (Embedded Template Library), Pigweed, Boost.SML, MISRA or AUTOSAR C++ guidelines, GCC -fanalyzer, host-side unit tests for firmware, or measuring WCET with DWT/ITM or -finstrument-functions.
track: mcu
---

# Embedded C++

Practical guidance for using modern C++ (C++11 to C++23) on resource-constrained, often safety-related
firmware. Source: *C++ in Embedded Systems*. The book builds for STM32 under GCC and runs examples in the
Renode simulator; the advice is vendor-neutral. Details are in `references/`.

## When to use this skill

- Deciding which C++ features a firmware project should allow, restrict or ban.
- Reviewing C++ firmware for hidden allocation, undefined behaviour, or unsafe conversions.
- Designing drivers and HAL layers in C++ (registers, peripherals, wrapping vendor C code).
- Replacing flag-laden super-loops with a sequencer, observer or state machine.
- Choosing a toolchain, analyzers, a test approach and a timing-measurement method.

Not covered: RTOS APIs (see `freertos`, `zephyr-rtos`), start-up code and CMSIS (see `bare-metal-cortex-m`).

## Core positions

1. **Most of C++ is free.** Classes, constructors and destructors, templates, `constexpr`, lambdas,
   `std::array` and `std::span` compile to what you would write by hand. Check this in the disassembly with
   optimization on; `-O0` output is misleading.
2. **Two features break the zero-overhead rule: exceptions and RTTI.** Both have compiler switches
   (`-fno-exceptions`, `-fno-rtti`). Install a `std::set_terminate` handler either way.
3. **Dynamic memory is the real obstacle.** Allocation is non-deterministic and can fail. Safety guidance
   ranges from "none" to "only at start-up". Use fixed-capacity containers, or delete `operator new` to
   prove it.
4. **Optimization is not the enemy.** Code that breaks at `-O2` usually contains undefined behaviour.
   Enable warnings, run analyzers and test both builds.
5. **Prefer compile-time to run-time.** Concepts, CRTP, templates and `constexpr` give polymorphism, tables
   and checks without indirection or RAM.
6. **Make misuse a compile error.** Strong types, `explicit`, `= delete`, brace initialization, `enum class`,
   `std::span`, `[[nodiscard]]`.

## Feature policy (defaults)

| Feature | Default |
|---|---|
| Classes, RAII, namespaces, templates, `constexpr`, concepts, non-capturing lambdas | Use |
| `std::array`, `std::span`, `<cstdint>`, `<limits>`, `<algorithm>`, `<type_traits>` | Use |
| Virtual functions | Use with judgement; prefer templates where the type is known at build time |
| `std::function` | Restrict: may allocate when captures exceed the small buffer |
| `std::optional`, `std::expected` | Use (`expected` needs C++23 support) |
| Exceptions, RTTI | Off unless justified |
| `std::vector`, `std::string`, `std::list`, `std::map` | Avoid, use fixed-capacity versions (ETL) |
| `<iostream>` | Avoid, use `printf` family or a small logger |

Full reasoning, mitigations and safety-standard positions: [myths-and-feature-policy.md](references/myths-and-feature-policy.md).

## Workflow

1. **Set the policy.** Pick the C++ standard the toolchain really supports (commercial safety compilers may
   stop at C++14 or C++17), the allocation rule, and exceptions and RTTI settings. Record them in the build
   flags.
2. **Define interfaces.** Put hardware behind small interfaces (runtime) or concepts (compile time).
   Application logic should compile and run on the host.
3. **Wrap vendor C.** Adapter plus static-class wrapper plus RAII; keep `extern "C"` correct.
4. **Pick the error strategy** per case with the table in [error-handling.md](references/error-handling.md).
5. **Test on the host** with fakes, run static analyzers, then measure on target.
6. **Measure timing** with a cycle counter or trace, not by inspection.

## Quick reference: where to look

| Question | Reference |
|---|---|
| Is C++ too heavy? What does X cost? Which features to ban? | [myths-and-feature-policy.md](references/myths-and-feature-policy.md) |
| Which compiler, analyzer, test framework? How to measure WCET? | [tooling-and-profiling.md](references/tooling-and-profiling.md) |
| Constructors, `explicit`, virtual dispatch, namespaces, `extern "C"`, containers | [classes-and-language-basics.md](references/classes-and-language-basics.md) |
| Error codes vs asserts vs exceptions vs `expected` | [error-handling.md](references/error-handling.md) |
| Templates, concepts, CRTP, `constexpr` tables, `consteval` | [templates-and-compile-time.md](references/templates-and-compile-time.md) |
| Casts, type punning, `std::span`, strong types, lambdas, callbacks | [type-safety-and-lambdas.md](references/type-safety-and-lambdas.md) |
| Register templates, bit-field types, wrapping vendor HAL, RAII | [hal-and-c-interop.md](references/hal-and-c-interop.md) |
| Sequencer, observer, finite state machine | [patterns-for-bare-metal.md](references/patterns-for-bare-metal.md) |
| ETL, Pigweed, CIB, SOLID, testability | [libraries-and-portability.md](references/libraries-and-portability.md) |

## Review checklist

- [ ] Exceptions and RTTI flags match the project policy; a terminate handler is installed
- [ ] No hidden allocation: no `std::vector`, `std::string`, `std::function` with large captures, or iostream
- [ ] Compiled and tested with optimization on; warnings on, `-Wconversion` and `-Wsign-conversion` considered
- [ ] No signed/unsigned mixing, no `reinterpret_cast` type punning (use `memcpy` or `std::bit_cast`)
- [ ] Single-argument constructors are `explicit`; unwanted overloads are `= delete`
- [ ] Buffers passed as `std::span`, not pointer plus length
- [ ] Register access is `volatile` and goes through typed bit fields where practical
- [ ] Vendor C headers are `extern "C"` guarded; ISRs have C linkage
- [ ] Hardware-touching globals are not constructed before clocks and peripherals are ready (use `init()`)
- [ ] Lambdas passed as callbacks do not capture locals by reference past their lifetime
- [ ] Asserts: programming errors only, with a cheap production variant if needed
- [ ] Application code depends on interfaces and has host-side tests with fakes
- [ ] Timing claims backed by measurement

## Version notes

The source targets GCC and C++23 on Cortex-M with commercial compilers noted as lagging. Features by
standard: `constexpr` and lambdas C++11, relaxed `constexpr` C++14, `if constexpr` and `std::optional`
C++17, concepts, `std::span` and `std::bit_cast` C++20, `std::expected` C++23. Verify each against your
toolchain and standard library, and check whether the library is hosted or freestanding.

## Sources

Synthesised from *C++ in Embedded Systems* (chapters 1 to 18). All wording and code are original;
per-file attributions are at the end of each reference.
