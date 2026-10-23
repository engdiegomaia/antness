---
name: embedded-linux-applications
description: Design, package, cross-build, deploy, and debug applications running on embedded Linux. Use for Python packaging and virtual environments, Qt Widgets/GUI applications, sensor-to-web services, Rust on Linux, process/thread and IPC choices, Docker/container images, CI/CD pipelines, and networked IoT services.
track: linux-embedded
---

# Embedded Linux applications

Guidance for the application layer on embedded Linux. Keep hardware drivers and kernel configuration in their respective skills; this skill covers the user-space programs, their runtime dependencies, and delivery pipeline.

## Workflow

1. Define the hardware and runtime contract: device interfaces, target ABI/libc, available memory/storage, display or network needs, and offline behavior.
2. Select a runtime that fits deployment and maintenance needs. Keep the device-facing interface narrow and isolate presentation, acquisition, and transport logic.
3. Build against the product's target SDK/sysroot. Record compiler, SDK, dependency, and target versions; never silently use host headers or libraries.
4. Package the application and its runtime dependencies as one reproducible unit: system packages, a controlled Python environment, or a container where the target supports it.
5. Automate build, static checks, tests, image creation, and artifact publication. Deploy immutable, versioned outputs and define rollback and observability before field release.
6. Test on representative hardware and under degraded conditions: sensor absent, network unavailable, slow storage, restart, and power loss.

## Choose the relevant reference

| Need | Reference |
|---|---|
| Python dependencies, venvs, reproducible app packaging | [python-packaging-and-deployment.md](references/python-packaging-and-deployment.md) |
| Process, thread, IPC and scheduler design | [processes-threads-and-ipc.md](references/processes-threads-and-ipc.md) |
| Sensor service, IIO sampling and web/API split | [python-sensor-service.md](references/python-sensor-service.md) |
| Qt GUI, asynchronous I/O and event handling | [qt-hardware-applications.md](references/qt-hardware-applications.md) |
| Rust user space or kernel-facing experiments | [rust-on-embedded-linux.md](references/rust-on-embedded-linux.md) |
| Container build and CI/CD pipeline | [containers-and-cicd.md](references/containers-and-cicd.md) |
| Networked devices, protocols and resilience | [distributed-iot-architecture.md](references/distributed-iot-architecture.md) |

## Review checklist

- [ ] Application architecture has explicit interfaces between hardware access, business logic, UI, and network transport.
- [ ] Target architecture, libc, ABI, SDK and runtime versions agree.
- [ ] Dependencies are pinned or otherwise reproducibly resolved; package installation is not improvised on production devices.
- [ ] Blocking hardware or network operations cannot freeze a user interface or starve time-sensitive work.
- [ ] IPC and concurrency are justified by isolation, reliability, or performance measurements.
- [ ] Device/network failures are bounded, visible, and recoverable; stale data is distinguishable from current data.
- [ ] CI builds from a clean checkout and publishes identifiable artifacts with provenance.
- [ ] Update, rollback, logs, health checks, and offline operation are defined.
- [ ] GUI examples are treated as engineering examples, not evidence of safety or regulatory suitability.

## Sources

Original synthesis from *Mastering Embedded Linux Development*, 4th ed., chapters 15–17; *Embedded Linux Essentials Handbook*, chapters 9–11 and 14–15; and *Embedded Systems Architecture*, 2nd ed., chapter 9. Per-reference source notes identify the chapter coverage. Check current tool and API documentation before adopting version-specific commands.
