---
name: serial-console-debug
description: Serial console setup and debugging — adapter selection, level shifting, terminal tools, log capture, and diagnosing no-output/garbage-output.
track: both
---

# Serial Console

## Connect

```bash
ls -l /dev/serial/by-id/        # ALWAYS use these, not ttyUSB0 — it renumbers
dmesg | tail                    # which adapter just enumerated

picocom -b 115200 /dev/serial/by-id/usb-FTDI_...-if00-port0
# exit: Ctrl-A Ctrl-X

# with logging (do this by default)
picocom -b 115200 --logfile boot-$(date +%s).log /dev/serial/by-id/...

minicom -D /dev/serial/by-id/... -b 115200
tio /dev/serial/by-id/... -b 115200       # reconnects automatically, good for power cycling
screen /dev/ttyUSB0 115200                # exit: Ctrl-A k
```

`tio` is the best choice for bring-up: it survives the adapter disappearing when the
board is power-cycled.

Permissions: add yourself to `dialout` (Debian/Ubuntu) or `uucp` (Arch), log out and in.
Do not `sudo` a terminal program as a workaround — it hides the real problem and the
logs end up root-owned.

## Electrical

- **Level**: 1.8 V, 3.3 V, or RS-232. A 3.3 V adapter on a 1.8 V console can damage the
  SoC. Check the module datasheet before connecting.
- **Ground**: always connect. A missing ground gives intermittent garbage.
- **TX/RX**: adapter TX -> board RX. Swapping gives silence, not an error.
- Never connect or disconnect on a powered board during bring-up.

## No output — order of checks

1. Is the board powered and out of reset? (scope, see `board-bringup`)
2. Is anything at all on the TX pin? (scope it — activity at the wrong baud looks like garbage,
   no activity looks like silence)
3. Correct pin? Console UART assignment differs between module variants.
4. Correct level shifting?
5. Correct baud? Wrong clock config -> wrong baud. If the crystal is off, so is the UART.
6. TX/RX swapped?
7. Is the bootloader configured to output on this UART? (different `stdout` in U-Boot env)

## Garbage output

Almost always a baud mismatch, which almost always means a clock problem. Try common
rates (115200, 57600, 9600). If a different rate produces readable text, the system
clock is not what the software thinks it is.

Persistent garbage at every rate: level mismatch or a floating ground.

## Capture everything

```bash
# timestamped capture from power-on — essential for boot-time work
grabserial -v -d /dev/ttyUSB0 -b 115200 -t -e 60 -o boot.log

# tee a session
picocom -b 115200 /dev/... | tee session.log
```
Never debug a boot problem from memory of what scrolled past. Capture, then read.

## Kernel console

```
console=ttymxc0,115200 earlycon=ec_imx6q,0x30860000,115200 loglevel=8
```
`earlycon` prints before the real console driver initializes — it is the difference
between "silent hang" and "hang after X". Enable it for any boot debugging.

Multiple consoles: `console=` can appear twice; the last one gets `/dev/console`.

## Production

Disable or authenticate the serial console in production images:
- U-Boot: `CONFIG_AUTOBOOT_KEYED` with a password, or no interrupt at all
- Linux: no `console=` getty, or a login with a real password
- NSH/Zephyr shell: disabled

A serial console on a shipped device is a full root shell to anyone with a screwdriver.
