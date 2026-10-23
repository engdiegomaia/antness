# Function Tracing with uftrace

## Contents
- [When to use function tracing](#when-to-use-function-tracing)
- [Instrumented tracing workflow](#instrumented-tracing-workflow)
- [Interpret trace output](#interpret-trace-output)
- [Limitations](#limitations)

## When to use function tracing

Function tracing can show call order, nesting, timing, arguments, and return values for instrumented programs and supported libraries. It is useful when logs lack call context or when a call path needs to be reconstructed. It is not a kernel-wide trace system and should not be assumed to work on every target architecture or binary.

## Instrumented tracing workflow

Build a controlled reproducer with the instrumentation expected by the installed `uftrace` version. The source demonstrates `-pg`-style instrumentation for supported compiler/tool combinations; verify current requirements and architecture support before using these options. Run the program under tracing, record the exact binary and command, then inspect the call graph and any selected argument or return-value details.

Start with one process and a short execution. Add library tracing only when needed, since dynamic libraries may lack instrumentation or symbols and tracing volume can grow quickly. Filter by function or depth when available in the installed version.

## Interpret trace output

Use indentation and timestamps to recover nesting and elapsed intervals. Check whether time is inclusive of child calls or self time in the selected report. Missing functions may result from absent instrumentation, inlining, tail calls, shared-library behavior, unsupported binaries, or filters. The trace shows one observed run, not all possible paths.

## Limitations

Instrumentation adds code and runtime overhead, can change timing, and may be incompatible with production binaries or toolchains. Do not use its timings as unmodified performance measurements. Protect trace files because arguments and return values may contain sensitive data.

## Sources

- *Reverse Engineering Armv8-A Systems*, chapter 13.
