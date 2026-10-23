# Serial Peripherals: UART, SPI and I2C

Read this when bringing up or debugging a UART/USART, SPI or I2C link at register level on a bare-metal
Cortex-M target, or when choosing which of the three a new device should hang off.

## Contents

- [Choosing a bus](#choosing-a-bus)
- [UART: framing and baud](#uart-framing-and-baud)
- [UART: the flag discipline](#uart-the-flag-discipline)
- [UART: printf retargeting](#uart-printf-retargeting)
- [UART: receiving without losing bytes](#uart-receiving-without-losing-bytes)
- [UART: flow control, half-duplex and RS-485](#uart-flow-control-half-duplex-and-rs-485)
- [SPI: modes and clocking](#spi-modes-and-clocking)
- [SPI: the transaction](#spi-the-transaction)
- [SPI: chip select and multi-slave buses](#spi-chip-select-and-multi-slave-buses)
- [SPI: the sensor register access pattern](#spi-the-sensor-register-access-pattern)
- [I2C: the protocol](#i2c-the-protocol)
- [I2C: electrical layer](#i2c-electrical-layer)
- [I2C: the STM32F1/F4 event sequence](#i2c-the-stm32f1f4-event-sequence)
- [I2C: the new peripheral (portability trap)](#i2c-the-new-peripheral-portability-trap)
- [I2C: bus recovery](#i2c-bus-recovery)
- [Cross-cutting rules](#cross-cutting-rules)
- [Checklist](#checklist)

---

## Choosing a bus

| | UART/USART | SPI | I2C |
|---|---|---|---|
| Wires (+GND) | 2 (TX, RX) | 3 + 1 CS per device | 2 (SDA, SCL) |
| Clock | none (implicit rate) | shared, master-driven | shared, master-driven |
| Typical rate | 9.6 kbps – 1 Mbps | 1 – 50 MHz | 100 k / 400 k / 1 M / 3.4 MHz |
| Addressing | none (point to point) | one CS line per device | 7-bit (or 10-bit) on the wire |
| Multi-drop | no (RS-485 adds it) | yes, via CS or daisy chain | yes, natively |
| Multi-master | n/a | no | yes, with arbitration |
| Duplex | full | full | half |
| Flow control | RTS/CTS, or none | implicit (master clocks) | clock stretching |
| Distance | metres (RS-232/485: much more) | ~30 cm, same board | same board |
| Typical devices | GPS, BT/WiFi modules, consoles, modems, PC debug | SD cards, displays, flash, fast ADCs/IMUs | sensors, EEPROM, RTCs, PMICs, GPIO expanders |

Decision rules:

- **Debug console or a text-stream module** → UART. No arbitration, no addressing, works with a USB-serial
  dongle and any terminal.
- **Throughput matters, or the device datasheet shows a CS/SCK/MOSI/MISO diagram** → SPI. Accept the pin cost.
- **Several slow devices and you are short on pins** → I2C. Two wires carry a dozen sensors.
- **Device supports both SPI and I2C** (most IMUs do): pick SPI if you poll fast or stream FIFOs, I2C if the
  sample rate is low and board routing is tight.

---

## UART: framing and baud

8N1 is the default: 1 start bit (line pulled low), 8 data bits LSB first, no parity, 1 stop bit (line high).
The line idles high. Total 10 bit-times per byte, so byte rate ≈ baud/10. Both ends must be configured
identically; there is no auto-negotiation.

Parity only *detects* single-bit errors; use it when the peer demands it. 1.5/2 stop bits are historical.

**Baud divisor.** The peripheral divides its input clock down. On STM32F1/F2/F4/L1 the divisor lives in
`USART_BRR` split into a mantissa (integer) and a fraction field:

- Oversampling by 16 (`OVER8 = 0`, the default): `USARTDIV = f_ck / baud`, mantissa in `BRR[15:4]`,
  fraction in `BRR[3:0]` (units of 1/16).
- Oversampling by 8 (`OVER8 = 1`): `USARTDIV = 2 * f_ck / baud`, fraction is only 3 bits (`BRR[2:0]`) and
  `BRR[3]` **must** be written 0.

A cheap integer formula that rounds correctly for OVER8=0 is to compute the whole 16ths at once:

```c
/* BRR, oversampling by 16: value is USARTDIV in 1/16 units, rounded */
uint16_t brr = (uint16_t)((f_ck + baud / 2U) / baud);
```

On newer families (F0/F3/F7/L0/L4/G0/G4/H7) `BRR` is a plain divisor for OVER8=0 — no mantissa/fraction
split. Check your reference manual.

**The error rule.** Compute the *actual* baud you will get back from the integer divisor
(`actual = f_ck / round(f_ck/baud)` for OVER8=0) and compare it with the target. Keep the error under
**2%**, ideally under 1%. UART resynchronises only on each start bit; over a 10-bit frame, a 2% rate error
has already shifted the sampling point by 20% of a bit at the stop bit, and at 3% the receiver samples the
stop bit in the wrong slot and raises a framing error.

Symptoms of a bad divisor, in order of increasing mismatch:

1. Occasional corrupted characters, worse at higher baud.
2. Persistent framing errors (`FE`) — the stop bit was not high when sampled.
3. Consistent garbage: every byte wrong but *repeatably* wrong. Usually a 2x or 16x divisor mistake, or the
   clock tree is not what you assumed.

That last one is the most common bring-up bug: the driver assumes `f_ck` is the 16 MHz HSI default while
the PLL has already raised the APB clock. Derive the UART's input clock from your clock-tree code, never
from a constant hardcoded in the UART driver. Oversampling by 8 doubles the reachable baud from a given
clock but halves the noise margin — use it only when 16x cannot reach the rate.

---

## UART: the flag discipline

Three transmit-side facts that cause real bugs:

- **TXE** (transmit data register empty) means the byte you wrote has moved from `DR` into the shift
  register. You may write the next byte. It does **not** mean anything has left the pin.
- **TC** (transmission complete) means the shift register has emptied, stop bits included. The wire is idle.
- Writing `DR` is what clears TXE; TC is cleared on newer parts via `ICR`, and on F1/F4 by the read-SR-then-
  write-DR sequence (or an explicit software clear).

**The classic bug:** disabling the USART, gating its clock, switching the pin to another function, deasserting
an RS-485 driver-enable, or entering a low-power mode right after the last `TXE`. The final character — and
often the one before it — is truncated mid-frame. Always wait for **TC**, not TXE, before doing any of those.

```c
/* last byte of a message, then safe to power down or release the bus */
while (!(uart_sr() & SR_TXE))  { if (timed_out()) return -ETIMEDOUT; }
uart_write_dr(last);
while (!(uart_sr() & SR_TC))   { if (timed_out()) return -ETIMEDOUT; }
```

Receive side:

- **RXNE** means a byte is sitting in `DR`. Reading `DR` clears it.
- **ORE** (overrun) means a new byte arrived while the previous one was still unread; the new byte is lost
  and, on most parts, RXNE handling stalls until ORE is cleared. At 115200 baud you have ~87 µs per byte —
  one long `printf` or a disabled-interrupt window is enough to overrun.

**The clear sequence everyone gets wrong (STM32F1/F2/F4/L1):** ORE, NE, FE and PE are cleared by a read of
`USART_SR` *followed by* a read of `USART_DR`. Reading only `SR` does nothing. Reading only `DR` does nothing.
And a compiler is entitled to delete a read whose value you discard — so the destination must be `volatile`:

```c
static inline void uart_clear_errors(void)
{
    volatile uint32_t tmp;
    tmp = USART2->SR;   /* step 1 */
    tmp = USART2->DR;   /* step 2 - both reads required, both must happen */
    (void)tmp;
}
```

On F0/F3/F7/L0/L4/G0/G4/H7 this is replaced by writing `ORECF`/`FECF`/… bits to `USART_ICR` — a single
write-1-to-clear. Code that ports between the two families breaks silently here: the old sequence compiles
fine against the new headers' `ISR`/`RDR` names only after you rename them, and the new W1C write against an
old part does nothing at all.

Other error flags worth decoding rather than ignoring: **FE** (framing — wrong baud, wrong stop bits, or the
line was broken mid-frame), **NE/NF** (noise — the three oversampled samples disagreed; signal integrity,
cable length or a missing ground), **PE** (parity). A driver that reports "framing error" is far more useful
during board bring-up than one that silently returns a corrupt byte.

---

## UART: printf retargeting

With newlib or newlib-nano, `printf` ends up calling `_write(int fd, const char *buf, int len)`. Implement it
and the whole stdio formatting layer works over your UART:

```c
int _write(int fd, const char *buf, int len)
{
    (void)fd;
    for (int i = 0; i < len; i++)
        if (uart_putc(buf[i]) < 0) return i;   /* propagate, don't hang */
    return len;
}
```

Some ST toolchain templates instead route through `__io_putchar(int ch)`; either hook works, pick the one
your startup code already references. Also stub `_read`, `_close`, `_lseek`, `_fstat`, `_isatty` or the link
fails or pulls in a hosted implementation.

Practical cautions:

- Full `printf` with `%f` costs kilobytes of flash and a lot of stack. Link newlib-nano; enable float
  formatting only if you need it.
- Buffering: call `setvbuf(stdout, NULL, _IONBF, 0)` or log lines wait for a flush that never comes.
- **Never call blocking `printf` from an ISR or a timing-critical loop.** One 40-character line at 115200
  baud is ~3.5 ms of busy-waiting — enough to miss encoder edges, overrun your own receiver, or blow a
  control-loop deadline. Logging that changes the timing of the bug you are chasing is a classic heisenbug.
  For hot paths, push into a ring buffer and drain it from the main loop or by DMA.
- Prefer a separate UART for logging so console traffic cannot interfere with a protocol link.

---

## UART: receiving without losing bytes

Polling `RXNE` from the main loop only works if your loop period is shorter than one byte time. It rarely is.
Two production-grade options:

**Interrupt + ring buffer.** Enable the RXNE interrupt (`RXNEIE`). The ISR reads `DR` (clearing RXNE), pushes
into a power-of-two circular buffer, and returns — no parsing, no `printf`, no blocking. Make head/tail
`volatile`; with one producer (ISR) and one consumer (main) no critical section is needed, as long as
each side writes only its own index.

**DMA circular + idle-line detection.** Point a circular DMA channel at a buffer and let it run forever; you
never get an overrun because the DMA services `RXNE` at hardware speed. To know *when* a message ended, enable
the **IDLE** line interrupt — it fires when the line has been idle for one frame time after data. In the IDLE
handler, read the DMA's remaining-count register (`NDTR` on STM32), compute how far the write pointer has
moved since last time, and hand that slice to the parser. This is the standard way to receive
variable-length, framed protocols (NMEA, AT commands, Modbus RTU) with near-zero CPU cost. Add the half-
transfer and transfer-complete interrupts if the buffer may wrap between idles.

For a fixed-length protocol, a plain (non-circular) DMA of exactly N bytes plus a software timeout is simpler.

---

## UART: flow control, half-duplex and RS-485

**RTS/CTS.** RTS is an output asserted while the local receiver has buffer space; CTS is an input that gates
the local transmitter. Enable both ends or neither — a device configured for flow control against one that
is not will simply stop transmitting forever. Use it when the peer can burst faster than you can drain
(Bluetooth/WiFi modules at 921600 are the usual case). XON/XOFF software flow control is not usable for
binary data.

**Half-duplex / single wire.** Some USARTs support a one-wire half-duplex mode where TX and RX share the pin
(open-drain, external pull-up). Only one side may drive at a time; the protocol must define turnaround.

**RS-485.** A differential transceiver with a driver-enable (DE) pin turns a UART into a multi-drop bus. The
timing is the whole problem:

1. Assert DE **before** writing the first byte, with enough setup for the transceiver (tens of ns, but a GPIO
   write plus the first start bit is normally sufficient).
2. Transmit the frame.
3. Deassert DE only **after TC sets** — not after TXE. Dropping DE at TXE cuts off the last character and
   usually also kills the stop bit, which the peer reports as a framing error on every single message.
4. Re-enable the receiver, and be ready to discard the echo if the transceiver loops TX back to RX.

Many STM32 USARTs can drive DE in hardware (`DEM` bit in `CR3`, with `DEAT`/`DEDT` assertion/deassertion
guard times in `CR1`) — on F0/F3/F7/L4/G0/G4/H7. Use it when available; the hardware gets the TC timing
right for free. On older parts you must do it in software, ideally from the TC interrupt rather than a
polling loop.

Bus turnaround time, inter-frame silence (Modbus RTU: 3.5 character times), and termination plus fail-safe
biasing at the cable ends are requirements, not optional details.

---

## SPI: modes and clocking

Two bits define the clock:

- **CPOL** — idle level of SCK. 0 = idle low, 1 = idle high.
- **CPHA** — which edge samples. 0 = sample on the *first* (leading) edge, shift on the second.
  1 = shift on the first edge, sample on the *second* (trailing) edge.

| Mode | CPOL | CPHA | Idle SCK | Data sampled on |
|---|---|---|---|---|
| 0 | 0 | 0 | low | rising |
| 1 | 0 | 1 | low | falling |
| 2 | 1 | 0 | high | falling |
| 3 | 1 | 1 | high | rising |

Modes 0 and 3 cover the large majority of devices.

**Reading the mode off a datasheet timing diagram:** look at SCK before CS goes low — that level is CPOL.
Then find the first SCK edge after CS falls and look at where the diagram marks the data valid/sample point.
If the first edge is the sampling edge, CPHA = 0; if the data changes on the first edge and is sampled on
the second, CPHA = 1. Many datasheets state "SPI mode 0 and mode 3 supported" outright — believe that over
your reading of the picture. If you got CPHA wrong, you typically read data shifted by one bit (0x3B becomes
0x76 or 0x1D); if CPOL is wrong, you often read all 0x00 or 0xFF.

**Bit order.** MSB first is the default and what nearly all devices use. `LSBFIRST` exists; setting it by
accident gives bit-reversed bytes (0x8F reads back as 0xF1).

**Speed.** The bit rate is the peripheral's input bus clock divided by a power-of-two prescaler
(STM32 `SPI_CR1.BR[2:0]`: 000 = /2 … 111 = /256). Note which bus the instance sits on — on STM32F4, SPI1 is
on APB2 and SPI2/SPI3 on the slower APB1, so the same `BR` gives different line rates. Start at a few
hundred kHz during bring-up, prove the WHO_AM_I read, then raise the clock. On flying leads the practical
ceiling is far below the peripheral's rated maximum.

---

## SPI: the transaction

SPI is a **shift register exchange**, not a pair of independent channels. Every clocked byte simultaneously
sends one byte out on MOSI and brings one byte in on MISO. Consequences you must build into the driver:

- **To read, you must write.** Clock out a dummy byte (0x00 or 0xFF — check which your slave prefers; some
  flash parts interpret stray 0x00s) for each byte you want to read.
- **To write, you must read.** Every write leaves a byte in the RX register. If you ignore it, the next
  transfer sets **OVR** (overrun). Drain RX as you go, or clear OVR at the end of the transfer (on STM32:
  read `DR`, then read `SR`).
- Transmit and receive are offset by one byte in a streamed transfer. For an N-byte full-duplex exchange the
  loop writes byte *i* and reads byte *i-1*; getting the pipelining wrong is why a naive driver returns data
  shifted by one position.

**Flag discipline:**

- `TXE` — the TX buffer accepted your byte. It is *in the shift register or queued*, not on the wire.
- `RXNE` — a received byte is available; read `DR` to clear.
- `BSY` — the peripheral is still clocking. It clears only when the shift register has fully emptied.

**The CS bug:** waiting only for `TXE` before deasserting CS truncates the last byte, because TXE sets as
soon as `DR` is free — one whole byte before the clock stops. The correct end-of-transfer sequence is:

```c
while (!(SPI1->SR & SR_TXE))  { /* bounded timeout */ }   /* DR free        */
while (  SPI1->SR & SR_BSY )  { /* bounded timeout */ }   /* wire is idle   */
(void)SPI1->DR;  (void)SPI1->SR;                          /* drain + clr OVR */
cs_high();                                                /* only now       */
```

Do not raise CS between bytes of a multi-byte command unless the device's protocol says to — many devices
reset their internal pointer on a CS edge, so a burst read becomes N repeated reads of the first register.

---

## SPI: chip select and multi-slave buses

**Software NSS is almost always what you want.** Configure the peripheral for software slave management
(STM32: `SSM = 1`, `SSI = 1` in `CR1`) and drive each slave's CS from a plain GPIO. This gives you:

- a CS per device, asserted and released exactly around the logical transaction, not per byte;
- control over the setup/hold time the device's datasheet requires around CS;
- the freedom to reconfigure CPOL/CPHA and the prescaler between devices on the same bus.

**Hardware NSS output** (`SSM = 0`, `SSOE = 1`) drives a single NSS pin, and on many parts it pulses per
frame rather than staying low for the whole transaction — wrong for almost every real slave and useless once
you have more than one.

**MODF (mode fault) and the master-enable-lost trap.** If the peripheral is a master with *hardware* NSS
input management and the NSS pin is pulled low by anything, the hardware assumes another master seized the
bus: it sets `MODF`, and **clears `MSTR` and `SPE`**. The peripheral silently demotes itself to a disabled
slave and all further transfers do nothing. Symptom: SPI works once and then goes dead, with no clock on the
scope. Fixes: use software NSS (`SSM=1, SSI=1`), or tie the NSS pin high. Recovery requires the documented
sequence — read `SR` while MODF is set, then write `CR1` — before you can set `MSTR`/`SPE` again.

**Sharing a bus between devices with different modes or speeds:** reconfigure `CR1` between transactions,
with `SPE` cleared while you change CPOL/CPHA/BR, and only while every CS is high. Changing the clock
polarity while a slave is selected produces a phantom clock edge that the slave counts as a bit. If one
device needs a radically different setup and the timing is tight, give it its own SPI instance.

**Daisy chaining** (MISO of device 1 into MOSI of device 2, one shared CS) exists for shift-register-like
devices: clock N bytes through the whole chain and latch on the CS rising edge. It saves pins, forbids
per-device addressing, and requires every device in the chain to support it — most sensors do not.

**Other slaves must release MISO.** A well-behaved slave tri-states MISO while its CS is high. One that does
not will fight whoever is talking: reads are correct with one device on the bus and corrupt with two.

---

## SPI: the sensor register access pattern

Most SPI sensors (accelerometers, gyros, magnetometers, many flash and radio parts) use a one-byte command
header followed by data:

- **bit 7** — R/W. 1 = read, 0 = write (ADXL345, LIS3DSH, LSM6DS*, and relatives). Some parts invert this —
  read the datasheet.
- **bit 6** — multiple-byte / auto-increment (`MB`). Set it to have the device's address pointer advance so
  you can stream a block in one transaction.
- **bits 5..0** — the register address.

So a single-register read of `0x00` is `0x80`; a burst read of six data bytes starting at `0x32` is
`0xC0 | 0x32 = 0xF2`, followed by six dummy bytes, all inside one CS assertion.

The canonical bring-up sequence:

1. CS low.
2. Write the command byte. Discard the byte clocked in during it — the slave had nothing to say yet.
3. Clock dummy bytes, one per byte you expect back, storing what comes in on MISO.
4. CS high.

Read the device ID register first. If WHO_AM_I/DEVID matches the datasheet constant, wiring, mode, bit
order and CS timing are all correct. All-0x00 or all-0xFF means no slave is responding (wiring, CS, power)
rather than a protocol bug. Burst-read sample data in one transaction rather than register by register —
faster, and it guarantees all axes come from the same sample instead of tearing across an update.

---

## I2C: the protocol

Two open-drain wires. Devices only ever pull low; pull-up resistors provide the high level. Logic 0 is
therefore dominant, which is what makes arbitration and clock stretching possible.

- **START**: SDA falls while SCL is high. Claims the bus.
- **Address frame**: 7 address bits MSB first, then the R/W̅ bit (0 = write, 1 = read), then an ACK slot.
- **ACK/NACK**: during the 9th clock the transmitter releases SDA; the receiver pulls it low to ACK. SDA left
  high is a NACK.
- **Data frames**: 8 bits + 1 ACK slot each. On a read, the *master* ACKs each byte and **NACKs the last one**
  to tell the slave to stop driving, then issues STOP.
- **STOP**: SDA rises while SCL is high. Frees the bus.
- **Repeated START**: a START instead of a STOP, keeping the bus. Essential for register reads (see below)
  and for preventing another master from slipping in mid-sequence.

**The shifted-address confusion.** A device datasheet may give its address as 7-bit (`0x53`) or as the
"write address" byte (`0xA6`, with read `0xA7`). These are the same device: `0xA6 = 0x53 << 1`. Decide once
which convention your driver's API uses, document it in the header, and convert at exactly one place. Most
of the "the sensor does not ACK" bug reports are an address off by a factor of two. If you are unsure, run
a bus scan: for every address 0x08..0x77, send START + address + W and record whether ACK came back.

**Register read = write-then-read with a repeated START.** The near-universal pattern is:

```
START, addr+W, ACK, reg_addr, ACK, REPEATED START, addr+R, ACK, data..., NACK on last, STOP
```

Using STOP instead of repeated START between the two halves usually still works on a single-master bus, but
on a multi-master bus another master can win the bus in the gap and move the slave's internal pointer.

**Clock stretching.** A slave that is not ready holds SCL low. The master tries to release SCL, sees it stay
low, and waits. Transactions can be delayed indefinitely this way — which is exactly why every wait in an
I2C driver needs a timeout. Not every master peripheral handles stretching well in every mode; some require
a minimum peripheral clock for it, and some MCUs have errata here. Check your reference manual.

**Arbitration and multi-master.** Two masters that start together compare, bit by bit, the level they intend
to drive against the level actually on SDA. The one that wanted a 1 and sees a 0 has lost; it aborts
immediately and the winner never notices. The loser's peripheral reports arbitration lost (`ARLO`), and the
driver should back off and retry the whole transaction, not resume mid-frame.

**Speed modes:** standard 100 kHz, fast 400 kHz, fast-mode-plus 1 MHz, high-speed 3.4 MHz (rare, needs a
special current-source driver). Every device on the bus must tolerate the speed you pick; the bus runs at
the slowest device's limit.

---

## I2C: electrical layer

Pull-ups are a design parameter, not a formality. Two bounds:

- **Minimum resistance** from drive strength: the device must still pull the line to V_OL (0.4 V) while
  sinking no more than 3 mA. `R_min ≈ (VDD - 0.4 V) / 3 mA` — about 1 kΩ at 3.3 V.
- **Maximum resistance** from rise time: the RC formed by the pull-up and the total bus capacitance must
  rise within the spec'd time. `R_max ≈ t_r / (0.8473 × C_bus)`, with `t_r` max 1000 ns (standard),
  300 ns (fast), 120 ns (fast-plus).

Practical values: 4.7 kΩ at 100 kHz, 2.2 kΩ at 400 kHz, ~1 kΩ at 1 MHz, for a bus around 100–200 pF.
Fit **one** pull-up pair per bus — breakout boards each carry their own, and five in parallel give an
effective ~940 Ω that no device can pull low. SDA never reaching a clean low means too many pull-ups; slow,
rounded rising edges on a scope mean too few, or too much bus capacitance (long wires, too many devices).

Do **not** enable the MCU's internal pull-ups as the bus pull-ups: they are typically 30–50 kΩ, far too weak.
They are acceptable only on a very short, very slow, 2-device bus, and even then only as a bring-up hack.
Configure the SDA/SCL pins as **alternate function, open-drain** — push-pull will fight the bus and can
damage parts.

---

## I2C: the STM32F1/F4 event sequence

> Applies to the older "I2C v1" peripheral: STM32F1, F2, F4, L1. See the next section for everything else.

Master read of a register, with the flag transitions you must wait on in order:

1. Wait `SR2.BUSY == 0` — bus free.
2. Set `CR1.START`. Wait `SR1.SB`. (SB is cleared by reading `SR1` then writing `DR`.)
3. Write `DR = (addr << 1) | 0` — address + write.
4. Wait `SR1.ADDR`. **Clear it by reading `SR1` and then reading `SR2`.** Both reads, in that order, into
   `volatile` variables. Forget this and the clock stays stretched by the peripheral and the transaction
   never advances — this is the single most common hang in a hand-written F4 I2C driver.
5. Wait `SR1.TXE`. Write `DR = reg_addr`.
6. Wait `SR1.TXE` (or `BTF` for a truly drained shift register). Set `CR1.START` again — repeated START.
7. Wait `SR1.SB`. Write `DR = (addr << 1) | 1` — address + read.
8. Wait `SR1.ADDR`. For a **single-byte** read: clear `CR1.ACK` *before* clearing ADDR, clear ADDR
   (`SR1` then `SR2`), then set `CR1.STOP`. For a multi-byte read, enable `CR1.ACK` and clear ACK + set STOP
   while receiving the second-to-last byte. The exact ordering for N=1 and N=2 is specified in the reference
   manual and is genuinely fiddly — follow it literally.
9. Wait `SR1.RXNE`, read `DR`. Repeat for each byte.

**Error flags you must handle:**

- **AF** (acknowledge failure) — nobody ACKed. Wrong address, device absent, device busy or asleep, or it
  NACKed a byte it did not like. Clear AF, issue STOP, and return an error. A polling driver that waits for
  `ADDR` after a NACK waits forever: `ADDR` will never set.
- **ARLO** — arbitration lost. Abort and retry the whole transaction.
- **BERR** — bus error: a START or STOP at an illegal position. Usually means noise or a misbehaving peer.
- **OVR/UDR** — in slave mode, data over/underrun.

**Why the naive driver deadlocks.** Every step above is written in textbooks as `while (!(I2C1->SR1 & FLAG));`
with no escape. If the slave is unpowered, absent, mis-addressed, or holds SCL low, that loop never exits and
your product is bricked until the watchdog fires — and if the watchdog resets you back into the same init
code, it reboots forever. Every single one of those waits needs a bounded timeout and an error return. See
the next-to-last section.

---

## I2C: the new peripheral (portability trap)

> **Flag this before you port anything.** STM32 F0, F3, F7, L0, L4, L5, G0, G4, H7, U5 and WB ship a
> *completely different* I2C peripheral ("I2C v2"). Register-level F4 I2C code does not port — it does not
> even compile, and if you paper over the names it will not work.

What changes:

- **Timing** is one `TIMINGR` register holding PRESC, SCLDEL, SDADEL, SCLH, SCLL — not `CR2.FREQ` + `CCR` +
  `TRISE`. You are expected to generate the value with STM32CubeMX's I2C timing tool or the published
  application note, not to derive it by hand.
- **The transfer is described up front.** `CR2` holds the slave address (`SADD`), direction (`RD_WRN`), byte
  count (`NBYTES`), and the `START`/`STOP`/`AUTOEND`/`RELOAD` controls. Setting `START` with `AUTOEND = 1`
  makes the hardware send address, N bytes, and STOP by itself.
- **Flags live in `ISR` and are cleared by writing `ICR`** (write-1-to-clear). The read-SR1-then-SR2 dance is
  gone entirely; so is the ADDR-clearing trap.
- Names shift: `TXIS` (transmit interrupt status, "give me the next byte") and `TXE` are separate; `TC`
  (transfer complete) and `TCR` (transfer complete reload) signal the end of an `NBYTES` chunk; `NACKF`
  replaces `AF`; `STOPF` marks the STOP.
- Transfers longer than 255 bytes use `RELOAD` to chain chunks.

The v2 flow is simpler and far less deadlock-prone, but it is a rewrite. Keep register-level code behind a
thin portable interface (`i2c_write_reg`, `i2c_read_regs`, returning error codes) so only one file changes
when the silicon does. Confirm which variant your part has before copying any example — most "STM32 I2C"
blog code is v1.

---

## I2C: bus recovery

A slave that was reset or power-cycled mid-byte can be left driving SDA low, waiting for clocks that never
come. The bus is then permanently stuck: the master sees BUSY forever and cannot even issue a START.
A soft reset of the MCU does not fix it, because the slave is the one holding the line. This is why an I2C
device that "works until the first debugger reset" then never works again.

Recovery procedure, to run at init and after any BERR/timeout:

1. Disable the I2C peripheral; reconfigure SCL and SDA as **GPIO open-drain outputs**, both driven high.
2. If SDA reads low, generate up to **9 clock pulses** on SCL (high, delay, low, delay at roughly the bus
   period), checking SDA after each. Nine is enough to flush any byte the slave was mid-way through, after
   which it releases SDA for the ACK slot.
3. Generate a STOP by hand: with SCL high, drive SDA low then release it high.
4. Restore the pins to alternate function, reset the peripheral (toggle its RCC reset bit, or `CR1.SWRST`
   on v1), and re-run the init.

If SDA is still low after nine clocks the problem is hardware: a shorted line, a dead device, or no pull-up.

---

## Cross-cutting rules

**Never block forever on a status flag.** Any `while (!(PERIPH->SR & FLAG));` is a latent hang: the device
may be unpowered, the clock may not be running, the pin may be mis-muxed, a slave may stretch the clock
indefinitely. Make the bounded wait the only wait primitive in the driver:

```c
static int wait_flag(volatile uint32_t *reg, uint32_t mask, bool set, uint32_t ticks)
{
    uint32_t t0 = now_ticks();
    while (((*reg & mask) != 0) != set) {
        if (now_ticks() - t0 > ticks)
            return -ETIMEDOUT;     /* caller aborts, cleans up, reports */
    }
    return 0;
}
```

Size the timeout from the protocol, not from a round number: one byte at the configured baud/clock plus
margin, times the byte count. And make the error path *clean up* — deassert CS, issue STOP, clear sticky
error flags — not just return.

**Interrupt-driven vs DMA.**

| | Interrupt per byte | DMA |
|---|---|---|
| Cost | one ISR entry/exit per byte (~tens of cycles) | one ISR at completion |
| Good for | short, irregular transfers; byte-at-a-time protocols; low rates | blocks of tens to thousands of bytes; high rates; audio/display streaming |
| Bad for | >100 kB/s — the ISR rate eats the CPU | very short transfers (setup cost dominates); protocols needing per-byte decisions |
| Complexity | moderate; a state machine | higher: stream/channel mapping, buffer lifetime, cache |

Rule of thumb: polling for a handful of bytes at init, interrupts for interactive/irregular traffic, DMA
once a transfer exceeds ~16 bytes or the line rate exceeds a few hundred kbit/s. SPI at 10 MHz is a byte
every 800 ns — interrupt-per-byte is not viable there.

**`volatile` and barriers.** Mark every register access and every buffer shared between an ISR and main code
`volatile`, or the compiler will cache a flag read in a register and your wait loop will spin forever at
-O2 while the flag is long since set. But `volatile` is **not** a memory barrier and says nothing about DMA:
DMA is a second bus master that the compiler knows nothing about. When handing a buffer to DMA:

- fill the buffer, then `__DMB()`, then enable the DMA channel — so the writes are visible before the engine
  starts reading;
- after a completion interrupt, `__DMB()` before reading the received data;
- on cached cores (Cortex-M7, and M33/M55 with cache enabled): clean (write back) the TX buffer before
  starting, and invalidate the RX buffer after completion — otherwise the DMA reads stale memory or the CPU
  reads a stale cache line. Align and size such buffers to the 32-byte cache-line granularity, or an
  invalidate will discard a neighbouring variable's dirty data.

See the DMA reference for the full ordering and cache rules.

---

## Checklist

Before declaring a serial link working:

1. Is the peripheral's input clock derived from the actual clock-tree configuration, not a hardcoded default?
2. UART: is the computed actual baud within 2% of target, and did you check it rather than assume?
3. UART: does every teardown path (disable, sleep, pin remux, RS-485 DE release) wait for **TC**, not TXE?
4. UART: are ORE/FE/NE/PE cleared with the sequence your family actually requires, into a `volatile`?
5. UART: is `printf` kept out of ISRs and hot loops?
6. SPI: did a WHO_AM_I/DEVID read return the datasheet constant?
7. SPI: does CS go high only after **BSY** clears, and stay low across the whole logical transaction?
8. SPI: software NSS (`SSM=1, SSI=1`) or NSS tied high, so MODF cannot silently clear MSTR?
9. SPI: is RX drained / OVR cleared on write-only transfers?
10. I2C: one pull-up pair on the bus, sized for the speed, and the pins open-drain alternate function?
11. I2C: is the address convention (7-bit vs shifted) documented and converted in exactly one place?
12. I2C v1: is `ADDR` cleared by reading `SR1` *then* `SR2`, and is NACK/AF handled instead of waited on?
13. I2C: does init run a bus-recovery (9-clock) routine, and does every wait have a timeout?
14. Does the driver return error codes on every failure path, and clean up the bus before returning?
15. DMA: `volatile` on shared state, barriers around handoff, cache maintenance on M7?

Sources: see the Sources section of ../SKILL.md (Bare-Metal Embedded C Programming; Insider's Guide to Arm Cortex-M Development; Embedded Systems Architecture, 2nd ed.). Per-chapter attribution was not recorded for this file.
