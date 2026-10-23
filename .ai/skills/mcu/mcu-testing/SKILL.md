---
name: mcu-testing
description: Firmware testing across host unit tests, simulation (Renode/QEMU/native_sim) and hardware-in-the-loop. Unity/CMock, ztest, pytest-embedded, coverage on embedded targets.
track: mcu
---

# MCU Testing

Layers defined in `.ai/rules/shared/30-embedded-testing.md`. This skill is the how.

## Design for testability

The only prerequisite that matters: **hardware access behind a seam.**

```c
/* port/hal_i2c.h — the seam */
struct i2c_ops {
    int (*write)(void *ctx, uint8_t addr, const uint8_t *d, size_t n);
    int (*read )(void *ctx, uint8_t addr, uint8_t *d, size_t n);
};

/* Driver takes the ops — testable on host with a fake */
int bme280_init(struct bme280 *dev, const struct i2c_ops *bus, void *ctx);
```

With Zephyr, the seam already exists (`struct device` + emulated bus drivers, `EMUL`).
With ESP-IDF/HAL SDKs, you create it. A driver that calls `HAL_I2C_Master_Transmit`
directly is untestable off-target — that is a design finding.

## Layer 2 — host unit tests

### Unity + CMock (vendor-agnostic C)
```c
void setUp(void)    { mock_i2c_Init(); }
void tearDown(void) { mock_i2c_Verify(); mock_i2c_Destroy(); }

void test_read_returns_EIO_when_bus_nacks(void)
{
    i2c_write_ExpectAndReturn(NULL, 0x76, NULL, 1, -EIO);
    i2c_write_IgnoreArg_ctx();
    TEST_ASSERT_EQUAL(-EIO, bme280_read(&dev, &sample));
}
```
Ceedling drives Unity+CMock+gcov with one command: `ceedling test:all gcov:all`.

### Zephyr ztest on native_sim
```bash
west twister -T tests -p native_sim --coverage
```
Full Zephyr kernel on host: threads, timers, devicetree and emulated drivers all work.
This is the highest-value layer for Zephyr projects.

### Naming
```
test_<function>_<expected>_when_<condition>
test_parse_frame_rejects_payload_longer_than_mtu
```

## Layer 3 — simulation

| Tool | Good for |
|------|----------|
| **Renode** | Full SoC + peripherals + multiple nodes + network; scriptable; runs real binaries |
| **QEMU** | Zephyr `qemu_cortex_m3`, ESP32 QEMU; fast, fewer peripherals |
| `native_sim` | Zephyr logic testing, fastest iteration |

Renode is the one that scales to "boot the real image and test the protocol":
```
mach create "dut"
machine LoadPlatformDescription @platforms/boards/stm32f4_discovery.repl
sysbus LoadELF @build/app.elf
showAnalyzer sysbus.usart2
start
```
Renode robot tests run in CI with no hardware, catching regressions that host unit
tests cannot express (interrupt timing, peripheral state machines).

## Layer 4 — hardware in the loop

```python
# pytest + pyserial + a power relay
def test_boots_to_shell(dut_power, serial_port):
    dut_power.cycle()
    assert serial_port.expect(b"uart:~$", timeout=10)

def test_survives_1000_power_cycles(dut_power, serial_port):
    for i in range(1000):
        dut_power.cycle()
        assert serial_port.expect(b"boot ok", timeout=10), f"failed at cycle {i}"
```

Infrastructure requirements:
- Devices addressed by stable id (`/dev/serial/by-id/`, probe serial number), never `ttyUSB0`
- Programmatic power control (USB relay, PDU) — reset is not enough to test cold boot
- Every failure collects: full serial log, coredump, and the flashed image hash
- Hard timeout on a hung target so the farm does not stall

Frameworks: `pytest-embedded` (ESP-IDF), `west twister --device-testing` with a
`hardware-map.yml` (Zephyr), Labgrid (vendor-neutral board farm).

## Coverage

- Host layers: `gcov`/`lcov`, target >=80% of host-testable logic.
- On target: `gcov` with a custom `_write` dumping over UART/RTT, or Renode coverage.
  Expect this to be expensive — use it periodically, not per commit.
- 100% of error-return paths in drivers are reviewed, by test where provokable and by
  inspection where not. Record which.

## CI shape

```yaml
on: [push]
jobs:
  static:   { steps: [compile -Werror, clang-tidy, cppcheck] }
  unit:     { steps: [ceedling gcov:all | west twister -p native_sim --coverage] }
  sim:      { steps: [renode-test tests/robot/*.robot] }
  hil:      { runs-on: [self-hosted, board-farm], if: nightly-or-release }
```

## Rules

- A bug fix begins with a failing test at the lowest layer that can express it.
- Never add a delay to fix a flaky test. Find the race; a delay hides it until the field.
- Quarantined flaky tests have an owner and a deadline, recorded in the repo.
- Always state which layer produced a result when reporting.
