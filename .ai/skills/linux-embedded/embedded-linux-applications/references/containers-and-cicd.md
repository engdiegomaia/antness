# Containers and CI/CD for embedded Linux applications

## Decide whether a container fits

A container can package an application and user-space dependencies into a versioned artifact, but it shares the host kernel. Confirm support for the target architecture, container runtime, storage capacity, startup supervision, device access, networking, and update strategy. Do not treat a container image as a complete OS image or as a substitute for ABI compatibility.

For Yocto-based products, integrating a container engine and runtime into the image is a BSP decision. Verify layer compatibility with the chosen Yocto release and account for image size, security updates, and service startup. On constrained devices, ordinary packages or a read-only application partition may be simpler.

## Pipeline shape

1. Pin source revisions, build tools, SDK/container base, and dependencies.
2. Build from a clean checkout; run formatting/static analysis and unit tests.
3. Build target artifacts for each supported architecture and configuration.
4. Exercise integration tests in an emulator or hardware runner when available.
5. Create a versioned image/package and attach build metadata, source revision, and dependency inventory.
6. Publish to a controlled registry or artifact store only after the required checks pass.
7. Promote the same immutable artifact through deployment stages; avoid rebuilding from mutable inputs for production.
8. Test update interruption, reboot, rollback, and offline recovery on representative devices.

Keep pipeline definitions and infrastructure configuration in version control. Secrets belong in the CI secret manager, not build files or image layers. A successful build is not proof that an update is safe or recoverable.

## Review

- [ ] Clean builds are repeatable and outputs are traceable to source and toolchain.
- [ ] Registry credentials and signing keys are scoped and kept out of artifacts.
- [ ] Image provenance and vulnerability/update ownership are defined.
- [ ] Device-specific tests cover startup, restart, hardware access, and resource limits.
- [ ] Rollback and recovery work when power or network fails mid-update.

Sources: *Mastering Embedded Linux Development*, 4th ed., ch 16 (DevOps, CI/CD, Docker images, Yocto integration and container updates); *Embedded Linux Essentials Handbook*, ch 15 (CI/CD pipeline and containerized builds).
