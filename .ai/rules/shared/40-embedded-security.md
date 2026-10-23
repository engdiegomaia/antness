# Embedded Security Rules

## Secrets and keys

- No keys, certificates, private key material, Wi-Fi credentials, API tokens, or device
  serials in the repository — including in `local.conf`, `prj.conf`, `sdkconfig`,
  `Kconfig` defaults, device tree, or test fixtures.
- Signing keys live in an HSM or a secrets manager. A key file in `keys/` with a
  `.gitignore` is not key management.
- Per-device identity is provisioned, never baked into a shared image.
- If a key is found committed: stop, report, treat it as compromised, plan rotation
  and re-provisioning. Deleting the file does not fix history.

## Boot and update

- Secure boot: verify the chain is complete (ROM -> SPL -> bootloader -> kernel -> rootfs
  dm-verity / app signature). A gap anywhere voids the chain.
- Never close/lock a device (burn fuses) outside an explicit, confirmed provisioning task.
- Updates: signed, versioned, anti-rollback enforced, and atomic with a verified rollback
  (A/B or RAUC/swupdate/Torizon Cloud). An update path without a tested rollback is
  a field-bricking path.

## Attack surface

- Disable in production: serial console autoboot interrupt, U-Boot shell access, JTAG/SWD,
  `CONFIG_*_SHELL`, debug UART command handlers, unauthenticated network services.
- Every externally reachable parser (BLE, CAN, UART protocol, USB, MQTT payload, OTA
  manifest) is untrusted input: bounds-check, length-check, reject unknown, fuzz it.
- Default-deny on network: no listening service enabled unless required and authenticated.

## Memory safety in C

- No unbounded `strcpy`/`sprintf`/`strcat`; use bounded variants with explicit sizes.
- Every buffer index derived from external data is validated against the buffer length.
- Integer overflow on length/size arithmetic is checked before allocation or copy.
- Prefer compile-time sized buffers; `-Wstack-usage`, `-fstack-protector-strong`,
  `-D_FORTIFY_SOURCE=2` where the toolchain supports it.

## Compliance context

When the product is in scope for the EU Cyber Resilience Act, IEC 62443-4-1/4-2,
ISO 21434, or a medical/industrial standard, say so explicitly and keep an SBOM
(`create-spdx` in Yocto, CycloneDX for Zephyr/ESP-IDF) as a build output, plus a
documented vulnerability-handling path (`cve-check`, Torizon/vendor advisories).
