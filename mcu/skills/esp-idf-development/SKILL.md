---
name: esp-idf-development
description: ESP-IDF development for ESP32 family — idf.py workflow, components, Kconfig, NVS, Wi-Fi/BLE, partitions, OTA, and power management. Use when sdkconfig or idf_component.yml is present.
track: mcu
---

# ESP-IDF Development

## Orient first

```bash
idf.py --version                 # IDF version determines the API
cat sdkconfig | grep CONFIG_IDF_TARGET
idf.py set-target esp32s3        # regenerates sdkconfig — do this before configuring
```

Targets differ substantially: ESP32 (dual Xtensa), S2 (single, no BLE), S3 (dual +
vector instructions for AI), C3/C6 (RISC-V), H2 (802.15.4). Never assume a feature.

## Build workflow

```bash
idf.py build
idf.py -p /dev/serial/by-id/usb-...  flash monitor    # stable device id, not ttyUSB0
idf.py menuconfig                    # then commit sdkconfig.defaults, not sdkconfig
idf.py size-components               # flash/RAM attribution per component
idf.py erase-flash                   # DESTRUCTIVE — confirm first
```

Commit `sdkconfig.defaults` (intent). `sdkconfig` is generated; whether it is committed
is a project decision — state it in the project AGENTS.md.

## Component structure

```
components/my_driver/
├── CMakeLists.txt        # idf_component_register(SRCS ... INCLUDE_DIRS ... REQUIRES ...)
├── Kconfig               # CONFIG_MY_DRIVER_* symbols
├── include/my_driver.h   # public
└── my_driver.c
```

`REQUIRES` = public dependencies (headers in your public header).
`PRIV_REQUIRES` = private. Getting this wrong causes include errors in consumers.

External components via `idf_component.yml` from the ESP Component Registry — pin
versions, do not use `*`.

## Memory reality

| Region | Notes |
|--------|-------|
| IRAM | Limited; only ISRs with `ESP_INTR_FLAG_IRAM` and `IRAM_ATTR` functions |
| DRAM | Internal SRAM, DMA-capable |
| PSRAM | External, must be enabled in Kconfig; **not DMA-capable on all targets**, higher latency |
| Flash | Code XIP via cache; a flash operation stalls all cores' cache |

```c
/* An ISR that can run while flash is being written must be IRAM-resident */
static void IRAM_ATTR gpio_isr(void *arg) { ... }
esp_intr_alloc(..., ESP_INTR_FLAG_IRAM, gpio_isr, NULL, &handle);
```
Any ISR not in IRAM will crash if it fires during an SPI-flash write (NVS commit, OTA).
This is the single most common ESP32 production crash.

DMA buffers: `heap_caps_malloc(n, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL)`.

## Error handling

```c
esp_err_t err = nvs_flash_init();
if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    ESP_ERROR_CHECK(nvs_flash_erase());     /* erases user data — deliberate */
    err = nvs_flash_init();
}
ESP_ERROR_CHECK(err);
```
`ESP_ERROR_CHECK` aborts on failure — correct during init, wrong in a network retry path.
Use `ESP_ERROR_CHECK_WITHOUT_ABORT` or explicit handling in recoverable paths.

## Wi-Fi / BLE

- Wi-Fi and BLE share the radio on ESP32/C3: coexistence must be configured, and
  throughput expectations adjusted.
- Never block the Wi-Fi event handler — post to a queue.
- Credentials in NVS, encrypted NVS partition in production. Never in `menuconfig`
  defaults committed to the repo.
- `esp_wifi_set_ps()` interacts with latency requirements; measure.

## Partitions and OTA

```csv
# partitions.csv
nvs,      data, nvs,     0x9000,  0x6000
otadata,  data, ota,     0xf000,  0x2000
phy_init, data, phy,     0x11000, 0x1000
ota_0,    app,  ota_0,   0x20000, 0x180000
ota_1,    app,  ota_1,   ,        0x180000
```
- Changing the partition table on a fielded device requires a migration plan — an OTA
  cannot resize its own partitions.
- OTA: always `esp_ota_mark_app_valid_cancel_rollback()` only after the app proves
  healthy, with `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y`. Marking valid at boot
  defeats rollback.
- Secure boot v2 + flash encryption: **burning these fuses is irreversible**. Never
  run `espefuse.py burn_efuse` or `idf.py secure-*` without explicit confirmation.

## Power

`esp_pm_configure()` with DFS + automatic light sleep. Peripherals need
`esp_pm_lock_acquire` around latency-sensitive work. Deep sleep loses RAM except
RTC slow memory (`RTC_DATA_ATTR`).

## Testing

```bash
idf.py -T my_driver build            # unit tests under components/*/test
pytest --target esp32s3 --port ...   # pytest-embedded for on-target tests
```
`qemu` target available for ESP32 for basic host-side validation.

## Common failure modes

| Symptom | Cause |
|---------|-------|
| `Guru Meditation Error: Cache disabled but cached memory region accessed` | ISR or its data not in IRAM/DRAM during a flash op |
| `StoreProhibited` on a pointer | null/invalid pointer, often a freed or uninitialized handle |
| Brownout detector triggered | insufficient supply current during TX peaks — power design, not software |
| Stack canary watchpoint triggered | task stack too small; raise and re-measure |
| OTA boots then reverts | rollback enabled and app never marked valid |
