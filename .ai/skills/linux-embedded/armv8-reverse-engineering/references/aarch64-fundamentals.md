# AArch64 fundamentals for binary analysis

Registers, the AArch64 procedure call standard, exception levels and the exception model — the minimum architectural state you must be able to read before any AArch64 disassembly or crash dump makes sense.

## Contents
- [Why this matters first](#why-this-matters-first)
- [General-purpose registers](#general-purpose-registers)
- [Special registers](#special-registers)
- [PSTATE and SPSR_ELx](#pstate-and-spsr_elx)
- [System registers](#system-registers)
- [AAPCS: the calling convention](#aapcs-the-calling-convention)
- [Exception levels](#exception-levels)
- [Exceptions and the vector table](#exceptions-and-the-vector-table)
- [Reading kernel binaries: EL and sp_el0 signatures](#reading-kernel-binaries-el-and-sp_el0-signatures)
- [Pitfalls](#pitfalls)

## Why this matters first

The Arm *architecture* (Armv8-A), not the particular Cortex core, is what determines what you can read in a binary. Instruction encodings, register names, AAPCS and the exception model are identical across Cortex-A53/A57/A72/A73 and later A-profile cores; only MMU/cache/clock *implementation* details differ. So when you pick up an unknown AArch64 binary, the first question is "which architecture profile", not "which SoC":

| Profile | Target | What you will be analysing |
|---|---|---|
| Armv8-A | Application processors — Linux, Android, Windows, macOS, servers, automotive | Full ELF user-space binaries, kernels, hypervisors; the subject of this skill |
| Armv8-R | Real-time, safety (automotive, medical, robotics) | 32-bit code, restricted memory architecture |
| Armv8-M | Microcontrollers (IoT, wearables, industrial) | Bare-metal/RTOS images, not Linux ELF |

Picking the wrong profile means picking the wrong disassembler mode and wasting hours on nonsense output.

## General-purpose registers

- `X0`–`X30` are the 64-bit general-purpose registers. `W0`–`W30` are the *same* registers viewed as their low 32 bits — writing `Wn` updates bits [31:0] of `Xn`. Seeing `W` forms in disassembly is a strong hint the source type was `int`/`unsigned int` rather than `long`/pointer.
- There is no `X31`: the encoding means either the zero register (`XZR`/`WZR`, reads as 0, discards writes) or the stack pointer `SP` depending on the instruction. Do not read `sp` in a disassembly listing as "a general-purpose register".
- Treat general-purpose registers as the function's local variables. Every instruction's inputs and outputs live there; the values you inspect in GDB or a debugger window *are* the computation.

Registers that carry meaning rather than just data:

| Register | Role | Why an analyst cares |
|---|---|---|
| `X0`–`X7` | Argument registers (AAPCS) | Tells you the arguments of a call without source |
| `X0` | Return value | Tells you what a function produced |
| `X8` | Linux syscall number on AArch64 | Identifies which syscall an `SVC` is performing |
| `X29` | Frame pointer (by convention) | Anchor for walking the call stack |
| `X30` | Link register — the return address | Tells you the *caller*, and therefore the call graph |

When you stop somewhere unknown, read `X30` first: it names the symbol that called you.

## Special registers

| Register | Meaning | Analysis use |
|---|---|---|
| `SP_EL0`…`SP_EL3` | Per-EL stack pointers | The stack you dump depends on which EL you are in |
| `ELR_ELx` | Exception link register: address to resume at after the exception | In a crash dump this is *where the fault happened* |
| `PC` | Address of the instruction being executed | Where you are now |

Armv8-A offers two stack models: a separate `SP_ELx` per exception level, or one shared SP across levels. Linux and Xen use the per-EL model, so assume separate stacks unless you have evidence otherwise — it changes which `SP` a handler is running on and therefore which memory region holds the frames you want.

`PC` is deliberately *not* writable by arithmetic instructions such as `ADD`/`SUB`; that is an anti-tampering property of the architecture. It changes only by:

1. Normal sequential advance after an instruction retires.
2. A branch (`B`, `BL`, `BR`, `BLR`) setting it to the branch target.
3. An exception, which sets it to the computed exception vector address.
4. `RET`, which moves `X30` into `PC`.

That list is the whole set of ways control flow can legitimately move. When a backtrace shows `PC` somewhere that none of those four explain, suspect a corrupted return address on the stack (see `dynamic-analysis.md`).

## PSTATE and SPSR_ELx

`PSTATE` is not a register — the architecture describes it as an abstraction of processor state, reachable only indirectly through system registers. There is no instruction that reads "PSTATE" as a whole. (It plays the role `CPSR` played in Armv7-A and has a similar bit layout.)

Fields you will actually use:

| Field | Meaning |
|---|---|
| `N` | Last flag-setting operation produced a negative result |
| `Z` | …produced zero |
| `C` | …produced a carry |
| `V` | …produced a signed overflow |
| `D` bit[9] | Debug exception mask |
| `A` bit[8] | Asynchronous (SError) mask |
| `I` bit[7] | IRQ mask |
| `F` bit[6] | FIQ mask |
| `M[3:0]` | Current exception level encoding — readable only via `CurrentEL` |

Mask semantics are the opposite of what the word "flag" suggests: **1 = masked = that exception is disabled**, 0 = enabled. `PSTATE.<D,A,I,F> = 1111` disables everything. If you find a long stretch of kernel code running with `I`=1, you are in a critical section and any latency bug you are chasing lives there.

`SPSR_ELx` is the snapshot of `PSTATE` taken *before* the exception, with the same bit layout. An exception handler reads it to learn what state it interrupted — and so do you: `SPSR_ELx` tells you which EL and which interrupt-mask state the faulting code was in.

The N/Z/C/V flags are the link between a comparison and the conditional branch that follows it; see `instructions-data-memory-flow.md` for how to read that pair.

## System registers

System registers configure the machine (MMU, caches, interrupts, trap handling) rather than hold data. Two rules make them readable:

1. **The suffix names the *lowest* EL that may access the register, not the only one.** `TTBR0_EL1` is reachable from EL1, EL2 *and* EL3. Access from EL0 raises a synchronous exception as a privilege violation. So `MRS X0, ESR_EL3` in a listing proves the code runs at EL3; `MRS X0, ESR_EL2` proves EL2 or above. This is the cheapest way to establish which privilege level an unknown blob is written for.
2. **They are reached only with `MRS`/`MSR`, never `LDR`/`STR`.**

```asm
    mrs  x0, ttbr1_el1      // read system register into GP register
    msr  ttbr1_el1, x0      // write GP register into system register
```

Commonly encountered system registers:

| Register | Purpose |
|---|---|
| `SCTLR_ELx` | System control — MMU enable, caches, alignment checking |
| `ACTLR_ELx` | Implementation-defined auxiliary controls |
| `TTBR0_ELx` | Base address of the first-level translation table |
| `VBAR_ELx` | Exception vector base address |
| `SCR_EL3` | Secure configuration and EL3 trap control |
| `HCR_EL2` | Virtualization and EL2 trap control |
| `MIDR_ELx` | Main ID — processor part and revision |
| `MPIDR_EL1` | Processor affinity (which core) |
| `CTR_EL0` | Cache type/geometry |

Primary system registers such as `VBAR_EL1` are normally programmed once in start-up code. Writes that take effect during runtime generally need a barrier immediately afterwards so the new configuration is synchronised across cores — code that writes a system register and then immediately depends on it *without* a barrier is a genuine bug worth flagging in a review.

## AAPCS: the calling convention

AAPCS (historically APCS/TPCS/ATPCS in older Arm documents) is the part of the ABI that says how functions hand control and data to each other. It is what lets you reconstruct a call graph and argument list from stripped code.

| Rule | Consequence when reading disassembly |
|---|---|
| Arguments go in `X0`–`X7` (left to right) | `mov w0, #2 ; mov w1, #3 ; bl f` means `f(2, 3)` |
| Return value in `X0` | `bl f` followed by a store of `w0` is `x = f(...)` |
| `BL <target>` branches *and* writes the return address into `X30`, in one hardware step | `X30` identifies the caller |
| `RET` moves `X30` into `PC` | End of function |

Prologue/epilogue pattern to recognise — a non-leaf function must spill `X30` because its own `BL` will overwrite it:

```asm
foo:
    stp   x29, x30, [sp, #-32]!   // push FP+LR, pre-decrement SP (stack grows down)
    mov   x29, sp                 // establish frame pointer
    ...
    ldp   x29, x30, [sp], #32     // pop FP+LR, post-increment SP
    ret                           // PC <- X30
```

Reading rules that follow:

- A function that **never** spills `X30` and ends in `RET` is a leaf function — it calls nothing.
- The pre-index `!` on the `STP` is what actually allocates the frame; the immediate is the frame size.
- The register paired with `X30` in the prologue (`X19`, `X29`, …) is a callee-saved register the function is about to clobber. Which registers appear there tells you roughly how much live state the function carries.
- Stack memory must already be reserved before any call can happen. Setting up `SP` for each EL is the core job of start-up code; a system that faults in the first `STP` of the first function has a start-up/SP bug, not a C bug.

## Exception levels

"Exception level" is a misleading name: EL is a **privilege level**, ELn ≡ PLn. The mapping used by essentially all modern systems:

| EL | Typical software | Can do |
|---|---|---|
| EL0 | User applications | No interrupt/MMU/cache config, no kernel addresses, no system registers |
| EL1 | Linux or RTOS kernel | Configure interrupts, MMU, caches, peripherals |
| EL2 | Hypervisor | Manage guest OSes at EL1; can reach EL1/EL0 code and data |
| EL3 | Secure monitor / first bootloader | Everything |

EL0 and EL1 are architecturally required; EL2 and EL3 are optional in an implementation. Bringing up EL2 or EL3 means at minimum configuring its `SP_ELx`, its `VBAR_ELx`, and `HCR_EL2`/`SCR_EL3` respectively — a half-initialised EL2 with no vector base is a classic bring-up failure.

Boot normally starts at EL3 (secure boot, secure memory regions, system register setup), drops to EL2, then to EL1.

**Moving between levels** — the instruction tells you the boundary being crossed:

| Instruction | From → to | Meaning to an analyst |
|---|---|---|
| `SVC` | EL0 → EL1 | A syscall. Syscall number is in `X8` on Linux/AArch64 |
| `HVC` | EL1 → EL2 | Guest OS calling the hypervisor; requires `HCR_EL2` configured |
| `SMC` | → EL3 | Secure monitor call (security extensions) |
| `ERET` | back down | Return from exception using `ELR_ELx`/`SPSR_ELx` |

Note that a privilege *increase* never happens by simply branching — it only happens through an exception. Code that appears to gain privilege any other way is a finding.

**Determining the current EL** — `CurrentEL` is the only way to read `PSTATE.M[3:0]`:

```asm
    mrs  x0, CurrentEL        // bits [3:2] encode the EL
```

Encoding: EL0 = `0b0000`, EL1 = `0b0100`, EL2 = `0b1000`, EL3 = `0b1100` — i.e. the EL number shifted left by 2. Real start-up code uses this defensively: the Xen hypervisor's AArch64 entry path reads `CurrentEL`, compares it against the EL2 encodings, and refuses to boot otherwise, precisely because a hypervisor that found itself at EL3 would be running with more privilege than its threat model assumes. Expect to find the same check in any serious firmware, and treat its *absence* as a hardening gap.

## Exceptions and the vector table

When the core takes an exception it suspends execution, branches `PC` to an exception vector address, and possibly changes EL.

| Class | Exception | Cause |
|---|---|---|
| Synchronous | Synchronous | Illegal instruction; invalid address access; `SVC`/`HVC`/`SMC`; misaligned stack access; unknown reason |
| Asynchronous | IRQ | Non-secure interrupt |
| Asynchronous | FIQ | Secure interrupt (in Armv8-A FIQ means *secure*, not merely "fast" as in Armv7-A) |
| Asynchronous | SError | External memory abort |

**The vector table.** `VBAR_ELx` holds the vector base address, set in start-up code. The vector address is `VBAR_ELx + offset`, and the offset is picked from a 4×4 table — four source situations × four exception types:

| Exception taken from | Sync | IRQ/vIRQ | FIQ/vFIQ | SError/vSError |
|---|---|---|---|---|
| Current EL with `SP_EL0` | 0x000 | 0x080 | 0x100 | 0x180 |
| Current EL with `SP_ELx`, x>0 | 0x200 | 0x280 | 0x300 | 0x380 |
| Lower EL, that level using AArch64 | 0x400 | 0x480 | 0x500 | 0x580 |
| Lower EL, that level using AArch32 | 0x600 | 0x680 | 0x700 | 0x780 |

There is a separate table per target EL (EL1, EL2, EL3). Read it backwards to localise a fault: in a Linux system (kernel at EL1), an entry at `VBAR_EL1 + 0x200` is a kernel-mode synchronous fault; `+0x280` is an interrupt taken while in the kernel; `+0x400` is a fault *from user space* (64-bit), e.g. a syscall or a segfault; `+0x600` is the same from a 32-bit process. Because Linux and Xen use per-EL stacks, the `SP_EL0`-shared row (0x000–0x180) is effectively unused on those systems — finding a handler installed there is unusual and worth investigating.

**What the hardware does when an exception is taken** (steps 2–4 are hardware; 1 and 5 are the cause and the software response):

1. Cause arises: memory abort (instruction or data), software interrupt (`SVC`/`HVC`), or external event (IRQ/FIQ/SError).
2. Registers are updated: `PSTATE` → `SPSR_ELx`; return address → `ELR_ELx`; faulting address → `FAR_ELx`; exception class encoding → `ESR_ELx[31:26]`.
3. The EL switches if required (EL0 → EL1; at EL1 it stays at EL1 unless `HCR_EL2` routes it to EL2 for virtualization).
4. `PC` branches to `VBAR_ELx + offset`.
5. The handler at that address runs.

This step list *is* the crash-dump reading procedure. From a dump you get, in order: which EL the fault was taken to (from the handler/vector), what state preceded it (`SPSR_ELx`), where to resume (`ELR_ELx`), what address was bad (`FAR_ELx`), and why (`ESR_ELx` exception class).

**How handlers differ by type:**

- *Synchronous* — the handler first reads `ESR_ELx` to distinguish a memory abort from a syscall. A memory abort at EL0 kills the offending user process; the same abort at EL1 is a kernel panic, because there is no recovery path. A syscall path instead reads the syscall number from `X8`, looks it up in the syscall table, and calls that handler. Linux implements 400+ of them.
- *IRQ/FIQ* — dispatch to the interrupt service routine for the asserted interrupt. The interrupt is the interface between a peripheral and the core.
- *SError* — effectively fatal; handlers typically reset the system, because an external memory abort means the memory system itself reported a failure. The precise cause is implementation-defined, i.e. varies per chipset vendor, so consult the SoC documentation rather than the Arm ARM alone.

Exception handlers are the highest-value entry points for analysis: every interesting transition in the system funnels through them.

## Reading kernel binaries: EL and sp_el0 signatures

Kernel and user-space AArch64 code share arithmetic and call conventions entirely. What distinguishes a kernel binary in disassembly:

- **`MSR`/`MRS` on EL1+ system registers.** `msr ttbr0_el1, x0` cannot appear in a user binary — EL0 has no privilege to execute it. Seeing it proves kernel (or firmware) code.
- **An exception-handling entry block.** In an AArch64 Linux image you will find a `vectors` symbol whose entries manipulate `SP` and then branch to per-case handlers with names of the form `el1t_64_sync`, `el1h_64_irq`, `el0t_64_sync`, and so on. The naming encodes the vector-table row and column directly, so the symbol name alone tells you which of the 16 slots you are in.
- **Frequent `mrs xN, sp_el0` right after the prologue.** This is the `current` macro. Because the kernel runs at EL1 on `SP_EL1`, `SP_EL0` is free, and arm64 Linux repurposes it to hold the address of the running task's `task_struct` — a register read is the fastest possible way to answer "who am I". `cpu_switch_to` writes the next task's `task_struct` pointer into `sp_el0` (`msr sp_el0, x1`) as part of every context switch.

  Practical consequence: **in a kernel dump, `sp_el0` *is* the current `task_struct` pointer.** That is your anchor for identifying the process, its stack, and its thread state. (Treat this as arm64-Linux-specific and verify against your kernel version; other kernels at EL1 may use `sp_el0` differently or not at all.)

```c
/* arch/arm64 'current' reduces to a single MRS */
static __always_inline struct task_struct *get_current(void)
{
    unsigned long sp_el0;
    asm ("mrs %0, sp_el0" : "=r" (sp_el0));
    return (struct task_struct *)sp_el0;
}
```

- **System-register suffix as a privilege fingerprint.** `ESR_EL1` → code runs at EL1+; `ESR_EL2` → EL2+ (hypervisor exception entry, which reads `ESR_EL2` to classify the trap); `ESR_EL3` → EL3 only, and executing it at EL2 faults. Use the highest suffix anywhere in the blob as a lower bound on the EL the image was built for.

## Pitfalls

- **Assuming the `_ELx` suffix means "only ELx".** It means *at least* ELx. Higher levels can access it too; lower levels fault.
- **Treating `PSTATE` as a readable register.** There is no instruction that reads it directly; go through `CurrentEL`, `DAIF`, `NZCV` and friends, or read `SPSR_ELx` for the pre-exception snapshot.
- **Reading mask bits backwards.** `I`=1 means IRQs are *disabled*.
- **Assuming FIQ means "fast interrupt" on Armv8-A.** It is the secure-world interrupt, normally owned by a secure OS. An Armv7-A mental model will mislead you here.
- **Forgetting `W` vs `X` width.** A comparison done on `W` registers only looks at 32 bits; a sign- or zero-extension bug in the original C often shows up precisely as a mismatched `W`/`X` pair in the disassembly.
- **Expecting the frame pointer.** `X29` is a convention, and optimised builds (`-fomit-frame-pointer`, high `-O`) may not maintain it. Do not assume a frame-pointer chain is walkable; corroborate with `X30` and the stack contents.
- **Confusing `SP_EL0` in a *kernel* dump with a user stack pointer.** On arm64 Linux it holds `task_struct`, not a stack address.
- **Writing a system register without a barrier** and then relying on the new configuration — the effect may not yet be visible to all cores.
- **Assuming the EL0-shared-stack vector rows are live.** On Linux/Xen they are not; a handler there is anomalous.
- Specific `ESR_ELx` class encodings and the full vector semantics for EL2/EL3 are outside what is summarised here — verify against the Arm Architecture Reference Manual for A-profile (DDI 0487) for your architecture revision.

Sources: Reverse Engineering Armv8-A Systems, ch 1 (Arm architecture fundamentals: registers, AAPCS, exception levels, exceptions), ch 10 (key features of kernel binaries: system register access, exception handling, sp_el0 and the current macro, identifying exception levels).
