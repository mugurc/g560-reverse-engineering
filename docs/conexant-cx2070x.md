# Conexant (CX2070x family) — EEPROM, patch, HID memory access, ROM

Tags: **[V]** verified on a real G560 with read-only requests · **[C]** observed in firmware code/data · **[I]** inference.
Offsets marked `img` are offsets in the decoded S-record image (`tools/s37_decode.py`); `cpu` are 65C02 code addresses.

## 1. The firmware package

The Windows updater `G560Update_122.3.23.exe` embeds two `FIRMWARE` resources (`tools/pe_extract.py`):

| Resource | Size | What it is |
|---|---:|---|
| `10000` | 45,909 B | plain-text **Motorola S-record** (598 `S3` records, all checksums valid, 18,455 payload bytes) = the **Conexant EEPROM image** |
| `10001` | 34,497 B | the STM32 image `Muse_DfuImg` — see [mcu-stm32.md](mcu-stm32.md) |

The image covers `img` ranges `0x002–0x08B` (VID/PID, USB strings), `0x10C–0x531` (config, HID descriptors), `0xB50–0x4EB9` (**17 KB of 65C02 patch code + tables**).

The updater also contains the Conexant "CAPE" library with several loader paths (`I2C bootloader`, `UART bootloader`, `ROM bootloader`, `Other Reno bootloader`), plus checks named `LayoutSignature`, `Device signature` and `Bad Checksum` (the last one refers to S-record line checksums). Device-class names inside it: `CX20562, CX2070x, CX2076x, CX2077x, CX2085x, CX2089x, CX2098x, CX2198x`.

## 2. EEPROM layout [C][V]

The layout matches what `fwupd` documents for this family ([`plugins/synaptics-cxaudio`](https://github.com/fwupd/fwupd/tree/main/plugins/synaptics-cxaudio)), and the G560's real EEPROM matches the 122.3.23 image **byte for byte** [V]:

| Offset | Content | Value on the G560 |
|---:|---|---|
| `0x00` | validity signature `'L'` | `4C` |
| `0x01` | EEPROM size code, `size = 1 << (code + 8)` | `07` → **32 KiB** |
| `0x14` | patch info: signature `'P'` + `u16le` patch address | `50 50 0B` → patch at **`0x0B50`** |
| `0x20` | custom info: patch-version-string address `u16le`, `cpx_patch_version[3]`, `spx_patch_version[4]`, **`layout_signature 'S'`**, `layout_version`, `application_status`, **VID**, **PID**, revision, string addresses | string at `0x4E79`; `'S'`, layout v**3**; VID `046D`, PID `0A78` |
| `0xBC` | "test mark" (protected by `fwupd`) | |
| `0x10C…0x531` | config + USB/HID descriptors (HID report descriptor at `0x494`) | |
| `0xB50…0x4EB9` | patch code, hook table, tables | version string `Logitech_G560_Pa…_9064_NVM-CHAN_…` at `0x4E79` |
| `0x4EB7` | device-kind signature `"CX4"` (`'4'` → CX2070x patch in `fwupd`) | |
| `0x7FFD` | a lone `0x08` byte outside the vendor image | meaning unknown |

Everything after `0x4EBA` is `0xFF` except `0x7FFD`.

**Write ordering used by the vendor** [C]: the S-record file starts with `0x14 ← 0x00` (invalidate the patch signature), writes the body, and ends with `0x20`, `0x25`, `0x4EB7 ("CX4")` and finally `0x14 ← 'P'`. The Windows tool's strings (`invalidating header`, `validating header`, `write magic failed`, `forcing delay after write operation`) describe the same discipline. No CRC/checksum over the EEPROM contents was found in `fwupd` or the vendor tool (whether the ROM checks one at boot is **unknown**).

## 3. HID memory-access protocol [V]

The G560's HID report descriptor declares report `0x04` OUT (36 B) and `0x05` IN (32 B) — exactly `fwupd`'s `MEM_WRITEID`/`MEM_READID`.

```
OUT report 0x04 (37 bytes on the wire including the report ID)
  [0] 0x04
  [1] flags: bit4 = address >= 64 KiB, bit5 = target is EEPROM, bit6 = WRITE
  [2] length (1..32)
  [3] address high   [4] address low           (big-endian)
  [5..36] payload (write) / zeros (read)

Read:  send the OUT report with bit6 clear, then GET_REPORT(IN, id 0x05, 33 bytes) → data in [1..32]
```

* `bit5` clear addresses the chip's CPU address space (RAM and ROM; the wire format does not distinguish them). ROM writes are rejected by `fwupd`.
* `fwupd` writes in 32-byte chunks with read-back verification, parks the firmware first (sets bit 7 of RAM `0x1000`) and unparks afterwards; the Windows tool forces a delay after each write on CX2070x.
* Known RAM locations (from `fwupd`, confirmed readable): `0x1000` park, `0x1001–0x1004` firmware version, `0x1005` chip id, `0x0400` reset (bit 6).

`tools/cx_hid_read.py` implements **reads only**; the single function that sends packets rejects any packet whose write bit is set, whose data field is non-zero, or whose length/ID is not exactly a read request.

### What we read [V]

* RAM `0x1000…0x1008` = `01 02 05 01 01 01 0F 0E 1D` — not parked; firmware version bytes `02 05 01 01` → `05.02.01.01` in `fwupd`'s formatting. The ROM contains the string `CHAN_V05.02.01.01`.
* Full EEPROM (32,768 B) — identical to the 122.3.23 image (and 15,463 bytes different from 122.2.22): **the speaker runs 122.3.23**.
* ROM `0x7000–0xFFFF` (36,864 B). Reset vector `0x7000`, NMI `0x70F5`, IRQ `0x7003`.
* RAM windows `0x12CC–0x12DF` and `0x15A0–0x164F` (live volume state, see [startup-volume.md](startup-volume.md)). Volatile-looking areas (`$13xx`, `$1417`, …) were deliberately not read.

## 4. Address space and the patch [C][V]

* The HID memory interface sees one address space. The patch is loaded into RAM: the code at `cpu 0x2056` on the device equals `img 0x172F` (**`cpu = img + 0x927`** for code). `img 0xB50–0xB5B` is a header that is not loaded; the **hook table** appears at `cpu 0x1488` on the device (the formula would give `0x1483`, so the loader places that part with a small offset — not understood).
* Regions of the image that look like gaps hold **live variables** at run time (e.g. `$15F0` is the current volume index). Variable/register addresses such as `$15F9`, `$1333` are therefore not code.
* **Hook table**: 3-byte entries, `4C lo hi` (`JMP target`) or `60 60 60` (`RTS`, unused). The ROM calls the table with `JSR $14xx` from about 40 places (pattern search, not full disassembly); ~32 entries are populated.
* **Non-standard instructions.** The core is a 65C02 variant with extra 4–5 byte opcodes. Observed in the patch: `D2 mask lo hi` = set bits `mask` in the byte at `lo/hi`, `C2 mask lo hi` = clear bits, `F2 lo hi mask rel` = test bits and branch (inferred). Generic disassemblers (e.g. Capstone's MOS65XX) mis-decode them as `CMP (zp)`/`NOP`/`SBC (zp)` and can lose sync — `tools/cx_dis.py` therefore prints with that caveat. Example: `D2 01 21 16` sets bit 0 of `$1621`, which the code uses as "start an I²C transfer".
* **I²C command block** (RAM `$1333…$1338`): control byte (`D6` → 22-byte `BB…` frame, `C4` → 4-byte `CC…` frame, `93/D3` → 19-byte HID++ frame, `93` with address `EF` = read), slave address (`EE`/`EF`), payload. Message catalogue: [architecture.md](architecture.md).
* **Timing at boot** [V]: after the device re-enumerates the CX computes its volume index ~2.2 s later and sends it 6 times (counter `$1637` runs 0→5, ~130–160 ms apart).

## 5. Volume data [C][V]

### 5.1 The 51-entry curve (gain in 1/256 dB, signed 16-bit)

Stored as two byte arrays (low bytes at `img 0x1A8B`, high bytes at `img 0x1ABE`). Identical in 122.2.22 and 122.3.23. (A first reading that joined them as 16-bit little-endian words produced a bogus "27-step" table — beware.)
The patch converts the current DSP gain (`$12CD:$12CC`) back to an index with a reverse lookup (`cpu 0x236C`); indices 1…50 are used (index 0 means mute on the MCU side).

| idx | value | dB |  | idx | value | dB |
|---:|---|---:|---|---:|---|---:|
| 0 | `0xCA00` | -54.00 |  | 26 | `0xF294` | -13.42 |
| 1 | `0xD055` | -47.67 |  | 27 | `0xF31C` | -12.89 |
| 2 | `0xD4CA` | -43.21 |  | 28 | `0xF3A1` | -12.37 |
| 3 | `0xD83B` | -39.77 |  | 29 | `0xF420` | -11.88 |
| 4 | `0xDB08` | -36.97 |  | 30 | `0xF49C` | -11.39 |
| 5 | `0xDD66` | -34.60 |  | 31 | `0xF514` | -10.92 |
| 6 | `0xDF72` | -32.55 |  | 32 | `0xF589` | -10.46 |
| 7 | `0xE140` | -30.75 |  | 33 | `0xF5FA` | -10.02 |
| 8 | `0xE2DD` | -29.14 |  | 34 | `0xF667` | -9.60 |
| 9 | `0xE452` | -27.68 |  | 35 | `0xF6D2` | -9.18 |
| **10** | **`0xE5A7`** | **-26.35** |  | 36 | `0xF73A` | -8.77 |
| 11 | `0xE6E0` | -25.12 |  | 37 | `0xF79F` | -8.38 |
| 12 | `0xE801` | -24.00 |  | 38 | `0xF802` | -7.99 |
| 13 | `0xE90F` | -22.94 |  | 39 | `0xF862` | -7.62 |
| 14 | `0xEA0B` | -21.96 |  | 40 | `0xF8C0` | -7.25 |
| 15 | `0xEAF8` | -21.03 |  | 41 | `0xF91C` | -6.89 |
| 16 | `0xEBD7` | -20.16 |  | 42 | `0xF976` | -6.54 |
| 17 | `0xECAA` | -19.34 |  | 43 | `0xF9CD` | -6.20 |
| 18 | `0xED73` | -18.55 |  | 44 | `0xFA23` | -5.86 |
| 19 | `0xEE31` | -17.81 |  | 45 | `0xFA77` | -5.54 |
| 20 | `0xEEE7` | -17.10 |  | 46 | `0xFAC9` | -5.21 |
| 21 | `0xEF94` | -16.42 |  | 47 | `0xFB19` | -4.90 |
| 22 | `0xF03A` | -15.77 |  | 48 | `0xFB68` | -4.59 |
| 23 | `0xF0D9` | -15.15 |  | 49 | `0xFBB5` | -4.29 |
| 24 | `0xF172` | -14.55 |  | 50 | `0xFC00` | -4.00 |
| 25 | `0xF206` | -13.98 |  | | | |

### 5.2 The volume range block (EEPROM `0x11A`) [C][V]

Quadruples of 16-bit little-endian words `(min, max, resolution, current)`, same in both firmware versions:

| Group | min | max | res | current (default) |
|---|---|---|---|---|
| 1 (playback master) | `0xCA00` (−54 dB) | `0xFC00` (−4 dB) | `0x0100` (1 dB) | **`0xE5A7`** (−26.35 dB = curve idx 10) |
| 2 | `0xCE00` (−50 dB) | `0x0500` (+5 dB) | 1 dB | `0xFB00` (−5 dB) |
| 3 | `0xE200` (−30 dB) | `0x0500` (+5 dB) | 1 dB | `0x0000` |

The host sees min/max as −54.0…−4.0 dB through CoreAudio [V] (this confirms the block is the USB volume-control range). `0xE5A7` is the only "current" value that is an exact curve entry rather than a round number, and four copies of it sit in RAM at `$12D0–$12D7`.

## 6. ROM facts [C]

* Strings: `(C) CONEXANT`, `CHAN_V05.02.01.01`, `Download initiated ..`, `Upload completed - power cycle device`, `Upload error - Try again`, `AEC Tuning- ESC to exit`, `DSP LOCKUP` → the ROM has a **UART console / download path**.
* Default USB identity (used when no EEPROM overrides it): device descriptor at `ROM 0xED47` = **`0572:1410`**, strings `Conexant`, `CONEXANT USB AUDIO`, `Communication Audio`.
* Default HID report descriptor at `0xEF20` already contains reports `0x01…0x07` (including the memory-access pair) — relevant for recovery ([risks-and-recovery.md](risks-and-recovery.md)).
* **No** Bluetooth, AVRCP or "Logitech" strings anywhere in ROM or patch.

## 7. Unknown / open

* Full disassembly of the ROM (needs the extended instruction set).
* Why the hook table is placed 5 bytes off the simple `+0x927` rule.
* Whether the ROM validates the EEPROM beyond the `'L'`/`'P'`/`'S'` signatures.
* The meaning of report pair `0x06/0x07` and of EEPROM byte `0x7FFD`.
* Where the standard HID++ features (IRoot, IFeatureSet, device name, firmware version) are implemented.
