Designing a type-safe C++ HAL over memory-mapped registers, and wrapping vendor C libraries (adapter, static class, RAII).

## Contents

- [The problem with register structs](#the-problem-with-register-structs)
- [Register template](#register-template)
- [Bit fields as types](#bit-fields-as-types)
- [Peripheral families with traits](#peripheral-families-with-traits)
- [Wrapping a vendor C HAL](#wrapping-a-vendor-c-hal)
- [RAII for C resources](#raii-for-c-resources)
- [Pitfalls](#pitfalls)

## The problem with register structs

CMSIS models a peripheral as a struct of registers (`RCC_TypeDef`) plus a macro that casts the base address
to a pointer. It works and is portable across Cortex-M vendors, but:

- Nothing stops a write of an arbitrary value to any register, and magic constants (a clock configuration
  like `0x08FFB80C`) hide which bits are set.
- Read-only and write-only registers are not distinguished.
- Bit positions and widths live in separate macros that the compiler cannot connect to a register.

C++ can fix all three at no run-time cost.

## Register template

Model one register as a class template parameterized by address, access policy and value type
(default `std::uint32_t`):

- Access policies are empty tag types (`read_access`, `write_access`, `read_write_access` derived from
  both). `read()` and `write()` are enabled only when the policy allows (via `std::enable_if_t` and
  `std::is_base_of_v`, or concepts in C++20). Misuse becomes a compile error.
- The address is converted with `reinterpret_cast<volatile T*>`. `volatile` stops the compiler from caching,
  merging or dropping accesses. The integer-to-pointer conversion is implementation-defined, so this design
  relies on your compiler's documented behavior.
- Because everything is `static` and known at compile time, generated code matched the hand-written CMSIS
  version in the book's size comparison.

## Bit fields as types

- Make the raw `write()` private and expose `set<BitField>()`, constrained by a concept: the type must
  describe the register type, position and an `enum class` of legal values.
- A single-bit enable/disable field is a tiny struct with position 0 and values on/off. Reuse via a generic
  `reg_bits_enable_disable` template.
- Multi-bit numeric fields (a 5-bit trim) take the value as a non-type template parameter (`auto Bits`).
  `static_assert` checks the value fits the field width and has the register's type.
- Read-only calibration bits are simply not given a `set` type.
- Call sites become self-documenting, such as `rcc::set<hsion::on>()`.

## Peripheral families with traits

When peripherals share a design but differ in details (TIM2 is 32-bit, TIM3 is 16-bit, different base
addresses and IRQ numbers), write one `timer<TimerTraits>` template. Each traits struct (`timer2_traits`,
`timer3_traits`) provides addresses, widths and constants. The template defines register aliases from the
traits, bit-field aliases, and a static `start(period)`. Instantiate `using timer2 = timer<timer2_traits>;`.
ISRs for each timer remain C-linkage functions that clear the flag. The result is generic, type-checked and,
per the book, as efficient as a hand-written C HAL because templates and `constexpr` let the compiler
optimize fully.

## Wrapping a vendor C HAL

Vendor HALs are tested on large numbers of devices and kept up to date, so reusing them is usually wiser than
rewriting. Wrap them so the application does not depend on them.

1. **Interface plus adapter.** Define an abstract `uart` (virtual `init`, `write(std::span<const char>)`).
   A concrete `uart_stm32` adapts the C HAL calls to it. Clients such as a GSM library receive a `uart&`
   through their constructor (dependency injection). Use `init()` rather than doing hardware setup in the
   constructor, to avoid problems when objects are global or static.
2. **Casting away const.** The C HAL transmit function takes a non-const pointer. Casting `const` away is
   safe only if you know the function does not modify the data.
3. **Static class.** Wrap the C functions one-to-one in a class of static methods with a deleted default
   constructor (the idea is borrowed from C#; C++ has no `static class` keyword). Make the adapter a template
   over this wrapper (`uart_stm32<HalUart>`). Tests can then substitute a fake `HalUart` and run on the host
   with no vendor code.
4. Check HAL return codes. The book's examples omit error handling for brevity; production code must not.

## RAII for C resources

Resource acquisition is initialization: acquire in the constructor, release in the destructor, so cleanup
happens on every return path.

- Wrap the littlefs file API in a `file` class: the constructor opens, the destructor closes if open, `read`
  and `write` take `std::span`. A separate type initializes and mounts the filesystem.
- Use dynamic allocation only inside such owner classes, never scattered through application code.
- Apply the same idea to locks, chip-select lines, DMA channels or any begin/end pair.
- Copying and moving of the wrapper should be deliberately deleted or implemented so a handle is not closed
  twice.

## Pitfalls

- A register template that is not `volatile`.
- Letting `write` stay public and bypassing the typed `set`.
- Initializing hardware in a constructor of a global object before clocks are configured.
- Dropping the HAL's error codes in the adapter.
- Wrapper objects that can be copied, causing a double close.
- Assuming `reinterpret_cast` of an address is portable across compilers.

Sources: C++ in Embedded Systems, ch 12 (writing a C++ HAL), ch 13 (working with C libraries, static classes, RAII).
