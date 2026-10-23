---
name: zephyr-development
description: Zephyr RTOS development — west workspace, devicetree, Kconfig, drivers, power management, and twister testing. Use when the repo contains west.yml, prj.conf, or board overlays.
track: mcu
---

# Zephyr RTOS Development

## Orient first

```bash
west topdir                       # workspace root
west list                         # manifest projects + revisions
west boards | grep -i <board>
cat zephyr/VERSION                # Zephyr version actually in the workspace
```

Zephyr APIs change between LTS and mainline. Confirm the version before quoting an API.

## Workspace and build

```bash
west init -m <url> --mr <tag> ws && cd ws && west update   # pinned manifest revision
west build -b <board> app -p auto                          # -p auto, not always pristine
west build -b <board> app -- -DEXTRA_CONF_FILE=debug.conf
west build -t menuconfig            # explore, then write the result into prj.conf
west build -t rom_report -t ram_report
west flash --runner jlink           # CONFIRM the board first
west debug
```

Never hand-edit `build/zephyr/.config` — it is generated. Configuration lives in
`prj.conf`, `boards/<board>.conf`, or a `Kconfig` symbol in your module.

## Devicetree

Devicetree describes hardware; Kconfig describes software. Do not encode board wiring
in Kconfig.

```dts
/* app.overlay — application view of the board */
&i2c1 {
    status = "okay";
    clock-frequency = <I2C_BITRATE_FAST>;

    sensor: bme280@76 {
        compatible = "bosch,bme280";
        reg = <0x76>;
    };
};

/ {
    aliases { env-sensor = &sensor; };
};
```

```c
static const struct device *const sensor = DEVICE_DT_GET(DT_ALIAS(env_sensor));

if (!device_is_ready(sensor)) {      /* mandatory, every device, every time */
    return -ENODEV;
}
```

Debug devicetree with the generated output, never by guessing:
```bash
build/zephyr/zephyr.dts              # final merged devicetree
build/zephyr/include/generated/devicetree_generated.h
```

Binding missing -> the node is silently dropped. `DEVICE_DT_GET` on a node without a
matching enabled driver fails at link time with an obscure undefined reference — check
`status = "okay"` and the driver's Kconfig symbol first.

## Application structure

```
app/
├── CMakeLists.txt
├── prj.conf
├── Kconfig                      # app-specific symbols
├── boards/
│   ├── <board>.conf
│   └── <board>.overlay
├── src/
└── drivers/ or modules/         # out-of-tree drivers as a Zephyr module
```

Out-of-tree driver: a module with `zephyr/module.yml`, its own `Kconfig`, `CMakeLists.txt`
and `dts/bindings/`. Added to the build via `ZEPHYR_EXTRA_MODULES` or the manifest.

## Threads, work and timing

```c
K_THREAD_DEFINE(worker_tid, STACK_SIZE, worker_fn, NULL, NULL, NULL,
                PRIORITY, 0, 0);          /* static allocation, preferred */

K_WORK_DEFINE(deferred, deferred_handler);    /* ISR defers here */

/* In the ISR */
k_work_submit(&deferred);                     /* never process in the ISR */
```

- System workqueue is shared — long work starves other users; use a dedicated workqueue.
- `k_sleep` in the system workqueue blocks every other user of it.
- `CONFIG_THREAD_ANALYZER=y` + `CONFIG_THREAD_ANALYZER_AUTO=y` for stack high-water.

## Power management

```
CONFIG_PM=y                    # system PM (sleep states from devicetree power-states)
CONFIG_PM_DEVICE=y             # per-device suspend/resume
CONFIG_PM_DEVICE_RUNTIME=y     # reference-counted device PM
```
Devices must implement `PM_DEVICE_DT_INST_DEFINE` and handle `SUSPEND`/`RESUME`
without losing state. Verify actual residency, do not assume the state was entered.

## Logging

```
CONFIG_LOG=y
CONFIG_LOG_MODE_DEFERRED=y     # do not format in the caller's context
CONFIG_LOG_DEFAULT_LEVEL=3
```
`LOG_MODULE_REGISTER(name, CONFIG_MY_MODULE_LOG_LEVEL);` per module. Dictionary logging
(`CONFIG_LOG_DICTIONARY_SUPPORT`) removes format strings from flash.

## Testing

```bash
west twister -T tests -p native_sim              # host
west twister -T tests -p qemu_cortex_m3          # emulated
west twister -T tests --device-testing --hardware-map map.yml   # real boards
```
Ztest:
```c
ZTEST_SUITE(sensor_suite, NULL, setup, before, after, teardown);
ZTEST(sensor_suite, test_read_returns_error_when_bus_fails) { ... }
```

## Common failure modes

| Symptom | Cause |
|---------|-------|
| `undefined reference to __device_dts_ord_N` | node `status` not `"okay"`, or driver Kconfig off |
| Build passes, device not ready at runtime | init priority ordering — check `CONFIG_*_INIT_PRIORITY` |
| Hard fault at boot, before `main` | stack size, or MPU region misconfiguration |
| Region `FLASH` overflowed | disable unused subsystems; check `rom_report` |
| Works on `native_sim`, hangs on target | busy wait on a peripheral, missing `status = "okay"` on a clock/pin node |
| Sporadic corruption with DMA | non-cache-aligned buffer on a cached core |

## Never

- Edit files under `zephyr/` in-tree to fix an application problem — use an overlay,
  a module, or a `Kconfig` fragment.
- Commit `build/`.
- Change a manifest revision as a side effect of another task.
