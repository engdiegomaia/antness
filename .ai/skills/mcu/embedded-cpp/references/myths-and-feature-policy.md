Which C++ features to allow, restrict or disable in resource-constrained firmware, and the evidence behind each decision.

## Contents
- The zero-overhead principle and what violates it
- Where "C++ bloat" actually comes from
- Optimization and undefined behaviour
- Dynamic memory: why it is the real problem
- Mitigations: reserve, PMR allocators, fixed containers
- Hard enforcement: deleting `operator new`
- Exceptions and RTTI: cost model and switches
- Safety-standard positions (MISRA / AUTOSAR / JSF)
- A feature policy table you can paste into a coding standard

## The zero-overhead principle and what violates it

C++ is designed around two claims: *you don't pay for what you don't use*, and *what you do use is about as efficient as what you'd hand-write*. Measured on a Cortex-M target, almost everything in the language upholds this — constructors, destructors, member functions, templates, lambdas, `std::array`, `std::span`, `constexpr`.

Exactly two language features break it, which is why every compiler has a switch to turn them off:

| Feature | Cost | GCC/Clang switch |
|---|---|---|
| Exceptions | Unwind tables in flash, runtime unwinder, non-deterministic throw path, often heap allocation of the exception object | `-fno-exceptions` |
| RTTI | Type info records attached to every polymorphic class's vtable; `dynamic_cast` does a runtime walk | `-fno-rtti` |

Everything else is a design choice whose cost you can read in the disassembly.

## Where "C++ bloat" actually comes from

Reading the generated assembly settles most arguments. Three findings worth internalising:

1. **An unused destructor costs nothing.** Delete an empty destructor and the compiler emits neither the function nor the call at scope exit. Declaring special members you don't need is what costs, not "having classes".
2. **Trivial accessors vanish under optimization.** A class with a private member, a constructor, a destructor and a getter compiles — at `-O3` — to the same couple of instructions as a plain struct. At `-O0` it compiles to dozens of lines of stack shuffling (removing the empty destructor alone cut the book's example to 44 lines). If you benchmark abstractions with optimization off, you will reach the wrong conclusion.
3. **Templates do not cost more than hand-written types.** Instantiating `ring_buffer<int,10>` and `ring_buffer<float,10>` produces the same code size as hand-writing `ring_buffer_int` and `ring_buffer_float`. The small difference you see in unoptimized object files is longer mangled names in the symbol table and disappears when stripped. Identical instantiations across translation units are folded by the linker.

The real template costs are **build time** (every TU instantiates independently) and **error-message quality** — not binary size.

C++ is also not an OOP language; it is multi-paradigm. Reaching for setters/getters and inheritance by reflex is where gratuitous code comes from. Types with only static members, free functions in namespaces, and plain aggregates are all idiomatic C++.

## Optimization and undefined behaviour

"We build at `-O0` because optimization breaks our code" is almost always a UB bug, not a compiler bug.

Canonical demonstration: signed integer overflow.

```cpp
bool foo(int x) { int y = x + 1; return y > x; }   // UB at INT_MAX
```

At `-O0` the addition wraps and `foo(INT_MAX)` returns false. At `-O2` the compiler is entitled to assume no overflow, so `foo` is compiled to `return true` unconditionally — two instructions, no arithmetic. Both behaviours are "correct" because the program was never well-formed.

The practical rule: **optimization is not negotiable in a size- and timing-constrained target**, and the obligation to eliminate UB is the developer's. Back that with static analysis, sanitizers on the host build, and unit/integration tests run against both optimized and unoptimized builds (so a genuine, rare compiler bug is still caught).

Flags worth enabling early: `-Wall -Wextra`, `-Werror` once the tree is clean, `-fanalyzer` (GCC ≥ 10) for uninitialized reads and out-of-bounds, plus clang-tidy and cppcheck. Different analyzers catch different things; run more than one. Note that `-fanalyzer` is slow on large trees, and `-Wuninitialized` only fires at `-O1` and above.

## Dynamic memory: why it is the real problem

Two independent objections, often conflated:

- **Non-determinism.** A general-purpose allocator's execution time depends on its global free-list state, not only on the requested size. You cannot measure a worst-case execution time (WCET) by sampling, because you cannot enumerate all reachable heap states.
- **Failure.** Allocation can fail. External fragmentation means a request can fail while plenty of total free memory exists, just not contiguous. Internal fragmentation (fixed-block pools, WCET-bounded allocators) wastes memory in the other direction.

Plus the classic lifetime bugs: leaks, dangling pointers, double free.

Know what the standard library actually does. `std::vector` typically allocates one element on first `push_back`, then doubles: pushing 8 elements yields allocations of 1, 2, 4, 8 with three deallocations and three copies in between. You can observe this on any platform by replacing the global `operator new`/`operator delete` with printing versions that forward to `malloc`/`free`.

## Mitigations: reserve, PMR allocators, fixed containers

Ordered from weakest to strongest:

| Mitigation | What it buys | Residual risk |
|---|---|---|
| `vec.reserve(N)` up front | One allocation instead of log₂N | Exceeding N reallocates silently |
| `std::pmr::monotonic_buffer_resource` over a static/stack buffer + `std::pmr::vector` | Allocations served from your buffer; no free until the resource dies | **Falls back to the upstream (heap) resource when the buffer is exhausted** |
| Global `operator new`/`delete` replacement with a deterministic pool allocator | Whole-program control | The library uses *several* `new` overloads (sized, aligned, nothrow); you must replace all of them |
| Fixed-capacity containers (ETL, your own, `std::array`-based) | No allocator in the picture at all | Capacity is a design decision you must get right |
| `operator new` deleted entirely | Compile-time guarantee | Rules out any library that allocates |

The PMR fallback is the trap. A `std::pmr::vector` backed by a small monotonic buffer still calls `operator new` once the buffer cannot satisfy a request (the book's test doubled its way past the buffer and fell through). The library also uses several `operator new` overloads and it is hard to tell which one a container picks without inspection, which makes global replacement tricky. The book concludes a local allocator is usually the better choice; neither is airtight.

## Hard enforcement: deleting `operator new`

If the requirement is "this image never allocates", prove it at link/compile time:

```cpp
void *operator new  (std::size_t)                                      = delete;
void *operator new[](std::size_t)                                      = delete;
void *operator new  (std::size_t, std::align_val_t)                    = delete;
void *operator new[](std::size_t, std::align_val_t)                    = delete;
void *operator new  (std::size_t, const std::nothrow_t&)               = delete;
void *operator new[](std::size_t, const std::nothrow_t&)               = delete;
void *operator new  (std::size_t, std::align_val_t, const std::nothrow_t&) = delete;
void *operator new[](std::size_t, std::align_val_t, const std::nothrow_t&) = delete;
```

Any component that allocates now fails to compile with `error: use of deleted function 'void* operator new(...)'`, pointing at the library header that did it. Cover every overload the library can reach (the book deletes eight: plain, array, aligned and nothrow variants) — missing one leaves a hole.

## Exceptions and RTTI: cost model and switches

**Exceptions.** A throw unwinds the stack, running destructors for every object between throw and catch, driven by unwind tables the compiler emits. Those tables grow with code size and the runtime is not time-bounded.

Two concrete gotchas:

- Just adding `-fexceptions` is not enough on a GNU Arm toolchain. The `nano.specs` newlib-nano / size-optimized `libstdc++`/`libsupc++` are built *without* exception support, so a throw calls `std::abort()` instead of unwinding. Dropping `-specs=nano.specs` to get working exceptions pulls in the full standard library — a hello-world-sized example jumped to ~88 KB. If you need exceptions on a small target, rebuild a size-optimized standard library from source with exceptions on.
- With `-fno-exceptions`, a `throw` (including `std::array::at()` out of range, `std::optional::value()` on empty) calls `std::terminate()`. Install your own handler so the failure is recorded rather than silent:

```cpp
std::set_terminate([] { log_fault(); std::abort(); });
```

Exceptions are not useless in firmware. They solve propagation (an error can't be ignored) and enforcement (an uncaught type terminates rather than continuing in an unknown state). They are invisible in the function signature, though, so you depend on documentation to know what throws. Reserve them for genuinely rare, recoverable conditions on targets with memory to spare, and use error codes / `expected` everywhere else — the two coexist fine, and must, because C libraries and legacy C++ already use codes.

**RTTI.** Type information is stored in the vtable of every polymorphic class. With `-fno-rtti`, `dynamic_cast` becomes a compile error (`error: 'dynamic_cast' not permitted with '-fno-rtti'`), which is what you want: a design that needs a downcast on a hot path usually wants a different design. Binaries are measurably smaller with RTTI off.

**`-fno-threadsafe-statics`** belongs in the same group. By default the compiler emits a guard variable and `__cxa_guard_acquire`/`release` calls around function-local statics; on a single-core bare-metal target you usually don't want that code, but be aware you are then responsible for not racing initialization against an ISR.

## Safety-standard positions

- **MISRA C++ 2008** (C++03 era) prohibits dynamic memory allocation outright.
- **MISRA C++ 2023** advises against allocation while the system is running, and offers startup-time allocation as the mitigation.
- **JSF Air Vehicle C++** uses the same policy: allocation allowed at startup, not during operation.
- **AUTOSAR C++14 guidelines**, rules A18-5-5 and A18-5-6, require memory management to have a demonstrable WCET, avoid fragmentation, avoid out-of-memory, avoid mismatched alloc/dealloc and avoid non-deterministic kernel calls — and require a documented failure-mode analysis for all of those.

Taking A18-5-5 literally is close to impossible: writing an allocator that *cannot run out of memory* means either proving a static upper bound on live allocations (at which point you may as well allocate statically) or handling failure at every call site. The complexity you add usually exceeds the value of allowing allocation at all. The defensible positions are: no allocation, or allocation only during startup before the system is declared operational.

Compiler qualification matters too. If your functional-safety standard (IEC 61508 umbrella; ISO 26262 automotive, EN 50128 rail, IEC 62304 medical, IEC 60730-1 appliances) demands a qualified compiler, you are limited to the vendors' FuSa editions — and those lag the language standard noticeably (FuSa toolchains have shipped C++14/C++17 support while C++20/23 were already published). Free GCC can also be qualified, by running a documented test-program suite and maintaining a deviation/mitigation process.

## Feature policy table

| Feature | Default policy | Notes |
|---|---|---|
| Classes, constructors, destructors, RAII | **Use** | Zero cost when not used; destructors are the point |
| Templates, `constexpr`, concepts | **Use** | Cost is build time, not binary size |
| Lambdas, non-capturing | **Use** | Convert to function pointers; usable from C callbacks |
| `std::array`, `std::span`, `<cstdint>`, `<limits>`, `<type_traits>`, `<algorithm>` | **Use** | No allocation |
| Virtual functions | **Use with judgement** | One indirection per call + vtable; prefer templates/CRTP on hot paths |
| `std::function` | **Restrict** | May heap-allocate above the small-object threshold (~16 bytes on many impls); not in freestanding. Prefer `etl::delegate` or a function pointer |
| `std::optional` / `std::expected` | **Use** | `std::expected` is C++23; check toolchain support |
| Exceptions | **Off** (`-fno-exceptions`) unless justified | Install a terminate handler either way |
| RTTI / `dynamic_cast` | **Off** (`-fno-rtti`) | |
| `std::vector`, `std::string`, `std::list`, `std::map` | **Avoid** | Allocate; use fixed-capacity equivalents |
| `<iostream>` | **Avoid** | Large static footprint and allocates; use `<cstdio>`'s `printf` |
| Global `new`/`delete` | **Delete them** if a no-allocation guarantee is required | All eight overloads |
| Optimization | **On** (`-O2`/`-O3`/`-Os`) | Plus `-ffunction-sections -fdata-sections -Wl,--gc-sections` |

Sources: *C++ in Embedded Systems* (Packt), ch. 1 (Debunking Common Myths about C++), ch. 2 (Challenges in Embedded Systems with Limited Resources), ch. 3 (Embedded C++ Ecosystem), ch. 7 (Practical C++ Error Handling Methods), ch. 17 (Libraries and Frameworks).
