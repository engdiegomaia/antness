# BSP & Layer Hygiene

## Ownership

| Change | Correct location |
|--------|------------------|
| Application recipe | your own layer, `meta-<product>` |
| Tweak to a third-party recipe | `.bbappend` in your layer |
| Kernel config change | `.cfg` fragment in `SRC_URI`, not a whole defconfig |
| Kernel source change | patch in `SRC_URI` with `Upstream-Status:` |
| Machine definition | `conf/machine/*.conf` in your BSP layer |
| Product policy (features, image contents) | distro config or image recipe |
| Local developer experiment | `local.conf` — never committed as product config |

`local.conf` is a developer file. If a setting must exist for every build, it belongs
in a distro, machine, or image recipe.

## Layer structure

```
meta-<product>/
├── conf/layer.conf              # BBFILE_COLLECTIONS, priority, LAYERDEPENDS, LAYERSERIES_COMPAT
├── conf/machine/<board>.conf
├── conf/distro/<distro>.conf
├── recipes-core/images/<product>-image.bb
├── recipes-bsp/u-boot/u-boot-*.bbappend
├── recipes-kernel/linux/linux-*.bbappend + files/*.cfg + files/*.patch
└── recipes-<app>/<app>/<app>_1.0.bb
```

`LAYERSERIES_COMPAT` must list the Yocto releases actually tested. An unlisted release
is an untested one.

## Patches

Every patch in a layer carries:
```
Subject: [PATCH] short description

Explanation of why, and the failure it fixes.

Upstream-Status: Submitted [link] | Backport [commit] | Denied [reason] | Inappropriate [reason]
Signed-off-by: Name <email>
```
`Upstream-Status` is mandatory. A patch without it is technical debt with no owner.

## Recipe correctness

- `LICENSE` and `LIC_FILES_CHKSUM` reflect the actual source. A checksum change on a
  version bump means the license text changed — read the diff before updating it.
- `SRC_URI` points at an immutable revision (tag or SHA), never a branch name alone.
  `SRCREV = "${AUTOREV}"` is forbidden in anything that ships.
- `DEPENDS` = build time, `RDEPENDS:${PN}` = runtime. Missing runtime deps produce an
  image that builds and fails on the device.
- `FILES:${PN}*` assigns every installed file to a package. Unpackaged files fail QA
  for a reason — do not silence with `INSANE_SKIP`.
- `do_install` writes only under `${D}`. Anything touching the host filesystem is a bug.

## QA errors

`do_package_qa` errors are almost always real. Before adding `INSANE_SKIP`, state which
check fired and why it does not apply. Common ones:

| Check | Real meaning |
|-------|--------------|
| `file-rdeps` | missing `RDEPENDS`, will fail at runtime |
| `host-user-contaminated` | build leaked host uid/gid into the image |
| `buildpaths` | build directory path embedded in a binary; breaks reproducibility |
| `ldflags` | recipe ignores `LDFLAGS`; security hardening flags dropped |
| `textrel` | non-PIC code; a security and memory-usage problem |
| `already-stripped` | binary stripped before packaging; no debug symbols available |

## Reproducibility and caching

- `sstate-cache` and `DL_DIR` are shared team assets. Scope cleanups to a recipe
  (`bitbake -c cleansstate <recipe>`), never wipe them to debug.
- `SOURCE_DATE_EPOCH` and `BUILD_REPRODUCIBLE_BINARIES` set for release builds.
- Two clean builds of a tagged tree produce identical image hashes, or the difference
  is explained.
