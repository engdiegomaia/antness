# Core Principles — Embedded Agentic Development

> Applies to both tracks. Track-specific rules override these where they conflict.

## Context before code

An embedded change is only correct relative to a hardware context. Before editing, know:

- **Target**: SoC/MCU part number, silicon revision, module variant
- **Memory map**: flash/RAM regions, linker script or device tree reserved memory
- **Clocks**: source, PLL config, and what the change does to them
- **Boot chain**: ROM -> SPL/first-stage -> bootloader -> kernel/app, and which stage you touch
- **Power**: supply rails, low-power states entered, wake sources

If any of these is unknown and the change depends on it, ask. Do not guess.

## Resource budgets are requirements

Treat these as acceptance criteria, not optimizations:

| Budget | Where it is checked |
|--------|---------------------|
| Flash / text size | map file, `size`, `west build -t ram_report/rom_report` |
| Static RAM | `.bss` + `.data` from map file |
| Stack high-water | RTOS stack analysis, `CONFIG_THREAD_ANALYZER`, `ulimit` on Linux |
| Heap fragmentation | prefer static/pool allocation; no `malloc` in steady state on MCU |
| ISR latency / jitter | measured, not assumed |
| Boot time | measured per stage (`grabserial`, `bootgraph`, `systemd-analyze`) |

Report the delta of any budget you affect.

## Failure handling

- Every hardware operation can fail: timeouts, NAKs, bus errors, brownouts.
- Never ignore a return code from a HAL/driver/syscall. If ignoring is deliberate,
  cast to `(void)` and write why.
- Prefer a defined degraded state over an undefined one. A watchdog reset is a design
  decision, not an accident.
- Never silently retry forever. Bound every retry loop and log the bound.

## Determinism

- Pin toolchain, SDK, and layer revisions. Bumping a revision is its own change with
  its own validation.
- No network fetches in the build unless the source is version-pinned and checksummed.
- Builds must reproduce from a clean tree with one documented command.

## Code style

- C: project's existing style wins. Otherwise MISRA-C:2012 advisory subset for MCU,
  kernel coding style for Linux kernel code.
- No hidden control flow in macros; no function-like macros where an `inline` works.
- Fixed-width types (`uint32_t`) at hardware and protocol boundaries, always.
- `volatile` only for MMIO and variables shared with ISRs — it is not a concurrency
  primitive.
- Endianness and alignment are explicit at every wire/storage boundary.
- Small files, one subsystem per file. Split above ~800 lines.

## Immutability, in embedded terms

The generic "never mutate" rule does not apply to hardware registers, DMA buffers, or
ring buffers, where in-place mutation is the design. It does apply to configuration
structures, protocol descriptors and state snapshots passed between layers: copy and
return, do not modify a caller's struct in place.

## Documentation of intent

Every non-obvious hardware interaction carries a comment with the *source*:

```c
/* Errata ERR050568: hold reset 10 ms before releasing, see i.MX8MP Rev.2 errata. */
k_msleep(10);
```

A magic delay without a citation is a bug waiting to be "optimized" away.
