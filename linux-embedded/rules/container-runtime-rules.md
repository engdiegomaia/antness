# Containers on Embedded Linux

> Applies to Torizon OS and any Docker/podman-based embedded deployment.

## Image discipline

- Base images are pinned by digest, not by tag. `debian:bookworm` moves; the digest
  does not.
- Multi-stage builds: build tooling never ships in the runtime image.
- Match the target architecture explicitly (`--platform linux/arm64`) and verify —
  an accidental amd64 image fails at runtime with an unhelpful exec-format error.
- Image size is a deployment cost: every megabyte crosses the field network on update.

## Runtime configuration

```yaml
services:
  app:
    image: registry/app@sha256:...       # digest-pinned
    restart: unless-stopped              # or on-failure with a backoff
    read_only: true                      # rootfs immutable
    tmpfs: [/tmp]
    cap_drop: [ALL]
    cap_add: [<only what is needed>]     # never blanket privileged
    devices:
      - /dev/spidev0.0:/dev/spidev0.0    # explicit device passthrough
    mem_limit: 256m                      # a leak must not take down the system
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }   # unbounded logs fill eMMC
```

Rules:
- `privileged: true` is a last resort and must be justified in a comment naming the
  exact capability or device that required it.
- Never bind-mount the whole `/dev` or `/sys`. Pass the specific device node.
- Always set a log rotation policy. Unbounded container logs are the most common cause
  of a full eMMC in the field.
- Always set memory limits. A leaking container must not OOM the whole device.

## eMMC/flash wear

- Containers write to the overlay by default. Anything high-frequency (logs, databases,
  telemetry buffers) goes to a tmpfs or a deliberately chosen, wear-aware location.
- Persistent data lives in a named volume on a partition chosen for the purpose, not
  inside the image layer.
- State the expected write volume per day for any new persistent writer.

## Updates

- Container updates and OS updates are separate lifecycles. State which one a change
  belongs to.
- A container update must be atomic from the device's perspective: pull, then switch.
  A half-pulled image on a device that lost power must not leave a broken service.
- Always keep the previous image on the device until the new one is proven healthy.

## Secrets

- No secrets in the image, in `docker-compose.yml`, or in environment variables
  committed to the repo. Use a device-provisioned secret store or mounted credentials
  with restricted permissions.
- Registry credentials on the device are device-scoped and revocable.
