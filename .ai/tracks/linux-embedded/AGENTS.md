# AGENTS.md — Embedded Linux Track

> Extends the root `AGENTS.md`. Load together with `.ai/rules/shared/*`.

## Scope

Board support and system integration on embedded Linux: Yocto/OpenEmbedded, Torizon OS,
Buildroot, kernel and driver development, device tree, AOSP, and on-device inference
(ONNX Runtime, TFLite + delegates, NPU/VPU acceleration).

## Skill routing

| Detected in repo | Skill |
|------------------|-------|
| `conf/local.conf`, `bblayers.conf`, `*.bb`, `*.bbappend`, `kas*.yml` | `.ai/skills/linux-embedded/yocto-openembedded/SKILL.md` |
| `docker-compose.yml` on a Toradex module, `tcbuild.yaml`, `torizoncore-builder` | `.ai/skills/linux-embedded/torizon-os/SKILL.md` |
| `configs/*_defconfig`, `package/*/Config.in` | `.ai/skills/linux-embedded/buildroot-development/SKILL.md` |
| `Makefile` with `obj-m`, `MODULE_LICENSE`, `Kconfig` in a kernel tree | `.ai/skills/linux-embedded/kernel-driver-development/SKILL.md` |
| `*.dts`, `*.dtsi`, `*.dtbo`, `arch/*/boot/dts/` | `.ai/skills/linux-embedded/device-tree/SKILL.md` |
| `Android.bp`, `device/<vendor>/`, `AndroidProducts.mk` | `.ai/skills/linux-embedded/android-aosp/SKILL.md` |
| Embedded Linux user-space applications: Python, Qt, Rust, IPC, containers, CI/CD | `.ai/skills/linux-embedded/embedded-linux-applications/SKILL.md` |
| AArch64 ELF disassembly, instruction-level debugging, or reverse engineering | `.ai/skills/linux-embedded/armv8-reverse-engineering/SKILL.md` |
| Model files, ONNX, TFLite, NPU/VPU/GPU delegate | `.ai/skills/linux-embedded/linux-edge-ai/SKILL.md` |
| New board, first boot, no console | `.ai/skills/linux-embedded/board-bringup/SKILL.md` |
| Test work | `.ai/skills/linux-embedded/linux-testing/SKILL.md` |

## Before you touch a BSP

State these, from the repo or by asking:

```
SoC / module:       e.g. i.MX8M Plus, Verdin iMX8MP, module revision
Carrier board:      name + revision
Build system:       Yocto (release name) / Buildroot (version) / Torizon / AOSP
Kernel:             version + vendor fork + branch
Bootloader:         U-Boot version, boot media, boot order
Boot chain:         ROM -> SPL -> U-Boot -> kernel -> initramfs? -> rootfs
Update mechanism:   none / RAUC / swupdate / Torizon Cloud / OSTree / A-B
Build command:      the single command that builds from clean
```

## Linux track hard rules

1. **Never edit under `tmp/`, `build/`, or another layer's recipes.** Changes go in your
   own layer as a `.bbappend`, a patch with `Upstream-Status:`, or a config fragment.
2. **Never modify the boot chain on the only boot medium without a recovery path.**
   See `.ai/rules/shared/10-hardware-safety.md`.
3. **Device tree describes hardware, not policy.** Use overlays where the platform
   supports them (Torizon, U-Boot `fdt apply`) rather than forking the base DTS.
4. **`bitbake -e` before asserting a variable's value.** Never guess what a variable
   expands to; the override and append order is not obvious.
5. **License and SBOM are build outputs.** `LICENSE` and `LIC_FILES_CHKSUM` correct on
   every recipe; SPDX/SBOM generated for every release image.
6. **No secrets in the image.** No keys, no default passwords, no dev certificates in
   anything shipped.
7. **Report image size, package count, and boot time deltas** for changes affecting them.
8. **A kernel change is validated by booting it**, or reported as not validated.

## Kernel context discipline

- Code in interrupt or atomic context must not sleep. `might_sleep()` violations are
  bugs even when they do not crash yet.
- Locking: state which lock protects which data, and the ordering, in a comment.
- Userspace pointers are validated with `copy_from_user`/`copy_to_user`, never
  dereferenced. Every `ioctl` argument is untrusted input.
- Resource acquisition uses devm_* where a device lifetime matches, so error paths
  do not leak.

## Build-failure routing

BitBake/Buildroot/kernel build errors -> `bsp-build-resolver` agent. Typical classes:
missing `DEPENDS`/`RDEPENDS`, `do_package_qa` failures, host-path contamination,
`LIC_FILES_CHKSUM` mismatch after a version bump, patch no longer applying, sstate
staleness, missing kernel config symbol pulled in by a defconfig fragment.

## Review triggers

- Device tree changed -> `device-tree-auditor`
- Kernel/driver code changed -> `kernel-driver-reviewer`
- Recipe/layer changed -> `yocto-recipe-reviewer`
- Container/compose or Torizon deployment changed -> `torizon-container-reviewer`
- Boot, keys, update, or network exposure changed -> `embedded-security-reviewer`
