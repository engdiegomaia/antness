Making interfaces harder to misuse: implicit conversions, casts, type punning, `std::span`, strong types, and lambdas with `std::function`.

## Contents

- [Implicit conversions](#implicit-conversions)
- [Pointer and size pairs become std::span](#pointer-and-size-pairs-become-stdspan)
- [Casts](#casts)
- [Type punning](#type-punning)
- [Strong types](#strong-types)
- [Lambdas](#lambdas)
- [std::function and the heap](#stdfunction-and-the-heap)
- [Callback pattern for interrupts](#callback-pattern-for-interrupts)
- [Pitfalls](#pitfalls)

## Implicit conversions

- Integer promotion: operands smaller than `int` (for example `uint8_t`, `uint16_t`) are promoted to `int`
  before arithmetic, so `uint8_t + uint16_t` is an `int`.
- Usual arithmetic conversions bring mixed operands to a common type. Mixing signed and unsigned converts the
  signed value to unsigned: with `int a = -1; unsigned b = 0;` the test `a + b > 0` is true.
- A bit-field's promoted type can be narrower than its declared underlying type.
- Float to integer loses precision silently; array to pointer ("decay") loses the size.
- Enable `-Wconversion` and `-Wsign-conversion` in GCC, and avoid mixing signed and unsigned in expressions.
- Use brace initialization to turn narrowing into a compile error, and `explicit` constructors to stop
  implicit class conversions.

## Pointer and size pairs become std::span

A `(T* p, size_t n)` interface relies on an unenforceable contract: the pointer is valid, the count is right,
the memory outlives the call. `std::span<T>` (C++20) bundles pointer and size, builds from C arrays,
`std::array` and `std::vector`, iterates with range-for, has `size()` and `operator[]`, works with
algorithms, and supports `subspan`. Prefer it for buffer parameters.

## Casts

| Cast | Use | Risk |
|---|---|---|
| `static_cast` | Well-defined conversions, signed/unsigned, enum to int, upcast and (unchecked) downcast, casting to `void` to silence an unused variable | Downcast to the wrong type is undefined behaviour with no check |
| `dynamic_cast` | Checked downcast returning `nullptr` | Needs RTTI, which firmware normally disables |
| `const_cast` | Interfacing with non-const-correct code | Modifying an object that was defined const is undefined; in the book's test the const value read back unchanged |
| `reinterpret_cast` | Reinterpret bits, pointer to integer (`std::uintptr_t`), register addresses | Dereferencing through the wrong type violates aliasing rules |
| C-style cast | Avoid; it silently picks whichever of the above compiles | Hides intent |

Calling a function through a pointer of the wrong signature is undefined even if it appears to work. Convert
back to the original type before calling.

## Type punning

Accessing an object through a different type is undefined except through `char`, `unsigned char`,
`std::byte`, a containing struct or union, or the same type with cv-qualifiers. Reading a byte array as a
struct via `reinterpret_cast` violates this even though it usually works.

- `std::memcpy` into an object of the target type is always allowed; the compiler normally optimizes the
  copy away (verify at your optimization level).
- `std::bit_cast<To>(from)` (C++20) returns the reinterpreted object; both types must have the same size.
  It does not reinterpret arrays as arrays of another type, so use `memcpy` there.

Checking endianness by reading the first byte of an integer through `char*` is valid.

## Strong types

Plain `uint16_t` parameters for different units (connection interval in 1.25 ms steps, supervision timeout
in 10 ms steps) invite swapped arguments, and macros for the multipliers only help readability.

- Wrap each unit in its own type with an `explicit` constructor so integers and the other unit cannot be
  passed by accident.
- Give the types a private strong `time` member and a user-defined literal such as `operator""_ms` so call
  sites read `10_ms` and the unit conversion lives in one place.
- Wrap the vendor function once in a typed C++ function and call that everywhere. The cost is zero at run
  time after optimization.

## Lambdas

- A lambda is an unnamed function object that can capture variables from its scope: by value (`[x]`), by
  reference (`[&x]`), or not at all (`[]`).
- Typical uses: predicates for algorithms (`std::sort`), small one-off actions, initializing a constant
  array in place, and callbacks for timers, buttons and interrupts.
- A reference capture creates a lifetime dependency. If the lambda runs after the captured variable is gone
  (asynchronous callbacks), the behaviour is undefined.
- Keep lambdas short; the optional trailing return type makes intent explicit.
- A non-capturing lambda converts to a plain function pointer and can be passed to a C API expecting one.

## std::function and the heap

`std::function<void()>` stores any callable (lambda, function pointer, functor). It must store the lambda's
captures. Implementations use small-object optimization (the book cites about 16 bytes on some platforms) and
otherwise allocate from the heap. A lambda capturing an array of six `int`s triggered `new` in the book's test;
four did not.

Options when the heap is off limits:

- Wrap the lambda in `std::reference_wrapper` so the `std::function` stores a reference. You now own the
  lifetime.
- Use a plain function pointer (non-capturing lambdas only).
- Use a fixed-capacity callable wrapper from an embedded library (see [libraries-and-portability.md](libraries-and-portability.md)).
- Keep captures small.

Verify the small-buffer size on your own standard library, since it is implementation-defined.

## Callback pattern for interrupts

A GPIO class stores a `std::function<void()>` (the command), a central manager keeps pointers to registered
GPIO objects, and the C-linkage vector-table handler (`EXTI4_15_IRQHandler` in the book) calls the manager,
which loops through the objects, checks and clears the pending flag, and runs each callback. Port-specific
setup comes from a template parameter that provides a static `init_clock()`, so no run-time port switch is
needed. Registering in the base-class constructor means the callback is wired up by creating the object.
Treat the callback as ISR context: short, non-blocking, and mindful of what a captured reference points to.

## Pitfalls

- Comparing signed and unsigned values.
- Using `reinterpret_cast` on a byte buffer to read a struct (use `memcpy` or `bit_cast`).
- `const_cast` followed by a write.
- Capturing locals by reference in a callback that fires later.
- A capturing lambda stored in `std::function` allocating on the heap in an ISR path.
- `uint16_t` parameters that differ only in unit.

Sources: C++ in Embedded Systems, ch 9 (type safety, strong types), ch 10 (lambdas, std::function, command pattern, GPIO interrupt manager).
