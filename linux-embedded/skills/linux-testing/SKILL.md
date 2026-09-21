---
name: linux-testing
description: Testing embedded Linux systems — image-level testing (ptest, Yocto testimage), kernel selftests, HIL board farms with Labgrid, boot-time and stress testing, and CI patterns.
track: linux-embedded
---

# Embedded Linux Testing

Layers defined in `shared/rules/30-embedded-testing.md`.

## Layer map for Linux

| Layer | Mechanism |
|-------|-----------|
| Static | `checkpatch.pl`, sparse (`make C=1`), `make W=1`, Coccinelle, shellcheck, `bitbake -c qa` |
| Host unit | Application logic compiled natively; GoogleTest/pytest/Criterion |
| Emulated | `runqemu` (Yocto), QEMU with the real kernel + rootfs |
| Image | Yocto `testimage`, package `ptest`, `oe-selftest` |
| HIL | Labgrid, board farm with power control, serial, and flashing |
| Soak | power cycling, thermal, memory/fd leak watch, long-running I/O |

## Yocto image testing

```bitbake
# local.conf or the image recipe
INHERIT += "testimage"
TEST_SUITES = "ping ssh date parselogs systemd myapp"
TEST_TARGET = "qemu"        # or "simpleremote" for real hardware
```
```bash
bitbake core-image-minimal -c testimage
```

`parselogs` catches kernel errors in the boot log automatically — enable it always.
It is the cheapest regression detector for BSP work.

Custom test case:
```python
from oeqa.runtime.case import OERuntimeTestCase
from oeqa.core.decorator.depends import OETestDepends

class MyAppTest(OERuntimeTestCase):
    @OETestDepends(['ssh.SSHTest.test_ssh'])
    def test_myapp_starts(self):
        status, output = self.target.run('systemctl is-active myapp')
        self.assertEqual(status, 0, msg=f'myapp not active: {output}')
```

## ptest

```bitbake
inherit ptest
SRC_URI += "file://run-ptest"
RDEPENDS:${PN}-ptest += "bash"
```
```bash
# on target
ptest-runner myapp
```
Upstream packages that ship tests get them for free with `ptest-runner` — a strong
smoke signal that the cross-built libraries actually work.

## Kernel testing

```bash
make kselftest                                  # in-tree selftests
make -C tools/testing/selftests TARGETS=gpio run_tests
# KUnit — unit tests inside the kernel
./tools/testing/kunit/kunit.py run --arch=arm64 --cross_compile=aarch64-linux-gnu-
```
Enable for at least one CI run per release:
`CONFIG_KASAN`, `CONFIG_PROVE_LOCKING`, `CONFIG_DEBUG_ATOMIC_SLEEP`,
`CONFIG_DEBUG_OBJECTS`, `CONFIG_UBSAN`. These find bugs that never reproduce otherwise.

## HIL with Labgrid

```yaml
targets:
  board-01:
    resources:
      - RawSerialPort: {port: "/dev/serial/by-id/usb-FTDI_...-if00-port0"}
      - NetworkPowerPort: {model: "gude", host: "pdu01", index: 3}
      - USBSDMuxDevice: {match: {"ID_PATH": "..."}}
    drivers:
      - SerialDriver: {}
      - NetworkPowerDriver: {}
      - ShellDriver:
          prompt: 'root@\w+:[^ ]+ '
          login_prompt: ' login: '
          username: 'root'
```
```python
def test_boots_and_reaches_shell(target):
    target.get_driver("PowerProtocol").cycle()
    shell = target.get_driver("CommandProtocol")
    assert shell.run_check("systemctl is-system-running --wait")
```

Requirements for any board farm:
- Devices addressed by stable id, never `ttyUSB0` or `/dev/sdb`
- Programmatic power control — reset is not a cold boot
- Every failure collects the full boot log, `dmesg`, the image hash and `journalctl -b`
- Hard timeout so a hung board does not stall the farm

## Boot time

```bash
systemd-analyze; systemd-analyze blame; systemd-analyze critical-chain
grabserial -v -d /dev/ttyUSB0 -t -m "U-Boot"     # timestamps from power-on
bootchart / bootgraph.pl < dmesg
```
Measure per stage: ROM -> SPL -> U-Boot -> kernel -> userspace -> application ready.
Report the stage-by-stage breakdown, not just the total.

## Stress and soak

```bash
stress-ng --cpu 4 --vm 2 --hdd 1 --timeout 3600 --metrics
memtester 256M 10
iperf3 -c <host> -t 600
for i in $(seq 1 1000); do power_cycle; wait_for_boot || echo "FAIL at $i"; done
```
Watch for: memory growth (`/proc/meminfo`, RSS per service), fd leaks (`ls /proc/*/fd | wc`),
eMMC wear (`/sys/block/mmcblk0/device/life_time`), thermal throttling, and kernel
errors accumulating in `dmesg`.

## CI shape

```yaml
static:  checkpatch, sparse, shellcheck, yocto QA
build:   kas build (cached sstate), artifact + SBOM + CVE report
emulate: runqemu + testimage (ping/ssh/parselogs/ptest)
hil:     nightly on the board farm — boot, peripheral, update, rollback, soak
release: reproducibility check (two clean builds, compare hashes)
```

Always state which layer produced a reported result.
