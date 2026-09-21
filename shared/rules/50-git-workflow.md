# Git Workflow — Embedded

## Commit format

```
<type>(<scope>): <description>

Body: what changed, why, and the hardware context.
Validated-on: <board + silicon rev + image hash> | not validated on hardware
```

Types: `feat fix refactor perf docs test chore ci bsp dts driver boot security`
Scopes: board (`verdin-imx8mp`), driver (`spi`), layer (`meta-app`), subsystem (`boot`).

## Embedded-specific practice

- **Binary blobs**: never commit build artifacts, `.elf`, `.wic`, `.bin`, `sstate`,
  `tmp/`, `build/`. Firmware release binaries go to a release/artifact store with a
  checksum recorded in the repo.
- **Submodules / manifests**: a manifest revision change is a separate commit with its
  own message explaining what moved and why.
- **Generated files**: CubeMX output, `.config`/`defconfig`, device tree blobs — commit
  the *source* (`.ioc`, `_defconfig`, `.dts`), not the generated output, unless the
  project has decided otherwise. State the project's decision in its `AGENTS.md`.
- **Vendor patches**: kernel/U-Boot patches live in the layer with a proper header
  (`Subject`, `Signed-off-by`, `Upstream-Status:`). `Upstream-Status` is mandatory in
  Yocto layers.

## Branch and release

- Release branches carry the pinned manifest. A release tag pins every input revision.
- Never rebase a branch a hardware lab is flashing from.

## Attribution

Follow the repository/host attribution policy already configured; do not add extra
trailers beyond what is configured.
