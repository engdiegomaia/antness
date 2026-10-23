# GNU Toolchain and the Firmware Build

Read this when setting up or debugging a Cortex-M build: choosing compiler flags, shrinking an image, interrogating the ELF/map to find out where the bytes went, writing a hand-rolled Makefile, flashing and debugging over SWD, or wiring firmware into CI.

## Contents

- [The five stages, and why they matter separately](#the-five-stages-and-why-they-matter-separately)
- [Tool inventory](#tool-inventory)
- [The flag set that actually matters](#the-flag-set-that-actually-matters)
- [Linking: specs, libraries, and the errors they produce](#linking-specs-libraries-and-the-errors-they-produce)
- [Producing .bin and .hex](#producing-bin-and-hex)
- [Interrogating the image: answering real questions](#interrogating-the-image-answering-real-questions)
- [Reading the .map file](#reading-the-map-file)
- [A hand-written firmware Makefile](#a-hand-written-firmware-makefile)
- [Flashing and debugging](#flashing-and-debugging)
- [Off-target testing and emulation](#off-target-testing-and-emulation)
- [CI for firmware](#ci-for-firmware)
- [Checklists](#checklists)

Vendor note: STM32/OpenOCD names appear as running examples. The stages, flags, ELF tooling and Make mechanics are identical for NXP, Nordic, TI, Renesas, Raspberry Pi RP2040 and anything else Cortex-M.

## The five stages, and why they matter separately

`arm-none-eabi-gcc main.c -o fw.elf` hides five distinct steps. Knowing them is how you localize a failure.

| Stage | Tool | In → out | What breaks here |
|---|---|---|---|
| Preprocess | `cpp` (via `gcc -E`) | `.c` + `.h` → `.i` | wrong include path, a `#define` you thought was set, conditional compilation silently excluding your code |
| Compile | `cc1` (via `gcc -S`) | `.i` → `.s` | type errors, warnings, optimization surprises |
| Assemble | `as` (via `gcc -c`) | `.s` → `.o` | hand-written assembly, wrong instruction set for the core |
| Link | `ld` (via `gcc`) | `.o` + libs → relocatable symbols resolved | undefined references, duplicate symbols, ABI mismatch |
| Locate | `ld` + linker script | → final ELF with absolute addresses | `region overflowed`, sections placed in the wrong memory, LMA/VMA confusion |

The last two are one `ld` invocation but two conceptual jobs: *resolving symbols* and *assigning addresses*. Most "it builds but doesn't boot" bugs are locate-stage bugs, not compile-stage bugs — see the linker-script reference.

Debug the stages individually when stuck:

```sh
arm-none-eabi-gcc $(CFLAGS) -E  src/main.c -o /tmp/main.i   # what did the preprocessor actually produce?
arm-none-eabi-gcc $(CFLAGS) -S  src/main.c -o /tmp/main.s   # what did the optimizer actually emit?
arm-none-eabi-gcc $(CFLAGS) -c  src/main.c -o /tmp/main.o
```

Dumping `-E` output is the fastest way to settle "is `USE_FEATURE_X` defined in this translation unit?" — far faster than reasoning about nested headers.

## Tool inventory

Everything is prefixed `arm-none-eabi-`: **arm** (architecture), **none** (no host OS — freestanding), **eabi** (Embedded ABI). A toolchain for Linux userspace on ARM would be `arm-linux-gnueabihf-`; using that one by mistake links a C library that expects syscalls you do not have.

| Tool | Use it for |
|---|---|
| `gcc` | driver for all five stages; also the correct way to invoke the linker (it supplies libgcc, crt files and the specs) |
| `ld` | the linker itself — call it directly only if you know why; you lose libgcc |
| `as` | assembler, for `.s` startup files |
| `objcopy` | ELF → raw `.bin` / Intel `.hex`, section stripping, padding |
| `objdump` | disassembly, section headers, relocations, symbol table |
| `readelf` | authoritative ELF structure: sections, program headers (LMA vs VMA), ARM build attributes |
| `nm` | symbol list, sorted by size — the fastest "what is big" tool |
| `size` | per-section totals → flash and RAM footprint |
| `gdb` | debugging over a remote stub |
| `ar` / `ranlib` | building static `.a` libraries |
| `strings`, `addr2line`, `c++filt` | forensics; `addr2line -e fw.elf 0x08001234` turns a hard-fault PC into file:line |

`addr2line` is underrated: capture the stacked PC/LR in your HardFault handler, print them over UART, and resolve them offline against the exact ELF that is on the device.

## The flag set that actually matters

### Architecture flags — must be identical for every object and for the link

```
-mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16
```

- `-mcpu` selects the core. Prefer it over `-march`; it implies the architecture and enables core-specific tuning. Modern GCC accepts feature suffixes: `-mcpu=cortex-m4+nofp`, `-mcpu=cortex-m33+nodsp`.
- `-mthumb` is mandatory. Cortex-M executes **only** Thumb. (Older documentation sometimes writes `-thumb`; that is a typo — the flag is `-mthumb`. `-marm` has no valid use on Cortex-M.)
- `-mfloat-abi`: `soft` (no FPU, software float, float args in integer registers), `softfp` (FPU instructions, but float args still in integer registers — ABI-compatible with `soft` libraries), `hard` (FPU instructions and float args in FPU registers — fastest, but every object and every library must agree).
- `-mfpu` names the FPU: `fpv4-sp-d16` (M4F, single precision), `fpv5-sp-d16` (M33, M7 single-precision-only part), `fpv5-d16` (M7 with double precision). GCC 10+ accepts `-mfpu=auto` to derive it from `-mcpu`; on newer toolchains you can often drop `-mfpu` entirely. Verify against your toolchain version.
- If you enable `-mfloat-abi=hard`, you must also enable the FPU in software at boot (set CPACR CP10/CP11 full access) before the first floating-point instruction, or you take a UsageFault. The compiler will happily emit FPU instructions in the startup path.
- `-mlittle-endian` is the default; stating it is harmless and documents intent.

### Code generation and size

```
-ffunction-sections -fdata-sections      # compile: one section per function/object
-Wl,--gc-sections                        # link: drop sections nothing references
```

These three work only as a set. Without the compile-side split, each object file is one big `.text` and the garbage collector can discard nothing. Expect 10–40% flash savings on a project that links a vendor HAL. Pair with `-Wl,--print-gc-sections` once, to see what was dropped — occasionally it eats something you needed (an interrupt vector in a custom section, a bootloader header). Protect those with `KEEP()` in the linker script or `__attribute__((used))` on the symbol; `used` alone does not survive `--gc-sections` for a section the script does not `KEEP`, so prefer `KEEP()` for anything the script places.

### Optimization

| Level | When |
|---|---|
| `-O0` | almost never; bloated, and some timing loops behave differently |
| `-Og` | **default for development** — optimizes but preserves debuggability; prefer it over `-O0` |
| `-O2` | default for release |
| `-Os` | release when flash-bound; usually within a few percent of `-O2` for speed |
| `-Ofast` | avoid — relaxes IEEE float semantics |
| `-flto` | last resort for size; breaks naive `--gc-sections` reasoning, confuses debuggers, and can silently drop weakly-referenced ISRs. If you use it, pass the same `-flto` and full flag set at link time and re-verify the vector table. |

Non-obvious: optimization changes *correctness* of code that lies to the compiler. Hardware registers must be `volatile`; busy-wait delay loops must be `volatile` or barrier-fenced or `-O2` deletes them; variables shared with an ISR need `volatile` plus a memory barrier or atomic access.

### Debug, warnings, dependencies

```
-g3 -gdwarf-4                      # -g3 keeps macro definitions so GDB can expand them
-Wall -Wextra -Wshadow -Wundef     # -Wundef catches "#if FEATURE" where FEATURE is a typo
-Werror                            # in CI, not necessarily on the developer's desk
-std=gnu11                         # gnu11/gnu17: ISO C plus GCC extensions you will use anyway
-fstack-usage -Wstack-usage=512    # per-function stack frames; the .su files feed worst-case analysis
-MMD -MP -MF"$(@:.o=.d)"           # emit header dependency files
```

`-g` costs nothing in flash — DWARF lives in the ELF, not in the `.bin` you flash. Build release images with `-g` too, archive the ELF, and you can post-mortem a field failure. `-MMD -MP` is what makes incremental builds correct; see the Makefile section.

`-Wundef` and `-Wshadow` are the two warnings that most often catch real embedded bugs that `-Wall` misses.

## Linking: specs, libraries, and the errors they produce

Link through `gcc`, not `ld`:

```sh
arm-none-eabi-gcc $(ARCHFLAGS) -T link.ld -nostartfiles \
  --specs=nano.specs --specs=nosys.specs \
  -Wl,--gc-sections -Wl,-Map=build/fw.map -Wl,--cref \
  -Wl,--print-memory-usage \
  $(OBJS) -o build/fw.elf -lm
```

- `--specs=nano.specs` selects **newlib-nano**: a reduced C library with much smaller `printf`/`malloc`. Typical saving is tens of KB. Newlib-nano specific: floating-point `printf` is *not* linked in by default — add `-u _printf_float` (and `-u _scanf_float`) if you need `%f`, and budget a few KB for it.
- `--specs=nosys.specs` provides stub implementations of the POSIX syscalls newlib expects (`_write`, `_sbrk`, `_close`, …) so the link succeeds on bare metal. Use it when you do not want I/O, or supply your own `_write` to retarget `printf` to UART/ITM/RTT and then you need neither stub nor semihosting. `--specs=rdimon.specs` routes them through semihosting instead — convenient under a debugger, but the device **hangs** if it executes a semihosting call with no debugger attached. Never ship it.
- `-nostartfiles` when you provide your own startup/reset handler (the normal bare-metal case); `-nostdlib` goes further and drops libgcc too, which breaks integer division and 64-bit math on cores without hardware divide. Prefer `-nostartfiles`.
- `-Wl,--print-memory-usage` prints a per-region used/size/% table derived from the linker script's `MEMORY` block. Requires binutils 2.31+. This is the single best one-line footprint readout, and the natural thing to gate on in CI.
- `-Wl,--cref` appends a cross-reference table to the map: which objects reference each symbol.

Linker errors decoded:

| Error | Cause |
|---|---|
| `undefined reference to '_sbrk'` / `_write` / `_close` | newlib wants syscalls — add `--specs=nosys.specs` or implement them |
| `uses VFP register arguments, <file> does not` | `-mfloat-abi` mismatch between objects, or against a prebuilt library |
| `region 'FLASH' overflowed by N bytes` | locate stage: image too big, or a section placed in the wrong region |
| `section .data VMA ... overlaps section .bss` | linker-script layout bug |
| `undefined reference to 'main'` after adding `-nostdlib` | you dropped the start files that reference it; usually you wanted `-nostartfiles` |
| undefined symbol that definitely exists in a `.a` | library listed before the object that needs it — on the command line, libraries go **last**; circular dependencies need `-Wl,--start-group ... -Wl,--end-group` |

Linker command-line order is semantic, not cosmetic: `ld` scans left to right and pulls an archive member only to satisfy an already-pending undefined symbol.

## Producing .bin and .hex

The ELF carries headers, symbols and debug info, and distinguishes LMA from VMA. A flash programmer usually wants something flatter:

```sh
arm-none-eabi-objcopy -O binary  build/fw.elf build/fw.bin
arm-none-eabi-objcopy -O ihex    build/fw.elf build/fw.hex
```

- `.bin` is raw bytes with **no address information** — you must tell the flasher the base address (e.g. `0x08000000` on STM32). Get it wrong and you brick the boot.
- `.hex` (Intel HEX) and `.srec` (Motorola S-record) embed addresses, so the flasher needs no base argument. Prefer them for release artifacts and for images with discontiguous regions (e.g. code in flash plus a config page at a far address) — `-O binary` fills the gap with padding, producing a needlessly huge file.
- `objcopy` emits only allocatable, loadable sections, so `.bss` is correctly absent and `.data` is taken from its LMA. That is exactly what you want.
- `--gap-fill 0xFF --pad-to 0x08080000` produces a fixed-size image padded with erased-flash value — needed for golden images, CRC-over-whole-image schemes and production programmers.
- `-R .section_name` removes a section (e.g. strip a bootloader-only region); `--only-section` extracts one.

If a CRC or signature is appended post-link, do it on the `.bin`/`.hex` and keep the ELF for debugging — never patch the ELF.

## Interrogating the image: answering real questions

### "Why is my image 40 KB?"

```sh
arm-none-eabi-size build/fw.elf          # Berkeley format: text data bss dec hex
arm-none-eabi-size -A build/fw.elf       # per-section, with addresses
```

Read it correctly:

- **Flash used = text + data** (`.data` initializers must be stored in flash to be copied to RAM at boot).
- **RAM used (static) = data + bss**, before any heap or stack. Stack and heap are *not* in this number — size says nothing about your real RAM headroom.
- A `.data` that is surprisingly large usually means large initialized arrays or lookup tables that should be `const` (moving them to `.rodata`/flash) — a two-character fix that can free kilobytes of RAM.

Then find the culprits:

```sh
arm-none-eabi-nm --print-size --size-sort --reverse-sort --radix=d build/fw.elf | head -40
```

This is the workhorse. Add `-C` to demangle C++ names. A `_printf_float`, `_dtoa_r` or `_malloc_r` near the top means the C library, not your code, is the problem.

### "Did that function get inlined / was it even emitted?"

```sh
arm-none-eabi-nm build/fw.elf | grep my_function          # absent → inlined or GC'd
arm-none-eabi-objdump -d --disassemble='my_function' build/fw.elf
arm-none-eabi-objdump -S build/fw.elf > build/fw.lst      # source interleaved with asm
```

`-S` requires `-g`. The interleaved listing is how you check that a `volatile` read was not hoisted out of a loop, that a tight ISR compiled to the handful of instructions you expected, or that the compiler used a hardware divide rather than calling `__aeabi_idiv`.

`-h` shows section headers with sizes and addresses; `-t` shows the symbol table; `-r` shows unresolved relocations in an individual `.o`.

### "Which object pulled in malloc?"

Three complementary methods, in increasing order of certainty:

1. `grep -n 'malloc\|_sbrk' build/fw.map` — the map's archive-inclusion block literally names the object that caused each library member to be pulled in (lines of the form *"member included to satisfy reference by <object>"*).
2. `-Wl,--cref` cross-reference table: the symbol, its defining file, and every file referencing it.
3. `arm-none-eabi-nm -u *.o | sort | uniq -c` to see which translation units have an undefined reference to it.

The usual culprits are `printf`/`sprintf` family, `strdup`, C++ `new`/exceptions/`std::function`, and `snprintf` with `%f`. Heap on a bare-metal MCU is a design decision; discovering it was linked in by accident is common.

### "Is this ELF built for the right core and float ABI?"

```sh
arm-none-eabi-readelf -A build/fw.elf     # ARM build attributes: CPU, Thumb, FP arch, ABI_VFP_args
arm-none-eabi-readelf -S build/fw.elf     # sections with addresses and flags
arm-none-eabi-readelf -l build/fw.elf     # program headers: VirtAddr vs PhysAddr → VMA vs LMA
```

`readelf -A` settles float-ABI and core-mismatch arguments instantly — invaluable when integrating a vendor-supplied binary blob. `readelf -l` is how you verify that `.data` has a flash LMA distinct from its RAM VMA; if they are equal, your startup copy loop is copying RAM onto itself and nothing will be initialized.

## Reading the .map file

Always generate it (`-Wl,-Map=...`). It is the authoritative record of the locate stage. Its useful blocks, in order of how often you need them:

1. **Archive member inclusion** — why each library object is present, and who asked for it.
2. **Discarded input sections** — what `--gc-sections` removed. Check here when a symbol vanished mysteriously.
3. **Memory configuration** — the `MEMORY` regions, as the linker understood them.
4. **Linker script and memory map** — the main body: every input section, its address, size, and originating object, in placement order. Sort-of-chronological by address, so you can spot an unexpected 8 KB blob and trace it back to a file.
5. **Cross reference table** (with `--cref`).

Two things it answers that nothing else does: where exactly the gap between two sections came from (alignment, or a `. = ALIGN(...)` in the script), and whether a symbol you expected at a fixed address actually landed there.

## A hand-written firmware Makefile

Understand Make even if you use CMake or a vendor IDE — IDEs generate makefiles, and CI needs a command-line path. A rule is `target: prerequisites` followed by TAB-indented recipe lines. Make rebuilds a target when it is older than any prerequisite.

Four mechanisms turn a toy makefile into a usable one:

**Pattern rules + automatic variables** replace one rule per file.

```make
$(BUILD)/%.o: %.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@
```

`$@` = target, `$<` = first prerequisite, `$^` = all prerequisites (deduplicated), `$*` = the stem matched by `%`. The `| $(BUILD)` is an **order-only prerequisite**: the directory must exist, but its timestamp must not trigger rebuilds. Omitting the `|` means every file written into the directory changes its mtime and rebuilds everything.

**vpath** lets objects live in one build directory while sources are scattered:

```make
vpath %.c src:src/drivers:vendor/CMSIS
```

**Generated dependency files** are what make incremental builds *correct*. Without them, editing a header rebuilds nothing and you debug a stale binary.

```make
CFLAGS += -MMD -MP
-include $(OBJS:.o=.d)
```

`-MMD` writes a `.d` file listing the headers each object depends on (`-MD` also lists system headers; usually unwanted). `-MP` adds a phony target for every header so that *deleting* a header does not break the build with "No rule to make target". The leading `-` on `-include` suppresses the error on the first build when no `.d` exists yet.

**Variable flavors.** `:=` expands once at definition (predictable, fast); `=` re-expands on every use (needed for variables referring to things defined later). Use `:=` by default. `?=` sets only if not already set — the right way to let the environment or CI override `CC` or `OPT`.

Skeleton:

```make
TARGET  := fw
BUILD   := build
CC      := arm-none-eabi-gcc
ARCH    := -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16
OPT     ?= -Og
CFLAGS  := $(ARCH) $(OPT) -g3 -std=gnu11 -Wall -Wextra \
           -ffunction-sections -fdata-sections -MMD -MP $(addprefix -I,$(INCDIRS))
LDFLAGS := $(ARCH) -T$(LDSCRIPT) -nostartfiles \
           --specs=nano.specs --specs=nosys.specs \
           -Wl,--gc-sections -Wl,-Map=$(BUILD)/$(TARGET).map -Wl,--cref \
           -Wl,--print-memory-usage

SRCS := $(wildcard src/*.c) $(wildcard src/drivers/*.c) startup.s
OBJS := $(addprefix $(BUILD)/,$(notdir $(SRCS:.c=.o)))
OBJS := $(OBJS:.s=.o)
vpath %.c $(sort $(dir $(SRCS)))
vpath %.s $(sort $(dir $(SRCS)))

.PHONY: all clean
all: $(BUILD)/$(TARGET).bin $(BUILD)/$(TARGET).hex

$(BUILD)/%.o: %.c | $(BUILD) ; $(CC) $(CFLAGS) -c $< -o $@
$(BUILD)/%.o: %.s | $(BUILD) ; $(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/$(TARGET).elf: $(OBJS) $(LDSCRIPT)
	$(CC) $(OBJS) $(LDFLAGS) -o $@
	arm-none-eabi-size $@

$(BUILD)/%.bin: $(BUILD)/%.elf ; arm-none-eabi-objcopy -O binary $< $@
$(BUILD)/%.hex: $(BUILD)/%.elf ; arm-none-eabi-objcopy -O ihex   $< $@
$(BUILD): ; mkdir -p $@
clean:  ; rm -rf $(BUILD)

-include $(OBJS:.o=.d)
```

Pitfalls that bite everyone once:

- **Recipes must start with a literal TAB.** An editor that expands tabs produces `missing separator`.
- `*.o` on the link line (instead of an explicit `$(OBJS)` list) silently links stale objects from deleted sources and defeats dependency tracking.
- `rm -f` vs `del` — do not hardcode Windows shell commands if CI runs on Linux.
- A linker-script change must force a relink: list `$(LDSCRIPT)` as a prerequisite of the `.elf` target. Most makefiles forget this, and you debug an image built against the old memory map.
- Changing `CFLAGS` does **not** invalidate objects. Either `make clean` after a flag change, or write the flags to a file that objects depend on.
- `make -j$(nproc)` is safe once dependencies are correct, and a good forcing function: a parallel build that fails intermittently has a missing prerequisite.

## Flashing and debugging

### OpenOCD

Start it once, in its own terminal, and leave it running — it opens a GDB server (3333 by default), a Telnet monitor console (4444), and a Tcl port (6666).

```sh
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg
# board files combine both:
openocd -f board/st_nucleo_f4.cfg
```

The modern, scriptable one-shot form supersedes the old init/halt/`flash write_image` dance:

```sh
openocd -f board/st_nucleo_f4.cfg -c "program build/fw.elf verify reset exit"
```

Flashing the **ELF** (not the `.bin`) is preferable: addresses come from the file, so there is no base-address argument to get wrong. Use `.bin` only where the tool demands it, and then always state the address explicitly.

### GDB

```sh
arm-none-eabi-gdb build/fw.elf \
  -ex 'target extended-remote :3333' \
  -ex 'monitor reset halt' \
  -ex 'load' \
  -ex 'monitor reset init'
```

- Prefer `target extended-remote` over `target remote`: it supports `run`/restart against the stub.
- `load` flashes the image *and* sets the PC — the normal develop-loop flashing method. `monitor <cmd>` forwards a command to OpenOCD (reset, flash, halt).
- `monitor reset halt` before `load`, `monitor reset init` after — flashing a running target gives unpredictable results.
- Put the boilerplate in a project `.gdbinit` and run `arm-none-eabi-gdb -x .gdbinit`; GDB refuses to auto-load one from the CWD unless `set auto-load safe-path` permits it.
- Some distributions ship `gdb-multiarch` instead of `arm-none-eabi-gdb`; then `set architecture arm` manually.
- Useful on Cortex-M: `info registers`, `p/x *(uint32_t*)0x40020000` to read a peripheral register, `x/16xw &buf`, `watch var` (hardware watchpoints — a scarce resource, typically 4), `bt`, `monitor reset halt`.
- Optimized builds make stepping confusing (`<optimized out>`, line jumps). Drop that translation unit to `-Og`/`-O0` rather than fighting it.

### Alternatives to OpenOCD

| Tool | Notes |
|---|---|
| **pyOCD** | Python, CMSIS-DAP focused, `pyocd flash`, `pyocd gdbserver`; good scripting story and easy pip install |
| **probe-rs** | Rust-based, fast, works with C/C++ ELFs; `probe-rs run --chip STM32F411RETx fw.elf`; built-in RTT |
| **SEGGER J-Link** | `JLinkExe`, `JLinkGDBServer`; the most reliable for high-speed flashing and RTT; proprietary |
| **ST-LINK utilities** | `st-flash` / `st-util` (open source), or STM32CubeProgrammer (`STM32_Programmer_CLI`) for production |
| **Black Magic Probe** | runs the GDB server *on the probe* — connect GDB directly to a serial port, no middleman daemon |
| **DFU** | `dfu-util` over USB, using an on-chip bootloader; no debug probe needed, but no debugging either |

For printf-style output, UART is universal, SEGGER RTT is dramatically faster and non-blocking, and ITM/SWO is free on Cortex-M3/M4/M7 when a probe supports it. Semihosting works but halts the core on every call and hangs a debugger-less device — development only.

## Off-target testing and emulation

The hardware in the loop is the slowest part of the edit-test cycle. Structure the code so most of it never needs the target.

**Host unit tests.** Split code into (a) pure logic — protocol parsers, state machines, filters, calculations — and (b) register pokes. Compile (a) with the host `gcc`/`clang` and test it with Unity+CMock (Ceedling), CppUTest, or `check`. Replace hardware calls with mocks (link a different object defining the same function; the `weak` attribute makes the production definition overridable without `#ifdef`). This is also where host `gcov`/`lcov` coverage comes from — you cannot sensibly measure coverage on target.

Non-obvious payoff: the discipline forces a clean driver/logic boundary, which is the same boundary you need to port to a different MCU later.

**QEMU.** `qemu-system-arm` models a handful of Cortex-M machines — `lm3s6965evb` (M3), `mps2-an385`/`-an500` and `netduinoplus2` among them. Peripherals are minimal and vendor-specific ones are absent, but core behavior (NVIC, faults, MPU, privilege modes, SysTick) is accurate enough to exercise startup code and OS ports. Run with `-nographic -S -gdb tcp::3333` and attach GDB exactly as to real hardware. Verify machine availability with `qemu-system-arm -M help` — the list changes between versions.

**Renode.** Models whole boards including peripherals, sensors, LEDs, and wired/wireless links between multiple emulated nodes; loads an ELF (`sysbus LoadELF`), spawns a GDB server (`machine StartGdbServer 3333`), and has a scripting language built for test automation. Markedly better than QEMU when you need peripherals or multi-node scenarios, and it supports non-Arm cores too.

**Arm FVP / Virtual Hardware.** Fixed Virtual Platforms are Arm's own cycle-inaccurate-but-functionally-accurate models (`FVP_MPS2_Cortex-M7` and similar), scriptable and headless, designed for CI at scale. Arm's hosted offering around them has been repackaged more than once — check current licensing and availability before building a pipeline on it.

Limits of every virtual target: it models what it models. Your exact sensor, radio, display and board wiring are not there. Use virtual targets for logic, not for electrical truth.

## CI for firmware

Embedded CI is harder than web CI for one structural reason: you develop on x86/ARM64 hosts and deploy to a different machine that you cannot spin up on demand. Everything below is about managing that gap.

**The test pyramid, mapped to where tests run:**

| Test kind | Count | Where |
|---|---|---|
| Unit — single functions, pure logic | hundreds–thousands | host build, or virtual target |
| Integration — components talking to each other | dozens–hundreds | virtual target, or hardware |
| System / black-box — does the product do the thing | a handful | real hardware, ideally the end device |

The economical shape is a **large virtual farm plus a small board garden**: scale unit tests on emulators or the host where instances are free and parallel, and keep a modest set of physical boards for the integration and system tests that need real electrical behavior.

Board farms are real but costly: boards wear out after enough flash cycles, hang in states needing a physical reset (budget relay-controlled power cycling), need rack space and cooling, and must be kept around for years to support shipped products. Every board in the farm is a maintenance liability; add them deliberately.

**What to gate on, in order of cost:**

1. **Build** — every supported target/board/config combination, warnings as errors. A matrix build catches the `#ifdef` that only compiles for one variant.
2. **Static analysis** — `clang-tidy`, `cppcheck`, or a MISRA-C checker if the domain requires it. Cheap, no hardware.
3. **Host unit tests + coverage** — fast, deterministic, parallel.
4. **Size regression** — store `size`/`--print-memory-usage` output as a baseline artifact and fail the build when flash or RAM grows beyond a threshold. This is the single highest-value embedded-specific gate: it catches the innocuous change that pulls in `printf` float support or `malloc` and eats 8 KB, *before* you discover it at 97% flash occupancy near release.
5. **Emulated integration tests** — Renode/QEMU/FVP, driven from a script.
6. **Hardware smoke test** — flash one real board, assert it boots, prints its banner, and passes a short self-test over UART. Keep it minutes, not hours; the full HIL suite runs nightly, not per commit.

**Mechanics that matter:**

- **Pin the toolchain.** "Works on my machine" in firmware usually means a different GCC. Run CI in a container with an exact toolchain version that developers can also run. GCC versions differ in image size and occasionally in behavior.
- **Archive the ELF and map per commit.** When a field unit faults, you need that exact ELF to `addr2line` against.
- **Build clean.** `make clean && make -j` as the CI command; a stale incremental build is a flake you cannot debug.
- Host-side harnesses in Python (or similar) so they can regex UART output and emit JUnit XML.
- Secrets go in the CI secret store as environment variables, never in the repo; signing keys belong in a restricted job or HSM.
- **If the IDE is the only way to build, CI cannot run.** Any IDE-based project needs a maintained command-line path — most IDE toolchains have a headless/batch mode, and several simply generate the makefile you can invoke directly.

## Checklists

**Flag hygiene**

- [ ] `-mcpu`, `-mthumb`, `-mfloat-abi`, `-mfpu` identical across every compile *and* the link
- [ ] FPU enabled in software at boot if `-mfloat-abi` is not `soft`
- [ ] `-ffunction-sections -fdata-sections` paired with `-Wl,--gc-sections`
- [ ] `-g3` kept even in release builds; the ELF archived
- [ ] `-MMD -MP` present and `.d` files `-include`d
- [ ] `--specs=` choice deliberate; no `rdimon.specs`/semihosting in a shipping image
- [ ] `-Wall -Wextra -Wundef -Wshadow`; `-Werror` in CI
- [ ] Linker script listed as a prerequisite of the ELF target

**Before believing a footprint number**

- [ ] Flash = text + data; RAM(static) = data + bss; stack and heap counted separately
- [ ] `--print-memory-usage` or `size -A` compared against the real `MEMORY` regions
- [ ] `nm --size-sort -S` run to identify the top consumers
- [ ] Map checked for unexpected library members and for what `--gc-sections` discarded
- [ ] Large initialized tables marked `const` so they stay in flash

**Before trusting the build, and in CI**

- [ ] `make clean && make -j` reproduces the artifact from scratch
- [ ] Toolchain version pinned and recorded in the build log
- [ ] `readelf -A` confirms core and float ABI; `readelf -l` confirms `.data` LMA differs from its VMA
- [ ] `.bin` flashed at the correct base address, or `.hex`/ELF used instead
- [ ] Matrix build with warnings as errors
- [ ] Static analysis and host unit tests with coverage
- [ ] Size regression gate against a stored baseline
- [ ] Emulated integration tests where peripherals permit
- [ ] Short hardware smoke test per commit; full HIL suite nightly
- [ ] ELF + map + size report archived per commit

Sources: see the Sources section of ../SKILL.md (Bare-Metal Embedded C Programming; Insider's Guide to Arm Cortex-M Development; Embedded Systems Architecture, 2nd ed.). Per-chapter attribution was not recorded for this file.
