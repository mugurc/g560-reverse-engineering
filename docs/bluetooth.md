# Bluetooth

Tags: **[V]** verified against a real G560 · **[C]** observed in vendor software/firmware · **[I]** inference.

**Short version: no Bluetooth control channel was found.** The speaker advertises an A2DP sink and nothing else we could see; neither the Conexant nor the STM32 firmware contains any Bluetooth control logic; and the vendor's Bluetooth updater library speaks a protocol (Airoha RACE) that belongs to a different hardware variant.

## 1. What the speaker advertises (SDP) [V]

A plain SDP query (macOS `IOBluetoothDevice.performSDPQuery`, public-browse-group records) returns **exactly one record**:

| Item | Value |
|---|---|
| Service class | `0x110B` Audio Sink |
| Protocol | L2CAP PSM `0x19` (AVDTP) v1.2 |
| Profile | `0x110D` Advanced Audio Distribution v1.2 |
| SupportedFeatures (`0x0311`) | 1 |

There is **no AVRCP (`0x110C`/`0x110E`), no HFP/HSP and no SPP (`0x1101`) record**. Practical consequence: a host has no standard way to read or set the speaker's own volume over Bluetooth (AVRCP absolute volume needs AVRCP), and no standard serial service to talk to.

System Profiler reports the services as `A2DP ACL`.

### What could not be established [V]

* SDP queries *filtered by UUID* (`performSDPQuery:uuids:`) always timed out after ~20 s — **even for `0x110B`, a record known to exist** — so that method is unusable against this device (its SDP server may not implement the ServiceSearch request type; unproven).
* The raw SDP channel (L2CAP PSM 1) is not available to user applications on macOS (`IOReturn 0xE00002BC`).
* An **RFCOMM channel scan** (channels 1–30, `tools/rfcomm_scan.py`; connection attempts only, nothing sent) failed on every channel with the same error `0xE00002BC` after exactly 3.1 s. The same code is returned for the SDP channel, which certainly exists, so macOS does not distinguish "refused" from "not permitted". There is no positive control. Result: **no RFCOMM service was found, but its absence is not proven.**

A definitive answer needs a different Bluetooth stack: e.g. Linux `sdptool browse <addr>` / `bluetoothctl`, or an HCI sniffer.

## 2. The vendor's Bluetooth updater [C]

Package: *Logitech G560 Gaming Speaker Updater 1.0.13* (Windows, 2025-10-17; the page notes that Logitech's firmware tools are no longer supported).

* `updater.exe` is a .NET application (namespace `Wonderboom_FW_update.BtLib`, i.e. a shared Ultimate Ears framework). It distinguishes devices with `IsAirohaDevice`.
* Two device profiles ship in it:
  * **`MUSE`** — Airoha-based hardware; includes `firmware.bin` (719,638 B, **encrypted**: entropy 7.996, no readable strings; version 1.1.1.20).
  * **`MUSECSR`** — a CSR-based variant (versions 201/203/204); **no firmware file and no update flow** (the `<Firmware>` tag is commented out).
* The address ranges in the two `config.xml` files decide which profile applies. The tested speaker's Bluetooth address falls in the **MUSECSR** ranges, so `firmware.bin` in this package is **not** for that hardware. (That the chip really is a CSR is inferred from the label only [I].)

### `btlib.1562.{32,64}.dll` (Airoha variant) [C]

* Exports only five functions: `GetBattery`, `GetVersion`, `UpdateFirmware`, `GetSupportedHardware`, `CleanNV`. There is no volume/EQ/free-form control.
* Transport: a **Winsock Bluetooth RFCOMM socket** — `socket(AF_BTH=0x20, SOCK_STREAM, BTHPROTO_RFCOMM=3)`; `SOCKADDR_BTH` with the device address (parsed from `%02X:…`), **`serviceClassId = {00000000-0000-0000-0099-AABBCCDDEEFF}`** and `port = 0xFFFFFFFF` (Windows resolves the channel through SDP). The `baud=115200, handshake` text in the log strings is a leftover.
* Protocol: **Airoha RACE**. Commands sent through the library's single send routine (`0x1700`):

| Command ID | Reply type | Task (function whose log string names it) |
|---|---|---|
| `0x0CD6` | `0x5D` | `run_task_bluetooth_get_battery` |
| `0x1C07` | `0x5D` | `run_task_fota_get_version` |
| `0x1C00` | `0x5D` | `run_task_fota_query_partition_info` |
| `0x0A01` | `0x5B` | `run_task_nvkey_writefullkey` (used by `CleanNV`) |
| `0x1C0A`, `0x1C01`, `0x1C06`, `0x1C02` | `0x5D`/`0x5B` | used inside the FOTA tasks (`new_transaction`, `storage_erase_partition`, `check_integrity`, `write_state`, `commit`); the exact ID↔task mapping was not determined |

Nothing in this list reads or sets volume, EQ or any user setting.

## 3. Do the speaker's own firmwares contain a Bluetooth hook? [C]

* **Conexant ROM and patch**: no Bluetooth, AVRCP or "Logitech" strings, no UART/BT register use in the patch. The ROM does have a UART console/download path (`Download initiated ..`, `AEC Tuning- ESC to exit`), which is a development/tuning interface, not a Bluetooth link.
* **STM32 image**: no USART/SPI/USB peripheral at all; only I²C slave toward the Conexant chip.
* The teardown places the Conexant chip on the Bluetooth module's daughter board as an "audio cross mixer". The most consistent picture is that Bluetooth audio enters the Conexant chip as audio and that there is **no digital control link** between the Bluetooth module and the rest — consistent with the missing AVRCP record. **[I]**

## 4. Conclusion

* Adding a Bluetooth control channel by modifying the Conexant or STM32 firmware does not look feasible: the radio and its stack live in a separate module whose firmware is not in the vendor package for this hardware.
* The only open possibility is a *hidden* RFCOMM service on the Bluetooth module (for example the Airoha RACE GUID above). It cannot be ruled out with macOS tools; see "help wanted" in the README.
