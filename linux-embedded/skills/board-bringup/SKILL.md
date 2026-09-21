---
name: board-bringup
description: New carrier board or new SoM first-boot bring-up — power, reset, clock, boot mode, console, bootloader, then kernel. Systematic ordering with measured evidence at each step.
track: linux-embedded
---

# Board Bring-up

> Do not skip steps. Do not start at software. Most "software" bring-up bugs are power,
> pinmux, or boot mode.

## Prerequisites on the desk

Schematic, pinmux table, module datasheet, carrier board design guide, SoC errata,
a known-good reference/evaluation board of the same module, oscilloscope, DMM,
USB-serial adapter, and a way to force recovery/serial-download mode.

## Step 0 — before power

- [ ] Visual inspection: correct module orientation, no solder bridges, all populated
- [ ] Continuity: no short between any supply rail and ground
- [ ] Boot-mode straps: read the schematic, confirm the resistors are fitted as intended
- [ ] Current-limited bench supply, limit set from the expected inrush

## Step 1 — power

Measure **every** rail with a scope, not a DMM (a DMM hides ripple and sequencing):

- [ ] Each rail reaches nominal, within tolerance
- [ ] The sequence matches the datasheet's power-up timing diagram
- [ ] No rail overshoots or oscillates
- [ ] Inrush current is within the supply's capability
- [ ] PMIC is enabled and its own rails are up (check its status over I2C if reachable)

A rail 5% low or sequenced wrong produces symptoms that look exactly like software bugs.

## Step 2 — reset

- [ ] Reset asserted at power-on, released after the required delay
- [ ] Release is clean — no ringing, no re-assertion
- [ ] Not oscillating (a reset loop looks like "no console")
- [ ] Watchdog, PMIC and supervisor reset sources all accounted for

## Step 3 — clock

- [ ] Main crystal/oscillator running at the specified frequency (scope on the load side)
- [ ] 32.768 kHz RTC clock present if the boot requires it
- [ ] Load capacitors match the crystal's spec — a wrong value gives a frequency offset
      that breaks UART baud and USB

## Step 4 — boot mode

- [ ] Strap pins read the intended value **at reset release** (scope them; a pin can be
      driven by a peripheral later)
- [ ] The intended boot medium is selected
- [ ] Recovery/serial-download mode can be forced — verify this **before** you need it

## Step 5 — console

- [ ] Correct UART pins per the schematic and the module's console assignment
- [ ] Level shifting correct (1.8 V vs 3.3 V — a mismatch gives garbage or nothing)
- [ ] TX/RX not swapped
- [ ] 115200 8N1 unless the BSP says otherwise
- [ ] Ground connected between adapter and board

Garbage characters usually mean a clock/baud mismatch; silence usually means wrong pin,
no power, or reset loop.

## Step 6 — first-stage output

Expected, in order: SoC boot ROM message -> SPL banner -> U-Boot prompt.

| Stops at | Look at |
|----------|---------|
| Nothing at all | steps 1–5 again; scope the UART TX pin for any activity |
| ROM message, no SPL | boot medium not readable, image not at the right offset, wrong boot mode |
| SPL, no U-Boot | DDR init failure — the most common new-board failure |
| U-Boot prompt | you are past hardware bring-up; now it is configuration |

DDR is its own project: run the vendor's DDR calibration/stress tool
(i.MX DDR Tool, `ddr_test`) and save the resulting timing configuration. Never accept
a DDR config that passes only at room temperature.

## Step 7 — U-Boot

```
=> bdinfo                 # DRAM size detected correctly?
=> mmc list; mmc info
=> i2c bus; i2c dev 0; i2c probe      # do the expected devices ACK?
=> gpio status -a
=> printenv bootcmd
=> fdt addr $fdt_addr; fdt print /soc  # is the right DTB loaded?
```
Interactive probing here is faster than any kernel-side debugging. If a device does
not ACK over I2C in U-Boot, the problem is electrical or pinmux, not the driver.

## Step 8 — kernel

```
earlycon=... loglevel=8 initcall_debug
```
- Kernel silent after U-Boot hands off: wrong `earlycon`/console in the DTB or cmdline,
  or a wrong load address.
- Panics in `initcall`: `initcall_debug` names the failing driver.
- Then work through `dmesg`, `devices_deferred`, pinctrl and clk debugfs — see
  `skills/device-tree`.

## Reporting a bring-up result

Always state: which step the board reached, the measured evidence at the failing step,
the single next experiment that discriminates between remaining hypotheses, and the
board serial/revision it applies to.

## Toradex-specific

`tdx-info` on a booting module gives module type, serial, BSP version and kernel — include
it in every report or support request. Compare the carrier against the Toradex carrier
board design guide for the module family, and check the module's errata list before
assuming a software cause.
