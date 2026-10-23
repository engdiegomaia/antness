#!/usr/bin/env bash
# PreToolUse guard: blocks irreversible hardware operations from running unattended.
#
# Claude Code: wire as a PreToolUse hook on Bash (see .ai/adapters/claude-hooks.json).
#   Reads the tool call JSON on stdin, exits 2 to block with a message on stderr.
# Other harnesses / manual: pass the command as $1.
#
# This is a safety net, not a policy. The policy is .ai/rules/shared/10-hardware-safety.md.
set -uo pipefail

if [ $# -ge 1 ]; then
  CMD="$*"
else
  INPUT="$(cat)"
  CMD="$(printf '%s' "$INPUT" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"
fi

[ -n "${CMD:-}" ] || exit 0

block() {
  cat >&2 <<EOF
[BLOCKED] Irreversible hardware operation detected.

  Command: $CMD
  Reason:  $1

This class of operation cannot be undone and may permanently disable the device.
Before proceeding, state to the user:
  - the exact device targeted (serial number / device node resolved by stable id)
  - what becomes irreversible
  - the recovery path (USB DFU / serial download / JTAG / SD boot / none)

See .ai/rules/shared/10-hardware-safety.md. The user must confirm this specific command.
EOF
  exit 2
}

# --- one-time programmable / secure boot -----------------------------------
case "$CMD" in
  *espefuse*burn*|*"efuse"*"burn"*)      block "eFuse burning is permanent" ;;
  *fuse\ prog*|*"fuse prog"*)             block "fuse programming is permanent" ;;
  *"secure_boot"*|*"SEC_CONFIG"*|*"srktool"*|*"cst "*)
                                          block "secure boot provisioning is permanent" ;;
  *nrfjprog*--eraseall*|*"--mass-erase"*|*"chip_erase"*|*"erase-flash"*)
                                          block "mass erase destroys the current image" ;;
esac

# --- raw block device writes ------------------------------------------------
case "$CMD" in
  *dd\ *of=/dev/sd*|*dd\ *of=/dev/nvme*|*dd\ *of=/dev/mmcblk*|*dd\ *of=/dev/disk*)
      block "raw write to a block device — a wrong device node destroys a host disk" ;;
  *mkfs*/dev/*|*sfdisk*/dev/*|*"parted "*/dev/*|*wipefs*/dev/*)
      block "partition table / filesystem operation on a raw device" ;;
esac

# --- bootloader environment on a device ------------------------------------
case "$CMD" in
  *fw_setenv*bootcmd*|*fw_setenv*bootargs*|*"saveenv"*)
      block "modifying the boot environment can make the device unbootable" ;;
  *uuu\ *|*"imx_usb"*|*"sdphost"*|*"blhost"*)
      block "SoC serial-download programming writes the boot chain" ;;
esac

# --- fleet operations -------------------------------------------------------
case "$CMD" in
  *torizoncore-builder*platform\ push*|*"aktualizr"*"--campaign"*)
      block "this pushes an update to devices — never issue fleet-wide autonomously" ;;
esac

# --- destructive build-state wipes -----------------------------------------
case "$CMD" in
  *rm\ -rf*sstate-cache*|*rm\ -rf*downloads*|*rm\ -rf*DL_DIR*)
      block "sstate/downloads are shared team assets; scope cleanup to a recipe" ;;
esac

exit 0
