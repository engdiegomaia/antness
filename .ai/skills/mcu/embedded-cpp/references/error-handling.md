Choosing an error-handling strategy for firmware: error codes, global handlers, asserts, exceptions, `std::optional` and `std::expected`.

## Contents

- [Decision table](#decision-table)
- [Error codes](#error-codes)
- [Global error handler with tag dispatch](#global-error-handler-with-tag-dispatch)
- [Asserts](#asserts)
- [Exceptions](#exceptions)
- [optional and expected](#optional-and-expected)
- [Pitfalls](#pitfalls)

## Decision table

| Situation | Use |
|---|---|
| Programming mistake (violated precondition, impossible state) | Assert during development; consider a lightweight assert that logs in production |
| Unrecoverable runtime fault (bus dead, safety limit hit) | Global error handler that logs, alerts and halts or resets |
| Recoverable failure the caller can act on | Error code, or `std::expected<T, E>` where C++23 is available |
| A value may legitimately be absent (data not ready) | `std::optional<T>` |
| Rare failures propagated through many layers, and memory plus timing allow it | Exceptions (usually not on small hard real-time targets) |

Several strategies coexist in real projects, especially because C libraries return codes.

## Error codes

- The callee exposes a list of codes; every caller must handle each one or pass it up. The list changes over
  the project's life, and callers must change with it.
- Weaknesses: callers can ignore the result, forget a case, or forget to propagate. Nothing stops the program
  continuing in an unknown state.
- Mitigation: mark the function or the error enum `[[nodiscard]]` and build with warnings as errors. This
  forces the value to be used but does not prove every case is handled.
- Use `enum class` for codes so they do not convert to integers.

## Global error handler with tag dispatch

For errors where the only sensible action is to log, show the user, and stop:

- Provide free functions `error::handler(tag)` overloaded on empty tag types (`i2c_failed`, `spi_failed`).
- Advantages over an enum: adding a new error means adding a new overload, existing handlers are untouched;
  an unhandled tag is a compile error; each handler can differ.
- What the handler does depends on the product. A medical device first tries to recover, then enters a
  critical state, alerts staff and degrades gracefully. A failed external transfer (for example a bad I2C
  read) should not be treated as a programming error.

## Asserts

- Asserts detect programming mistakes, not run-time faults. They check preconditions and invariants.
- Standard `assert` prints the expression, file, function and line, and calls `std::abort`. Those strings
  end up in flash, which is expensive on a small MCU.
- `NDEBUG` removes asserts. They are normally off in production and must be disabled before safety
  validation of a release.
- A cheaper embedded pattern: on failure, log only the program counter (four bytes) and halt or reset.
  Convert the address back to a source line offline with the map file and `addr2line`. A small inline helper
  can capture the PC. Inlining is a hint, so check at `-O0`.
- Keeping a logging assert in production gives post-mortem data. Store the address in non-volatile memory.
- Asserts are not a substitute for handling real run-time errors.

## Exceptions

- Thrown objects propagate up the call stack until a matching `catch`; unmatched exceptions call
  `std::terminate`. Standard-library exceptions derive from `std::exception`.
- In the book's Cortex-M test, enabling exceptions meant dropping the size-optimized nano library
  variants and the binary grew to about 88 KB. The nano C++ runtime is built without exception support, so a
  throw there ends in `std::abort`. A size-optimized runtime built with exceptions is possible.
- Costs: flash for unwind tables, RAM, and non-deterministic timing during stack unwinding.
- Visibility: exceptions are not part of a function's declaration, so documentation must say what throws and
  where it is caught.
- Replace the default terminate handler with `std::set_terminate` to log and reset when exceptions are
  disabled or a throw escapes.
- Where a fast, deterministic reaction is required (for example shutting down an output stage), prefer a
  direct handler call over unwinding.

## optional and expected

- `std::optional<T>` (C++17): "value or nothing". Use when absence is normal, such as a sensor with no new
  sample yet. Test with a boolean conversion or `has_value()`.
- `std::expected<T, E>` (C++23): "value or error object". Use `has_value()`, `value()` and `error()`. The
  error type can be a rich enum, and the return type makes the failure visible in the signature.
- Both live on the stack with no heap use. Check your compiler's library support before relying on
  `std::expected`; older toolchains need a backport or a different pattern.

## Pitfalls

- Using an assert for a recoverable bus error.
- Leaving full-text asserts in a small-flash build.
- Shipping with asserts silently disabled and no other check.
- Ignoring `[[nodiscard]]` warnings by not enabling them as errors.
- Enabling exceptions in one translation unit and building the rest with `-fno-exceptions`.
- Treating `optional` as an error channel; it carries no reason.

Sources: C++ in Embedded Systems, ch 7 (error handling), ch 1 and ch 2 (exception and RTTI cost background).
