# MCU Coding Style

> Extends `.ai/rules/shared/00-core-principles.md`. The project's existing style always wins.

## Types and registers

```c
/* Fixed width everywhere at hardware and protocol boundaries */
uint32_t status = periph->SR;

/* Register access through the vendor header, not hand-rolled addresses */
#define TIMEOUT_MS 100U          /* named, unsigned-suffixed */

/* Bitfields in structs are not portable for MMIO — use masks and shifts */
reg = (reg & ~MASK_FIELD) | ((value << SHIFT_FIELD) & MASK_FIELD);
```

Never use `int` for a register value, a length, or a protocol field.

## Functions and control flow

- Early return over nested conditionals; max 4 levels of nesting.
- Functions under 50 lines; an ISR under 20.
- Every switch on an enum handles the default case explicitly.
- No recursion in firmware without a proven bound.
- No VLAs, no `alloca`.

## Error handling

```c
int ret = sensor_read(&dev, &sample);
if (ret != 0) {
    LOG_WRN("sensor_read failed: %d", ret);   /* logged, not swallowed */
    return ret;                                /* propagated */
}
```

Deliberate ignores are explicit: `(void)k_work_cancel(&w); /* best effort on shutdown */`

## MISRA-C:2012 advisory subset

Adopt at minimum: no implicit conversions that lose sign or width, one `return` per
error class rather than scattered exits with side effects, no side effects in `sizeof`,
no `goto` except a single-level error unwind, all `if`/`else`/`loop` bodies braced,
no reliance on evaluation order.

Deviations are documented inline with the rule number and the reason.

## Logging

- Compile-time levels per module; production builds drop debug strings.
- Never log in an ISR — defer.
- No secrets, keys, or raw credentials in logs, at any level.

## Naming

```
module_action_object()    /* sensor_read_sample, uart_tx_flush */
MODULE_CONSTANT_NAME      /* UART_TIMEOUT_MS */
module_static_variable    /* file-static, lower snake */
s_prefix or m_ prefix     /* only if the project already uses it */
```

## Header hygiene

- One public header per module, self-contained, include-guarded, `extern "C"` guarded
  if C++ may consume it.
- No global variables in headers. No definitions in headers except `static inline`.
