# RTOS & Concurrency Rules (MCU)

## Interrupt context

Forbidden in an ISR: blocking waits, mutex acquisition, dynamic allocation, `printf`,
long loops, floating point on cores without lazy FP stacking, and any API not documented
as ISR-safe.

Allowed: read/write registers, push to a lock-free/ISR-safe queue, give a semaphore
(ISR variant), submit work to a work queue, set an atomic flag.

```c
/* FreeRTOS: always the FromISR variants, always the yield */
BaseType_t higher = pdFALSE;
xQueueSendFromISR(q, &evt, &higher);
portYIELD_FROM_ISR(higher);
```

```c
/* Zephyr: defer, do not process */
k_work_submit(&handler_work);
```

## Priority design

- Assign priorities from deadlines (rate-monotonic as a starting point), not from
  perceived importance.
- Document the full priority table in one place. An undocumented priority is a future
  inversion bug.
- Mutexes used across priority levels must have priority inheritance enabled
  (`CONFIG_MUTEX`/FreeRTOS mutex, not a binary semaphore).
- Interrupt priorities: respect the RTOS's max-syscall priority boundary
  (`configMAX_SYSCALL_INTERRUPT_PRIORITY`, Zephyr's zero-latency IRQs). An ISR above it
  must not call any kernel API.

## Shared state

| Sharing | Correct mechanism |
|---------|-------------------|
| ISR -> task, single value | atomic, or `volatile` + single-writer discipline documented |
| ISR -> task, stream | ring buffer / message queue with ISR-safe put |
| task <-> task | mutex, or message passing (preferred) |
| DMA <-> CPU | cache maintenance (clean before, invalidate after) + ownership flag |
| Multicore | atomics + memory barriers + non-cacheable shared region |

`volatile` prevents the compiler from caching a value. It does not order accesses, does
not make read-modify-write atomic, and does nothing about cache coherency on M7/multicore.

## DMA

- Buffers are cache-line aligned and cache-line sized on cores with D-cache (M7, M55).
- Clean the cache before a memory-to-peripheral transfer; invalidate after a
  peripheral-to-memory transfer. Getting this wrong produces intermittent corruption
  that looks like a "random bug".
- Buffer lifetime outlives the transfer — never a stack buffer.
- Always handle the error/abort interrupt, not just completion.

## Low power

- Entering a sleep state may gate peripheral clocks and stop the tick. Verify wake
  sources and that pending work is not lost across the transition.
- Tickless idle changes timing assumptions; re-validate timeouts after enabling it.

## Deadlock and starvation review

For each new lock: state the lock ordering. Two locks taken in different orders anywhere
in the codebase is a deadlock, not a risk of one.
