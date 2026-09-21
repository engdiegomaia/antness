---
name: device-tree
description: Device tree authoring and debugging — DTS syntax, bindings, overlays, pinmux, clocks, regulators, and correlating the tree with the schematic. Use when *.dts, *.dtsi or *.dtbo are involved.
track: linux-embedded
---

# Device Tree

## What belongs here

Device tree describes **hardware that cannot be discovered**: what is wired to what.
It is not configuration and not policy. If a value is a software choice, it belongs in
a driver parameter, sysfs, or userspace — not the DTS.

## Structure

```
arch/arm64/boot/dts/<vendor>/
├── <soc>.dtsi          # SoC: peripherals, addresses, interrupts, clocks
├── <module>.dtsi       # SoM: what the module wires up (PMIC, eMMC, RAM)
├── <board>.dts         # carrier board: connectors, sensors, displays
└── <board>-overlay.dtso  # optional, runtime-applied changes
```

Never fork a vendor `.dtsi` to change a board detail. Include it and override in your
`.dts`, or use an overlay.

## Core syntax

```dts
&i2c1 {
	status = "okay";
	clock-frequency = <400000>;
	pinctrl-names = "default";
	pinctrl-0 = <&pinctrl_i2c1>;

	sensor@48 {
		compatible = "ti,tmp102";       /* MUST match a driver's of_match_table */
		reg = <0x48>;                    /* I2C address */
		#thermal-sensor-cells = <0>;
	};
};

&gpio3 {
	my-enable-hog {
		gpio-hog;
		gpios = <7 GPIO_ACTIVE_HIGH>;
		output-high;
		line-name = "sensor-enable";
	};
};
```

- `compatible` is the binding contract. A typo means the node exists and no driver
  binds — silent failure.
- `status = "disabled"` in the SoC dtsi is the default for most peripherals. Enabling
  is your job.
- `reg` meaning is bus-dependent: address+size on MMIO, address on I2C, chip select on SPI.
- Use the header constants (`GPIO_ACTIVE_LOW`, `IRQ_TYPE_LEVEL_LOW`, clock ids) — raw
  numbers are unreviewable.

## Pinmux — where bring-up fails

```dts
pinctrl_uart3: uart3grp {
	fsl,pins = <
		MX8MP_IOMUXC_ECSPI1_SCLK__UART3_DCE_RX   0x140
		MX8MP_IOMUXC_ECSPI1_MOSI__UART3_DCE_TX   0x140
	>;
};
```
- Every pin belongs to exactly one function. Two nodes claiming the same pad is a
  conflict; the kernel may or may not complain, and the peripheral silently misbehaves.
- The pad config value (drive strength, pull, slew, hysteresis) matters: a missing
  pull-up on I2C or on a boot strap is a real failure mode.
- **Cross-check every pinmux entry against the schematic.** This is the single highest-value
  review action on a new board.

## Overlays

```dts
/dts-v1/;
/plugin/;

&{/soc@0/bus@30800000/spi@30820000} {
	status = "okay";
	spidev@0 {
		compatible = "rohm,dh2228fv";
		reg = <0>;
		spi-max-frequency = <500000>;
	};
};
```

```bash
dtc -@ -I dts -O dtb -o my.dtbo my.dtso       # -@ keeps symbols, required for overlays
fdtoverlay -i base.dtb -o merged.dtb my.dtbo  # verify the merge offline
```
Overlays must be built against the **same base tree version** they will be applied to.
A mismatched phandle silently targets the wrong node.

## Verifying on target

```bash
ls /proc/device-tree/                      # the live tree
dtc -I fs -O dts /proc/device-tree > live.dts    # dump it as readable DTS
cat /proc/device-tree/model
cat /sys/firmware/devicetree/base/soc@0/.../status

cat /sys/kernel/debug/pinctrl/*/pinmux-pins   # what actually claimed each pin
cat /sys/kernel/debug/clk/clk_summary         # clock rates and enable counts
cat /sys/kernel/debug/regulator/regulator_summary
cat /sys/kernel/debug/gpio
cat /sys/kernel/debug/devices_deferred        # probes waiting on a dependency
```

Never assert what the tree contains — dump it.

## Validation

```bash
make dtbs_check                                          # validate against YAML bindings
make dt_binding_check DT_SCHEMA_FILES=Documentation/devicetree/bindings/iio/...
dtc -I dtb -O dts -o - arch/.../board.dtb | less        # see the merged result
```
New compatibles need a YAML binding in `Documentation/devicetree/bindings/`. Undocumented
compatibles are rejected upstream and are unreviewable internally.

## Common failure modes

| Symptom | Cause |
|---------|-------|
| Node present, no driver bound | `compatible` mismatch, or the driver's Kconfig is off |
| Driver probes then defers forever | a referenced clock/regulator/gpio provider is missing or disabled; `devices_deferred` |
| Peripheral enabled but dead | pinmux missing, or conflicting with another node |
| Works from U-Boot, dead in Linux | different device tree used by each stage |
| Interrupt never fires | wrong interrupt number/parent/trigger type |
| I2C device NAKs | wrong `reg` address, missing pull-ups, or the device is unpowered (missing regulator) |
| Overlay applies but changes nothing | built against a different base tree; phandles resolved to the wrong node |
