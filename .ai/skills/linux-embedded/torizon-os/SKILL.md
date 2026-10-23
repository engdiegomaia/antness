---
name: torizon-os
description: Torizon OS development — containerized applications on Toradex modules, TorizonCore Builder, device tree overlays, Torizon Cloud updates, and the VS Code/Torizon IDE workflow.
track: linux-embedded
---

# Torizon OS

## Model

Torizon OS is an OSTree-based, immutable Linux built with Yocto, where **applications
run in Docker containers**. The OS is updated atomically via Torizon Cloud (Uptane/Aktualizr);
containers are updated as a separate lifecycle via `docker-compose`.

Consequences that drive every decision:
- The rootfs is read-only. Application state lives in volumes or `/var`.
- You do not build a custom OS image to add an application — you ship a container.
- You customize the OS (device tree, overlays, kernel modules, splash) with
  **TorizonCore Builder**, not by rebuilding Yocto, unless you genuinely need a custom BSP.

## When to use which tool

| Need | Tool |
|------|------|
| Ship an application | Docker container + `docker-compose.yml` |
| Enable a peripheral (SPI, I2C, CAN, display) | Device tree overlay via TorizonCore Builder |
| Add an out-of-tree kernel module | TorizonCore Builder `build` with a module recipe |
| Change the kernel config / add a BSP patch | Yocto with `meta-toradex-*` (full BSP build) |
| Update a fleet | Torizon Cloud (OS) + container registry (apps) |

## Device tree overlays

```bash
# Get the overlays for the running version
git clone -b toradex_<kernel-version> https://github.com/toradex/device-trees

# Apply with TorizonCore Builder
torizoncore-builder dt checkout
torizoncore-builder dto apply device-trees/overlays/verdin-imx8mp_spidev_overlay.dts
torizoncore-builder dto status          # what is currently applied
torizoncore-builder dto deploy --remote-host <ip> --remote-username torizon ...
```

`tcbuild.yaml` makes this reproducible:
```yaml
input:
  easy-installer:
    toradex-feed:
      version: "6.x.y"
      machine: verdin-imx8mp
      distro: torizon
      variant: torizon-core-docker
customization:
  device-tree:
    include-dirs: ["device-trees/include"]
    custom: device-trees/dts-arm64/verdin-imx8mp-dev.dts
    overlays:
      add: ["device-trees/overlays/verdin-imx8mp_spidev_overlay.dts"]
  filesystem: ["changes/"]
output:
  easy-installer:
    local: product-image
    bundle: { compose-file: docker-compose.yml }
```
Build it: `torizoncore-builder build --file tcbuild.yaml`

Overlay rules: the overlay must match the **kernel version's** device tree; an overlay
from a different BSP release may apply and then misbehave. Verify with
`torizoncore-builder dto status` and, on the target, `ls /proc/device-tree/`.

## Containers

```yaml
services:
  app:
    image: registry/app@sha256:...
    restart: unless-stopped
    devices:
      - /dev/spidev0.0:/dev/spidev0.0
      - /dev/gpiochip3:/dev/gpiochip3
    volumes:
      - app-data:/var/lib/app
    logging:
      driver: journald                 # or json-file with rotation limits
    mem_limit: 256m
volumes:
  app-data:
```

- Toradex provides base images (`torizon/debian`, `torizon/wayland-base`,
  `torizon/*-imx8`) with the correct userspace for the SoC's GPU/VPU/NPU. Use them
  rather than a plain Debian when you need hardware acceleration — the vendor
  userspace libraries must match the kernel.
- Access hardware by passing the specific device node. `privileged: true` is a last
  resort and must be justified.
- Set log rotation and memory limits. See `rules/container-runtime-rules.md`.

## Updating

```
OS:         Torizon Cloud, Uptane-signed, atomic OSTree deploy, automatic rollback
Containers: compose bundle pushed as a Torizon Cloud package, or a registry pull
```

Rules:
- Test the update on the **oldest supported field version**, not just the latest.
- Always roll out to a canary group first with a defined success metric and abort
  criteria. A fleet-wide push is never autonomous — see `.ai/rules/shared/10-hardware-safety.md`.
- Verify rollback works before the release: install, force a failure, confirm the
  device reverts and comes back online.

## Development loop

- Torizon IDE Extension (VS Code) gives container build + deploy + debug on the target.
- Faster manual loop: build for arm64 (`docker buildx build --platform linux/arm64`),
  push to a registry or `docker save | ssh ... docker load`, then `docker compose up`
  on the device.
- On-device debugging: gdbserver in the container, `docker exec` for inspection,
  `journalctl -f` on the host for system-level issues.

## Diagnostics on the target

```bash
sudo tdx-info                     # module, version, hardware — always start here
ostree admin status               # deployed and rollback OSTree commits
journalctl -b -p err              # errors this boot
docker compose ps && docker compose logs -f
cat /proc/device-tree/model
dmesg | grep -iE "fail|error|timeout"
```

`tdx-info` output is the first thing to include in any Toradex support question — it
identifies the module, carrier, BSP version and kernel precisely.

## Common failure modes

| Symptom | Cause |
|---------|-------|
| Device node missing in the container | overlay not applied, or device not passed through |
| Overlay applies but peripheral dead | pin conflict with another enabled node; check `dto status` and the pinmux |
| GPU/VPU not accelerating | base image userspace does not match the SoC or kernel version |
| Container restarts forever | missing device/volume, or OOM from a missing `mem_limit` context |
| eMMC full after weeks | unbounded container logs or overlay writes |
| Update installs then reverts | health check failed — read the aktualizr/OSTree logs, this is rollback working |
