# STM32 microcontroller image (`Muse_DfuImg`)

Tags: **[C]** observed in firmware code/data · **[I]** inference. Addresses are flash addresses (image base `0x08004000`).
All of this comes from static analysis of the image inside the vendor's Windows updater; the MCU itself was never read or written.

## 1. Image format [C]

`10001` inside `G560Update_*.exe` is a 64-byte U-Boot-style header followed by the body (`tools/uimg.py`):

| Field | 122.3.23 | 122.2.22 |
|---|---|---|
| magic | `0x27051956` | same |
| body size | 34,433 B | 34,051 B |
| load / entry | `0x08004000` | same |
| build date | 2021-03-18 | 2018-10-08 |
| OS / arch / type / compression | 5 / 2 / 2 / 1, name `Muse_DfuImg` | same |
| header CRC, data CRC | **CRC-16/XMODEM** (poly `0x1021`, init 0; header CRC computed with the CRC field zeroed), both valid | both valid |

There is **no cryptographic signature at this layer**. (Whether the device-side bootloader — flash `0x08000000–0x08003FFF`, not part of the update — checks anything else is unknown, as is the transport used to deliver the image.)
The entropy of the body is ≈6.7 bits/byte (plain Thumb code).

Body layout: vector table (60 entries = 16 system + 45 IRQs, `SP=0x200006E0`, `Reset=0x0800C52D`), code from `0x080040F4`.

## 2. Peripherals [C]

Peripheral base addresses actually loaded by the code (not just present as data): I²C1 and I²C2, GPIOA/B/C/F(H), ADC, TIM3–TIM7, DMA1/DMA2, EXTI, IWDG, RCC, PWR, FLASH interface. This matches an **STM32L1** (the teardown names an **STM32L100**). **There is no USART, SPI or USB peripheral** — the MCU can only talk to the rest of the speaker over I²C and GPIO.

* **I²C1 (master, 100 kHz, DMA ch 6/7)** with a 96-slot × 32-byte transaction queue at `0x200006E0`. Devices: `0x34` and `0x36` (two amplifiers), `0x78` and `0x7E` (two identical LED-driver-like devices). Writes to `0x34/0x36` are dropped while GPIOC pin 15 reads low, writes to `0x78` while GPIOB pin 0 reads high (presumably "amp rail off" / "LEDs off").
* **I²C2 (slave, 7-bit `0x77`)** with RX/TX ring buffers. This is the link to the Conexant chip; GPIOC pin 8 is used to tell the CX that a response is ready.
* Persistent settings live in a CRC-16-protected store read by `0x08005484(buf, addr, len)` (callers use ids such as `0x3D`, `0x80`, `0x2D`, `0x88`).
* Flash-controller registers are used by routines at `0x080072E8…0x080073A6` (self-programming of settings).

## 3. HID++ dispatcher [C]

Requests from the CX arrive as `[deviceIdx=0xFF][featureIdx][func<<4 | swId][params…]`; `0x080081AC` handles them:

* `deviceIdx != 0xFF` → error `0x0A`; `featureIdx ≥ 10` → error `0x06`; `func ≥ nfuncs` → error `0x07`; a feature flagged with bit 5 returns error `0x05` until RAM flag `0x20001C03` is set; errors are returned as `FF <featureIdx> <func|swId> <err>`.
* Feature table at `0x0800C394` (10 pointers to 12-byte records `{id:u16, flags:u8, nfuncs:u8, …, funcTable*}`):

| idx | ID | nfuncs | function table |
|---:|---|---:|---|
| 4 | `0x8070` | 16 | `0x0800C300` (fn 3 `setZoneEffect` = `0x08004C85`) |
| 7 | `0x8320` | 1 | `0x0800C4FC` |
| 8 | `0x8040` | 3 | `0x0800C47C` (`0x0800C241`, `0x0800C255`, `0x0800C291`) |
| 9 | `0x8305` | 2 | `0x0800C49C` |

* A mailbox ("channel") table at `0x2000034C` (10 × 8 bytes) connects the I²C layer to the logic. The message pump `0x08005AD8` reads channels 7/8 (incoming HID++ long/short), writes 4/5/6 (response/error/notification) and 0/1/2 (status reports).
* Notifications are built per feature through a second record array (`0x0800C3BC`).

## 4. Command interpreter (messages other than HID++) [C]

`0x0800A298` interprets the 4-byte and 22-byte commands described in [architecture.md](architecture.md). Notable ones:

* `CC 00 01 <idx>` → `0x0800AC16`: if `idx < 0x33` and the amplifiers are enabled, store the master index at `0x20001BF8` and apply it (`0x0800AF30`).
* `BB 05 02 …` → builds the version reply `bb 05 02 00 55 31 … 22 03 … 23` (`'U' '1'`, 22.03, build `0x23`).
* `BB 05 04 <0/1>` → source/mode flag; `BB 05 05 <0/1>` → another flag; `BB 03 0x` → power/mute style transitions; `BB 05 01 <1|5>` → actions including a settings write.

## 5. Volume logic [C]

* Amplifier registers (TAS5731M-family): `0x07` master volume, `0x06` soft mute (`3` mute / `0` unmute), `0x00` = `0x6C`, `0x04`, `0x1B` oscillator trim = `0` during init. Register meanings are cross-checked against the Linux `tas571x` driver (**TAS5731M datasheet not consulted** [I]).
* Two **52-entry byte tables** map the master index (0…51) to register `0x07`: table 1 → amplifier `0x36` (satellites?), table 2 → amplifier `0x34` (very likely the subwoofer) with an additional subwoofer trim: `reg = clamp(table2[idx] − 2·trim[level/5], 0, 0xFE)`, `level` = 0…100 stored in the settings store (id `0x88`, default **70**).
* In the TAS571x family the register is in 0.5 dB steps with *lower value = louder*: `dB = 24 − value/2` (`0x00` = +24 dB, `0x30` = 0 dB, `0xFE`/`0xFF` ≈ mute). **[I]** — proven for the family in the Linux driver, assumed for the TAS5731M.
* **Default master index = 25** in both versions: the init function (`0x080074BA`) calls `0x080075A4`, which does `movs r0,#0x19 ; strb r0,[0x20001BF8]` (instruction bytes `19 20` at body offset `0x35AE`). This value is only effective until the Conexant chip sends its own index (~2 s after boot) — see [startup-volume.md](startup-volume.md).

### Tables (hex, index 0 → 51)

122.3.23 (`0x0800AC8C`, `0x0800ACC0`):

```
table 1 (amp 0x36): fe a3 9d 97 91 8b 88 85 80 7e 7c 7a 78 76 74 72 70 6e 6c 6a 68 66 64 62 60 5e 5b 58 56 54 52 50 4e 4d 4c 49 48 47 46 45 44 43 42 40 3e 3c 3a 38 36 33 2e 00
table 2 (amp 0x34): fe 9f 99 93 8d 87 82 7f 7c 7a 78 76 74 72 70 6e 6c 6a 68 66 64 62 60 5e 5c 5a 57 54 52 50 4e 4c 4a 49 48 46 45 44 43 42 41 40 3f 3e 3d 3c 3b 3a 38 35 30 00
```

122.2.22 (`0x0800AD80`, `0x0800ADB4`):

```
table 1 (amp 0x36): fe ae aa a6 a2 9b 98 95 91 8e 8b 88 85 82 7f 7c 79 76 73 70 6d 6a 67 64 61 5e 5b 58 56 54 52 50 4e 4c 4c 49 48 47 46 45 44 43 42 40 3e 3c 3a 38 36 33 2e 00
table 2 (amp 0x34): fe c3 bf bb b7 b0 ac a8 a4 9f 9b 97 93 8f 8b 87 83 7f 7b 77 73 6f 6b 67 63 5f 5b 57 53 53 4f 4d 4b 49 49 46 45 44 43 42 41 40 3f 3e 3d 3c 3b 3a 39 37 30 00
```

These tables are what the vendor's 122.3.23 release note calls the adjusted "master volume curve" for satellites and subwoofer; the Conexant 51-entry gain curve is **identical** in both versions. With the `dB = 24 − v/2` assumption, for example index 25 is −23 dB (satellites) / −21 dB (subwoofer path) in 122.3.23, and the low indices differ noticeably between versions (index 1: satellites `0xAE`→`0xA3`, subwoofer `0xC3`→`0x9F`).

## 6. LEDs [C][I]

LED effects run on this MCU (`0x8070` ColorLEDEffects, `0x8040` BrightnessControl). The two devices at `0x78`/`0x7E` receive per-channel writes plus "update" (`0x25`), "reset" (`0x4F`) and "shutdown" (`0x00`) register writes; the exact part is not identified. The LED/startup-animation code has **not** been analysed.

## 7. Not analysed

* Update protocol / bootloader of the MCU.
* LED effect engine and the startup animation.
* The other MCU-side messages (`BB 03 …`, `BB 05 01 …`) beyond the sketch above.
