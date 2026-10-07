# Logitech G560 — reverse-engineering notes

Unofficial, independent research notes and tools about the internals of the **Logitech G560 LIGHTSYNC gaming speaker**
(USB `046d:0a78`): which chips it contains, how they talk to each other, how the firmware images are structured,
where the startup volume comes from, and what is (not) possible over Bluetooth.

> **Not affiliated with Logitech, Conexant, Synaptics, STMicroelectronics or Texas Instruments.** All trademarks belong to their owners.
> **No proprietary firmware is included in this repository** — only notes, hashes of the official downloads, and tools you run on files you download yourself.
> **Everything done on a real device was read-only.** Nothing was ever written to the speaker. See [what was *not* done](#what-was-not-done).

## TL;DR

Confidence tags: **[V]** verified on a real G560 with read-only requests · **[C]** observed directly in firmware code or data · **[I]** inference / hypothesis.

* **Architecture** — USB host → *Conexant CX2070x-family* audio chip (65C02-based, USB + DSP) → I²C → *STM32L100* microcontroller → two *TI TAS5731M* class-D amplifiers (and the LED driving). **[C][V]** → [docs/architecture.md](docs/architecture.md)
* **Firmware images** — the Windows updater contains two images: a Conexant **EEPROM image** (Motorola S-record) and an STM32 image (`Muse_DfuImg`, U-Boot-like header, CRC-16/XMODEM, **no signature at that layer**). **[C]**
* **The device exposes the Conexant HID "memory access" interface** (report `0x04` OUT 36 B / `0x05` IN 32 B — the same one `fwupd`'s `synaptics-cxaudio` plugin uses). We dumped the full 32 KiB EEPROM and 36 KiB of ROM with it; the EEPROM is **byte-identical to the 122.3.23 image** in the updater. **[V]** → [docs/conexant-cx2070x.md](docs/conexant-cx2070x.md)
* **Startup volume** — the chip powers up at a gain of `0xE5A7` (−26.35 dB, curve index 10), stored at EEPROM `0x120`. A USB host overwrites it within ~0.13 s; the MCU's own default (index 25) is only live for ~2 s. **[V]** for the power-on gain and timings, **[I]** for the Bluetooth-only consequence → [docs/startup-volume.md](docs/startup-volume.md)
* **Bluetooth** — the speaker publishes **only an A2DP sink** over SDP (no AVRCP/HFP/SPP). No Bluetooth-related strings, registers or peripherals were found in either firmware (the Conexant ROM was dumped but not fully disassembled). **No Bluetooth control channel was found**; the vendor's BT updater library speaks Airoha RACE, which belongs to a *different* hardware variant. **[V][C]** → [docs/bluetooth.md](docs/bluetooth.md)
* **Volume curve changes** between firmware 122.2.22 and 122.3.23 are in the **MCU's amplifier tables**, not in the Conexant image. **[C]** → [docs/mcu-stm32.md](docs/mcu-stm32.md)
* **Risks & recovery** for modifying the startup volume were researched but **not exercised** → [docs/risks-and-recovery.md](docs/risks-and-recovery.md)

## Repository layout

| Path | Contents |
|---|---|
| [`docs/`](docs/) | Findings, by topic (architecture, Conexant, MCU, Bluetooth, startup volume, risks, how to reproduce) |
| [`docs/tr/NOTES.tr.md`](docs/tr/NOTES.tr.md) | The original chronological working notes, in Turkish |
| [`tools/`](tools/) | Python/Swift tools. Offline analysers (no device needed) and a small number of **read-only** device tools |
| [`LICENSE`](LICENSE) | MIT — code |
| [`LICENSE-DOCS.md`](LICENSE-DOCS.md) | CC BY 4.0 — documentation |

## Tools

Offline (work on files you obtain from the vendor — see [docs/reproduce.md](docs/reproduce.md)):

| Tool | Purpose |
|---|---|
| `pe_extract.py` | Pull the embedded `FIRMWARE` resources out of the Windows updater `.exe` |
| `s37_decode.py` | Motorola S-record → flat binary (also verifies record checksums) |
| `uimg.py` | Validate/unpack the `Muse_DfuImg` header (CRC-16/XMODEM) |
| `mcu_dis.py` | Thumb-2 disassembler + cross-references for the STM32 image |
| `cx_dis.py` | 65C02 recursive-descent disassembler for the Conexant patch (address map, hook table) |
| `pe_func.py`, `pe_strxref.py` | x86-64 helpers for the vendor's Windows DLLs |

Host-side, read-only (macOS): `hid_report_descriptor.py` (reads the cached HID descriptor from `ioreg`), `sdp_dump.py` (SDP query),
`g560_db.swift` / `g560_volume.swift` (CoreAudio volume read).

Device tools:

| Tool | Notes |
|---|---|
| `cx_hid_read.py` | **Read-only** Conexant memory reader. The only code path that talks to the device refuses any packet with the write bit set. |
| `cx_boot_watch.py` | Watches the device disappear/reappear and samples a few RAM words at boot (read-only) |
| `rfcomm_scan.py` | Tries to open RFCOMM channels 1–30 (opens data channels; sends nothing) |
| `probe_hidpp.py`, `watch_hidpp.py` | Read-only HID++ 2.0 feature enumeration / polling |
| `g560.py` | ⚠️ **Writes** LED settings to the device (and can make them persistent). Earlier experiment, use at your own risk |

## Quick start

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt           # hidapi, capstone, pefile (+ pyobjc on macOS for Bluetooth tools)

python3 -I tools/hid_report_descriptor.py              # no device I/O: shows the report IDs the speaker declares
python3 -I tools/cx_hid_read.py --dry-run ram 1000 9   # prints the packet that WOULD be sent; sends nothing
python3 -I tools/cx_hid_read.py ram 1000 9             # real read: CX RAM 0x1000..0x1008 (firmware version etc.)
```

Tested on macOS (Apple silicon). The HID tools use `hidapi`, so Linux/Windows should work in principle but are untested.
`g560.py`, `probe_hidpp.py` and `watch_hidpp.py` import each other, so run those three from inside `tools/`.

## What was *not* done

* No firmware, EEPROM or RAM byte was ever **written** to the speaker. The risk analysis in `docs/risks-and-recovery.md` is a plan, not an experience report.
* The STM32 firmware update protocol and the speaker's Bluetooth module firmware were **not** analysed (the latter is not in the vendor package for this hardware variant).
* The CX ROM was dumped but **not fully disassembled** (the CPU has non-standard extended instructions that common disassemblers mis-decode).
* The startup-volume claim for Bluetooth-only use is an inference: with a USB host attached, the host overwrites the value too quickly to observe it.
* LED/startup-animation logic was not analysed.

## Contributing / help wanted

Corrections are very welcome — most hypotheses here are tagged **[I]** for a reason. Particularly useful:

* A second G560 (or another hardware revision) to compare EEPROM dumps and the BT module.
* Someone with a Linux box: `sdptool browse <addr>` / `bluetoothctl` against the speaker would settle whether a hidden RFCOMM service exists (macOS cannot tell "refused" from "not permitted").
* The extended 65C02 instruction set of the Conexant core (`B2/C2/D2/E2/F2 …`).
* Datasheet-level confirmation of the TAS5731M volume register scale.

## Safety note

Writing to the Conexant EEPROM or the MCU can brick the speaker. There is no official recovery procedure, and Logitech states that its firmware tools are no longer supported.
Nothing here is advice to do so. If you experiment, dump and keep your own EEPROM backup first.

## License

Code: [MIT](LICENSE). Documentation: [CC BY 4.0](LICENSE-DOCS.md).
