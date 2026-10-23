# ADC, RTC and Watchdog at Register Level

Read this when you are bringing up analog acquisition, a calendar/backup domain, or a watchdog on a bare-metal Cortex-M part and need the ordering constraints and the failure modes, not just the register names.

## Contents

- [ADC fundamentals](#adc-fundamentals)
- [ADC bring-up order](#adc-bring-up-order)
- [Sampling time: the single biggest cause of wrong readings](#sampling-time-the-single-biggest-cause-of-wrong-readings)
- [Conversion modes, groups and flags](#conversion-modes-groups-and-flags)
- [Triggering, DMA and overrun](#triggering-dma-and-overrun)
- [Noise and accuracy practice](#noise-and-accuracy-practice)
- [ADC portability trap: newer STM32 families](#adc-portability-trap-newer-stm32-families)
- [RTC: the backup domain](#rtc-the-backup-domain)
- [RTC: clock source and prescalers](#rtc-clock-source-and-prescalers)
- [RTC: the write-unlock and init sequence](#rtc-the-write-unlock-and-init-sequence)
- [RTC: BCD and shadow-register coherency](#rtc-bcd-and-shadow-register-coherency)
- [RTC: alarms, wakeup timer, backup registers](#rtc-alarms-wakeup-timer-backup-registers)
- [RTC: calendar logic you must write yourself](#rtc-calendar-logic-you-must-write-yourself)
- [Watchdogs: choosing one](#watchdogs-choosing-one)
- [IWDG registers and sequence](#iwdg-registers-and-sequence)
- [Where to kick the dog](#where-to-kick-the-dog)
- [Reset-cause detection and debug freeze](#reset-cause-detection-and-debug-freeze)
- [Checklists](#checklists)

---

## ADC fundamentals

An N-bit ADC divides the input span into `2^N` intervals and reports which one the
sample fell into. Three numbers follow from that:

| Quantity | Formula | Note |
|---|---|---|
| Number of codes | `2^N` | 12-bit → 4096 codes, `0 .. 4095` |
| LSB / step size | `Vref / 2^N` | 12-bit at 3.3 V → 805 µV |
| Voltage from code | `Vin ≈ code * Vref / 2^N` | code is the *bottom* of its interval |

**The off-by-one.** People habitually write `code * Vref / (2^N - 1)`. For a
converter whose transfer function is "code = floor(Vin · 2^N / Vref)", the correct
divisor is `2^N`. The full-scale code `2^N - 1` then maps to `Vref·(2^N-1)/2^N`,
one LSB below Vref — which is right: the top code means "somewhere in the last
interval", not "exactly Vref". Using `2^N - 1` adds a systematic gain error of
one part in 4096 (0.024 % at 12 bits). That is negligible next to Vref error and
irrelevant for a potentiometer, but it is wrong, and in a ratiometric measurement
where the sensor and the ADC share the same reference it is the only error term
you control. Pick one convention, write it in a comment next to the macro, and
never mix the two in the same codebase.

**Vref dominates absolute accuracy.** Resolution buys you *granularity*, not
accuracy. A 16-bit converter running off a 3.3 V rail that sags 2 % under load is
less accurate in absolute terms than a 10-bit converter with a 0.1 % external
reference. Decide first whether your measurement is:

- **Ratiometric** — the sensor is a divider powered from the same rail that feeds
  Vref (potentiometer, resistive bridge, ratiometric Hall sensor). Rail drift
  cancels. Use the MCU rail as Vref and do not buy a precision reference.
- **Absolute** — thermocouple, battery voltage, 4-20 mA shunt, anything compared
  to a physical unit. Rail drift goes straight into your answer. Use a dedicated
  reference, or measure the internal bandgap channel and back-compute Vref
  (see [Noise and accuracy practice](#noise-and-accuracy-practice)).

**Single-ended vs differential.** Single-ended measures pin-to-ground, so any
ground offset between the sensor's ground and the MCU's ground is added to your
signal. Differential measures the difference of two pins and rejects the common
mode — use it for bridges, current-shunt sense, and anything with a long cable.
Most classic STM32F4-class ADCs are single-ended only; differential inputs appear
on the newer L4/G4/H7 ADC. Check your reference manual before promising a
differential channel.

**ENOB vs nominal bits.** The datasheet number on the box is the *nominal*
resolution. Effective number of bits (ENOB) accounts for noise, INL/DNL and
distortion and is typically 1.5-3 bits lower on an MCU-integrated converter. A
"12-bit" MCU ADC that gives you 10 noise-free bits in a real board is normal. Do
not design a control law that needs the bottom two codes to mean something.

## ADC bring-up order

The order matters. Peripherals that are not clocked ignore writes silently, and a
pin left in digital input mode will quietly corrupt your readings.

1. **Enable the GPIO port clock** (`RCC_AHB1ENR` on STM32F4).
2. **Put the pin in analog mode** — `MODER = 0b11` for that pin on STM32. This is
   not the same as input mode. Analog mode disconnects the Schmitt-trigger input
   buffer. Leaving the digital buffer enabled on an analog pin means the buffer
   sits at its switching threshold, draws crowbar current, injects that current
   back into your source impedance, and in low-power modes it is also a
   measurable standby-current leak. Also clear any pull-up/pull-down
   (`PUPDR = 0`): a 40 kΩ pull-up across a 10 kΩ sensor is a 20 % gain error.
3. **Enable the ADC peripheral clock** (`RCC_APB2ENR` on STM32F4).
4. **Set the ADC clock prescaler** so the ADC clock stays inside the datasheet's
   min/max — on STM32F4 this is the shared `ADC_CCR.ADCPRE` field, common to all
   ADC instances on the die, so you cannot give ADC1 and ADC2 different clocks.
   Too fast and the comparator does not settle (missing codes, nonlinearity); too
   slow and the sample-and-hold capacitor droops. Both limits are in the
   datasheet, not the reference manual.
5. **Choose resolution** (`ADC_CR1.RES` on F4). Lower resolution shortens the
   conversion phase, which is how you trade accuracy for throughput.
6. **Choose sampling time per channel** (`ADC_SMPR1/SMPR2` on F4 — 3 bits per
   channel). See the next section; this is the step people get wrong.
7. **Build the sequence** (`ADC_SQR3/SQR2/SQR1` on F4 — 5 bits per slot, first
   conversion in `SQR3.SQ1`, and the sequence *length minus one* in `SQR1.L`).
   A length field left at 0 means "one conversion" — forgetting to set it when
   you add channels is why the second channel never appears.
8. **Enable the ADC** (`ADC_CR2.ADON` on F4) and **wait the stabilization time**
   from the datasheet (t_STAB) before the first conversion. A busy-loop delay is
   fine; skipping it makes the first few conversions garbage.
9. **Calibrate** if the part supports it (F0/L0/L4/G4/H7 have `ADC_CR.ADCAL`;
   classic F4 does not). Calibration must run with the ADC enabled-but-not-
   converting, per the reference manual.
10. **Start the conversion** (`ADC_CR2.SWSTART`, or let an external trigger do it).

## Sampling time: the single biggest cause of wrong readings

Before converting, the ADC closes a switch and charges an internal hold capacitor
through your source impedance plus the internal switch resistance. The sampling
window must be long enough for that RC to settle to within half an LSB:

```
t_sample >= (R_source + R_adc) * C_hold * ln(2^(N+1))
```

`R_adc` and `C_hold` are in the datasheet (typically a few hundred ohms and a few
pF to tens of pF). `ln(2^(N+1))` is about 9.0 for 12 bits — roughly nine time
constants.

Consequences you should internalize:

- **High-impedance sources need long sampling or a buffer.** A 100 kΩ divider
  feeding a 12-bit ADC with a 10 pF hold cap needs ~9 µs of sampling. If your
  SMPR setting gives you 0.5 µs, you will read low — the cap never gets there.
  Either select the longest SMPR value, lower the source impedance, add a local
  capacitor (0.1 µF to ground at the pin, which supplies the charge pulse), or
  put a rail-to-rail op-amp follower in front. The datasheet usually quotes a
  maximum recommended source impedance per sampling-time setting — use that
  table instead of doing the arithmetic, and do the arithmetic when the table
  does not cover your case.
- **This is the #1 cause of "my readings are wrong and the neighbouring channel
  bleeds in."** With one shared hold capacitor behind a mux, insufficient
  sampling time means the cap still carries residue from the *previous* channel
  when the conversion starts. A 3.3 V channel next to a 0 V channel will pull
  the 0 V reading up. It looks exactly like crosstalk; it is actually
  undersampling. Fix: longer SMPR on the high-impedance channels (you can set
  sampling time per channel — do so, do not use one value for all), lower source
  impedance, or deliberately discard the first conversion after a mux change.
- Sampling time is per channel. In a scan sequence, the total conversion time is
  the sum of `(t_sample + t_conv)` over every slot. Compute it before you promise
  a sample rate.

## Conversion modes, groups and flags

| Mode | STM32F4 control | Use it for |
|---|---|---|
| Single | `CR2.CONT = 0` | Event-driven or timer-paced single reads |
| Continuous | `CR2.CONT = 1` | Free-running on one channel, e.g. a pot |
| Scan | `CR1.SCAN = 1` + `SQRx` | A sequence of channels per trigger |
| Discontinuous | `CR1.DISCEN` + `DISCNUM` | Convert the sequence in sub-groups |
| Injected | `JSQR` + `CR2.JSWSTART` | High-priority interrupting conversions |

**Regular vs injected groups.** Regular channels are the ordinary sequence set by
`SQRx`, result in the single shared `ADC_DR`, flagged by `EOC`. Injected channels
are a separate, higher-priority group set by `ADC_JSQR`: starting an injected
conversion suspends the regular sequence, the results land in their own
`ADC_JDR1..JDR4` registers, and completion sets `JEOC`. Because injected results
have dedicated registers, they do not need DMA, which is exactly why you use them
for the measurement you cannot afford to lose — motor phase current synchronized
to a PWM edge, a cell voltage in a BMS — while a slow regular sequence grinds
through temperature and housekeeping channels in the background.

**EOC is cleared by reading DR.** On the classic STM32F4 ADC, `ADC_SR.EOC` is set
by hardware at the end of a regular conversion and cleared by hardware when you
read `ADC_DR` (or by writing 0 to the bit). This bites two ways:

- A debugger watch window or a stray `ADC1->DR` read in a logging statement clears
  the flag, and your polling loop hangs forever.
- In an `EOC` interrupt you must read `DR`, or the interrupt re-fires immediately
  and you never leave the handler.

**OVR** (`ADC_SR.OVR`) means a new result overwrote the previous one before
anything read it. In polled single-shot code you will never see it. You see it
when you move to interrupts or DMA and the consumer cannot keep up — a continuous
scan at a high ADC clock into an `EOC` ISR that does `printf` is the classic. OVR
is sticky: on many parts the ADC stops issuing DMA requests until you clear it,
so a one-time glitch becomes a permanently dead channel. Always handle OVR
explicitly: clear the flag, and either reduce the rate or reinitialize the DMA
stream. Silently ignoring it is how you ship "it works for ten minutes".

**Analog watchdog** (unrelated to the system watchdog): `CR1.AWDEN` plus high/low
threshold registers raise `AWD` and optionally an interrupt when a monitored
channel leaves a window. Use it for overcurrent/overvoltage trips without CPU
polling — it reacts in hardware, every conversion, with no software latency.

## Triggering, DMA and overrun

**Trigger from a timer, not from software, when timing matters.** `CR2.EXTSEL` +
`EXTEN` lets a timer's TRGO output start the conversion. Software-triggered
sampling inherits all the jitter of your main loop and your interrupt latency,
which smears the spectrum of anything you later FFT and ruins any control law
that assumes a fixed sample period. A timer TRGO gives you a sample instant
locked to the hardware clock. It also lets you *place* the sample: in a motor
drive, trigger on the PWM centre so you sample while the switches are quiet.

**Scan mode of multiple channels essentially requires DMA.** There is one
`ADC_DR`. In a scan, each conversion overwrites it, and the window in which you
can read result N before result N+1 lands is one conversion time. Polling cannot
win that race reliably, so you get OVR or silently shuffled channels. Configure
DMA in circular mode with as many transfers as there are sequence slots, and your
buffer index *is* the sequence position — provided nothing ever desynchronizes.
On STM32F4 set `CR2.DMA` and `CR2.DDS` (DMA disable selection) so requests keep
coming in continuous mode. If a channel's values ever appear in the wrong
buffer slot, you have had an unhandled overrun; fix the overrun, do not add a
heuristic to re-identify channels.

Injected channels are the escape hatch when you need two or three results and do
not want a DMA stream.

## Noise and accuracy practice

- **Oversample and decimate.** Averaging `4^k` samples and shifting right by `k`
  buys `k` extra effective bits, *if* the noise is at least ~1 LSB RMS and
  roughly white. 16 samples → +2 bits. Free, deterministic, and it costs
  latency. This is the first thing to try when the last two codes dance.
- **Median then IIR.** A 3- or 5-point median kills impulsive noise (a switching
  spike) that an average only smears; follow it with a one-pole IIR
  (`y += (x - y) >> k`) for the slow drift. Use integer arithmetic; a float IIR
  on a Cortex-M0 is a waste.
- **Discard the first conversion after a mux change.** Cheap, and it covers the
  residual-charge case from the sampling-time discussion.
- **Measure the internal reference channel to calibrate Vref drift.** Parts with
  an internal bandgap channel (`VREFINT`) and a factory-programmed calibration
  value let you compute the actual Vref:
  `Vref_actual ≈ Vref_cal_nominal * VREFINT_CAL / VREFINT_measured`. Convert
  every other channel using that, and your absolute accuracy stops depending on
  the rail. The internal temperature channel works the same way, and needs a very
  long sampling time — it has high source impedance by construction.
- **Layout and decoupling.** Decouple VDDA/VREF+ with 100 nF close to the pin plus
  a bulk capacitor; ferrite-bead VDDA from VDD if the digital rail is noisy. Keep
  analog traces short and away from switching nodes. Give the analog ground a
  single, deliberate tie to digital ground. None of the software above will save a
  board that routes a 1 MHz SPI clock under the sense trace.
- **Sample away from noisy edges.** Synchronize the ADC trigger so the sample
  instant does not coincide with PWM transitions, motor commutation, flash
  erases, or the radio transmitting. A timer TRGO at the PWM centre point is the
  standard answer.

## ADC portability trap: newer STM32 families

The STM32F1/F4 ADC described above (`CR1`/`CR2`/`SMPRx`/`SQRx`/`SR`, `ADON`,
`SWSTART`) is **not** the ADC in F0/F3/L0/L4/G0/G4/H7/U5. Those use a
substantially different IP:

- Different registers: `ADC_ISR`/`ADC_IER`/`ADC_CR`/`ADC_CFGR`/`ADC_CFGR2`,
  `ADC_SQR1..4`, `ADC_SMPR1/2` with different field layouts.
- An explicit enable/disable handshake: `ADEN` + wait for `ADRDY`, `ADSTART`,
  `ADSTP`, `ADDIS` — you cannot just toggle a bit.
- A **deep-power-down** bit (`DEEPPWD`) and an internal **voltage regulator**
  (`ADVREGEN`) that must be brought up with a datasheet-specified delay before
  anything else works. Forgetting this is the classic "the new part's ADC reads
  zero" bug.
- Mandatory/supported **self-calibration** (`ADCAL`, single-ended and differential
  separately on some parts).
- **Hardware oversampling** (`CFGR2.OVSR`/`OVSS`) that does the
  oversample-and-decimate above in hardware, with no CPU cost.
- Differential channels, configurable sequencers, and per-instance clocking.

Treat the ADC as the least portable peripheral in the MCU. Keep its driver behind
a narrow interface (`adc_init()`, `adc_read_channel()`, `adc_start_scan_dma()`)
and expect to rewrite the body, not just the register addresses, when the family
changes. Always re-read the reference manual's ADC chapter for the new part
rather than porting bit definitions.

## RTC: the backup domain

The RTC does not live in the normal peripheral world. It sits in a **backup
domain**: a separate power island fed from VBAT when the main rail is gone, with
its own clock source and its own reset. That is the whole point — the calendar
keeps running through a power cut, and the backup registers keep their contents.

Consequences:

- Writes to backup-domain registers are **blocked by default** after every reset,
  including a warm one. You must unlock twice (power-domain and RTC-level).
- The backup domain has its own reset (`RCC_BDCR.BDRST` on STM32). Asserting it
  wipes the calendar, the prescalers, *and* the backup registers. Do it in
  first-time initialization only — never unconditionally at boot, or your
  "persistent" clock resets on every power-up.
- With no battery on VBAT, there is no backup domain in practice. The RTC is then
  only a low-power timebase and wake source, not a calendar.

## RTC: clock source and prescalers

| Source | Typical accuracy | Use for |
|---|---|---|
| LSE, 32.768 kHz crystal | ±20 ppm (≈1 min/year) | Calendars, timestamps, anything a human reads |
| LSI RC | **1-5 %** (seconds per minute) | Low-power wake-up intervals only |
| HSE / divider | As good as the HSE | Rare; dies with main power |

**Never run a calendar from LSI.** 1 % is about 15 minutes per day. The LSI RC is
also strongly temperature-dependent. It is fine as a wake-up tick ("wake me in
roughly 10 s"), and it is what the independent watchdog runs on, but a data
logger timestamped from LSI is worthless. If the board has no 32.768 kHz crystal
and you need a calendar, the fix is a board change or an external I2C RTC chip,
not a software correction factor.

32.768 kHz is chosen because it is `2^15`: a chain of divide-by-two stages lands
exactly on 1 Hz with no fractional error.

**The two prescalers.** The STM32 RTC divides in two stages (`RTC_PRER`):

- **PREDIV_A**, the asynchronous prescaler — runs first, in the low-power clock
  domain. A *large* value here means fewer high-frequency transitions and lower
  current.
- **PREDIV_S**, the synchronous prescaler — produces the final 1 Hz calendar tick
  and sets the sub-second resolution (`RTC_SSR` counts down from PREDIV_S).

The register fields hold *divider minus one*. For a 32.768 kHz LSE the standard
values are **PREDIV_A = 127, PREDIV_S = 255** → 128 × 256 = 32768 → exactly 1 Hz,
with 1/256 s sub-second resolution and minimum power. If you want finer
sub-seconds, shift the split the other way (e.g. A = 0, S = 32767 gives 1/32768 s
resolution at higher current). For a nominal 32 kHz LSI you would need
128 × 250, i.e. PREDIV_A = 127 and PREDIV_S = 249 — and the result is still only
as good as the LSI, which is to say not good.

Program `PREDIV_S` and `PREDIV_A` in **two separate write accesses**, sync field
first, inside init mode — the reference manual is explicit about this. Check yours.

## RTC: the write-unlock and init sequence

Every step is mandatory. Skipping one does not raise a fault; the write is simply
dropped and the RTC keeps whatever it had. "My RTC init does nothing" is almost
always a missing step here.

```c
/* 1. Clock the power controller, so DBP is writable at all */
RCC->APB1ENR |= RCC_APB1ENR_PWREN;

/* 2. Disable backup-domain write protection */
PWR->CR |= PWR_CR_DBP;

/* 3. Start and wait for the RTC clock source (LSE or LSI), then select it
 *    in RCC_BDCR (RTCSEL) and set RTCEN.  RTCSEL is write-once until the
 *    backup domain is reset -- you cannot change the source later without
 *    a BDRST pulse, which also wipes the calendar. */

/* 4. Unlock the RTC registers with the key sequence */
RTC->WPR = 0xCA;
RTC->WPR = 0x53;

/* 5. Enter init mode and wait for the hardware to acknowledge it */
RTC->ISR |= RTC_ISR_INIT;
while ((RTC->ISR & RTC_ISR_INITF) == 0) { }

/* 6. Write PREDIV_S, then PREDIV_A (separate accesses), hour format (CR.FMT),
 *    then RTC_TR and RTC_DR in BCD. */

/* 7. Leave init mode; the calendar starts counting from what you wrote */
RTC->ISR &= ~RTC_ISR_INIT;

/* 8. Re-arm write protection */
RTC->WPR = 0xFF;
```

After leaving init mode, **wait for `RTC_ISR.RSF`** before reading the calendar
back — the shadow registers are not valid until the first copy has happened. If
`BYPSHAD` is set you skip this but take on the coherency problem below.

The `WPR` key is `0xCA` then `0x53` in that order, as two byte writes. Any other
value re-arms the protection. Unlock once around the whole init block rather than
per register.

## RTC: BCD and shadow-register coherency

`RTC_TR` and `RTC_DR` hold **BCD**, not binary. 23 is stored as `0x23`, not
`0x17`. Two one-line converters are all you need, and you need them in both
directions:

```c
static uint8_t dec2bcd(uint8_t v) { return (uint8_t)(((v / 10u) << 4) | (v % 10u)); }
static uint8_t bcd2dec(uint8_t v) { return (uint8_t)(((v >> 4) * 10u) + (v & 0x0Fu)); }
```

Every bug in this area is a missing conversion in one direction. Make the
accessors convert at the register boundary so that nothing above the driver ever
sees BCD, and never pass a raw BCD value into `printf("%d")`.

**Shadow-register coherency.** The calendar registers you read are shadow copies
updated once per RTC clock. If the update lands between your read of `TR` and
your read of `DR`, you can get 23:59:59 on the *new* day — an hour or a day off,
once per day, forever, and impossible to reproduce at a breakpoint. Three valid
strategies:

1. **Read `TR` first, then `DR`.** Reading `TR` freezes the shadow pair until
   `DR` is read. This is the documented, cheapest fix — but it means you must
   always read `DR`, even if you only want the time, or the shadows stay locked.
2. **Read twice and compare.** Read the pair, read it again, accept only when the
   two agree. Works everywhere, including across vendors.
3. **Bypass the shadow registers** (`RTC_CR.BYPSHAD = 1`) and read the counters
   directly. Now there is no shadow to go stale — useful when you read from a
   low-power mode where the shadows are not maintained — but a read can catch a
   carry in progress, so you must use strategy 2 on top of it.

Pick one and enforce it in a single `rtc_get_datetime()` function. Do not let
application code touch `RTC->TR` directly.

## RTC: alarms, wakeup timer, backup registers

- **Alarm A / Alarm B** (`RTC_ALRMAR`, `RTC_ALRMBR`) fire when the calendar
  matches the programmed fields. The **mask bits** are the useful part: mask the
  date/hours/minutes and you get "every minute at second 30" or "every day at
  07:00" without re-arming by hand. Alarms wake the MCU from Stop and Standby
  through the EXTI line the RTC is wired to — on STM32 you must also enable that
  EXTI line and its rising-edge trigger, or the alarm flag sets and the part
  never wakes. Disable the alarm (`CR.ALRAE = 0`) and wait for `ISR.ALRAWF`
  before rewriting its registers.
- **Periodic wakeup timer** (`RTC_WUTR` + `CR.WUTE`, clock selected by
  `CR.WUCKSEL`) is a 16-bit auto-reload downcounter. It is the right primitive
  for "sleep 30 s, sample, sleep again" duty cycling — lower overhead and finer
  control than re-arming an alarm each cycle. Same EXTI caveat. Wait for
  `ISR.WUTWF` before writing `WUTR`.
- **Backup registers** (`RTC_BKPxR`) are general-purpose 32-bit words in the
  backup domain. They survive a system reset, a watchdog reset and main-rail loss
  *while VBAT holds*. They do **not** survive backup-domain power loss, a
  `BDRST`, or tamper detection (which clears them on purpose).

**Warm-boot detection.** Put a magic value in one backup register at the end of
first-time init, and check it at boot:

```c
#define RTC_INITED_MAGIC 0x32F2u

if (RTC->BKP0R != RTC_INITED_MAGIC) {
    rtc_full_init();          /* resets backup domain, sets prescalers + a default time */
    RTC->BKP0R = RTC_INITED_MAGIC;
} else {
    rtc_unlock_only();        /* clock the PWR domain, set DBP; calendar already runs */
}
```

Without this, every reboot resets the clock to the compile-time default, and the
backup domain reset you do "just to be safe" wipes the calendar you were trying
to preserve. `RTC_ISR.INITS` (set once the year field has been programmed) is a
reasonable alternative signal, but a magic value is explicit and also versions
your own backup-register layout.

## RTC: calendar logic you must write yourself

The hardware handles leap years only within its programmed year range and only
for the Gregorian rule it implements — check what your reference manual claims
before relying on it. Everything below is yours:

- **Daylight saving.** The hardware gives you a one-hour add/subtract
  (`RTC_CR.ADD1H`, `SUB1H`) and a "backup" status bit (`CR.BKP`) to record that
  you applied it. It does **not** know your timezone rules. Store UTC in the RTC,
  keep the offset in a backup register, and apply the conversion in software —
  then a timezone-rule change is a firmware update, not a data corruption.
- **Leap seconds, timezone databases, and the 2100 non-leap-year** are all
  software problems. Converting to and from a Unix epoch in software and keeping
  the RTC as a monotonic second counter is often simpler than reasoning about BCD
  calendar arithmetic.
- **Drift.** Even LSE drifts with temperature. `RTC_CALR` lets you add or remove
  pulses over a calibration window; if you have a network or GNSS time source,
  measure the error over a day and program the correction rather than stepping
  the clock.

## Watchdogs: choosing one

| Type | Clock | Catches | Cost |
|---|---|---|---|
| **Independent (IWDG)** | Own low-speed RC (LSI) | Hangs, deadlocks, **main clock failure** | Coarse timing |
| **Windowed (WWDG)** | APB bus clock | Hangs *and* too-early refreshes (runaway loop) | Dies with the main clock |
| **External supervisor** | Its own oscillator | Everything above, plus MCU-internal failures | Extra BOM, extra pin |
| **Software timer** | Main clock, your ISR | **Nothing worth having** | — |

A "software watchdog" implemented as a timer interrupt that calls `NVIC_SystemReset()`
is not a watchdog. If the fault stopped the clock, corrupted the vector table,
disabled interrupts, or parked the core in a HardFault loop, your timer ISR never
runs. The independent watchdog runs off its own RC oscillator precisely so that it
survives a stopped or misconfigured main clock — that is the entire point, and it
is why you prefer it unless you specifically need the window.

Use the **windowed** watchdog when the failure you fear is a runaway loop that
*still* kicks — e.g. a corrupted state machine spinning through your main loop
1000× too fast. The window makes "too early" a fault too. Use both on safety-
relevant designs: IWDG for clock-loss survival, WWDG for timing discipline.

## IWDG registers and sequence

Four registers, all behind write keys so a wild pointer cannot disable the
watchdog (STM32 names):

| Register | Purpose |
|---|---|
| `IWDG_KR` | Key register: `0xCCCC` start, `0x5555` unlock PR/RLR, `0xAAAA` refresh |
| `IWDG_PR` | Prescaler: divide LSI by 4, 8, 16, … 256 (values 0..6) |
| `IWDG_RLR` | 12-bit reload value, `0x000`..`0xFFF` |
| `IWDG_SR` | `PVU`, `RVU` — set while a PR/RLR write is propagating to the LSI domain |

```c
IWDG->KR  = 0xCCCC;                 /* start the free-running downcounter */
IWDG->KR  = 0x5555;                 /* unlock PR and RLR */
IWDG->PR  = prescaler_code;         /* write immediately: protection re-arms */
IWDG->RLR = reload_value;
while (IWDG->SR != 0) { }           /* wait for PVU and RVU to clear */
IWDG->KR  = 0xAAAA;                 /* load the counter before it can expire */
```

The `IWDG_SR` wait is not optional: PR and RLR cross a clock domain, and a refresh
issued while they are still updating can load a stale value. Write PR and RLR
immediately after the `0x5555` unlock — the unlock is transient.

**Timeout arithmetic:**

```
t_timeout = prescaler_divider * (RLR + 1) / f_LSI
```

With `f_LSI` nominally 32 kHz, prescaler 4 and `RLR = 0xFFF`: `4 × 4096 / 32000 ≈ 512 ms`.

**The LSI tolerance is wide** — on many STM32F4 parts the datasheet range is
roughly 17-47 kHz against a 32 kHz nominal, and it moves with temperature and
voltage. Therefore:

- Compute the **worst-case shortest** timeout using `f_LSI_max`, and make sure
  your slowest legitimate loop iteration still kicks comfortably inside it.
- Compute the **worst-case longest** timeout using `f_LSI_min` to know how long a
  hung system can actually stay hung, and check that against your safety
  requirement.
- A rule of thumb: target a nominal timeout of 2-4× your worst-case loop period,
  then verify both ends against the tolerance. If the margin does not close, you
  need the windowed watchdog on a precise clock, or an external supervisor.
- Some parts let you measure the LSI against a known clock (routing LSI to a
  timer input capture) and calibrate the reload value at boot. Worth it when the
  margin is tight.

**The hardware-watchdog option byte.** Many STM32 parts have a `WDG_SW` option bit.
Programmed for hardware mode, the IWDG starts automatically at power-on and
**cannot be disabled by software** — the firmware must kick it from the very first
milliseconds, including through its own startup and clock configuration. That is
exactly what you want in a deployed safety-relevant product (firmware that fails
before `main()` still resets), and exactly what will brick your debug session if
you enable it before the code is ready. Enable it late, and make sure your
bootloader and application both kick.

## Where to kick the dog

**The cardinal rule: the refresh must prove the whole system is alive.**

- **Never kick from a timer ISR.** An ISR keeps firing long after the main loop
  has deadlocked on a mutex, spun in a `while (!flag)` on a flag nothing will
  set, or stalled waiting on a dead peripheral. A watchdog kicked from an ISR
  guarantees only that interrupts still work — the one thing least likely to be
  broken. This single mistake disables more watchdogs in the field than any
  other.
- **Kick once per pass of the main supervisory loop**, at exactly one call site.
  One site means you can reason about it; three means someone will add a fourth
  inside an error path.
- **Require every subsystem to check in.** The robust pattern is a bitmask or a
  per-task deadline table. Each subsystem sets its bit (or updates its
  last-seen-alive timestamp) when it completes a cycle; the supervisor kicks only
  when all required bits are set within their deadlines, then clears them:

```c
static volatile uint32_t alive_flags;

#define TASK_SENSOR  (1u << 0)
#define TASK_COMMS   (1u << 1)
#define TASK_CONTROL (1u << 2)
#define TASKS_ALL    (TASK_SENSOR | TASK_COMMS | TASK_CONTROL)

/* in the main supervisory loop, once per pass */
if ((alive_flags & TASKS_ALL) == TASKS_ALL) {
    alive_flags = 0;
    IWDG->KR = 0xAAAA;
}
```

  Now a silently dead comms task causes a reset instead of a device that looks
  alive and answers nothing. Give long-running tasks a deadline rather than a
  plain flag if their periods differ by orders of magnitude.

**What a watchdog does and does not protect against.** It catches *hangs*:
infinite loops, deadlocks, a stalled bus wait, a lost interrupt, a crashed clock.
It does **not** catch *wrong answers*: a sign error in your control law, a
mis-scaled ADC reading, a corrupted calibration constant. Code that cheerfully
computes garbage at full speed kicks the watchdog perfectly. Plausibility checks
on outputs, range checks on inputs, and CRCs on stored parameters are separate
work, and the watchdog is no substitute for them.

Also plan the **recovery**: a watchdog reset is a reboot. Decide before shipping
what must survive it (calibration in flash, a fault counter in a backup register,
outputs that must fail to a safe state in hardware, not in software) and what
must be re-initialized. A device that resets every 500 ms forever is not more
available than one that is simply hung — add a reset counter in a backup register
and enter a defined safe/degraded mode after N consecutive watchdog resets.

## Reset-cause detection and debug freeze

**Read and log the reset cause at every boot.** Without it, a watchdog reset in
the field is invisible: the device just works again and nobody learns anything.
On STM32 the flags live in `RCC_CSR` — `IWDGRSTF`, `WWDGRSTF`, `PORRSTF`,
`PINRSTF`, `SFTRSTF`, `LPWRRSTF`, `BORRSTF` — and they are **sticky across
resets**, so you must clear them yourself with `RCC_CSR.RMVF` after reading, or
every subsequent boot reports the same cause.

```c
uint32_t cause = RCC->CSR;          /* read first */
RCC->CSR |= RCC_CSR_RMVF;           /* then clear, or it lies forever */
if (cause & RCC_CSR_IWDGRSTF) {
    /* increment a watchdog-reset counter in a backup register and log it */
}
```

Check power-on/BOR *before* the watchdog bit when decoding: a power-on reset can
leave several flags set. Store the decoded cause plus a counter in a backup
register (it survives a watchdog reset) and expose it over your debug interface.

**Debug freeze.** Halting at a breakpoint stops your code but not the IWDG's
independent oscillator, so the board resets out from under the debugger. The
`DBGMCU` block has freeze bits (`DBGMCU_APB1_FZ.DBG_IWDG_STOP`,
`DBG_WWDG_STOP`; `DBGMCU_APB1FZR1` on newer families) that stop the watchdog
counters while the core is halted. Enable them for development.

**Leaving debug freeze — or the watchdog itself — disabled in production hides
bugs.** A build where the watchdog is `#ifdef`-ed out "for now" is a build whose
watchdog has never been tested, and the first time it runs will be in a
customer's hands. Gate the freeze bits on `DEBUG`, keep the watchdog enabled in
every build including development, and deliberately test the reset path: add a
hidden command that spins forever and verify the device comes back and logs the
cause.

## Checklists

**ADC bring-up**

- [ ] GPIO clock on; pin in **analog** mode, pulls disabled
- [ ] ADC clock on; prescaler inside the datasheet's min/max ADC clock
- [ ] Resolution set; sampling time set **per channel** against source impedance
- [ ] Sequence length field set (not just the channel slots)
- [ ] ADC enabled, stabilization delay observed, calibration run if supported
- [ ] Multi-channel scan uses DMA; `OVR` handled explicitly, not ignored
- [ ] Timer TRGO trigger if timing or jitter matters
- [ ] `EOC` cleared by reading `DR` — no stray `DR` reads, no debugger watch on it
- [ ] Conversion formula uses `2^N`, written down once, used everywhere

**RTC bring-up**

- [ ] PWR clock enabled, `DBP` set, RTC `WPR` key sequence written
- [ ] Clock source matches the requirement (LSE for calendars, never LSI)
- [ ] Init mode entered, `INITF` waited for, prescalers written sync-then-async
- [ ] Init mode exited, `RSF` waited for before the first read
- [ ] Write protection re-armed (`WPR = 0xFF`)
- [ ] Calendar reads are coherent (TR-then-DR, or read-twice-and-compare)
- [ ] BCD conversion at the driver boundary, both directions
- [ ] Magic value in a backup register prevents re-initializing on warm boot
- [ ] Backup-domain reset happens only on first-time init, never unconditionally
- [ ] Timezone/DST handled in software over a UTC-based RTC

**Watchdog bring-up**

- [ ] IWDG chosen unless a window is specifically needed; software timers rejected
- [ ] Timeout computed at both `f_LSI_min` and `f_LSI_max`, margin verified
- [ ] PR/RLR written immediately after the `0x5555` unlock; `IWDG_SR` waited on
- [ ] Refresh at exactly one site in the main supervisory loop — **not** in an ISR
- [ ] Every subsystem checks in before the refresh is issued
- [ ] Reset cause read and cleared at boot; watchdog resets counted and logged
- [ ] Safe/degraded mode after N consecutive watchdog resets
- [ ] Debug freeze bits gated on the debug build only
- [ ] Watchdog enabled in **every** build; reset path deliberately tested
- [ ] Hardware-mode option byte decision made consciously, late in the project

Sources: see the Sources section of ../SKILL.md (Bare-Metal Embedded C Programming; Insider's Guide to Arm Cortex-M Development; Embedded Systems Architecture, 2nd ed.). Per-chapter attribution was not recorded for this file.
