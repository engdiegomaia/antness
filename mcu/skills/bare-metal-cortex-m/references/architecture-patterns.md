# Firmware architecture, project process and CI

How to organize a Cortex-M firmware project, choose between a super-loop and an RTOS, and validate changes automatically.

## Contents
- Source organization and layering
- Super-loop vs RTOS
- Project lifecycle: prototype, refactor, API
- Security design points
- Why CI, and what makes it hard on embedded
- Test tiers and where to run them
- Three CI flow levels
- CI review checklist

## Source organization and layering

- Keep application code thin. Put behaviour in small, self-contained modules that each own one concern and expose a narrow header.
- Stack the code in layers: application, middleware, HAL, then vendor drivers / CMSIS. Only the HAL touches vendor register or driver APIs, so porting means rewriting one layer.
- Choosing middleware (RTOS, file system, network stack, crypto): check licence terms, flash/RAM cost, maintenance status, and whether it already ships ported for your core.
- Put configuration (clock rates, pin maps, feature flags) in one place under revision control, not scattered as magic numbers.
- Revision control, an issue tracker and code review are baseline hygiene, not extras.

## Super-loop vs RTOS

| | Super-loop (event-driven) | RTOS |
|---|---|---|
| Structure | `main` loops over flags set by ISRs | Preemptive tasks with priorities |
| Latency | Worst case = longest handler in the loop | Bounded by priority and kernel overhead |
| Cost | No kernel RAM/flash | Stacks per task, kernel footprint |
| Risk | One slow handler delays everything | Races, priority inversion, stack sizing |

Rule of thumb: stay with a super-loop while handlers are short and deadlines are loose. Move to an RTOS when independent activities have mixed deadlines or when a middleware stack expects one. Keep ISRs short in both models (see interrupts-and-dma.md).

## Project lifecycle: prototype, refactor, API

1. Prototype first. Use synthetic data and mocks for hardware you do not have yet, to settle algorithm and data flow early.
2. Refactor once the shape is known, with tests in place so behaviour stays fixed.
3. Treat each module header as a contract. Document it (Doxygen or equivalent): units, ownership, blocking behaviour, error codes, thread/ISR safety.
4. Plan the product's life: updates, support window, and how fixes reach deployed devices.

## Security design points

- Plan vulnerability management and a secure update path from the start, because connected devices outlive their first release.
- Prefer open, reviewed cryptographic standards over home-grown schemes.
- Use hardware crypto accelerators and a hardware true random number generator where the part has them.
- If untrusted or third-party code must run, isolate it (MPU, privilege split, TrustZone-M). See security-trustzone-mpu.md.

## Why CI, and what makes it hard on embedded

Desktop-style flow: each developer tests on a personal board with ad-hoc scripts, merges about daily, and problems surface late (merge conflicts, hard-to-trace regressions, duplicated work, inconsistent metrics, near-release chaos, bugs reaching production). CI flow: small commits roughly hourly, an automatic build and standard regression suite per commit, passing code promoted to checkpoint branches and merged, so the shared branch always works and metrics are recorded per commit.

Embedded difficulty: you develop on a PC and deploy on different hardware, so you need cross-compilers and, mainly, test hardware. Cloud scaling that works for web apps does not apply directly.

- Board farm: scales, but costs a lot to maintain (worn flash, boards needing manual reset, space, cooling, organization) and must keep old hardware for long-supported products.
- Virtual platforms (for example Arm Virtual Hardware): scale in the cloud, but model only what they implement. Core behaviour matches; your exact peripherals (radios, sensors, displays) usually do not.

## Test tiers and where to run them

| Tier | Purpose | Typical count | Run on |
|---|---|---|---|
| Unit | One function/module in isolation | hundreds to thousands | Host or virtual platform |
| Integration | Interaction between components | dozens to hundreds | Virtual or hardware, depending on what is covered |
| System (black-box) | Whole product against requirements | a dozen or fewer | Physical hardware, ideally the end device |

Best-performing setups: a big virtual farm running automated unit tests, plus a small board "garden" running integration and system tests.

## Three CI flow levels

Trade-off throughout: simpler setups are less repeatable and shorter-lived.

1. Simple local script: a batch/shell script that rebuilds and flashes via the IDE's headless command line, writing output to files. Better than nothing, but it is manual testing sped up. It checks no results unless you add parsing.
2. Central CI server (for example Jenkins) triggered by a repository push webhook: builds and runs tests on every commit. Targets can be a board farm or host-native builds of portable code. Do not leave a trial tunnel or disabled TLS verification in a production setup.
3. Virtual farm: the same pipeline, with jobs launching virtual platforms in the cloud.

## CI review checklist

- [ ] Every commit triggers a clean build with warnings visible.
- [ ] Portable logic builds and unit-tests on the host.
- [ ] Hardware-dependent code has mocks or a virtual-platform test.
- [ ] A small set of hardware tests covers integration and system behaviour.
- [ ] Results and metrics (including coverage) are stored per commit.
- [ ] CI credentials and tokens are not committed or embedded in URLs in shared config.

Sources: Embedded Systems Architecture, 2nd ed., ch. 3 (configuration management, source organization, lifecycle, security); Insider's Guide to Arm Cortex-M Development, ch. 9 (continuous integration).
