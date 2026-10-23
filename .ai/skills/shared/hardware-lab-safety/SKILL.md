---
name: hardware-lab-safety
description: Safe procedures for lab work with embedded hardware — power supplies, probing, ESD, shared boards, and irreversible operations. Read before instructing any physical procedure.
track: both
---

# Hardware Lab Safety

> This skill exists so an agent never produces a confident procedure that damages
> hardware or a person.

## Before instructing any physical procedure

State explicitly:
1. What hardware is being touched (board, serial number, revision)
2. Whether it must be powered or unpowered
3. The hazard, if any (mains, battery, motor, RF, laser, heat, high current)
4. What is irreversible about the step
5. The recovery path if it goes wrong

If any of these is unknown, ask before proceeding.

## Power supplies

- Always set a **current limit** before applying power to a new board. Derive it from
  the expected consumption, not the supply's maximum.
- Never exceed a datasheet absolute-maximum rating; state the value you are working from.
- Bring rails up in the documented sequence. Out-of-order sequencing can latch up a SoC
  permanently.
- Power down before changing any connection.

## Probing

- Never probe a powered board with a hand-held probe on a fine-pitch part. Use a
  fixture or a soldered wire.
- Scope ground clip placement matters: a long ground lead gives false ringing. Use the
  spring ground for anything above a few MHz.
- Never connect a mains-referenced scope ground to a non-isolated live circuit.
- Check the probe's voltage rating before measuring anything above logic levels.

## ESD

Boards without enclosures are ESD-sensitive. Wrist strap, mat, and handling by the
edges. An ESD event usually does not kill a part outright — it degrades it, and the
board fails weeks later in a way nobody connects to the handling.

## Irreversible operations

Full list in `.ai/rules/shared/10-hardware-safety.md`. The classes:
fuse/eFuse/OTP burning, secure boot enablement, bootloader overwrite on the only boot
medium, partition table changes, mass erase, production key provisioning.

Each requires explicit per-command user confirmation with the recovery path stated.
"The user already approved flashing" does not extend to burning fuses.

## Shared lab discipline

- Announce which board you are about to power, reset, or flash — by serial number or
  hostname, not "the board".
- Never leave a board powered and unattended during a soak test without thermal and
  current monitoring.
- Restore boot mode switches and jumpers to their documented state when finished.
- Label anything modified (bodge wire, removed resistor) — the next person will not
  read your chat log.

## Hazard-specific notes

| Hazard | Rule |
|--------|------|
| Mains-connected | Isolation transformer, differential probe. Never a standard scope ground. |
| Li-ion / LiPo | Never short, never charge unattended, never puncture. Thermal runaway is fast. |
| Motors / actuators | Mechanical guard, e-stop reachable, assume unexpected motion on reset |
| RF transmit | Respect duty cycle and antenna connection — transmitting without a load damages the PA |
| Laser / IR | Eye safety class, never look into the emitter, even IR you cannot see |
| Hot surfaces | Heatsinks and power devices during soak; thermal camera before touching |

When a procedure involves any of these, say so before the first step, not in a footnote.
