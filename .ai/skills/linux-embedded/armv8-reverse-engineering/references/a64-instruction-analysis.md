# AArch64 Instruction Analysis

## Contents
- [Recover the calling convention](#recover-the-calling-convention)
- [Read data processing](#read-data-processing)
- [Follow memory operations](#follow-memory-operations)
- [Recover control flow](#recover-control-flow)

## Recover the calling convention

Use AAPCS64 as a hypothesis for function boundaries: x0–x7 commonly carry integer or pointer arguments and return values, x30 is the link register, and the stack pointer follows ABI alignment rules. Callee-saved registers and stack frames provide clues to function structure. Variadic calls and special ABI cases need additional care.

BL stores a return address in LR; BR transfers to a register target; BLR calls through a register. Indirect calls may dispatch through a function pointer or virtual table. Validate the target from data flow rather than assigning a name from one instruction alone.

## Read data processing

Track the destination and source registers through MOV/MVN, arithmetic, logical operations, and shifts. ADD/SUB may calculate offsets or update stack/frame state; AND/BIC/ORR/EOR often implement masks and flags. Width matters: W-register writes zero-extend into the corresponding X register. Shifted operands can encode multiplication, alignment, or bit-field logic.

Compare and test instructions set condition flags in PSTATE. Conditional branches consume those flags; a condition code must be interpreted from the immediately relevant comparison path, since intervening flag-setting instructions may replace them. CBZ/CBNZ and TBZ/TBNZ branch on a register or bit without the usual prior comparison.

## Follow memory operations

LDR and STR access memory through a base register with immediate or register offsets and optional addressing modes. Derive effective addresses from the current register values and instruction width. Loads and stores of byte, halfword, word, and doubleword values differ in width and signed extension. A sequence of offsets can reveal a structure layout, but confirm against debug types, source, or repeated accesses.

Check whether the address is stack, heap, mapped I/O, kernel, or shared memory. A syntactically valid pointer does not establish that the mapping or access permission is valid.

## Recover control flow

Build a basic-block graph from direct branches and fall-through edges. Identify loops, early returns, switch dispatch, and tail calls. Follow calls into relevant functions only as far as the analysis question requires. SVC, HVC, and SMC indicate exception-mediated transitions whose meaning depends on OS, hypervisor, firmware, and calling convention.

## Sources

- *Reverse Engineering Armv8-A Systems*, chapters 1, 3–5.
