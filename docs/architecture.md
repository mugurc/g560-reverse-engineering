# Architecture

Confidence tags: **[V]** verified on a real G560 with read-only requests · **[C]** observed directly in firmware code/data · **[I]** inference.

## Block diagram

```
   USB host (PC/Mac)                                   Bluetooth source
          │ USB 046d:0a78                                     │ A2DP
          ▼                                                   ▼
 ┌─────────────────────────────┐   audio (analog/I²S) [I]  ┌───────────────────────┐
 │ Conexant CX2070x family     │◄──────────────────────────│ Bluetooth module      │
 │  USB audio + HID, DSP       │                           │ (separate firmware;   │
 │  65C02-style core           │                           │  "MUSECSR" = CSR? [I])│
 │  ROM 0x7000–0xFFFF (36 KiB) │                           └───────────────────────┘
 │  external I²C EEPROM 32 KiB │
 │  (patch + config + USB/HID  │
 │   descriptors)              │
 └──────────────┬──────────────┘
                │ I²C — CX is master, 100 kHz, MCU slave address 0x77 (0xEE/0xEF)  [C]
                ▼
 ┌─────────────────────────────┐  I²C1 (MCU is master)
 │ STMicroelectronics STM32L100│──────────► 2 × TI TAS5731M class-D amplifiers, 8-bit addr 0x34 and 0x36  [C]
 │ Cortex-M3                   │──────────► 2 identical LED-driver-like devices, 8-bit addr 0x78 and 0x7E   [C]
 │  HID++ features, volume     │
 │  tables, LED effects        │
 └─────────────────────────────┘
```

## Components

| Component | Evidence | Tag |
|---|---|---|
| **Conexant CX2070x-family** audio chip (teardown names *CX20701* on the Bluetooth-module daughter board) | IgorsLab teardown; the EEPROM image ends with the `fwupd` device-kind signature `CX4` (= CX2070x patch); device speaks the Conexant HID memory protocol | [C][V] |
| **STM32L100** (ST, Cortex-M3) | IgorsLab teardown; peripheral base addresses in the MCU image match the STM32L1 map; MCU has **no** USART/SPI/USB | [C] |
| **2 × TI TAS5731M** | IgorsLab teardown; the MCU writes registers `0x00`=`0x6C`, `0x04`, `0x06` (soft mute), `0x07` (master volume), `0x1B`=`0` to I²C `0x34`/`0x36`, matching the TAS571x register map | [C] |
| LED drivers on I²C `0x78`/`0x7E` | two identical devices, register use (`0x25`, `0x4F`, `0x00`) resembles an IS31FL3236-type driver, **not confirmed**; the teardown does not name them (it says the STM32 drives four RGB channels) | [I] |
| Bluetooth module | SDP shows only an A2DP sink. The vendor's updater configuration labels this address range *MUSECSR* (CSR), but the chip itself was not identified | [I] |

## USB / HID interface [V]

One USB HID device (`046d:0a78`) with one interface and these reports (parsed from the report descriptor — see `tools/hid_report_descriptor.py`):

| Report ID | Dir | Data bytes | Meaning |
|---:|---|---:|---|
| 0x01 | IN | 1 | Consumer control (volume up/down, mute, …) |
| 0x02 / 0x03 | IN / OUT | 2 | Consumer-page vendor data |
| **0x04** | **OUT** | **36** | **Conexant memory access — request** |
| **0x05** | **IN** | **32** | **Conexant memory access — response** |
| 0x06 / 0x07 | OUT / IN | 36 / 32 | A second request/response pair (purpose unknown) |
| 0x08 | IN | 1 | Telephony (mute/hook) |
| **0x11** | IN/OUT | 19 | **HID++ 2.0 long report** (usage page `0xFF43`, usage `0x0202`) |

The HID descriptor lives in the EEPROM (at `0x494`; Telephony part `0x4F5`, HID++ part `0x516`). The ROM contains a default descriptor
with reports 1–7 (but without HID++).

## Who handles which HID++ feature?

HID++ requests arrive on report `0x11`. The Conexant patch forwards them to the MCU over I²C (19-byte frames starting with device index `0xFF`).
The MCU dispatcher (`0x080081AC`) owns a 10-entry feature table:

| MCU feature index | Feature ID | Functions | Notes |
|---:|---|---:|---|
| 4 | `0x8070` | 16 | ColorLEDEffects; fn 3 = `setZoneEffect` |
| 7 | `0x8320` | 1 | not documented in the sources I checked |
| 8 | `0x8040` | 3 | BrightnessControl |
| 9 | `0x8305` | 2 | not documented in the sources I checked |
| 0–3, 5, 6 | — | — | empty in the MCU: standard features (IRoot, IFeatureSet, …) are answered elsewhere, most likely by the Conexant side **[I]** |

## CX ↔ MCU I²C protocol [C]

The Conexant chip is the I²C **master**, the MCU the **slave** (7-bit address `0x77`, i.e. `0xEE` write / `0xEF` read, 100 kHz).
The CX builds a command block in RAM (`$1333`: control byte whose low 6 bits are the payload length, `$1334`: address byte, `$1335…`: payload)
and a ROM routine bit-bangs it. The MCU parses the byte stream with a small state machine (`0x0800A18A`):

| First byte | Total length | Meaning |
|---|---:|---|
| `0xFF` | 19 (+ an implicit leading `0x11`) | HID++ long report (device index `0xFF` = directly attached) |
| `0xCC` | 4 | short command. **`CC 00 01 <idx>` sets the master volume index** (0–50 from the CX; the MCU accepts `< 0x33`) |
| `0xBB` | 22 | long command. Seen from the CX: `BB 05 02 00` (version query; MCU answers `bb 05 02 00 'U' '1' … 22 03 … 23`, i.e. the "U1 22.03 build 0x23" that HID++ reports), `BB 05 04 01/00` (source/mode flag), `BB 05 01 …`, `BB 05 05 …`, `BB 03 01 80` |

The MCU signals "response ready" to the CX with a GPIO (GPIOC pin 8); the CX then reads from `0xEF`, and a reply starting with `0xFF` is a HID++ frame.

## Volume signal chain [C][V]

```
host volume (USB SET_CUR, 1/256 dB)          ┌──────────────── EEPROM 0x120: power-on gain 0xE5A7 ───────────────┐
        │                                     ▼                                                                   │
        └──► CX DSP gain $12CD:$12CC ──► reverse lookup in 51-entry curve (ROM routine in the patch, 0x236C)
                                              │  index 1…50
                                              ▼
                              I²C   CC 00 01 <idx>   (re-sent 6× after a change)
                                              ▼
                         MCU: master index (RAM 0x20001BF8, default 25 until the first CX message)
                                              ▼
              amp register 0x07 = table1[idx] on 0x36,  table2[idx] − 2·subTrim[level/5] on 0x34
```

Details: [conexant-cx2070x.md](conexant-cx2070x.md), [mcu-stm32.md](mcu-stm32.md), [startup-volume.md](startup-volume.md).
