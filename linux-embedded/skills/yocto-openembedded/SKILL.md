---
name: yocto-openembedded
description: Yocto Project / OpenEmbedded development — layers, recipes, bbappends, kernel config fragments, images, kas, devtool, SBOM and debugging BitBake failures. Use when bblayers.conf, *.bb or kas*.yml is present.
track: linux-embedded
---

# Yocto / OpenEmbedded

## Orient first — never guess

```bash
bitbake-layers show-layers            # layer priority order (matters for bbappends)
bitbake-layers show-recipes <pkg>     # which layers provide it, which version wins
bitbake-layers show-appends <recipe>  # what is appending to it
bitbake -e <recipe> | grep ^SRC_URI=  # the ACTUAL value after all overrides
bitbake -e <recipe> | grep -E "^(PV|PR|S|D|WORKDIR|DEPENDS)="
cat conf/bblayers.conf conf/local.conf
git -C <each layer> log -1            # the revision actually checked out
```

`bitbake -e` is the only authoritative source for a variable's value. Override and
append ordering (`:append`, `:prepend`, `:remove`, `:<machine>`, `:<distro>`) is not
readable by inspection.

## Setup

```bash
# kas (preferred — reproducible, declarative)
kas build kas/product.yml
kas shell kas/product.yml

# or classic
source oe-init-build-env build
bitbake core-image-minimal
```

Pin every layer to a SHA or tag in the kas file / repo manifest. A branch name is not
a pin.

## Recipe anatomy

```bitbake
SUMMARY = "Product application"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=..."     # must match the real file

SRC_URI = "git://example.com/app.git;protocol=https;branch=main \
           file://0001-fix-build.patch \
           file://app.service"
SRCREV = "a1b2c3d4..."                          # never AUTOREV in a product

S = "${WORKDIR}/git"

DEPENDS = "zlib openssl"                        # build-time
RDEPENDS:${PN} = "bash"                         # runtime — different thing

inherit cmake systemd

SYSTEMD_SERVICE:${PN} = "app.service"

do_install:append() {
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/app.service ${D}${systemd_system_unitdir}
}

FILES:${PN} += "${systemd_system_unitdir}/app.service"
```

## bbappend — modifying someone else's recipe

```bitbake
# recipes-kernel/linux/linux-toradex_%.bbappend
FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI += "file://my-feature.cfg \
            file://0001-driver-fix.patch"
```

`FILESEXTRAPATHS:prepend` with the trailing colon is required, and it must use `:=`
(immediate expansion) — `=` here silently fails to find your files.

Kernel config goes in a `.cfg` fragment, never a full defconfig:
```
# my-feature.cfg
CONFIG_SPI_SPIDEV=y
CONFIG_IIO=m
```
Verify it took effect: `bitbake -c menuconfig virtual/kernel` then `diffconfig`, or
check `build/tmp/work/.../linux-*/build/.config` after the build.

## devtool — the right way to iterate

```bash
devtool modify linux-toradex          # extracts source into workspace/, git-backed
# ...edit, build, test...
devtool build linux-toradex
devtool finish linux-toradex meta-mylayer   # generates patches into your layer
devtool reset linux-toradex
```
This produces properly formatted patches in your layer. Editing under `tmp/work/`
directly loses the change on the next clean — never do it.

## Images

```bitbake
inherit core-image

IMAGE_FEATURES += "ssh-server-openssh"       # DEV ONLY — remove for production
IMAGE_INSTALL:append = " myapp tzdata"        # note the leading space
IMAGE_FSTYPES = "wic.gz ext4"

# Production hardening
IMAGE_FEATURES:remove = "debug-tweaks allow-empty-password empty-root-password"
```
`debug-tweaks` gives an empty root password. It must never reach a production image —
check it explicitly in every release review.

## Build failure triage

```bash
bitbake <recipe> -c <task> -f -v         # force a task with verbose output
cat tmp/work/<arch>/<recipe>/<ver>/temp/log.do_compile     # the real error
cat tmp/work/.../temp/run.do_compile                       # the exact script that ran
bitbake -g <image> && cat pn-buildlist   # dependency graph
bitbake -c cleansstate <recipe>          # scoped; never wipe the whole sstate
bitbake -k <image>                       # keep going, collect all failures
```

| Failure | Cause |
|---------|-------|
| `Nothing PROVIDES '<x>'` | missing layer, or recipe name differs; `show-recipes` |
| `LIC_FILES_CHKSUM does not match` | license file changed upstream — read the diff, then update |
| `do_package_qa: file-rdeps` | missing `RDEPENDS`; the image would fail at runtime |
| `do_package_qa: buildpaths` | build path embedded in a binary; breaks reproducibility |
| `Patch does not apply` | source version moved; refresh the patch with devtool |
| `host-user-contaminated` | `do_install` preserved host uid/gid; use `install` not `cp -a` |
| Stale behaviour after an edit | sstate served a cached task; `cleansstate` that recipe |
| `ERROR: Task ... attempted to execute unexpectedly` | usually a missing dependency in the task graph |

## Licensing and SBOM

```bitbake
INHERIT += "create-spdx"                 # SBOM as a build output
INHERIT += "cve-check"                   # CVE report per image
COPY_LIC_MANIFEST = "1"
```
Review the CVE report per release with an explicit accepted-risk list. Commercial
licenses must be allowed deliberately via `LICENSE_FLAGS_ACCEPTED`, never blanket.

## Never

- Edit anything under `tmp/`. It is regenerated.
- Put product configuration in `local.conf`.
- Use `AUTOREV` or an unpinned branch in a shipping recipe.
- Silence a QA error with `INSANE_SKIP` without stating why the check does not apply.
- Delete `sstate-cache`/`DL_DIR` to debug — scope to the recipe.
