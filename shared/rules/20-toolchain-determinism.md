# Toolchain & Build Determinism

## Pinning

| Ecosystem | Pinned in | Never change as a side effect |
|-----------|-----------|-------------------------------|
| Zephyr | `west.yml` manifest revisions, SDK version | manifest `revision:` fields |
| ESP-IDF | IDF tag/commit, `idf_component.yml` | IDF version |
| MCUXpresso | SDK version + board package | SDK tarball version |
| STM32 | CubeMX pack version, HAL version | `.ioc` MCU firmware package |
| NuttX | nuttx + apps repo tags | both must move together |
| Yocto | `bblayers.conf` + kas/repo manifest SHAs | layer branches or SHAs |
| Buildroot | Buildroot tag, `*_defconfig` | Buildroot release |
| AOSP | manifest revision | manifest |

A revision bump is a standalone change with its own build + boot validation.

## Environment

- Prefer containerized builds (`crops/poky`, `espressif/idf`, Torizon build containers,
  `zephyrprojectrtos/ci`) so the host distro is not part of the build inputs.
- Record the exact build command in the project's `AGENTS.md`. One command, clean tree.
- Never rely on a mutable `~/.local`, a hand-installed cross compiler, or an unpinned
  `pip install`. If a tool is required, it is declared.

## Cache and state hygiene

- Build failures that "fix themselves" after a clean are unexplained bugs, not fixes.
  Record what changed before clearing state.
- Yocto: `sstate-cache` and `DL_DIR` are shared assets. Never delete them to debug;
  use `bitbake -c cleansstate <recipe>` scoped to the recipe.
- Zephyr/CMake: prefer `west build -p auto`; a full pristine build is the fallback,
  not the default.

## Reproducibility checks

- `SOURCE_DATE_EPOCH` set for Yocto/Buildroot reproducible builds.
- No timestamps, hostnames, build paths, or `__DATE__`/`__TIME__` baked into binaries.
- Two clean builds of the same tree produce identical artifact hashes, or the difference
  is explained.
