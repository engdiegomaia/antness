# Clocks and Low-Power Design on Cortex-M

Read this when bringing up the clock tree, changing the system frequency at runtime, or cutting the energy budget of a battery-powered Cortex-M product.

## Contents

- [The clock tree](#the-clock-tree)
- [Clock gating: no clock, no registers](#clock-gating-no-clock-no-registers)
- [The clock-up sequence and why the order is fixed](#the-clock-up-sequence-and-why-the-order-is-fixed)
- [Everything derived from the clock must be recomputed](#everything-derived-from-the-clock-must-be-recomputed)
- [Clock security, MCO, and accuracy requirements](#clock-security-mco-and-accuracy-requirements)
- [Power management techniques and race-to-sleep](#power-management-techniques-and-race-to-sleep)
- [The low-power mode ladder](#the-low-power-mode-ladder)
- [WFI, WFE and the lost-wakeup race](#wfi-wfe-and-the-lost-wakeup-race)
- [Practical low-power engineering](#practical-low-power-engineering)
- [Measuring power](#measuring-power)
- [Budgeting battery life](#budgeting-battery-life)
- [Checklists](#checklists)

Naming note: register names here (RCC, PWR, FLASH_ACR LATENCY, HSI/HSE/LSI/LSE, EXTI) are STM32 examples. Every vendor has the same blocks under different names — NXP calls it SCG/CCM and SMC, Nordic has CLOCK plus the automatic POWER/system-off model, TI has PRCM/SysCtl, RP2040 has `clocks`/`pll_sys`/`xosc` plus the `SLEEP_EN` gate registers. The ordering rules below are architectural, not vendor-specific.

## The clock tree

Think of it as: **sources → PLL → system clock mux → bus prescalers → per-peripheral gates**.

### Oscillator sources

| Source | Typical accuracy | Start-up | Use it for |
|---|---|---|---|
| Internal fast RC (HSI) | percent-level, drifts with temperature and supply | fast — microseconds | boot, fallback, anything that tolerates loose timing |
| External crystal (HSE) | tens of ppm | slow — hundreds of microseconds to milliseconds | USB, CAN, RF, precise timebases |
| External clock input (bypass mode) | whatever drives it | immediate | board where another chip distributes a clean clock |
| Internal slow RC (LSI) | poor, tens of percent over temperature | fast | watchdog, coarse RTC wake-ups |
| External slow crystal (LSE, usually 32.768 kHz) | tens of ppm | very slow — up to a second | calendar RTC, long sleep intervals that must not drift |

A crystal is a *component you can get wrong*. It needs the load capacitors the crystal datasheet specifies (derived from its load capacitance minus board stray), a drive level the oscillator can sustain, and a clean layout. A crystal that is mis-loaded, cracked, or badly soldered will simply never report ready. Boot code must survive that — see the fallback rule below.

### PLL

A typical Cortex-M PLL is a chain: **input divider M → VCO multiplier N → output dividers P / Q / R**.

- M brings the source down to the PLL *reference* frequency. The silicon specifies a legal window for it (often around 1–2 MHz); outside it the PLL may not lock or will lock with poor jitter.
- N multiplies the reference up to the *VCO* frequency, which also has a legal window (often a few hundred MHz).
- P, Q, R divide the VCO down to independent outputs — typically P for the system clock, Q for a 48 MHz USB/SDIO clock, R for an extra domain.

The two windows are what make most arithmetically-correct settings illegal: a combination that yields the right final frequency but puts the reference or the VCO outside its window is invalid even though the division works out. Use the vendor's clock-configuration tool or a validated table; verify against the datasheet rather than inventing M/N/P by hand. Check your datasheet for the actual windows — they differ per family and per voltage scale.

### Bus prescalers

The PLL output feeds a system clock that is then divided per bus: a core/AHB prescaler, and one or more peripheral bus prescalers (APB1, APB2 on STM32). **Each bus has its own maximum**, and the slow peripheral bus is usually capped well below the core. Two consequences:

- A frequency change must not transiently overrun a bus. Set the prescalers to safe values *before* raising the source frequency.
- Timers hanging off a prescaled bus often get a ×2 multiplier on their clock when the bus prescaler is not 1. That asymmetry is a classic source of "my PWM is half the frequency I computed". Read the clock-tree diagram in the reference manual, not just the register descriptions.

## Clock gating: no clock, no registers

Every peripheral sits behind an enable bit in a clock enable register (RCC AHBxENR / APBxENR on STM32; `SLEEP_EN`/`CLK_ENABLE` equivalents elsewhere). The hard rule:

> **A peripheral's registers are not writable — often not even readable — until its clock is enabled.** Writes are silently dropped or the access faults.

This is the single most common bring-up bug. Symptoms: a GPIO configuration that reads back as zero, a UART that never transmits, a peripheral whose registers all read 0x00000000. Before debugging the driver, confirm the gate bit.

Two further details that bite:

- Some buses need a short delay (or a read-back of the enable register) after setting the gate before the first peripheral access. Read back the enable register; that also acts as the barrier.
- Enabling a clock does not release the peripheral from reset on all parts. If a peripheral behaves as though it has stale state, check the separate reset register.

Gating is also your first power lever: every enabled clock line costs current whether the peripheral is used or not. Disable the gates for everything you are not using.

## The clock-up sequence and why the order is fixed

```c
/* Skeleton — register names are STM32-style examples. */
clock_up(void)
{
    /* 1. Run from the internal RC while we reconfigure everything else. */
    enable_hsi(); wait_for(HSIRDY);
    select_sysclk_source(HSI); wait_until_sws_reports(HSI);

    /* 2. Bring up the new source WITH A BOUNDED TIMEOUT. */
    enable_hse();
    if (!wait_for_with_timeout(HSERDY, HSE_TIMEOUT)) {
        disable_hse();
        return clock_up_fallback_hsi();   /* a dead crystal must not brick us */
    }

    /* 3. Raise the regulator voltage scale if the target frequency needs it. */
    set_voltage_scale(SCALE_FOR(target_hz)); wait_for(VOS_READY);

    /* 4. Flash FIRST, going up: more wait states + prefetch/ART, before the clock rises. */
    flash_set_latency(wait_states_for(target_hz, vdd));
    flash_enable_prefetch_and_caches();
    read_back(FLASH_ACR);                  /* confirm the latency actually took */

    /* 5. Prescalers so no bus exceeds its max at the new SYSCLK. */
    set_ahb_prescaler(...); set_apb1_prescaler(...); set_apb2_prescaler(...);

    /* 6. Configure and start the PLL, then wait for lock. */
    configure_pll(m, n, p, q); enable_pll(); wait_for(PLLRDY);

    /* 7. Switch, and CONFIRM the switch by polling the status field. */
    select_sysclk_source(PLL);
    wait_until_sws_reports(PLL);

    /* 8. Publish the new frequency and re-derive everything from it. */
    SystemCoreClock = target_hz;
    reconfigure_clock_derived_peripherals();
}
```

Why each step exists:

- **Run from the RC first.** You cannot reconfigure the PLL while the system clock is sourced from it. Parking on the always-available internal RC makes the rest of the sequence safe.
- **Bounded timeout on the external source.** An unbounded `while (!(RCC_CR & HSERDY));` turns a cracked crystal, a cold-solder joint, or a wrong load cap into a product that hangs before reaching `main()` — with no UART, no LED, no watchdog kick, and no way to field-diagnose it. Spin a bounded number of iterations, then fall back to the internal RC at a reduced frequency, set a status flag the application can report, and keep running. This is the difference between a degraded unit and an RMA.
- **Voltage scale before frequency.** High frequency ranges require the core regulator at a higher scale; raising the clock first means running the logic below its required voltage. Going down, lower the frequency first and the scale afterwards.
- **Flash wait states before the clock, and only after the clock on the way down.** Flash is far slower than the core. The wait-state (latency) field tells the flash controller how many stall cycles to insert per access. Raise the clock with too few wait states and the core latches instruction words before the flash has driven them: you execute garbage, which usually ends in a HardFault, sometimes in something worse than a fault. The rule is symmetric and easy to get backwards:
  - **Clocking up:** latency **up** first, then frequency up.
  - **Clocking down:** frequency **down** first, then latency down.
  Always read `FLASH_ACR` back and confirm the latency field equals what you wrote before touching the clock — the write can be ignored if the value is unsupported. Enable prefetch and the instruction/data caches (ART on STM32) at the same time; at high wait-state counts they are the difference between the claimed MIPS and half of it.
- **Prescalers before the switch.** The instant the mux moves to the PLL, every bus sees the new frequency divided by its current prescaler. If APB1 is still at /1 from the previous low-frequency configuration, it will be driven far beyond its rating for as long as it takes you to fix it. Set the dividers conservatively first; you can relax them after the switch if the numbers allow.
- **Confirm the switch.** Writing the source-select field is a request. The hardware moves the mux only when the target source is stable, and it silently ignores a request for a source that is not ready. Poll the status field (SWS) until it reports the source you asked for; otherwise you will proceed believing you are at 168 MHz while still running at 16 MHz, and every derived timing will be wrong by an order of magnitude.

## Everything derived from the clock must be recomputed

Changing the system clock invalidates every divider computed from the old frequency. If you change the clock and nothing else, the system keeps running — it just lies about time and garbles every bus. Re-derive, in this order:

| Derived from the clock | What happens if you forget |
|---|---|
| `SystemCoreClock` / `cpu_freq` global | every later computation uses the stale value; the bug propagates everywhere |
| SysTick reload (`SysTick_Config` or `RVR = f/1000 - 1`) | the millisecond tick runs at the wrong rate; all delays and RTOS scheduling scale wrongly |
| UART baud-rate divisors | **the classic one** — "I raised the clock and my console turned to garbage"; the UART is now transmitting at ~10× the configured baud |
| Timer prescalers and auto-reload | PWM frequency, input capture scaling and timeout periods all shift |
| ADC prescaler | ADC clock exceeds its max, sampling becomes nonlinear or the conversions are junk |
| SPI baud divider, I2C timing registers | SCK/SCL out of the slave's spec; on I2C the timing register encodes rise/fall times, not just a divider |
| Any software busy-wait calibrated in loop iterations | delays change by the frequency ratio — one reason not to use calibrated loops |
| USB / SDIO / RNG clock from the PLL Q output | enumeration fails, cards do not initialise |

The clean pattern is a single `clock_apply(freq)` that sets the clock and then calls each peripheral's `reconfigure(SystemCoreClock)`, so no caller can change the clock without re-deriving. Peripherals that are mid-transaction should be quiesced first.

## Clock security, MCO, and accuracy requirements

**Clock security system.** Most Cortex-M parts can monitor the external oscillator while running (CSS on STM32; equivalent monitors elsewhere). If the crystal stops — shock, cold, a failed solder joint — the hardware switches the system clock back to the internal RC and raises a **non-maskable interrupt**. Enable it on any product that depends on the external source, and implement the NMI handler: it must clear the failure flag, record the event, bring the system to a safe state (stop PWM to a motor, mute the amplifier, drop CAN off the bus) and then either re-attempt the crystal or stay on the RC at reduced capability. An unimplemented NMI handler that loops forever turns a recoverable clock failure into a hang.

**MCO.** The clock-out pin lets you route HSI, HSE, SYSCLK, PLL output or the LSE to a GPIO through a small divider. Put a scope on it and measure the real frequency. This answers, in seconds, the questions that otherwise consume an afternoon: did the PLL lock at the value I think? is the crystal actually oscillating? is it at the right frequency or off by the wrong load caps? Divide the output so the pin and your probe can follow it.

**Accuracy requirements by use.** Pick the source from the tightest consumer on the board:

| Consumer | Requirement | Implication |
|---|---|---|
| USB full-speed device | 48 MHz within roughly ±0.25 % | crystal, or the internal RC trimmed by a clock-recovery system (CRS) locked to USB SOF; untrimmed RC will not enumerate reliably |
| CAN / CAN FD | bit timing must agree with every other node across temperature; budget is tight and shrinks as bit rate rises | crystal, and compute the bit-timing segments properly rather than copying another board's values |
| Ethernet RMII/MII | ±50 ppm class | crystal or an external clock from the PHY |
| RF transceivers | part-specific, usually tight ppm | dedicated crystal, often the radio's own |
| UART | roughly 2 % total error between the two ends | internal RC is usually fine at moderate baud; at high baud and over temperature, less so |
| Calendar RTC | drift the user will notice; a few seconds per day comes from ~30 ppm | LSE crystal, never LSI |
| Watchdog, coarse wake-ups | order-of-magnitude is enough | LSI is the right choice — it keeps running when everything else is off |

## Power management techniques and race-to-sleep

Four levers, coarsest to finest:

1. **Clock gating** — turn off the clock to unused peripherals and unused clock domains. Cheap, reversible, no state lost. The PLL itself is one of the most power-hungry blocks on the die, and the larger the multiplication factor from a slow source, the more it costs.
2. **Power gating** — remove supply from a block or an external device entirely, so it draws nothing (not even leakage). On-chip this is the power-domain control in the PMU; off-chip it is a MOSFET switched by a GPIO. Design the switch so the default, undriven state is *off*, held by a passive, so a reset or an un-initialised GPIO cannot leave the load powered.
3. **Dynamic voltage and frequency scaling (DVFS)** — run slower and at a lower core voltage when performance is not the bottleneck. Dynamic power scales roughly with frequency and with the square of voltage, so dropping the voltage scale is where the win is.
4. **Low-power modes** — stop the core, then the clocks, then the regulators. See the ladder below.

**The race-to-sleep rule.** For a fixed amount of work, finishing fast and going deep usually beats running slowly. The dynamic energy to execute an instruction is roughly fixed, so stretching the work over more time does not reduce it — but leakage, the regulator's quiescent draw, the brown-out detector and any peripheral kept alive all accrue *with time*. Running at half speed for twice as long therefore pays about the same dynamic energy and twice the static overhead.

The rule has two conditions, and both must hold:

- **The deep state must actually be reachable.** If something — a running peripheral, a DMA transfer, a debugger attachment, a clock you forgot to gate — prevents entry to the deep mode, racing just leaves you idling in Run.
- **The wake-up energy must be small relative to the work.** Each wake costs the oscillator and PLL start-up, the regulator ramp, and the re-initialisation code. If you wake every few milliseconds, that transition energy can exceed the work energy, and the right answer is to batch work and wake less often — or, for very short gaps, to stay in a shallow mode where the wake is nearly free.

DVFS still wins where the CPU is *not* the bottleneck: when the system is waiting on a slow sensor, a UART, or an I2C bus, the clock rate does not change the completion time, so lowering it is a pure saving. The practical shape is a small set of named power states (e.g. "performance", "power-save", "acquire") with a defined frequency, voltage scale and sleep mode each, and explicit transitions — not ad-hoc frequency changes scattered through the code, since each change costs the full re-derivation above.

## The low-power mode ladder

Vendor names vary wildly (Stop 0/1/2, Standby, Shutdown; VLPS/VLLS; System ON/OFF; DORMANT). The ladder is the same:

| Mode | Retained | Wakes on | Wake latency | Typical current | What your code must do on exit |
|---|---|---|---|---|---|
| **Run** | everything | n/a | n/a | mA to tens of mA, scaling with frequency | n/a |
| **Sleep** (WFI/WFE, SLEEPDEEP clear) | core registers, SRAM, all peripherals keep running | **any enabled interrupt**; DMA and peripherals continue in the background | a few CPU cycles | somewhat below Run — you save the core, not the peripherals or the PLL | nothing; execution resumes at the instruction after WFI |
| **Stop / deep sleep** (SLEEPDEEP set, power-down bit clear) | SRAM and CPU register content; peripheral configuration | only the always-on sources: EXTI lines (incl. GPIO edges), RTC alarm/wake-up timer, independent watchdog, some comparators | microseconds to tens of microseconds — more if flash was powered down or the regulator was in its lowest-leakage setting | hundreds of µA down to single-digit µA, part-dependent | **clear SLEEPDEEP**, clear the wake-up flag, **and reconfigure the clock tree — the system came back on the internal RC with the PLL off**, then re-derive every divider and re-enable any interrupt you masked |
| **Standby** | nothing except the backup domain (RTC, backup registers, a few retention bytes) — SRAM and CPU registers are **lost** | wake-up pin, RTC alarm/wake-up timer, independent watchdog reset, external reset | milliseconds — it is a full boot, so start-up code time adds to the silicon's wake time | single-digit µA down to sub-µA | **nothing resumes** — execution restarts at the reset handler. Read the standby/wake-up flags early in `main()` to distinguish a wake from a cold boot, clear them, and restore state from backup registers or non-volatile storage |
| **Shutdown / off** | backup domain only, and even the backup regulator may be off | typically only the wake-up pin and an external reset; sometimes RTC if the backup domain is kept alive | milliseconds, full boot plus a brownout-style ramp | nanoamps to hundreds of nA | same as Standby; nothing survives but what you wrote to non-volatile memory |

Check your datasheet for actual current figures — they vary by an order of magnitude between families, and by a factor of several within a family depending on voltage, temperature, and which retention options you selected.

Choosing between them:

- **Sleep** for the idle time inside an interrupt-driven application: make your main loop `while (1) { handle_work(); WFI(); }`. This is free money and costs nothing in complexity.
- **Stop** for inactivity from milliseconds to seconds, when you still want asynchronous responsiveness (a button, an incoming edge, a sensor's data-ready line) and you want to resume exactly where you were. It is the most flexible deep mode because almost any configurable event can wake it.
- **Standby** for long, scheduled inactivity — minutes to hours between an RTC-driven sensor read. Use it only when a valid wake path exists in the *hardware* design (the wake-up pin is routed, the RTC has a usable clock source) and when the application can rebuild its state from scratch.
- **Shutdown** for shelf mode, shipping mode, or a product that only ever wakes on a physical button.

The traps, in order of how often they are hit:

1. **Stop reverts the system clock to the internal RC.** The PLL is off when you come back. If you do not call your clock-up sequence on exit, you are running at a fraction of the intended speed with every divider computed for the old frequency. Symptoms look like a timing bug, not a power bug.
2. **Standby is a reset, not a return.** The `WFI` never returns. Code written as if it will — "sleep, then continue" — is wrong.
3. **Peripherals needed for wake must stay clocked.** The wake source's clock domain must survive the mode you are entering. In Standby, GPIO controllers are off: an EXTI button event is not a wake source there; the dedicated wake-up pin is.
4. **The wake-up flag latches.** Clear it before entering the mode and again after waking, or the next entry returns immediately.

## WFI, WFE and the lost-wakeup race

`WFI` suspends until an interrupt (or a debug event) arrives. `WFE` suspends until the **event register** is set — by an explicit `SEV`, by a configured EXTI event, or by an interrupt that reaches the NVIC. The event register is a one-bit sticky latch: if an event arrived *before* the `WFE`, the instruction consumes the latch and returns immediately without sleeping. That is a feature, and it is what makes the following idiom safe.

The race: you check a flag, decide to sleep, and the interrupt that would have set the flag fires in the window between the check and the `WFI`. You sleep anyway, and nothing will wake you until the *next* event — which may never come.

The standard sleep-safe idiom relies on a specific Cortex-M property: **a pending interrupt wakes WFI even when PRIMASK masks it.** So you mask interrupts, re-check the condition with no race window, and sleep inside the critical section:

```c
/* Sleep-safe idle. work_pending is set by an ISR and declared volatile. */
__disable_irq();                 /* PRIMASK = 1; an IRQ arriving now stays pending */
if (!work_pending) {
    __DSB();
    __WFI();                     /* a pending IRQ still wakes us, masked or not */
}
__enable_irq();                  /* the pending handler runs here, exactly once */
/* ... handle work_pending ... */
```

If the interrupt fires before `__disable_irq()`, the flag is already set and we skip the sleep. If it fires after, it stays pending, wakes the `WFI`, and runs the moment PRIMASK clears. There is no window.

Related controls:

- **`SEVONPEND`** (SCR): with it set, any interrupt becoming pending generates an event, so it wakes a `WFE` even if that interrupt is disabled in the NVIC. Use it when you want NVIC-disabled sources to act as pure wake-ups without running handlers.
- **`SLEEPONEXIT`** (SCR): the core re-enters sleep automatically on return from the last active handler, instead of going back to thread mode. For a purely interrupt-driven application this removes the main loop entirely and closes the race by construction — but it also means your thread-mode code never runs again, so set it only once everything is initialised.
- **`SLEEPDEEP`** (SCR): selects *which* mode `WFI`/`WFE` (and `SLEEPONEXIT`) enter. Clear → Sleep. Set → the deep mode selected by the PWR control register (Stop vs Standby, plus the regulator options). Clear it immediately on wake, or an unrelated later `WFI` in your idle loop will drop the system into Stop.
- Masking an interrupt in the NVIC while using `WFE` filters it out as a wake source; it stays pending and runs once you are back in Run mode.

## Practical low-power engineering

- **Replace busy-wait loops with sleep.** `while (!(GPIOx->IDR & PIN));` holds the CPU at full power for the entire wait. Use an EXTI edge interrupt and sleep. Where a device genuinely only supports polling, poll from a timer interrupt at a rate matched to the device, and sleep in between. The one legitimate busy-wait is the ready-flag poll on an on-chip block you just enabled (oscillator ready, PLL lock, regulator ready) — those have a documented bounded latency of a few cycles to a few hundred microseconds. Anything whose latency depends on the outside world gets an interrupt and a timeout.
- **Batch work and wake on a period.** Ten sensor reads buffered and transmitted in one radio burst cost far less than ten wake/transmit/sleep cycles, because each cycle pays the full oscillator start-up, PLL lock and radio ramp. Choose the wake period from the energy budget, not from habit.
- **Configure every unused GPIO.** A floating input sits near the switching threshold and the input buffer's Schmitt trigger oscillates, burning current continuously on every such pin. Set unused pins to analog mode (input buffer disabled — the cheapest state on most parts) or to input with a pull. "Unused" includes pins on a package you did not bond out in your design but which still exist in the die's power model, and pins on a module whose function you later removed.
- **Mind the pulls you do use.** Any pull-up on a bus that idles low — or a pull-down on one that idles high — burns V/R continuously. I2C pull-ups are the usual offender: with two 2.2 kΩ pull-ups, a bus held low draws milliamps. Either raise the resistor values to the maximum the bus timing allows, or power the pull-up rail from a GPIO and switch it off between transactions.
- **Disable the debug-in-low-power bits.** The debug block defaults, on many parts, to keeping clocks alive in Sleep/Stop/Standby so the debugger stays attached. That is convenient during development and costs milliamps — enough to completely mask your optimisation. Clear those bits in production builds, and never trust a power measurement taken with a debugger attached.
- **Account for what runs regardless.** The regulator's own quiescent current, the brown-out detector, the independent watchdog and its low-speed oscillator, and the RTC all draw during deep sleep. On a sub-µA budget these are not rounding errors — they can be most of the floor. Some parts let you disable the BOD in low-power modes; weigh that against the reset guarantee you lose.
- **External components usually dominate.** A sensor left powered, a status LED at a few mA, a pull-up network, a level shifter, an always-on regulator for a peripheral rail — any of these dwarfs the MCU's sleep current. Measure the whole board and go after the biggest term first. Switch external loads with a MOSFET from a GPIO, and remember that leakage paths through signal lines (a serial bus still driven high into a powered-down device) keep drawing even when the supply is cut; catch these in prototyping.
- **Gate aggressively, un-gate explicitly.** Disable peripheral clocks you are not using, including the ones a vendor startup file enabled for you.

## Measuring power

Do not estimate. The gap between the predicted and measured figure is routinely an order of magnitude, and it is always caused by something no spreadsheet captured.

- **An ammeter in series** gives you an average. It tells you nothing about the shape of the duty cycle, and it will under-report peaks that matter for the battery's internal resistance.
- **A low-side shunt plus an oscilloscope** is the practical lab method: a small series resistor (a few ohms — large enough to produce a readable voltage, small enough that the IR drop does not disturb the supply) with the scope on the voltage across it. You see the entire profile: the wake-up transient, the active burst, the radio spike, the sleep floor. Use a differential probe or a current probe if the shunt is high-side.
- **A purpose-built energy measurement header** on the board — or the jumper most development kits provide for exactly this — lets you isolate the MCU and its rails from the on-board debug circuitry, which otherwise shares the USB supply and swamps everything you are trying to measure.
- **Integrate over a full duty cycle**, not over a convenient window. The number that determines battery life is charge per cycle (µA·h or mA·s), divided by the cycle period. A scope-captured current waveform integrated over one complete wake/work/sleep cycle gives you this directly; an average-current reading over an arbitrary interval does not.
- Instrument a spare GPIO: toggle it on entry to each power state and capture it alongside the current trace. You can then attribute each segment of the energy to a state in your design, which is the only way to know which one to attack.

## Budgeting battery life

Build the budget as a weighted sum over one duty cycle. For each state *i* with current *Iᵢ* and duration *tᵢ* in a cycle of period *T*:

```
I_avg = ( Σ (I_i · t_i) + E_wake_transitions / V ) / T
```

In practice:

1. List the states: active-compute, peripheral-active (radio TX, sensor powered), sleep, deep sleep. Include the external loads that are on during each.
2. Get *Iᵢ* from measurement, not datasheet typicals — datasheet figures are at a specific voltage and temperature with everything else off.
3. Add the transition energy per wake: oscillator start-up plus PLL lock plus regulator ramp plus re-initialisation code, each at its own current for its own duration. At high wake rates this term can dominate; if it does, that is your answer — wake less often.
4. Divide by the cycle period to get average current, then `life_hours ≈ capacity_mAh / I_avg_mA`.
5. **Sanity-check against self-discharge.** A coin cell loses a few percent of its capacity per year on the shelf; alkaline and lithium primaries vary widely. If your computed life exceeds the cell's shelf life, the chemistry is your limit, not your firmware — and further optimisation buys nothing. Also derate for temperature, for the usable fraction of capacity above your brown-out threshold, and for the cell's ability to supply your peak current (a coin cell's internal resistance can collapse the rail during a radio burst, which is a design problem a bulk capacitor fixes).

## Checklists

**Clock bring-up**

- [ ] External source has a bounded timeout and a tested fallback to the internal RC
- [ ] PLL reference and VCO frequencies are inside the documented windows
- [ ] Voltage scale raised before the frequency (and lowered after it, going down)
- [ ] Flash wait states raised before the clock; prefetch/caches enabled; `FLASH_ACR` read back
- [ ] Bus prescalers set so no bus exceeds its maximum during or after the switch
- [ ] The source switch is confirmed by polling the status field, not assumed
- [ ] `SystemCoreClock` updated and every derived divider re-computed
- [ ] Clock security enabled and the NMI handler implemented, if an external source is relied on
- [ ] Real frequency verified on MCO with a scope at least once per board revision

**Low-power bring-up**

- [ ] Every unused GPIO set to analog or input-with-pull
- [ ] Unused peripheral clocks gated off
- [ ] Debug-in-low-power bits cleared in production builds; measurements taken with the debugger detached
- [ ] Idle loop uses the mask / re-check / WFI idiom; `SLEEPDEEP` cleared on every wake
- [ ] Wake-up flags cleared before entry and after exit
- [ ] Stop-mode exit path calls the full clock-up sequence
- [ ] Standby entry has a verified hardware wake path, and `main()` distinguishes wake from cold boot
- [ ] State needed across Standby is in backup registers or non-volatile memory
- [ ] Budget built from measured currents integrated over a full duty cycle, sanity-checked against cell self-discharge

Sources: see the Sources section of ../SKILL.md (Bare-Metal Embedded C Programming; Insider's Guide to Arm Cortex-M Development; Embedded Systems Architecture, 2nd ed.). Per-chapter attribution was not recorded for this file.
