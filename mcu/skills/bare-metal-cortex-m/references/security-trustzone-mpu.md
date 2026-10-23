# Security and Isolation on Cortex-M: PSA, MPU, Privilege Separation, TrustZone-M

Read this when threat-modelling a Cortex-M product, configuring the MPU (stack guard, kernel-only regions), running tasks unprivileged behind an SVC system-call interface, or splitting firmware into secure and non-secure worlds on an Armv8-M part.

## Contents

- [The isolation ladder](#the-isolation-ladder)
- [Security as a process: PSA](#security-as-a-process-psa)
- [Armv7-M MPU programming](#armv7-m-mpu-programming)
- [Privilege levels and SVC system calls](#privilege-levels-and-svc-system-calls)
- [TrustZone-M: secure and non-secure worlds](#trustzone-m-secure-and-non-secure-worlds)
- [Crossing the boundary: SG, BXNS, BLXNS](#crossing-the-boundary-sg-bxns-blxns)
- [Building a two-image TrustZone project](#building-a-two-image-trustzone-project)
- [TF-M and the PSA services](#tf-m-and-the-psa-services)
- [Pitfalls](#pitfalls)
- [Checklists](#checklists)

Scope notes: register addresses, option-byte names and flash/SRAM layouts in the TrustZone sections come from one STM32L5-class (Cortex-M33) example in the source; other vendors use different gate controllers and option settings, so treat those as illustrations of the *pattern*. The books do not cover the Armv8-M MPU register model, readout protection, or key-storage hardware; where this file mentions them it says so and points you to the vendor and Arm reference manuals.

## The isolation ladder

Each rung adds protection and cost. Use the lowest rung that meets the threat model, and layer them rather than substituting.

| Mechanism | What it separates | Available on |
|---|---|---|
| Privileged / unprivileged (thread) mode | Kernel from application code; blocks access to system control registers such as the NVIC and SCB | All Cortex-M except where the core omits it (check the core) |
| MPU | Memory regions by privilege and attribute (no-access, read-only, execute-never) | Optional on Armv6/7-M cores, present on most Armv8-M parts; check the MPU type register |
| TrustZone-M | Two worlds, secure and non-secure, each with its own privilege levels | Armv8-M with the Security Extension (M23, M33, M35P, M55, M85) |
| Physical tamper resistance | Attacks with physical access | Specialised parts only |

TrustZone-M does not replace thread/privilege separation or the MPU. It adds a second axis, so a TrustZone core has four execution contexts: secure privileged, secure thread, non-secure privileged, non-secure thread. Each world can run its own RTOS with the classic privilege split.

TrustZone cores also bank the stack pointers. There are four (MSP and PSP for each world) and, with the Main extension, a stack-limit register for each (MSPLIM_S, PSPLIM_S, MSPLIM_NS, PSPLIM_NS). The CPU checks the stack against its limit on every push and raises an exception on overrun. That is a cheaper and more precise stack-overflow defence than an MPU guard region, so use it when the core has it.

## Security as a process: PSA

The Platform Security Architecture is a framework, not a library. Four stages:

1. **Analyze** — identify assets and threats for the specific use case and lifecycle.
2. **Architect** — derive hardware and firmware requirements from the threats.
3. **Implement** — build on certified silicon and a reference firmware stack.
4. **Certify** — optional third-party certification.

The threat list worth walking through for every product:

| Software attacks | Hardware attacks |
|---|---|
| Spoofed device identity; cloned device identity | Tampering with removable or external storage |
| Spoofed update sender; injected firmware | Eavesdropping on physical buses |
| Tampered images; update rollback to a vulnerable version | Debug-port abuse during repair or at end of life |
| Tampered data in trusted services; persistent malware surviving resets | |
| Erased logs and history; side-channel leakage | |
| Data extraction through communication interfaces | |
| Abuse of the trusted/untrusted interface; breach of a trusted service giving unrestricted access | |

The ten PSA security goals turn those threats into requirements:

1. Devices are uniquely identifiable.
2. Devices support a security lifecycle (development, manufacture, deployment, use, end of life).
3. Devices are securely attestable (they can prove identity and integrity).
4. Only authorized software executes (secure boot and secure loading).
5. Secure updates are supported (including credentials and hardware configuration, not only application code).
6. Unauthorized rollbacks of updates are prevented.
7. Isolation is supported (software sections from each other and from the outside).
8. Interaction across isolation boundaries is supported without compromising either side.
9. Sensitive data is bound to the individual device; keep it in inherently secure storage and block access in certain states such as debugging.
10. Trusted services and crypto operations are kept to the minimum needed for the other goals.

Goal 10 drives the central design rule: **put as little as possible in the trusted part, and review that part exhaustively.**

Certification levels, useful mainly to narrow part selection: Level 1 (security principles, questionnaire based; applies to devices, system software and APIs; pre-certified silicon plus pre-certified software is the usual route), Level 2 (SoCs, resistance to scalable software attacks, independent lab penetration testing of the root of trust), Level 3 (SoCs, adds side-channel and physical attacks; choose for high-value assets in publicly accessible hardware such as door locks). The book notes that some common RTOSes and SoC families were Level 1 certified at the time; re-check current lists.

## Armv7-M MPU programming

The MPU is optional and separates memory by privilege and attribute; a violation raises a memory-management fault. It is useful even on bare metal.

### Registers

Five registers in the system control block at 0xE000ED90:

| Offset | Register | Purpose |
|---|---|---|
| 0x00 | TYPE | Whether an MPU exists and how many regions. Reads zero when absent, so check this first |
| 0x04 | CTRL | Enable the MPU; enable the default (background) map for unmapped addresses |
| 0x08 | RNR | Select which region the next base/attribute writes affect |
| 0x0C | RBAR | Region base address |
| 0x10 | RASR | Region attributes and size |

The book's Armv7-M part has up to eight programmable regions.

### RASR fields

| Bits | Meaning |
|---|---|
| 0 | Region enable |
| 5:1 | Size code (log2 of the size minus one; the book lists codes from 1 KiB to 4 GiB) |
| 18:16 | Shareable / cacheable / bufferable attributes |
| 26:24 | Access permissions, separately for privileged and unprivileged code |
| 28 | Execute-never (XN) |

Mark device and system-register regions non-cacheable so transactions stay strictly ordered.

### The configuration recipe

1. Read TYPE; bail out if the MPU is absent.
2. Write CTRL to 0 so the MPU is off while you edit regions.
3. For each region, write RNR, then RBAR, then RASR (the book writes RNR before each of the two).
4. Enable with CTRL = 1. With the background map disabled, any address not covered by a region is inaccessible, including the system region at 0xE0000000. Map the system and peripheral regions explicitly or you will fault on your next register access.

A strict example configuration from the book, in order:

| Region | Covers | Attributes |
|---|---|---|
| 0 | Flash | Read-only |
| 1 | RAM | Read-write, execute-never (no code runs from RAM) |
| 2 | 1 KiB guard at the bottom of the stack | No access, execute-never |
| 3 | System region (0xE0000000) | Read-write, execute-never, non-cacheable |

**Higher-numbered regions take priority over lower-numbered ones where they overlap.** That is how region 2 carves a hole in region 1. Design region numbers as layers, widest at the bottom.

### Guard region for stack overflow

Place the stack so a no-access block sits just below its limit. Any access into the guard raises a memory fault instead of silently corrupting the neighbouring heap. The MPU does not catch heap overruns by itself; only accesses that actually hit the guard fault. Armv8-M cores with stack-limit registers do this check in hardware for every push.

### Access-permission encoding: a pitfall

The book's two chapters define the read-only constant differently (5 in one example, 6 in another) and name the "user read-only" constant in a way that reads as if privileged code also lost write access. The AP field encodes privileged and unprivileged permissions together. From the Armv7-M encoding (not spelled out in the source, so verify in the Armv7-M Architecture Reference Manual):

| AP | Privileged | Unprivileged |
|---|---|---|
| 000 | none | none |
| 001 | read/write | none |
| 010 | read/write | read-only |
| 011 | read/write | read/write |
| 101 | read-only | none |
| 110 | read-only | read-only |

When you copy constant tables out of a book, check each against the manual and test with a deliberate violation.

### Other rules to respect

- **Enable the MemManage fault** (SHCSR memory-fault enable bit) so violations land in a dedicated handler; otherwise they escalate to HardFault.
- Reconfigure regions with the MPU disabled and put a data memory barrier before re-enabling, as the book's per-task example does.
- Regions typically need their base aligned to their size on Armv7-M and sizes are powers of two; align stack and buffer symbols in the linker script accordingly. Verify the exact rule and any sub-region options for your core.
- The books do not cover the Armv8-M MPU. It uses a base/limit model instead of power-of-two size codes; consult the Armv8-M Architecture Reference Manual before porting a configuration across.

## Privilege levels and SVC system calls

Use this when you run application code unprivileged and the kernel privileged.

**Privilege levels.** Cortex-M boots privileged. Application threads can be relegated to user level by setting the low bit of the CONTROL register. Privilege can only be changed from handler mode: the usual place is the context-switch exception, which sets CONTROL just before returning. Unprivileged code cannot touch the SCB region, so it cannot enable or disable interrupts through the NVIC; those operations belong to the kernel.

**Two stacks.** Use MSP for the kernel and interrupt handlers and PSP for threads (the Arm recommendation). Which stack is used on return to thread mode is chosen by the exception-return value:

| Return value in LR | Effect |
|---|---|
| 0xFFFFFFF9 | Return to thread mode on MSP, privileged use in the book's flat scheduler |
| 0xFFFFFFFD | Return to thread mode on PSP |

The task-switch handler must save and restore the preempted context on the right stack (MSP for the kernel task, PSP for user tasks), set LR to the matching exception-return value, and write CONTROL to 0 for the kernel or 1 for user threads before `bx lr`.

**Per-task memory protection.** Combine privilege levels with the MPU:

- Make flash globally readable and SRAM accessible to user code as policy dictates.
- Mark kernel stacks (or the RAM region holding every task stack), peripheral space and the system region kernel-only.
- On every context switch, open one small region giving the incoming task read/write access to its own stack, then re-enable the MPU. A task can then corrupt only its own stack.

**System calls through SVC.** Because user tasks cannot touch peripherals or request a context switch, give them a system-call interface:

1. A user-side wrapper executes `svc` (the book uses `svc 0` with a request number in R0). The AAPCS passes the first four arguments in R0 to R3 across the mode switch.
2. The SVCall handler runs privileged, saves the user context, switches on the request number, performs the operation, and optionally picks another task to run if the call blocks.
3. It restores the context and returns with the proper exception-return value and CONTROL setting.

Design points: the list of system-call numbers is the contract between tasks and kernel and the only route to protected resources; keep work inside the handler to a few instructions and defer anything slow to a kernel task; a kernel that implements every service in kernel space grows quickly, which is the price of physical separation.

For a production system prefer an existing RTOS that already implements this (FreeRTOS MPU port, Zephyr user mode; see the `freertos` and `zephyr-rtos` skills) over rolling your own.

## TrustZone-M: secure and non-secure worlds

### Memory attributes

With TrustZone enabled, every address (RAM, flash, peripherals) carries one of three attributes: Secure, Non-Secure, or Non-Secure Callable (NSC). NSC regions hold the entry points through which non-secure code may call into the secure world. They act like system calls with new powers.

Two units attribute memory before any other gate:

- **SAU (Security Attribution Unit)** — configurable by secure code; resets to everything-secure and disabled.
- **IDAU (Implementation-Defined Attribution Unit)** — hard-wired by the chip vendor.

Combination rule (book's table): IDAU-secure always wins; otherwise the stricter of the two applies, and NSC results only when neither says secure. In short, the SAU can make a region more secure than the IDAU says but can never open up an IDAU-secure region.

### SAU programming

Four registers: SAU_CTRL (enable, and an inversion flag that makes everything non-secure), SAU_RNR (select region), SAU_RBAR (base), SAU_RLAR (limit plus flag bits: bit 1 selects NSC, bit 0 enables the region; the low five bits are flags). Pattern:

1. Define the non-secure windows you need *inside* intervals the IDAU allows. Because the SAU starts all-secure, each region carves out a non-secure or NSC window.
2. Example set: one NSC region for veneers, one non-secure flash region for the application image, one non-secure SRAM region for its stack and data, one non-secure peripheral region.
3. Enable the SAU, then enable the SecureFault handler so attribution violations are reported cleanly.

### Further gates and peripherals

SAU/IDAU is only the first filter. The example part adds:

- A watermark-based flash gate configured through option bytes: flash between the start and end marks is secure, everything outside is non-secure; overlapping marks make the whole area non-secure.
- A block-based SRAM gate, one secure bit per block, configured with a loop over registers.
- Peripherals come in two kinds. **Securable** peripherals sit behind a gate controller and are secure by default after reset; turn the secure bit off for each one the non-secure world may use. **TrustZone-aware** peripherals expose banked secure and non-secure register sets, and may let you mark individual pins (for example GPIO) secure through a write-only secure-configuration register available only to secure code.

### Aliasing and banked registers

Enabling TrustZone duplicates parts of the address map. Secure flash may appear at a second alias, and many peripheral registers have separate secure and non-secure addresses. The example part moves GPIO from a 0x4_ address range for the non-secure view to a 0x5_ range for the secure view, and the Corstone model distinguishes secure and non-secure by address bit 28. Write separate driver base addresses (or use the CMSIS device header's secure/non-secure aliases via the `__ARM_FEATURE_CMSE` macro) for each world and never share a pointer across the boundary.

Vector table offset is banked too: VTOR_S and VTOR_NS.

## Crossing the boundary: SG, BXNS, BLXNS

| Direction | Mechanism |
|---|---|
| Secure code starts the non-secure world | `BLXNS` branches and switches to non-secure state in one step |
| Non-secure code calls a secure function | Call a veneer, which jumps to an `SG` (Secure Gateway) stub in an NSC region; the stub then enters the real secure function |
| Secure function returns to non-secure caller | `BXNS lr` |
| Secure code calls a non-secure function | Function-pointer type with the `cmse_nonsecure_call` attribute, which the compiler turns into `BLXNS` |

Rules the hardware enforces:

- Non-secure code can only enter secure code at an address whose first instruction is `SG` in an NSC region. Jumping into the middle of a secure function faults.
- `SG`, `BLXNS` and `BXNS` are only usable from secure state.
- The compiler scrubs registers before `BLXNS` so secure values do not leak into non-secure state. Do not hand-write the transition without doing the same.

### Staging the non-secure image from the secure bootloader

Sequence from the book's example (secure code runs first after reset):

1. Configure the SAU, flash and SRAM gates and peripheral security.
2. Set `VTOR_NS` to the non-secure image's vector table.
3. Read the initial stack pointer and reset-handler address from the first two words of the non-secure image.
4. Set the non-secure stack limit (`MSPLIM_NS`) from the stack pointer minus a size you choose, then write `MSP_NS`.
5. Clear the least-significant bit of the entry address before `BLXNS`. The reset handler address in the vector table has the Thumb bit set; a non-secure branch target must not.
6. Execute `BLXNS`.

Lock down what the application must not touch (for example mark selected pins secure) *before* the jump.

## Building a two-image TrustZone project

A TrustZone project is two sub-projects built and linked separately and loaded into separate memory areas: a secure project holding boot code, configuration, crypto and update logic, and a non-secure project holding the rest. Put the minimum in the secure image and review it hardest.

Toolchain support (CMSE, the Cortex-M Security Extension):

| Item | Purpose |
|---|---|
| `-mcmse` compile option (with the right `-mcpu`) | Enables CMSE: `__ARM_FEATURE_CMSE` macro, SG stub generation |
| `__attribute__((cmse_nonsecure_entry))` | Marks a secure function callable from the non-secure world; the compiler emits the SG stub and a secure-side body |
| `__attribute__((cmse_nonsecure_call))` | Function-pointer type for calling non-secure code from secure code |
| Linker `--cmse-implib` and `--out-implib=<file>` (GNU ld) | Produces an import object containing veneers that the non-secure image links against |
| Secure linker script | Defines secure flash, secure RAM, and a separate NSC region for the SG stubs; place the `.gnu.sgstubs` section in it |
| Non-secure linker script | Only the non-secure flash and RAM windows; secure and NSC regions are unreachable |

Non-secure application builds need no special flags; they only link the veneer object. The veneer symbols are what satisfy calls to secure services. Relink the non-secure image against the freshly generated import object whenever the secure image changes (my inference: the stub addresses are fixed by the secure build).

Entry-point and enable settings are vendor-specific. In the STM32L5 example, TrustZone is enabled with an option byte (TZEN), the secure boot address is another option byte with a granularity of 128 bytes, and enabling TrustZone is effectively one-way without a more involved procedure; changing some option bytes can brick a device. Read the vendor reference manual first.

## TF-M and the PSA services

Trusted Firmware-M is the open-source reference implementation of the PSA firmware specifications for Armv8-M. It relies on the secure/non-secure split and has three parts:

| Part | Role |
|---|---|
| Secure boot | A two-stage bootloader (MCUboot) authenticates signed images, then hands over to the secure image, which initializes the SAU, MPU and secure services before launching the non-secure image. Signing keys are embedded in the bootloader; secure and non-secure images can use different keys |
| Secure core | Secure initialization and secure API dispatch; the Secure Partition Manager creates the partition database and isolation boundaries. A partition is one thread of execution and the smallest unit of isolation |
| Secure services | Crypto (PSA Crypto API), secure storage, initial attestation |

Storage options: **Internal Trusted Storage** holds small, critical data such as keys and image hashes, offered by the platform root of trust and reachable from the secure side only. **Protected Storage** holds larger data in external flash with data-at-rest protection (optionally device-bound encryption, integrity and rollback protection) and is reachable from the non-secure side too.

Attestation produces a token of device-specific items that an external verifier uses to check identity and integrity.

Client API shape: `psa_connect(sid, version)` to open a handle to a root-of-trust service, `psa_call(...)` to use it, `psa_close(handle)` to release it, all routed through a non-secure interface dispatcher that locks around the call and enters the secure veneer.

Prefer TF-M plus a PSA-certified part over a hand-built secure world when security is a requirement. The book's build and test commands target an older Arm Virtual Hardware image and Python setup; use the current TF-M user guide for build steps.

## Pitfalls

| Pitfall | Why it bites |
|---|---|
| MPU enabled without mapping the system region or background map | The next system-register or peripheral access faults, often as a HardFault |
| MemManage fault not enabled | MPU violations escalate to HardFault and lose their fault address information |
| Copying MPU permission constants between examples | The AP encoding packs privileged and unprivileged access together; mislabelled constants silently open or close the wrong access |
| Region numbers treated as unordered | Overlap resolution depends on region number; a narrow exception must have a higher number than the region it carves from |
| Guard region assumed to catch heap overflow | It only catches accesses that actually touch the guard |
| SAU left disabled or regions placed outside IDAU-allowed intervals | Non-secure code faults on its first instruction fetch |
| Peripherals still secure-by-default after reset | The non-secure application cannot use its UART or I2C until secure code clears the secure bit |
| Entry address passed to `BLXNS` with the Thumb bit set | Non-secure branch targets must have bit 0 clear |
| Secure-world code or data in the non-secure window | Everything in the NS window is reachable by a compromised application |
| Secure image grows with convenience features | Violates goal 10; every extra line is attack surface |
| `printf`-style helpers exposed as NSC entry points | Easy to demonstrate, but a general-purpose secure entry point from untrusted code is a liability; validate every pointer and length crossing the boundary |
| Enabling TrustZone or changing option bytes casually | Effectively one-way on many parts and may brick the board |
| Treating a virtual platform as proof of security | Models omit timing and physical effects; test side channels and fault injection on silicon where the threat model requires it |

Validate every argument that crosses the boundary (pointers must point into non-secure memory, lengths must be bounded). The source books show the mechanics but not input validation; make it a project rule.

## Checklists

Threat model and architecture:

- [ ] Use case and lifecycle written down; attack list from the PSA categories walked through
- [ ] Each threat mapped to one or more of the ten goals, with an owner mechanism
- [ ] Trusted code minimised and listed explicitly
- [ ] Silicon and software chosen with the needed certification level
- [ ] Debug-port policy decided for production (goal 9)

MPU and privilege separation:

- [ ] MPU presence checked; background map decision made deliberately
- [ ] Regions ordered widest-first, narrow exceptions later; XN set on data and device regions
- [ ] System and peripheral regions mapped; device regions non-cacheable
- [ ] MemManage fault handler enabled and tested with a deliberate violation
- [ ] Stack guard or stack-limit register active for every stack
- [ ] User tasks run on PSP with CONTROL set; kernel on MSP
- [ ] SVC interface minimal, validated, handlers short

TrustZone-M:

- [ ] Secure and non-secure projects separate, with separate linker scripts
- [ ] SAU regions inside IDAU-allowed intervals; SecureFault handler enabled
- [ ] Flash and SRAM gates, peripheral security bits and pin security configured before the jump
- [ ] `VTOR_NS`, `MSP_NS`, `MSPLIM_NS` set; entry address LSB cleared
- [ ] NSC region contains only intended SG stubs; every entry point validates its inputs
- [ ] Non-secure image linked against the current import object
- [ ] Option-byte and enable procedure read from the vendor manual before touching hardware
- [ ] Secure boot verifies signatures; anti-rollback and update path covered

Sources: Insider's Guide to Arm Cortex-M Development, chapters 1 and 7 (security goals, PSA, TF-M, secure/non-secure example); Embedded Systems Architecture 2nd edition, chapter 5 (memory protection unit), chapter 10 (system resource separation, privilege levels, system calls) and chapter 11 (Trusted Execution Environment, TrustZone-M).
