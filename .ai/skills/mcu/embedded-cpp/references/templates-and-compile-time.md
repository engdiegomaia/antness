Templates, concepts, static polymorphism, and compile-time computation (`constexpr`, `consteval`) for firmware.

## Contents

- [Template basics](#template-basics)
- [Constraining templates](#constraining-templates)
- [Static polymorphism instead of virtual functions](#static-polymorphism-instead-of-virtual-functions)
- [Compile-time computation](#compile-time-computation)
- [Worked ideas: parsers and lookup tables](#worked-ideas-parsers-and-lookup-tables)
- [consteval](#consteval)
- [Pitfalls](#pitfalls)

## Template basics

- A template is a pattern, not a function or type. The compiler instantiates a real function or class for
  each distinct set of template arguments it deduces or is given; each instantiation is a separate type
  (`std::array<int, 4>` and `std::array<int, 8>` are unrelated types).
- An instantiation fails to compile if the type lacks what the body needs (for example no `operator+`).
- Full specialization supplies a custom implementation for one type.
- `auto` deduces a variable's type; `decltype` gets an expression's type; `static_assert` with
  `std::is_same_v` verifies deduction at compile time.
- Binary-size myth: one generic type costs no more than hand-writing the same type for each element type,
  and identical instantiations are merged by the linker. See [myths-and-feature-policy.md](myths-and-feature-policy.md).
- Build time grows with instantiations spread over many translation units.

## Constraining templates

| Technique | Use |
|---|---|
| `std::enable_if` plus `<type_traits>` (`std::is_arithmetic`, `is_integral`, `is_floating_point`) | Pre-C++20; enable or disable an overload (SFINAE: substitution failure is not an error). Error messages are long and hard to read |
| `if constexpr` (C++17) | Choose a code path at compile time inside one function, instead of two near-identical templates |
| Concepts (C++20) | Name the requirements (`Arithmetic`), put them on the template parameter. Intent is visible in the declaration and errors say which constraint failed |

Prefer concepts where the toolchain allows C++20. Prefer `if constexpr` to duplicated overloads that differ
in one branch.

## Static polymorphism instead of virtual functions

Dependency inversion (high-level code depends on an abstraction, not a concrete driver) can be done at
compile time when all types are known, which is normal in firmware. Two ways:

1. **Template parameter.** `gsm_lib<Uart>` holds a reference to a `Uart` and calls `write(std::span<char>)`.
   Any type with a matching `write` compiles. Simple, but the interface is implicit.
2. **CRTP plus a concept.** A base template `uart_interface<Derived>` exposes `init()` that calls
   `static_cast<Derived&>(*this).initImpl()`. The concrete class derives from the template instantiated
   with itself. A concept (for example `TheUart`) then requires the argument to derive from
   `uart_interface<T>`, making the contract explicit.

Benefit over virtual: no vtable, no indirect call, calls can inline. Cost: each instantiation is its own type,
the code is harder to read, and the type must be known at compile time (no swapping at run time).

## Compile-time computation

- A compiler can evaluate a function at compile time only if every argument is known at compile time.
- Template metaprogramming (recursive templates, for example a factorial in a type's `value`) works but is
  hard to read. Use `constexpr` instead.
- `constexpr` variables must be initialized immediately with a constant expression and have a literal type.
  They replace macro constants and add type safety (a macro `VOLTAGE / CURRENT` of two integer literals
  does integer division).
- A `constexpr` function can run at compile time or run time depending on its arguments. C++14 relaxed the
  rules so loops are allowed (C++11 needed recursion).
- At `-O0` a plain `square(2)` still produces calls and stack traffic; marking it `constexpr` makes the
  compiler fold it to the constant. Check generated code on your target compiler.
- Math library functions are not uniformly `constexpr`. The book found GCC accepts `sin` in a constant
  expression while Clang rejected it. Verify per compiler; do not depend on it for portable code.

## Worked ideas: parsers and lookup tables

- **Compile-time MAC address parser.** A `constexpr` constructor takes `"00:11:22:33:44:55"` and fills a
  `std::array<uint8_t, 6>`. The book confirmed the parsing code is absent from the binary by comparing sizes
  of two builds (identical).
- **Thermistor lookup table.** Compute temperature from resistance with the Steinhart-Hart equation (four
  manufacturer coefficients, more accurate than the two-point beta method but too heavy to run on a small
  MCU) over an evenly spaced resistance range at compile time, and store the table in flash. At run time:
  read the ADC, convert to resistance with the voltage-divider formula, look up the temperature. The book
  composes the table from a `constexpr` linear-space generator and a small signal class with overloaded
  operators.
- The same approach suits UUIDs, CRC tables, sine tables and filter coefficients.

## consteval

`consteval` (C++20) marks an immediate function: every call must be a compile-time constant, or the build
fails. Use it where an accidental run-time evaluation would be a bug or a size or timing cost.

## Pitfalls

- Leaving a heavy `constexpr` function callable at run time with non-constant input and assuming it was
  folded. Use `constexpr` variables or `consteval` to force it.
- CRTP base casting to the wrong derived type.
- Relying on `enable_if` error messages for diagnostics; use concepts.
- Large lookup tables copied to RAM; make sure they are `constexpr`/`const` so the linker keeps them in flash.
- Assuming `constexpr` math functions work on every compiler.

Sources: C++ in Embedded Systems, ch 8 (templates, concepts, compile-time polymorphism), ch 11 (compile-time computation), ch 1 (constexpr and templates background).
