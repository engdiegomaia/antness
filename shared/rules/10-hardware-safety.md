# Hardware Safety Rules (CRITICAL)

> These are stop conditions. They override task completion.

## Operations requiring explicit per-command user confirmation

Never run these autonomously, even with broad permissions granted earlier:

| Class | Examples |
|-------|----------|
| One-time programmable | `fuse prog`, `efuse`, `espefuse.py burn_efuse`, OCOTP writes |
| Secure boot enablement | closing the device, `SEC_CONFIG`, burning SRK hashes, `esp_secure_boot` |
| Bootloader overwrite | writing SPL/U-Boot/boot ROM region on the only boot medium |
| Partition table / GPT | `sfdisk`, `parted`, `dd` to `/dev/mmcblk*`, `/dev/sd*` |
| Mass erase | `st-flash erase`, `nrfjprog --eraseall`, chip erase |
| Persistent env changes | `fw_setenv bootcmd`, `setenv` + `saveenv` on production units |
| Update campaigns | pushing an OTA/Torizon Cloud update to a fleet |
| Fleet-wide commands | any command over a device list rather than one device |

For each: state the command, the device it targets, what becomes irreversible, and
the recovery path (recovery mode? JTAG? board RMA?). Then wait.

## Bricking-risk checklist, before any boot-chain write

- [ ] Is there a recovery path that does not require desoldering? (USB DFU, serial
      download mode, JTAG, SD boot, boot mode switches)
- [ ] Is the current image backed up and the backup verified readable?
- [ ] Is the device a development unit, or a customer/production unit?
- [ ] Does the new image boot in a simulator or on a sacrificial board first?

If any answer is "no"/"unknown", stop and report.

## Lab and electrical safety

- Never instruct a voltage/current change on a supply without stating the limits from
  the datasheet absolute-maximum table.
- Never suggest probing or connecting/disconnecting on a powered board.
- Mains-connected, motor, battery, laser, or RF-transmitting hardware: state the hazard
  explicitly before any procedure.
- Never disable a hardware protection (OCP, OVP, thermal shutdown, watchdog) to make a
  test pass.

## Destructive-by-accident patterns to reject

```bash
dd if=image.wic of=/dev/sda            # unverified device node -> host disk
rm -rf $BUILDDIR/tmp                   # fine; but rm -rf $BUILDDIR with sources inside is not
bitbake -c cleanall <everything>       # multi-hour rebuild, confirm first
west flash                             # confirm the board is the intended one
picocom /dev/ttyUSB0                   # confirm which adapter, multiple boards on one host
```

Always resolve device nodes by stable id (`/dev/serial/by-id/...`, `lsblk -o NAME,SIZE,MODEL`)
and echo the resolution to the user before the destructive step.

## Shared-lab discipline

Boards are shared. Before power cycling, resetting, or flashing, state which board
(serial number / hostname / adapter id) you are about to touch.
