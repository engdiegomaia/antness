---
name: kernel-driver-development
description: Linux kernel and device driver development — platform drivers, subsystem frameworks (IIO, regmap, gpiod, V4L2), out-of-tree modules, debugging with ftrace/dynamic debug, and upstream patch discipline.
track: linux-embedded
---

# Kernel & Driver Development

Rules in `.ai/rules/linux-embedded/kernel-driver-rules.md`. This skill is the how.

## Orient first

```bash
uname -r; cat /proc/version
zcat /proc/config.gz | grep CONFIG_<X>      # or /boot/config-$(uname -r)
lsmod; modinfo <module>
dmesg -w                                     # keep this open while testing
ls /sys/bus/platform/devices/ /sys/class/
cat /sys/kernel/debug/gpio                   # gpio allocation
```

Know the kernel version and whether it is a vendor fork. APIs move between releases —
`devm_platform_ioremap_resource`, `gpiod_*`, and the timer API all changed. Check the
tree you are building against, not documentation for mainline.

## Platform driver skeleton

```c
static int my_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct my_priv *priv;
	int irq, ret;

	priv = devm_kzalloc(dev, sizeof(*priv), GFP_KERNEL);
	if (!priv)
		return -ENOMEM;

	priv->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(priv->base))
		return PTR_ERR(priv->base);

	priv->clk = devm_clk_get_enabled(dev, NULL);
	if (IS_ERR(priv->clk))
		return dev_err_probe(dev, PTR_ERR(priv->clk), "failed to get clock\n");

	priv->reset = devm_gpiod_get_optional(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(priv->reset))
		return dev_err_probe(dev, PTR_ERR(priv->reset), "reset gpio\n");

	irq = platform_get_irq(pdev, 0);
	if (irq < 0)
		return irq;

	ret = devm_request_threaded_irq(dev, irq, NULL, my_thread_fn,
					IRQF_ONESHOT, dev_name(dev), priv);
	if (ret)
		return dev_err_probe(dev, ret, "failed to request irq\n");

	platform_set_drvdata(pdev, priv);
	return 0;
}

static const struct of_device_id my_of_match[] = {
	{ .compatible = "vendor,my-device" },
	{ }
};
MODULE_DEVICE_TABLE(of, my_of_match);   /* without this, module autoload fails */
```

`dev_err_probe` handles `-EPROBE_DEFER` silently and logs everything else — use it in
every probe error path.

## Use the subsystem, not a char device

| Hardware | Framework |
|----------|-----------|
| Sensor (ADC, IMU, temp) | IIO — gives sysfs, buffers, triggers, userspace ABI for free |
| GPIO | gpiod consumer API; never the legacy integer API |
| Register map over I2C/SPI | regmap — caching, locking, debugfs |
| Input device | input subsystem |
| Camera | V4L2 / media controller |
| Display | DRM/KMS |
| Network | netdev |
| PWM, clk, regulator, hwmon, watchdog, rtc | the matching framework |

A raw char device with custom ioctls is the wrong answer when a framework exists: you
lose the standard userspace ABI, and the driver will not be upstreamable.

## regmap

```c
static const struct regmap_config my_regmap_cfg = {
	.reg_bits = 8,
	.val_bits = 8,
	.max_register = MY_REG_MAX,
	.cache_type = REGCACHE_RBTREE,
	.volatile_reg = my_is_volatile,     /* status regs must not be cached */
};
priv->regmap = devm_regmap_init_i2c(client, &my_regmap_cfg);
```
Mark status/interrupt registers volatile, or cached reads will return stale values —
a classic "the interrupt fires forever" bug.

## Out-of-tree module

```makefile
obj-m += mydriver.o
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules
```
Cross-compiling: `make -C $KDIR M=$PWD ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- modules`

In Yocto, an out-of-tree module is a recipe inheriting `module`. Prefer upstreaming or
at least an in-layer patch over a permanently out-of-tree module: it breaks on every
kernel bump and nobody else maintains it.

## Debugging

```bash
# dynamic debug — per-file, per-function, no rebuild
echo 'file mydriver.c +p' > /sys/kernel/debug/dynamic_debug/control
echo 'module mydriver +p' > /sys/kernel/debug/dynamic_debug/control

# ftrace — what actually ran
echo function_graph > /sys/kernel/debug/tracing/current_tracer
echo my_probe > /sys/kernel/debug/tracing/set_graph_function
cat /sys/kernel/debug/tracing/trace

# probe failures
cat /sys/kernel/debug/devices_deferred      # drivers stuck on EPROBE_DEFER
dmesg | grep -i "probe"

# performance
perf top; perf record -g -- <workload>
```

Development kernel config, always on:
```
CONFIG_DEBUG_KERNEL, CONFIG_DEBUG_ATOMIC_SLEEP, CONFIG_PROVE_LOCKING,
CONFIG_DEBUG_OBJECTS, CONFIG_KASAN (if the platform supports it),
CONFIG_DEBUG_INFO, CONFIG_DYNAMIC_DEBUG, CONFIG_FTRACE
```
Lockdep and KASAN find bugs that never reproduce otherwise. Run the HIL suite at
least once per release with them enabled.

## Oops decoding

```bash
./scripts/decode_stacktrace.sh vmlinux < oops.txt
addr2line -e vmlinux <address>
faddr2line vmlinux my_probe+0x4c/0x120
```
Read the oops top-down: the fault type, the faulting address (`0000000000000000` = NULL
deref), `RIP`/`PC` = where, then the call trace = how you got there.

## Upstream discipline

```bash
scripts/checkpatch.pl --strict <patch>
make C=1                       # sparse: __user, endianness, context annotations
make W=1                       # extra warnings
make dt_binding_check DT_SCHEMA_FILES=Documentation/devicetree/bindings/...
```
New bindings are YAML and must validate. Patches carry `Signed-off-by` and the
subsystem prefix. Even if you never send it upstream, matching upstream style makes
the next kernel bump survivable.
