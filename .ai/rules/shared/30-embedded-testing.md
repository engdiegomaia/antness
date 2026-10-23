# Embedded Testing Strategy

The generic "80% coverage" target applies to code that can run on the host. Hardware-bound
code is covered by a different, layered strategy. State which layer produced each result.

## The five layers

| Layer | What runs | Tools |
|-------|-----------|-------|
| 1. Static | No execution | compiler warnings-as-errors, clang-tidy, cppcheck, sparse, MISRA checker, Coccinelle |
| 2. Host unit | Logic with hardware abstracted | Unity/CMock, ztest native_sim, GoogleTest, pytest |
| 3. Simulation | Full firmware, virtual hardware | Renode, QEMU, Zephyr `native_sim`, `qemu_*` boards |
| 4. HIL | Real silicon, automated | pytest + pyserial/pyocd, Zephyr twister with hardware map, Labgrid, Torizon test containers |
| 5. Soak / stress | Long-running on target | power cycling, thermal, memory-leak watch, watchdog counters |

Layers 1–3 run in CI on every commit. Layer 4 runs at least nightly and before release.

## Rules

- Hardware access sits behind a thin abstraction so layer 2 is possible. If a module
  cannot be tested on host, that is a design finding, not an excuse.
- A bug fix starts with a failing test at the lowest layer that can express it.
- Never weaken a test to make it pass. Never add a `sleep` to fix a race — find the race.
- Flaky HIL tests are quarantined with an owner and a deadline, never deleted silently.
- Coverage targets: >=80% for host-testable logic (layer 2), 100% of error-return paths
  in drivers reviewed by inspection when they cannot be provoked.

## Measuring on target

Report with units and method:
- timing: cycle counter (DWT CYCCNT), GPIO toggle + scope, `ktime_get()`, tracing
- memory: map file + runtime high-water, not estimates
- power: measured on a rail with a known shunt, state the instrument

"Should be fast enough" is not a result.
