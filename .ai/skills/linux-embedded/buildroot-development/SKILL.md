---
name: buildroot-development
description: Buildroot development — defconfigs, external trees (BR2_EXTERNAL), package creation, rootfs overlays, and build debugging. Use when configs/*_defconfig or package/*/Config.in is present.
track: linux-embedded
---

# Buildroot

## Model

Buildroot builds a complete rootfs from source in one pass. It is not a package manager:
there is no runtime package installation, and **there is no incremental rebuild you can
fully trust** — changing a package's configuration usually requires rebuilding it
explicitly, and changing toolchain or global options requires a full rebuild.

Choose Buildroot over Yocto when the image is small, fixed, and rebuilt as a unit.
Choose Yocto when you need package feeds, multiple images, or layered BSP reuse.

## Workflow

```bash
make list-defconfigs
make <board>_defconfig
make menuconfig
make savedefconfig                 # ALWAYS — regenerates the minimal defconfig
cp defconfig configs/<board>_defconfig
make -j$(nproc)
```

Commit `configs/<board>_defconfig` (minimal, reviewable). Never commit `.config`
(generated, thousands of lines, unreviewable).

Output lands in `output/images/` — kernel, dtb, rootfs, bootloader.

## BR2_EXTERNAL — keep your work out of the tree

```
br2-external/
├── external.desc          # name: MYPRODUCT   desc: ...
├── external.mk            # include $(sort $(wildcard $(BR2_EXTERNAL_MYPRODUCT_PATH)/package/*/*.mk))
├── Config.in              # source "$BR2_EXTERNAL_MYPRODUCT_PATH/package/Config.in"
├── configs/<board>_defconfig
├── board/<vendor>/<board>/
│   ├── rootfs_overlay/    # files copied verbatim into the rootfs
│   ├── post-build.sh
│   ├── post-image.sh
│   ├── genimage.cfg
│   └── linux.fragment     # kernel config fragment
└── package/myapp/
    ├── Config.in
    └── myapp.mk
```

```bash
make BR2_EXTERNAL=/path/to/br2-external <board>_defconfig
```

Never patch the Buildroot tree itself for product needs. Everything goes in the
external tree.

## Package definition

```makefile
# package/myapp/myapp.mk
MYAPP_VERSION = v1.2.3
MYAPP_SITE = https://github.com/org/myapp.git
MYAPP_SITE_METHOD = git
MYAPP_LICENSE = MIT
MYAPP_LICENSE_FILES = LICENSE
MYAPP_DEPENDENCIES = host-pkgconf zlib openssl
MYAPP_INSTALL_STAGING = NO

define MYAPP_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/myapp $(TARGET_DIR)/usr/bin/myapp
	$(INSTALL) -D -m 0644 $(MYAPP_PKGDIR)/myapp.service \
		$(TARGET_DIR)/usr/lib/systemd/system/myapp.service
endef

$(eval $(cmake-package))     # or autotools-package, generic-package, meson-package
```

```
# package/myapp/Config.in
config BR2_PACKAGE_MYAPP
	bool "myapp"
	select BR2_PACKAGE_OPENSSL
	help
	  Product application.
```
Dependencies declared with `select` (Config.in) **and** `_DEPENDENCIES` (.mk). Missing
either causes a build-order failure that looks random.

## Rebuilding correctly

```bash
make myapp-rebuild        # re-run build+install for one package
make myapp-reconfigure    # re-run configure too (after changing its options)
make myapp-dirclean       # wipe that package's build dir
make linux-menuconfig && make linux-update-defconfig   # kernel config, saved to the fragment
make clean                # everything except downloads and ccache
```

Changing a global option (toolchain, libc, architecture) invalidates everything:
do a full rebuild. A "worked after `make clean`" result means the incremental state
was wrong — note what changed.

## Rootfs customization

| Need | Mechanism |
|------|-----------|
| Add static files | `BR2_ROOTFS_OVERLAY` directory |
| Modify files after build | `BR2_ROOTFS_POST_BUILD_SCRIPT` |
| Build the final image layout | `BR2_ROOTFS_POST_IMAGE_SCRIPT` + `genimage.cfg` |
| Users/permissions | `BR2_ROOTFS_USERS_TABLES`, `BR2_ROOTFS_DEVICE_TABLE` |

Overlay files keep their permissions from the host — set them correctly, and never
place secrets in the overlay.

## Reproducibility and licensing

```
BR2_REPRODUCIBLE=y
BR2_PER_PACKAGE_DIRECTORIES=y    # better isolation + parallelism
make legal-info                  # license manifest + source archive in output/legal-info/
```
`make legal-info` is the compliance deliverable. Run it for every release.

## Common failure modes

| Symptom | Cause |
|---------|-------|
| Package built but missing from the image | install commands write outside `$(TARGET_DIR)` |
| `.config` keeps changing in git | `.config` committed instead of `savedefconfig` output |
| Random build ordering failures | dependency in `Config.in` but not `_DEPENDENCIES` (or the reverse) |
| Kernel config change lost | edited `.config` instead of `make linux-update-defconfig` |
| Host tool used instead of cross | missing `host-` prefixed dependency |
| Works after full rebuild only | stale per-package state; identify what changed, do not just clean |
