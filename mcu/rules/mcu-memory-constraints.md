# MCU Memory & Resource Constraints

## Budgets are tracked per change

Report for every change that adds code or data:

```
flash: <before> -> <after> (<delta>)  of <total>
sram:  <before> -> <after> (<delta>)  of <total>   (.data + .bss)
```

Sources: `arm-none-eabi-size`, the `.map` file, `west build -t rom_report / ram_report`,
`idf.py size-components`, `riscv64-*-size`.

## Allocation policy

| Phase | Allowed |
|-------|---------|
| Pre-scheduler init | Heap allocation permitted if it is never freed |
| Steady state | Static, stack, or fixed-size pools only |
| ISR context | Stack only |

If the project must use a heap in steady state, it uses a deterministic allocator with
a bounded pool and the fragmentation behaviour is documented.

## Stack discipline

- Every RTOS thread's stack is sized from a worst-case call-depth analysis
  (`-fstack-usage`, `puncover`, `stack-usage` reports), plus interrupt nesting depth,
  plus documented headroom (typically 25%).
- Runtime verification: Zephyr `CONFIG_THREAD_ANALYZER`, FreeRTOS
  `uxTaskGetStackHighWaterMark()`, stack painting + periodic check.
- MPU-based stack guards enabled on parts that support them.
- Large buffers never live on the stack. `uint8_t buf[4096]` inside a function is a
  finding.

## Flash and constant data

- `const` tables go in flash, verify with the map file that they did.
- String literals from logging are a major flash consumer: use deferred/binary logging
  (Zephyr `CONFIG_LOG_MODE_DEFERRED`, dictionary logging; ESP-IDF log level per component).
- Dead code: `-ffunction-sections -fdata-sections -Wl,--gc-sections` and verify.

## External memory

When PSRAM/external QSPI is used, state explicitly which sections live there, the access
latency penalty, whether it is cached, and whether DMA can reach it. Never place ISR code
or time-critical data in external memory without measuring.

## Power as a budget

For battery devices, report sleep-state residency and average current alongside memory.
A change that prevents the lowest sleep state is a regression even if it is fast.
