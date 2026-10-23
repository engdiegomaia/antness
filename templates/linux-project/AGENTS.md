# AGENTS.md — <project name>

> Project-specific context. The shared environment is in `.ai/`; this file is the
> part only you can write. Agents read it before touching hardware.

## Hardware

```
SoC:              <e.g. i.MX8M Plus>
Module / SoM:     <e.g. Verdin iMX8MP Quad 4GB WB IT, revision>
Carrier board:    <name + revision>
Storage:          <eMMC size, SD, QSPI NOR>
RAM:              <size>
Console:          <UART, /dev/serial/by-id/..., baud>
Network:          <interfaces, how the board is reached>
Recovery:         <USB recovery / SD boot / boot switches — how to unbrick>
Boards in lab:    <hostname/serial -> owner>
```

## Software

```
Build system:     <Yocto <release> / Buildroot <ver> / Torizon OS <ver> / AOSP <ver>>
Distro / image:   <name>
Kernel:           <version, vendor fork, branch/SHA>
Bootloader:       <U-Boot version, boot order>
Boot chain:       ROM -> <SPL> -> <U-Boot> -> <kernel> -> <initramfs?> -> <rootfs>
Update mechanism: <none / RAUC / swupdate / Torizon Cloud / OSTree / A-B>
Layers:           <list with pinned revisions, or the kas/repo manifest path>
Track skill:      <.ai/skills/linux-embedded/...>
```

## Commands

```bash
# Build (from a clean tree, one command)
<command>

# Deploy to a device — CONFIRM the device first
<command>

# Test (emulated)
<command>

# Test (hardware)
<command>

# Image size / SBOM
<command>
```

## Budgets

```
Image size:       <current> / <target>
Boot time:        <per stage: ROM/SPL/U-Boot/kernel/userspace/app-ready>
RAM at idle:      <target>
eMMC write rate:  <expected per day — for wear estimation>
```

## Project decisions

- Generated files committed: <defconfig? sdkconfig? DTB?>
- Device tree changes: <overlay / base DTS fork — and why>
- Production image hardening: <debug-tweaks removed, console disabled, ...>
- Regulated scope: <none / IEC 62443 / EU CRA / medical / automotive>

## Known hazards on this hardware

<Errata workarounds, a peripheral that needs a specific power sequence, a carrier
board bodge, an eMMC batch with known wear issues. Anything that would surprise
someone touching it.>
