# Kernel & Driver Rules

## Context rules

| Context | May sleep | Notes |
|---------|-----------|-------|
| Process (syscall, ioctl, read/write) | yes | can use mutex, `copy_*_user`, GFP_KERNEL |
| Interrupt handler (hardirq) | **no** | spinlock only, GFP_ATOMIC, keep it minimal |
| Softirq / tasklet | **no** | same restrictions as hardirq |
| Threaded IRQ handler | yes | preferred for anything non-trivial |
| Workqueue | yes | the standard deferral target |
| Timer callback | **no** | use a workqueue if you need to sleep |
| Spinlock held | **no** | any sleep here is a deadlock |

`might_sleep()` and `CONFIG_DEBUG_ATOMIC_SLEEP` catch violations. Enable them in
development builds — always.

## Locking

- State in a comment which lock protects which fields, and the acquisition order.
- `spinlock_t` for short critical sections shared with interrupt context
  (`spin_lock_irqsave` when the lock is taken from both contexts).
- `struct mutex` for anything that may sleep.
- RCU for read-mostly data where readers must not block.
- Two locks taken in two different orders anywhere is a deadlock. `CONFIG_PROVE_LOCKING`
  (lockdep) finds it — run with it enabled during development.

## Userspace boundary

```c
static long my_ioctl(struct file *f, unsigned int cmd, unsigned long arg)
{
    struct my_req req;

    if (_IOC_TYPE(cmd) != MY_IOC_MAGIC)          /* validate the command itself */
        return -ENOTTY;

    if (copy_from_user(&req, (void __user *)arg, sizeof(req)))
        return -EFAULT;

    if (req.len > MY_MAX_LEN)                     /* validate every field */
        return -EINVAL;
    ...
}
```
- Never dereference a `__user` pointer. Never trust a length, index, or offset from
  userspace. Check for integer overflow before using a size in arithmetic.
- Sparse (`make C=1`) enforces `__user` annotations — run it.

## Resource management

```c
/* devm_* ties the resource to the device lifetime; probe error paths stay simple */
base = devm_platform_ioremap_resource(pdev, 0);
if (IS_ERR(base))
    return PTR_ERR(base);

irq = platform_get_irq(pdev, 0);
if (irq < 0)
    return irq;

ret = devm_request_threaded_irq(dev, irq, NULL, my_thread_fn,
                                IRQF_ONESHOT, dev_name(dev), priv);
```
Mixing `devm_*` with manual release in the same driver is a use-after-free waiting to
happen. Pick one discipline per resource.

## Driver model

- Use the subsystem framework, never a raw char device, when one exists: IIO for
  sensors, input for input, regmap for register access, gpiod for GPIO, PWM, hwmon,
  clk, regulator, V4L2 for video.
- `regmap` gives you caching, locking and debugfs for free on I2C/SPI register maps.
- Bindings live in `Documentation/devicetree/bindings/` as YAML and must validate:
  `make dt_binding_check DT_SCHEMA_FILES=...`.
- `MODULE_LICENSE("GPL")` — a non-GPL license blocks GPL-only symbols and has legal
  implications; do not "fix" a symbol error by changing the license string.

## Error handling

- Return negative errno. Propagate, never invent codes.
- `dev_err`/`dev_warn`/`dev_dbg` with the device prefix, not `printk`. No logging in
  a hot path; use tracepoints.
- `dev_err_probe(dev, ret, "...")` handles `-EPROBE_DEFER` correctly and quietly.

## Performance and DMA

- `dma_alloc_coherent` for descriptors; `dma_map_single`/`dma_map_sg` with correct
  direction for streaming, and respect ownership — no CPU access while the device owns
  the buffer.
- `dma_set_mask_and_coherent` before any mapping; a 32-bit-capable device on a 64-bit
  system fails silently or bounces otherwise.
- No busy-waiting in a driver. `readl_poll_timeout` with a real timeout.

## Style

Kernel coding style, enforced: `scripts/checkpatch.pl --strict` clean on new code.
Patches for upstream carry `Signed-off-by` and a proper subject prefix
(`spi: imx: fix ...`).
