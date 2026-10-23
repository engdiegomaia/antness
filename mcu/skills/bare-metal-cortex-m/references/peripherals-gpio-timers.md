# GPIO and Timers at Register Level

Read this when configuring pins, generating periodic events or PWM, measuring external signals with input capture, or debugging a peripheral whose register writes appear to do nothing.

## Contents

- [Clock gating comes first](#clock-gating-comes-first)
- [GPIO: the configuration registers](#gpio-the-configuration-registers)
- [Output drive: push-pull, open-drain, speed](#output-drive-push-pull-open-drain-speed)
- [Alternate function muxing](#alternate-function-muxing)
- [Atomic set/reset vs read-modify-write](#atomic-setreset-vs-read-modify-write)
- [Reading inputs and debouncing](#reading-inputs-and-debouncing)
- [SysTick](#systick)
- [Wraparound-safe time comparisons](#wraparound-safe-time-comparisons)
- [General-purpose timers: the time base](#general-purpose-timers-the-time-base)
- [The update event, UG and preload](#the-update-event-ug-and-preload)
- [Counting modes and one-pulse mode](#counting-modes-and-one-pulse-mode)
- [PWM](#pwm)
- [Input capture and encoder mode](#input-capture-and-encoder-mode)
- [Timer-triggered peripherals](#timer-triggered-peripherals)
- [Checklists](#checklists)

Naming note: register names in this file (`MODER`, `OTYPER`, `OSPEEDR`, `PUPDR`, `IDR`, `ODR`, `BSRR`, `LCKR`, `AFRL`/`AFRH`, `PSC`, `ARR`, `CNT`, `CCRx`, `CCMRx`, `CCER`, `CR1`, `EGR.UG`, `SR.UIF`, `DIER`) are **STM32 naming**. The equivalent on your part may be called something else — NXP LPC/Kinetis split pin muxing into IOCON/PORT and direction/data into GPIO `PDOR`/`PSOR`/`PCOR`/`PTOR`, RP2040 uses `GPIO_OUT_SET`/`GPIO_OUT_CLR` plus a per-pin `GPIOx_CTRL` function select, Nordic uses `PIN_CNF[n]` with `OUTSET`/`OUTCLR`. The *behaviour* described here is near-universal; the exact bit layout is not. Check your reference manual before writing any value.

## Clock gating comes first

**The single most common "my register writes don't stick" bug**: the peripheral's bus clock is off. A gated peripheral's registers read back as zero (or as reset values) and swallow writes silently — no fault, no warning. On a Cortex-M the write may even be posted and retired before the bus rejects it, so the debugger shows your code sailing past the line that did nothing.

Rules:

1. Enable the peripheral clock **before** the first access to any of its registers — GPIO port, timer, everything.
2. On some cores and bus bridges there is a latency of one or more cycles between the gate write and the peripheral becoming reachable. The safe idioms are to **read the enable register back** (which forces the write to complete) or to insert a data memory barrier. A dummy read-back is cheap and portable; do it in your `init()`.
3. Gates are per-peripheral and live on the bus the peripheral sits on. GPIO ports are typically on a high-speed bus (AHB), timers on the peripheral buses (APB1/APB2) — a timer and a GPIO port therefore live in *different* enable registers.
4. If the peripheral also has a reset line, consider pulsing reset before configuring: it guarantees a known starting state after a warm reset where the gate was already on.
5. Gating unused peripherals back off is a real power optimisation, not a micro-optimisation. See the clocks and power reference.

## GPIO: the configuration registers

A GPIO port is a group of up to 16 (sometimes 32) pins sharing one register block and one clock gate. Each pin has, conceptually, five independent configuration items:

| Item | STM32 register | Meaning |
|---|---|---|
| Mode / direction | `MODER`, 2 bits per pin | input (00), general-purpose output (01), alternate function (10), analog (11) |
| Output type | `OTYPER`, 1 bit per pin | push-pull (0) or open-drain (1) |
| Output speed / slew | `OSPEEDR`, 2 bits per pin | drive strength and edge rate |
| Pull resistors | `PUPDR`, 2 bits per pin | none / pull-up / pull-down |
| Alternate function number | `AFRL` (pins 0-7) / `AFRH` (pins 8-15), 4 bits per pin | which peripheral owns the pin |

Data moves through `IDR` (read pin state) and `ODR` (output level), with `BSRR` for atomic changes.

Decision rules:

- **Analog mode for ADC/DAC pins, and for unused pins.** Analog mode disconnects the digital input buffer. On an ADC pin that avoids digital input leakage and distortion; on an unused pin it kills the shoot-through current you get when a floating pin sits near the input threshold and the Schmitt trigger oscillates. A board full of floating digital-input pins is a measurable power leak.
- **Never mutate a 2-bit or 4-bit field with `|=` alone.** The field keeps its old bits. Always clear the field first, then set it:
  ```c
  port->MODER &= ~(3u << (pin * 2));   /* clear both bits */
  port->MODER |=  (1u << (pin * 2));   /* 01 = output      */
  ```
  Forgetting the clear is why "configuring the pin as output" sometimes lands you in alternate-function mode instead.
- **Configure before enabling.** Set type, speed and pulls *before* switching `MODER` to output or alternate function, so the pin never spends a microsecond driving the wrong level or the wrong edge rate. For outputs that must come up at a known level, write `BSRR` first, then switch the mode.
- **Locking.** `LCKR` (STM32 naming) freezes a pin's configuration until the next reset, via a specific write-read key sequence. Use it for safety-critical pins — motor enables, brake lines, watchdog strobes — where a stray pointer must not be able to re-mux the pin. It protects configuration, not the output level.

## Output drive: push-pull, open-drain, speed

**Push-pull** drives both rails actively. Use it for everything by default: LEDs, chip selects, reset lines you own exclusively.

**Open-drain** only pulls low; the high level comes from an external (or internal) pull-up. Use it when:

- The bus is shared and multiple devices may drive it — I²C SDA/SCL, 1-Wire, shared interrupt lines, wired-OR fault lines. Two push-pull drivers in opposition is a short circuit.
- The line must be level-shifted to a different voltage rail by the pull-up.
- The signal is a wired-AND of several sources.

Internal pull-ups are typically tens of kΩ. For I²C at 400 kHz they are usually too weak and the rising edge rounds off; use external resistors sized from the bus capacitance.

**Output speed / slew rate** is a real trade-off, not a "faster is better" knob:

| Setting | Gain | Cost |
|---|---|---|
| Low / slow | less ringing and overshoot, lower radiated emissions, less ground bounce, lower dynamic current | slow edges — unusable above a few hundred kHz, bad for SPI clocks |
| High / fast | clean edges at high data rates | di/dt spikes, overshoot past the supply rails, crosstalk, EMI, a harder EMC test |

Rule: **choose the slowest setting that still meets the signal's timing requirement.** An LED or a relay driver needs the slowest; a 20 MHz SPI clock or an external memory bus needs the fastest. If an EMC pre-scan shows harmonics at multiples of a clock, the output speed setting on that clock pin is one of the first things to try lowering. Series termination resistors (22–33 Ω) near the driver help too.

## Alternate function muxing

A pin can be wired to many internal peripherals, but exactly one at a time. Two steps, in this order:

1. Write the alternate-function number into the pin's 4-bit field (`AFRL` for pins 0-7, `AFRH` for pins 8-15 — note the index on `AFRH` is `pin - 8`).
2. Switch `MODER` to alternate-function mode.

The number-to-peripheral mapping is in a table in the datasheet (not the reference manual), and it is **per-package and per-part**. The same pin name on a different family member may carry a different AF number. Never copy an AF constant from another project without re-checking the table.

Pitfalls:

- The pull/speed/type settings still apply in alternate-function mode and still matter. An I²C pin in alternate function must still be set open-drain.
- Both endpoints of the mux must agree: muxing the pin to a timer channel does nothing until the timer's output is also enabled.
- Some signals are available on several pins. Pick based on PCB routing and on not colliding with a peripheral you need later — do this on a pin-assignment spreadsheet before layout, not after.
- Peripherals occasionally need the pin muxed *before* the peripheral is initialised (and sometimes the reverse). If a bus hangs at init, try swapping the order.

## Atomic set/reset vs read-modify-write

`ODR` is an ordinary register: `ODR |= PIN` compiles to load, OR, store. Between the load and the store an interrupt can run, change a *different* pin in the same port, and have its change overwritten when your store lands. This is a genuine lost-update race and it is intermittent, which makes it expensive to find.

The hardware answer is a **write-only set/clear register**. On STM32 it is `BSRR`: writing 1 to bit *n* sets pin *n*, writing 1 to bit *n+16* clears it; zeros are ignored, so no read is involved and no other pin is touched. The equivalents: NXP `PSOR`/`PCOR`/`PTOR`, RP2040 `GPIO_OUT_SET`/`GPIO_OUT_CLR`/`GPIO_OUT_XOR`, Nordic `OUTSET`/`OUTCLR`.

```c
#define PIN_SET(port, pin)    ((port)->BSRR = (1u << (pin)))
#define PIN_CLEAR(port, pin)  ((port)->BSRR = (1u << ((pin) + 16)))
```

Rules:

- **Use the atomic register for every runtime pin change.** Reserve `ODR` writes for the one-shot initial level before the pin is enabled, where no concurrency exists.
- A single `BSRR` write can set some pins and clear others in the same instruction — useful for stepper phases, parallel bus patterns, and chip-select handoffs that must be glitch-free.
- If both set and reset bits for the same pin are written in one word, set typically wins on STM32 — but verify in your manual rather than relying on it.
- Toggling is the awkward case: if there is no hardware XOR register you must read `ODR` and compute, which is again read-modify-write. Keep a shadow variable in a single owner, or do the toggle with interrupts masked, or use a part that has an XOR register.
- Bit-banding (where the core provides it) gives atomic single-bit writes to `ODR` as an alternative, but it is not present on all Cortex-M cores and is not portable.

## Reading inputs and debouncing

Reading is simple: `IDR` reflects the pin voltage through the Schmitt trigger. Mask the bit, compare, done. Note the electrical sense: a button to ground with a pull-up reads **0** when pressed. Write a named helper (`button_is_pressed()`) rather than scattering inverted bit tests.

Mechanical contacts bounce for roughly 1–20 ms depending on the switch. Un-debounced, a single press produces a burst of edges — and if it is wired to an edge interrupt, a burst of interrupts.

| Approach | When | Notes |
|---|---|---|
| Hardware RC + Schmitt input | the signal feeds an edge interrupt, or edges must be clean on a scope | ~10 kΩ with 100 nF gives a ~1 ms time constant; needs a Schmitt-trigger input or the slow edge causes its own multiple triggering. Costs parts, works with zero CPU. |
| Software periodic sampling | most buttons and switches | sample on a timer or SysTick tick, decide in software, zero extra hardware |
| Integrator / counter | noisy industrial inputs | count up while high, down while low, flip state at thresholds; rejects short glitches in both directions |

The standard software pattern: sample the pin every 1–5 ms from a timer tick, and only accept a state change after N consecutive identical samples totalling **5–20 ms**. A compact form is a shift register — shift the sample into a byte each tick and compare against all-ones or all-zeros.

Rules:

- Debounce in a periodic context, not in a busy-wait delay, and never with `delay_ms()` inside an ISR.
- If a button must raise an interrupt, debounce in hardware or use the ISR only to *start* a debounce timer and disable the edge interrupt until the timer expires.
- Detect edges in the debounced state, not the raw pin, and report press/release as events to the main loop.
- Long-press and double-click belong in the same state machine, driven off the same tick.

## SysTick

SysTick is part of the Cortex-M core, not the vendor's peripheral set, so the same code works across vendors. That is its main virtue.

- **24-bit down counter.** It counts down to zero, reloads from the reload register, and repeats. 24 bits is the hard ceiling on one period: at 100 MHz, about 168 ms.
- **`RELOAD = ticks - 1`.** The counter spends one tick at each value from RELOAD down to 0 inclusive, so RELOAD+1 ticks elapse per period. Off-by-one here gives a timebase that is wrong by one part in RELOAD — invisible on an LED, visible after an hour of accumulated drift. Valid range is 1 to 0x00FFFFFF.
- **Clock source.** The control register selects the processor clock or an implementation-defined reference (often core clock / 8). Prefer the processor clock: you already know its frequency, and the reference clock's divider is not guaranteed across parts. Whichever you pick, derive RELOAD from the *same* number your clock code actually programmed — a `SystemCoreClock` variable updated by the clock-switch routine, not a compile-time constant that silently goes stale when someone adds a PLL.
- **Writing the current-value register** clears the counter *and* the count flag; any written value is ignored. Do this after changing RELOAD so the new period starts immediately rather than after one stale cycle.
- **`COUNTFLAG` is read-to-clear.** It tells you the counter hit zero since the last read. That is fine for a polled delay loop, but it means **you cannot share it** — a debugger read, or a second function polling it, consumes the event and the other reader misses a tick. Polling COUNTFLAG and taking a SysTick interrupt in the same system is a bug.

Two usage modes:

```c
/* Interrupt mode - the normal choice */
volatile uint32_t g_ticks;          /* volatile: written by the ISR */
void SysTick_Handler(void) { g_ticks++; }
```
The tick counter must be `volatile`, or the compiler will hoist the read out of a wait loop and spin forever. On a 32-bit core a `uint32_t` read is atomic; a 64-bit tick counter is not, and needs a seqlock or a masked read.

Polled mode (set RELOAD, clear the current value, enable without the interrupt, spin on COUNTFLAG) is acceptable only in early bring-up or in code that runs before interrupts are configured.

**When SysTick is the wrong tool:**

- *Sub-microsecond timing.* The ISR entry/exit overhead alone is tens of cycles, and the resolution is one tick. Use the cycle counter (DWT CYCCNT, where fitted) or a free-running hardware timer at full clock speed.
- *Long sleeps.* SysTick usually stops in deep-sleep modes and its 24 bits cap one period at a fraction of a second. Use an RTC or a low-power timer for anything beyond that.
- *A precise long-term clock.* SysTick runs off the system clock, which is typically an RC oscillator or a PLL from one. It drifts. Discipline it against an RTC crystal if wall-clock accuracy matters.
- *Anything an RTOS owns.* Most RTOSes claim SysTick for their scheduler tick. Do not also drive application timing from it directly; use the RTOS API.

## Wraparound-safe time comparisons

A 32-bit millisecond tick wraps after 49.7 days. Code that compares absolute values breaks at the wrap, in the field, long after testing:

```c
while (g_ticks < start + delay) { }      /* WRONG: breaks at wraparound */
```

The correct form compares the *difference*, using unsigned arithmetic so the subtraction wraps correctly, then reads the result as signed:

```c
uint32_t deadline = g_ticks + delay_ms;
while ((int32_t)(g_ticks - deadline) < 0) { }   /* wraparound-safe */

/* elapsed time, same principle */
uint32_t elapsed = g_ticks - start;             /* correct across a wrap */
```

This is correct as long as the interval being measured is less than half the counter range. Apply the same pattern to hardware counters — for a 16-bit timer, cast to `int16_t`.

## General-purpose timers: the time base

Vendors ship two tiers. **General-purpose timers** give a counter (16 or 32 bits), a 16-bit prescaler, several independent capture/compare channels, up/down/center counting, interrupt and DMA generation, and usually encoder-interface support. **Advanced timers** add the pieces motor control needs: complementary outputs with programmable dead-time, a repetition counter (update the registers only every N cycles), and a break input that forces the outputs to a safe state on a fault. Use an advanced timer for any half-bridge; a general-purpose timer cannot safely drive one.

The time base is three registers: the counter (`CNT`), the prescaler (`PSC`), and the auto-reload (`ARR`).

```
f_counter = f_timer_clk / (PSC + 1)
f_event   = f_timer_clk / ((PSC + 1) * (ARR + 1))
```

Both fields are "value minus one" for the same reason as SysTick's reload: the hardware counts the zero.

**Choosing PSC vs ARR** is the one real design decision:

- The prescaler sets the **resolution** — one count is `(PSC+1) / f_timer_clk` seconds.
- The auto-reload sets the **range** — the period is ARR+1 counts.
- For a given period, **the smallest prescaler that keeps ARR inside the counter width gives the best resolution.** Push the division into ARR, not PSC.
- For PWM this is not optional: duty-cycle resolution is exactly ARR+1 steps. ARR = 99 gives you 1% steps and nothing finer, regardless of how clever the rest of the code is. Want 10-bit dimming? ARR must be at least 1023.
- A 32-bit counter (available on some general-purpose timers) removes the trade-off for long periods; prefer it when you have one.

Worked example: a 16 MHz timer clock and a 1 Hz event. PSC = 1599 divides to 10 kHz; ARR = 9999 then counts 10 000 ticks = 1 s. The alternative PSC = 15999 / ARR = 999 gives the same second with a tenth of the resolution.

### The APB timer-clock doubling rule (STM32-specific)

On STM32 the clock fed to a timer is **not** simply the APB bus clock. If the APB prescaler is 1, the timer clock equals the bus clock; if the APB prescaler is anything other than 1, **the timer clock is twice the bus clock**. The hardware does this so timers keep full resolution when the bus is slowed down.

Consequences: a board where APB1 runs at HCLK/4 has timers clocked at HCLK/2, and firmware that computed PSC from "the APB1 frequency" will be out by a factor of two — every period, every baud-like rate, every PWM frequency. Derive the timer clock from a function that applies the rule, never from a hard-coded constant, and verify with a scope once per board. Other vendors do not generally do this, which is exactly why it catches people porting code in.

## The update event, UG and preload

The update event (UEV) is what happens when the counter overflows (up-counting) or underflows (down-counting). It sets the update interrupt flag, can raise an interrupt or a DMA request, and — crucially — **it is the moment the shadow registers latch**.

`PSC` and (when preload is enabled) `ARR` and `CCRx` are buffered. Writing them changes the *preload* register; the active *shadow* register only takes the new value at the next update event. This exists so a PWM period or duty cycle can be changed without producing a runt pulse.

The practical rules:

- **After reconfiguring a stopped timer, generate an update event in software** by setting the UG bit in the event-generation register (`EGR.UG` — STM32 naming). This forces prescaler and auto-reload into their shadow registers and resets the counter, so the very first period is already correct. Without it, the first period runs with the old (often reset-value) prescaler, which is the classic "my first timer interrupt comes far too early" symptom.
- **`EGR.UG` also sets the update interrupt flag.** If the interrupt is already enabled, you get a spurious interrupt immediately. Either generate the update *before* enabling the interrupt, or clear the update flag right after the UG write. Clearing it unconditionally in `init()`, after UG and before enabling the NVIC line, is the safe habit.
- **Clear the update flag at the top of the ISR**, before doing work. The flag is sticky and write-0-to-clear (on STM32 you AND away the bit, you do not write 1). Forgetting makes the ISR re-enter the moment it returns — a hang that looks like the main loop never running. Clear it with a plain store, then read it back or rely on the peripheral write ordering, so the write retires before the handler returns; otherwise a late-retiring write re-enters the handler anyway.
- **ARPE** (auto-reload preload enable) decides whether ARR is buffered at all. Enable it whenever you change the period while running — otherwise a new ARR takes effect immediately, and if the counter has already passed the new value it runs all the way around the counter before the next event. Leave it disabled only when you want an immediate, deliberate retrigger.

## Counting modes and one-pulse mode

| Mode | Behaviour | Use |
|---|---|---|
| Up-counting | 0 → ARR, update on overflow | the default; periodic ticks, edge-aligned PWM |
| Down-counting | ARR → 0, update on underflow | occasionally convenient for countdown semantics |
| Center-aligned | 0 → ARR → 0, update at one or both ends | motor and audio PWM; see below |

Center-aligned mode halves the effective PWM frequency for the same ARR (the counter traverses the range twice per period) — compensate in the arithmetic. It also gives two update events per period unless configured otherwise, which matters if an ISR or a DMA request hangs off the update.

**One-pulse mode** makes the counter stop automatically at the next update event. Combined with a trigger input it gives you a hardware monostable: an input edge starts the counter, the output goes active after the programmed delay, stays active for the programmed width, and the timer disarms itself. Use it for precise single pulses (ultrasonic trigger, camera strobe, ignition dwell) where software jitter is unacceptable. The delay comes from CCR, the width from ARR - CCR.

## PWM

PWM comes from the output-compare unit: the counter is compared against a channel's capture/compare register, and the output flips when they match. The usual mode ("PWM mode 1" on STM32) drives the output active while `CNT < CCR` and inactive after, giving

```
duty = CCR / (ARR + 1)
```

with CCR = 0 meaning permanently off and CCR > ARR meaning permanently on. Check whether your part's "100%" case needs CCR = ARR+1 explicitly; several do.

Setup order:

1. Enable the timer clock gate and the GPIO port gate.
2. Mux the pin to the timer's channel alternate function, set it push-pull, and pick an output speed appropriate to the PWM frequency.
3. Program PSC and ARR for the frequency; program CCR for the duty.
4. Select the PWM output-compare mode in the channel's mode register and enable the channel's output in the enable register.
5. Enable CCR preload (so duty changes are glitch-free) and ARPE.
6. Generate an update event, clear the update flag, then enable the counter.

Frequency choice: above ~20 kHz for anything audible (motors, solenoids, switching converters) so the whine is out of band; a few hundred Hz to a few kHz is plenty for LEDs, though flicker matters for anything a camera will film or a person will see in peripheral vision. Remember that frequency and duty resolution trade against each other through ARR.

**Center-aligned PWM for motor drive.** In a three-phase inverter, center-aligned PWM aligns the phase midpoints, which cancels much of the common-mode switching noise, puts the current-sense sampling point in a quiet window, and reduces the harmonic content compared to edge-aligned. It is the default choice for FOC and for anything where you sample current in the PWM period.

**Complementary outputs and dead-time (advanced timers only).** A half-bridge needs the high-side and low-side switches to be exact inverses — except that MOSFETs turn off more slowly than they turn on, so a naive inversion has both on briefly and shoots current straight through the bridge. Advanced timers generate the complementary pair in hardware with a programmable dead-time inserted on both transitions. Compute the dead-time from the FET turn-off delay plus the gate-driver propagation mismatch plus margin; verify it on a scope with a current probe before applying full bus voltage. Also configure the **break input** so an over-current or fault comparator forces both outputs to the safe state in hardware — this must not depend on software reacting in time. The main output enable (a separate bit on advanced timers) must be set, or the channels stay dark no matter how correct the rest is.

**Updating duty from an ISR.** With CCR preload enabled, writing CCR at any time is safe: the value latches at the next update event, so the pulse currently being emitted is never truncated. Write the whole value with a single 32-bit store; do not read-modify-write it. If several channels must change coherently (three-phase), write them all within one period — or drive them from DMA on the update event so the hardware does the coherent swap. Keep the arithmetic out of the ISR: compute duty in the control loop, store, and let the ISR copy.

## Input capture and encoder mode

**Input capture** latches the counter value into CCR on a selected edge of an input pin, and can raise an interrupt or DMA request. Because the latch is in hardware, the measurement has no interrupt-latency jitter — the ISR only has to read the already-captured number.

- **Period / frequency**: capture rising edges; the period is the difference between consecutive captures. Frequency is the timer counter frequency divided by that.
- **Pulse width / duty**: use two channels mapped to the same input (PWM input mode on STM32), one on each edge; one CCR gives the period, the other the high time.
- **Time of flight** (ultrasonic, lidar): start the counter on the trigger, capture on the echo edge.

**Overflow between captures is the main pitfall.** If the input is slower than one counter period, the raw difference is meaningless. Fixes, in order of preference: widen the time base (32-bit counter, or a larger prescaler at the cost of resolution); or count update events in the update ISR and compose a wide timestamp as `(overflows << width) + capture`. If you do the latter, handle the race where an overflow occurs between the capture and the ISR read — compare the captured value against the current counter, or check the update flag, and adjust the overflow count accordingly. Getting this wrong produces a measurement that is occasionally one whole period out, which looks like noise.

Also watch:

- **Over-capture**: if a second edge arrives before you read CCR, the old value is lost and an over-capture flag is set. Check that flag; it tells you the reading rate is too low and the data cannot be trusted.
- **Input filter**: capture inputs have a digital filter field — the edge is only accepted after N consecutive agreeing samples at a chosen sampling frequency. Use it for mechanical or noisy signals instead of debouncing in software; it costs nothing and adds a known, bounded delay.
- **Input prescaler**: capture every 1st, 2nd, 4th or 8th edge. Useful for high-frequency inputs where capturing every edge would flood the CPU; divide the computed period accordingly.

**Encoder mode** wires two channels to a quadrature encoder's A and B lines and lets the timer count edges with direction decoded from the phase relationship. The counter *is* the position — read it whenever you want, with no edge-counting ISR and no missed counts at high speed. Configure the input filters (encoders are electrically noisy), set ARR to the counts-per-revolution if you want automatic wrapping at a mechanical revolution, and handle the index/Z pulse separately if you need an absolute reference. For velocity, sample the counter on a fixed tick and take the difference with the wraparound-safe subtraction above.

## Timer-triggered peripherals

A timer can emit a **trigger output (TRGO** — STM32 naming) on an update event, a compare match, or on enable. That trigger can be routed internally to start an ADC conversion, kick a DAC output, or raise a DMA request — with no CPU involvement at all.

Use it whenever a peripheral must run at a precise rate:

- **ADC sampling.** Software-triggered conversions inherit every scrap of interrupt latency and main-loop jitter. Jitter in the sampling instant is indistinguishable from noise in the sampled signal, and it wrecks any FFT or control loop. A timer-triggered ADC samples at exactly the programmed rate. For current sensing in a motor drive, trigger from a compare match placed in the quiet part of the PWM period.
- **DAC waveform output.** Timer update → DMA request → next sample from a buffer. Arbitrary waveforms at an exact rate with zero CPU load.
- **Periodic DMA transfers.** Strobing a parallel bus, refreshing a display, bit-banging a protocol at fixed timing.
- **Timer chaining.** One timer's TRGO can be another's clock or trigger, giving effective counter widths and periods beyond what one timer provides.

Design rule: **if you find yourself polling in a loop to make something happen at a regular interval, check whether a timer trigger can do it in hardware.** The hardware path is more accurate, lower power (the CPU can sleep), and removes a whole class of latency bugs.

## Checklists

**GPIO bring-up**

- [ ] Peripheral clock gate enabled, with a read-back or barrier, before the first register access
- [ ] Multi-bit fields cleared before being set — not just OR-ed
- [ ] Type, speed and pulls configured before the pin is switched to output or alternate function
- [ ] Initial output level written before the pin is enabled
- [ ] Output speed is the slowest that meets the signal's timing requirement
- [ ] Open-drain selected for every shared or wired-OR line; pull-ups sized for the bus
- [ ] Alternate-function number taken from the datasheet table for *this* part and package
- [ ] Unused and analog pins set to analog mode
- [ ] All runtime pin changes go through the atomic set/clear register, never `|=` on the output register
- [ ] Mechanical inputs debounced (5-20 ms) in a periodic context, not in an ISR busy-wait
- [ ] Safety-critical pin configuration locked

**Timer bring-up**

- [ ] Timer clock gate enabled; timer input frequency derived with the APB doubling rule applied (STM32)
- [ ] PSC chosen as the smallest value that keeps ARR in range — resolution pushed into ARR
- [ ] PWM duty resolution (ARR+1 steps) meets the application requirement
- [ ] Both PSC and ARR written as "value minus one"
- [ ] Update event generated in software after configuration, and the update flag cleared before the interrupt is enabled
- [ ] ARPE and CCR preload enabled wherever period or duty changes at runtime
- [ ] Update flag cleared at the top of every timer ISR, with the write retired before return
- [ ] Capture paths handle counter overflow between captures, and check the over-capture flag
- [ ] Capture input filter and prescaler configured for noisy or fast inputs
- [ ] Advanced timer: dead-time computed from real FET timing, break input configured, main output enable set
- [ ] Periodic ADC/DAC/DMA work driven from a timer trigger rather than software polling
- [ ] Measured period and duty verified on a scope at least once per board revision

Sources: see the Sources section of ../SKILL.md (Bare-Metal Embedded C Programming; Insider's Guide to Arm Cortex-M Development; Embedded Systems Architecture, 2nd ed.). Per-chapter attribution was not recorded for this file.
