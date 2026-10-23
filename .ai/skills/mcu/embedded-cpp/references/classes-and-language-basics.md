Everyday C++ language features for firmware: classes, initialization, inheritance and virtual dispatch, namespaces, overloading, C interop, references and containers.

## Contents

- [Encapsulation](#encapsulation)
- [Static methods and structs](#static-methods-and-structs)
- [Initialization](#initialization)
- [Inheritance and virtual dispatch](#inheritance-and-virtual-dispatch)
- [Namespaces](#namespaces)
- [Overloading](#overloading)
- [Mixing C and C++](#mixing-c-and-c)
- [References and move semantics](#references-and-move-semantics)
- [Containers and algorithms](#containers-and-algorithms)
- [Pitfalls](#pitfalls)

## Encapsulation

- Encapsulation means bundling data with the functions that work on it and decoupling units with single
  responsibilities. It is not tied to OOP; access specifiers (`public`, `private`, `protected`) are one tool.
- Class default access is private, struct default is public. Put the public interface first so readers see
  how to use the class before its internals.
- Trivial getters and setters add nothing over a public member and weaken encapsulation. Use a setter only
  when it earns its place, for example to validate (clamp a baud rate to a maximum).
- A separate `init()` method is common for peripherals. Global and static objects are constructed before
  `main()` and before hardware is configured, so a constructor cannot safely touch registers. `init()` gives
  control over the order in which peripherals come up.

## Static methods and structs

- A class of only `static` methods is usable without creating an object. It can use only static members.
  Grouping functions in a type (instead of a namespace) matters because a type can be a template argument.
- Use a `struct` for plain data carriers (for example accelerometer x/y/z samples passed from a sensor to a
  buffer to a fusion stage) and keep behaviour elsewhere. Structs are also a convenient wrapper for static
  functions because members default to public.

## Initialization

| Tool | Notes |
|---|---|
| Default member initializers (C++11) | Give every member a safe default in the class body; avoids random pointer values and repeated assignments across constructors |
| Member initializer list | Required for references and `const` members; initializes before the constructor body |
| Default initialization | Write `uart u;` with no parentheses; `uart u();` declares a function |
| Direct initialization | `uart u(115200);` |
| Brace initialization | Rejects narrowing (float to int), so mistakes become compile errors |
| `explicit` constructor | Stops a single-argument constructor from acting as an implicit conversion |
| `= delete` on a constructor overload | Makes a bad call (for example a float where a `uint8_t` is expected) fail to compile |
| `static inline` data member (C++17) | Define and initialize a static member inside the class body, no separate definition needed |

A non-explicit one-argument constructor is a converting constructor: passing `115200` to a function that
takes a `uart` silently builds one. Prefer `explicit` by default.

## Inheritance and virtual dispatch

- Without `virtual`, the called function is chosen at compile time from the static type (static binding).
  A base-class reference to a derived object calls the base version.
- With `virtual`, the call goes through a hidden table of function pointers (vtable); each object carries a
  pointer to its class's table. That costs a pointer per object, a table per class, and an indirect call.
- Mark overriding functions `override` so the compiler catches signature mismatches or a missing `virtual`.
- A class with a pure virtual function is abstract and cannot be instantiated. A class made only of pure
  virtual functions is an interface.
- Virtual dispatch is a runtime-polymorphism choice. If the concrete type is known at compile time, template
  based (static) polymorphism avoids the indirection; see [templates-and-compile-time.md](templates-and-compile-time.md).

## Namespaces

- Use namespaces in place of C-style name prefixes. Everything except `main` should live in a namespace.
- `using namespace std;` is discouraged; bring in single names in a small scope instead.
- An unnamed namespace gives internal linkage (same as C `static` at file scope).
- C++17 allows nested declarations as `namespace a::b {}`.

## Overloading

- Same function name, different parameter lists; the compiler picks by argument types. Return type alone
  cannot distinguish overloads.
- The compiler uses name mangling to give each overload a distinct symbol. This is why C code cannot call a
  C++ function directly unless it has C linkage.

## Mixing C and C++

- Vendor HAL, CMSIS and RTOS code are C; your code is C++. Both are compiled separately and linked into one
  ELF.
- Wrap C declarations in `extern "C"` (usually `#ifdef __cplusplus` guards in the header) to prevent name
  mangling. Standard C headers and most vendor HAL headers already do this. If a header lacks guards, wrap
  the `#include` itself.
- Use the `<cstdio>` style C++ headers for the C library.
- ISR handlers, `__cyg_profile_func_*` hooks and anything the linker or C startup code references by name
  need C linkage.

## References and move semantics

- A reference is an alias that must be initialized and cannot be rebound. There are no arrays of or pointers
  to references.
- Lvalue references (`T&`, `const T&`) alias existing objects. Rvalue references (`T&&`) bind to temporaries
  and enable moving resources instead of copying them.
- Moving matters mainly for types that own dynamic resources, which firmware avoids; know it exists because
  container APIs expose both overloads.

## Containers and algorithms

- `std::array` is the default container: fixed size known to the type, stack or static storage, no heap.
  `.at()` checks bounds (throws, or terminates when exceptions are off); `[]` does not.
- `std::vector` allocates dynamically; see [myths-and-feature-policy.md](myths-and-feature-policy.md) for the
  mitigation options.
- A fixed-capacity vector can be built on `std::array` plus a count (push_back, pop_back, back, end) and used
  as the underlying container for `std::stack` and `std::priority_queue`. Decide deliberately what happens on
  overflow (the book's example drops silently).
- `<algorithm>` and `<numeric>` work on any container: `std::copy`, `std::copy_if`, `std::sort`,
  `std::transform`, `std::iota`. They replace hand-written index loops and read closer to intent.

## Pitfalls

- Constructing hardware-touching globals and assuming the clocks are already running.
- Forgetting `explicit` and getting silent conversions.
- Using `uart u();` and creating a function declaration.
- Trivial getters on every member.
- A virtual function in a hot path or in a class instantiated thousands of times without measuring.
- Calling C++ from a vector table entry without `extern "C"`.
- Using `[]` on `std::array` and assuming bounds are checked.

Sources: C++ in Embedded Systems, ch 5 (classes), ch 6 (beyond classes: namespaces, overloading, C interop, references, containers).
