# Choosing Cortex-M Hardware, Software Stack and Tools

Read this when picking a core or part for a new product, choosing a dev board, deciding bare metal versus RTOS, or setting up compilers, IDEs and build environments for a team.

## Contents

- [Start from the use case, then rank requirements](#start-from-the-use-case-then-rank-requirements)
- [Core families and what each is for](#core-families-and-what-each-is-for)
- [The six ranking axes](#the-six-ranking-axes)
- [From core to part and board](#from-core-to-part-and-board)
- [Bare metal, RTOS, middleware](#bare-metal-rtos-middleware)
- [CMSIS pieces worth knowing](#cmsis-pieces-worth-knowing)
- [Judging an SDK](#judging-an-sdk)
- [Where to run code before the hardware exists](#where-to-run-code-before-the-hardware-exists)
- [Compilers and IDEs](#compilers-and-ides)
- [Development environments: local, virtual, cloud](#development-environments-local-virtual-cloud)
- [Checklists](#checklists)

Dating note: the source is a 2022 book. Benchmark figures, tool names and vendor offerings change; treat numbers here as order-of-magnitude guidance and re-check current Arm and vendor datasheets before committing a design.

## Start from the use case, then rank requirements

Core selection goes faster when you write down the workload first and only then look at parts. The useful questions:

- What does the device sense or control, and how often (sample rate, deadline)?
- Does it run on a battery, harvest energy, or sit on mains?
- Does it hold private data or accept remote updates (security)?
- Is there a regulated safety level to meet (safety)?
- Is unit cost the dominant constraint (area, memory, features)?

Rank the answers, pick the two or three that actually drive the design, and let those choose the core. Everything else is a tiebreaker.

Typical mappings (illustrative, not exhaustive):

| Product shape | Why it points to... |
|---|---|
| Battery wearable with sensitive data | A TrustZone-capable Armv8-M core (M33 class): security, optional DSP/FPU, moderate power |
| Always-on industrial sensor, tiny budget | M0+ class: lowest power and area, enough compute for simple control |
| Sensor node doing filtering and edge DSP | M4/M7/M33 with DSP extension and FPU; M7 for the heaviest scalar DSP |
| Always-on keyword spotting or vision at the edge | M55/M85 class with Helium vector extension, optionally paired with an NPU (Ethos-U) |
| Tamper-exposed device (door lock, public hardware) | Core with physical tamper resistance (M35P class) |

## Core families and what each is for

| Core | Position | Notes that matter in practice |
|---|---|---|
| M0 / M0+ | Lowest power and silicon area, cheapest | Armv6-M; simple pipeline. M0+ is normally preferred over M0 |
| M23 | M0+-like power/area plus TrustZone | Armv8-M Baseline; security features cost some power when included |
| M3 | Balanced, no FPU | Armv7-M; moderate area and power |
| M4 | M3 plus DSP extension and optional FPU | Common for motor control, sensor fusion, wearables |
| M7 | High scalar performance, superscalar pipeline, optional caches and TCM | Strong for demanding DSP and safety-oriented designs; the book singles it out for ECC, MBIST and dual-core lockstep options |
| M33 | TrustZone, optional DSP/FPU/MPU, custom instruction interface | Good all-rounder when security matters |
| M55 | First core with the Helium (MVE) vector extension | Large ML/DSP uplift; pairs with Ethos-U NPU |
| M85 | Highest scalar and vector performance of the family | Newest Helium implementation, TrustZone |
| M35P | M33-derived with physical tamper protection | For devices attackers can touch |

Two traps:

1. **Optional features are decided at chip-design time.** FPU, DSP extension, MPU, TrustZone, caches and TCM may or may not be implemented in the specific microcontroller. Read the part's datasheet, not the core's marketing page.
2. **Armv8-M cores (M23, M33, M35P, M55, M85) carry the security architecture; Armv6-M/Armv7-M cores do not.** Choose on architecture generation, not only on speed.

## The six ranking axes

The book frames selection as six axes. For each, find the cores that rank well, then intersect the axes you care about.

| Axis | What to look at | Caveats |
|---|---|---|
| Power | Static (leakage) vs dynamic power; dynamic is quoted per MHz so cores at different clocks compare fairly; process node shifts both | The book quotes roughly 4 µW/MHz for M0+ at 40 nm. M33/M3/M4 land at about three times that. Lower nodes lower power for the same core |
| DSP / scalar performance | CoreMark and Dhrystone per MHz | Book-reported CoreMark/MHz: M85 ≈ 6.3, M7 ≈ 5.3, M55 ≈ 4.4, M33 ≈ 4.1, M4 ≈ 3.5, M3 ≈ 3.4. Benchmarks are imperfect; run your own workload when you can |
| ML performance | Matrix-multiply throughput; vector (Helium) vs scalar | ML is mostly matrix math, so vector hardware matters. M55 is roughly an order of magnitude ahead of M7; M4 is stretched even on small ML tasks (vibration, keyword spotting) |
| Security | Armv8-M with TrustZone, PSA certification at board level | TrustZone is optional per part: verify it is enabled on the chip or board |
| Safety | Exception handling, MPU, software test libraries, dual-core lockstep, ECC, memory BIST | Book view: M7 has the richest set; M55/M33/M23 reach SIL 3 / ASIL D class; M4/M3/M0+ reach SIL 2 / ASIL B class with test libraries. Confirm against the vendor's safety manual and certificates, not this table |
| Cost | Silicon area (smaller core is cheaper), volume, and how many optional features the part includes | Pick the part with only the features you need |

Safety terms: diagnostic requirements cover random hardware faults (detected with fault-detection hardware); systematic requirements cover process and verification. IEC 61508 uses SIL 1–4, automotive uses ASIL A–D.

## From core to part and board

Once the core is chosen, the part and board add three more decisions:

**Memory.** Most Cortex-M parts mix flash (non-volatile, holds code) and SRAM (faster, volatile). External DRAM appears when SRAM would cost too much. Compute caches, TCM and flash wait states determine real speed; moving hot code and data from flash to SRAM is a standard tuning step. Most Cortex-M systems run out of memory before they run out of cycles, so size memory with margin. The Cortex-M memory map places flash and SRAM at standard addresses, which simplifies startup code across parts.

**Power supply and environment.** Battery versus mains, rail voltages, current limits. Even mains-powered IoT products increasingly care about energy because fleet-wide consumption adds up. Prefer boards with a power-measurement header so you can measure real current during development.

**Peripherals.** Parts within a core class differ mainly in peripherals. Group needs into three buckets: sensing the environment, communication/storage, digital and analog I/O. Typical patterns the book notes:

- M0/M0+ boards: GPIO, analog inputs, USB, expansion connectors, a few basic sensors.
- M3/M4/M7 boards: wireless (BLE, NFC, RF, Wi-Fi), richer sensors, PWM, ADC/DAC.
- M23/M33 boards: TrustZone and Trusted Firmware-M support, LTE/NB-IoT options, audio codecs, microSD.

Scan vendor selection tables and product summaries; what a vendor highlights tells you the intended market.

Secondary factors that decide real projects:

| Factor | Why it matters |
|---|---|
| Software ecosystem | RTOS support, SDK quality, connectivity stacks, cloud certification of the board |
| Community | Searching for a representative problem tells you whether answers exist; some boards die out |
| Board size | A prototype near the real form factor accelerates product work |
| Temperature grade | Consumer is roughly 0–70/85 °C; industrial roughly −40–85 °C; automotive has its own grades; wider range costs more |
| Availability | Supply shortages affect how many boards you can get for a team or a test lab |

Boards are cheap relative to engineering time. If the first board turns out to have the wrong CPU, memory or peripherals, buying another is often the fastest way to learn.

## Bare metal, RTOS, middleware

Decide the foundation first, then the libraries.

| Choose | When | Why |
|---|---|---|
| Bare metal | Few tasks, simple scheduling (polling plus interrupts), tight code and cost budget | No scheduler or abstraction overhead; smallest footprint |
| RTOS | Many concurrent activities (sensing, processing, communications), middleware stacks, cloud connectivity, OTA updates | Scheduler gives deterministic multitasking; middleware integrates more easily |

Middleware (USB, TCP/IP, filesystems, GUI, TLS, cloud connectors) can be bolted onto bare metal but is generally easier with an RTOS. TLS stacks such as Mbed TLS ship in many vendor SDKs; use a tested library, never hand-rolled crypto. For the RTOS options and how to choose between them see the sibling skills: `freertos` for FreeRTOS and `zephyr-rtos` for Zephyr.

Use-case examples the book walks through:

- Medical wearable: bare metal plus CMSIS, with TF-M for secure storage and CMSIS middleware for Bluetooth.
- Industrial flow sensor: bare metal with almost nothing added, because small memory drives cost.
- City-wide IoT sensor with edge DSP and OTA: an RTOS plus CMSIS-DSP.
- Vibration anomaly detection: bare metal, CMSIS-DSP for feature extraction, an embedded ML runtime such as TensorFlow Lite for Microcontrollers.
- Voice and vision: RTOS required; choose by the connectivity and cloud features needed.

## CMSIS pieces worth knowing

CMSIS is an open collection of APIs, libraries and utilities that keeps code portable across Cortex-M vendors.

| Component | What it gives you |
|---|---|
| CMSIS-Core | Startup code, system configuration, device header files, NVIC and SysTick access. Detail: `references/register-access-and-cmsis.md` and `references/linker-and-startup.md` |
| CMSIS-DSP | 60+ optimized signal-processing routines: basic and fast math, complex math, filters (FIR, biquad), matrix, PID/motor control, FFT and transforms, statistics, interpolation, SVM and Bayes classifiers, distance functions, quaternions |
| CMSIS-NN | Optimized neural-network kernels (convolution, activations, fully connected, pooling, softmax); integrates with TensorFlow Lite for Microcontrollers |
| CMSIS packs | Device support and software components delivered separately from the toolchain |

Prefer CMSIS-DSP over hand-written filters and FFTs: it is tuned for the DSP and vector extensions.

## Judging an SDK

An SDK bundles drivers, middleware, examples and sometimes tools. Compare candidates on:

- **Examples:** useful for learning, but they demonstrate a concept; testing, error handling and optimization are still your job.
- **Reuse:** which Cortex-M parts, which compilers, which build system it supports, and how hard it would be to migrate off it.
- **Middleware and language bindings:** C/assembly first; Python and Rust bindings exist for education and prototyping.
- **Cloud and security libraries:** vendor-tested TLS and cloud connectors save integration time.
- **IDE and debugger coupling:** does it force a particular IDE or debug probe?
- **Host OS support:** most tools target Windows, Linux and macOS; check what your team and CI use.
- **Automatable install:** avoid tools needing a graphical installer or click-through license if you want containers and CI.
- **Long-term support:** devices live for years and need security fixes; match SDK support life to product life.

Vendor SDK families named in the book: Raspberry Pi Pico SDK (CMake based, runs best on Linux), NXP MCUXpresso, ST STM32Cube (with an initialization-code generator). Naming and bundling change between releases, so check the current vendor download pages.

## Where to run code before the hardware exists

| Platform | Strength | Limit |
|---|---|---|
| Development board | Real speed, real peripherals, easy debug connection | Board farms for automated tests are costly to maintain; remote I/O control is hard |
| Virtual platform (QEMU, Renode, Arm Fast Models, Imperas/OVP) | No hardware needed; fast (tens to thousands of MIPS); good for early firmware and CI | Programmer's-view models only: no cycle timing, so no real performance analysis; instruction counts give only directional answers; unmodelled features (custom instructions) cannot run |
| Host (native PC) build of portable logic | Fastest edit-test loop for pure logic | Different CPU and libraries from the target; must isolate hardware access |
| Cloud virtual or remote physical boards | Pay-per-use, scriptable, wide board choice | Emerging; modelling differences remain |
| Logic simulation, emulation, FPGA prototyping | Used by teams designing custom silicon | Not relevant if you are targeting an existing microcontroller |

Eight metrics for comparing platforms: ease of use, speed, accuracy, synchronization of multiple time domains, abstraction limits, visibility and debug access, time to create, and automated-test support. Multi-core virtual models usually run cores in turns rather than truly in parallel, which can change timing-dependent behaviour; do not trust race-condition results from a virtual platform.

Use several platforms at once: virtual platform for early bring-up and CI, boards for timing and power.

## Compilers and IDEs

A toolchain means compiler, assembler, linker and disassembler/image utilities.

| Toolchain | Notes |
|---|---|
| Arm Compiler for Embedded (LLVM based; armclang, armlink, fromelf) | Commercial; first with support for new Arm cores; MicroLib C library for small size; link-time optimization; a safety-qualified variant exists |
| GNU Arm toolchain (arm-none-eabi-gcc, as, ld, objdump, gdb) | Free, large community, command-line only; the vendor now brands it "Arm GNU Toolchain" — verify current naming and download location |
| IAR | Commercial compiler and debugger inside its own IDE |

Choose on target-core support, licence cost, code size and speed on your code, safety qualification need, and vendor support. For hands-on GNU toolchain use, see `references/toolchain-and-build.md`.

IDEs bundle editor, build and debug; most choices come down to team preference or to the compiler bundled with them: Keil MDK (µVision plus Arm Compiler, CMSIS packs, Windows centric), Arm Development Studio (Eclipse based, includes virtual platforms), IAR Embedded Workbench, Arduino IDE (sketch format limits it to Arduino boards), and VS Code (an editor extended with plugins for build and debug). Cloud IDEs are emerging.

## Development environments: local, virtual, cloud

Treat interactive development (a person edits, builds, runs, debugs) and automated development (CI runs builds and tests on a schedule or on push) as different needs.

| Need | Interactive | Automated |
|---|---|---|
| Simplicity | Critical: used daily by everyone | Helpful: a few people maintain it |
| Replicability | Helpful | Critical: every developer must reproduce a failing run |
| Longevity | Depends on the team | Critical: setup cost amortizes across projects |

| Environment | Good for | Weak at |
|---|---|---|
| Local OS install | Simplest interactive work | Replicability: tool version drift between laptops causes lost hours; unsuitable for team CI |
| VM (VirtualBox) | GUI-heavy tools on a mismatched host OS | Large images, slow start |
| Container (Docker) | Reproducible, code-defined (Dockerfile), small and fast; ideal for CI and many parallel regressions | Less suited to GUI tools |
| Cloud | Scalable, replicable, reusable across projects | Learning curve; hard to reach physical boards, so pair it with virtual platforms |

Practical stance: let developers use whatever local setup they like for editing, but build and test in a pinned container, so "works on my machine" differences vanish. Windows-only tools (such as some IDEs) are the usual reason to run a local Windows environment or a VM. Windows line endings and path conventions deserve care when files move between hosts.

## Development workflow and test placement

Keep the edit-build-debug loop short and reproducible: compile with warnings visible, inspect link
maps and binary sections, retain debug symbols for development, and make target interaction/scripted
flashing repeatable. A compiler produces object files; the linker resolves symbols and places sections
according to the memory map. When a failure appears only after linking, inspect the linker map and
section layout before treating it as a source-level defect.

Place checks at the cheapest level that can exercise the behavior. Unit-test portable logic on the
host, validate compiler and linker behavior with a target build, use an emulator for supported boot
and functional paths, and reserve physical boards for peripheral behavior, electrical timing, power,
and integration that the model cannot represent. Emulator results are evidence only for modeled
features; they do not establish real-time performance or validate unmodeled hardware.

Sources for this addition: *Embedded Systems Architecture*, 2nd ed., ch 1 (embedded-system constraints,
memory and peripheral interfaces) and ch 2 (compiler/linker workflow, debugging, functional validation,
hardware tools and emulation).

## Checklists

Choosing a core and part:

- [ ] Workload and deadlines written down; top three requirements ranked
- [ ] Core family chosen from the ranking axes, not from familiarity alone
- [ ] Optional features (FPU, DSP, MPU, TrustZone, caches, TCM) confirmed present on the specific part
- [ ] Memory sized with margin; hot paths can live in SRAM or TCM if needed
- [ ] Peripheral list matched against the part's real selection table
- [ ] Temperature grade, supply, and availability checked
- [ ] Safety and security certificates verified at part and board level, not assumed from the core

Choosing the software stack and tools:

- [ ] Bare metal versus RTOS decided against task count, middleware needs and footprint
- [ ] SDK checked for supported cores, compilers, build system, installability and support lifetime
- [ ] Toolchain and IDE chosen; build is runnable from the command line
- [ ] Builds run in a pinned container so CI and developers get the same result
- [ ] A virtual platform is available for early bring-up and automated tests
- [ ] Performance and power validated on real hardware, not on a virtual model

Sources: *Insider's Guide to Arm Cortex-M Development*, chapters 1–3 (selecting hardware, software and tools);
*Embedded Systems Architecture*, 2nd ed., chapters 1–2 (system constraints and development workflow).
