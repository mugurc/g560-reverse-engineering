# Where does the startup volume come from?

Tags: **[V]** verified on a real G560 with read-only requests · **[C]** observed in firmware · **[I]** inference.

## Result in one paragraph

When the speaker is powered on, the Conexant chip's volume gain is **`0xE5A7` = −26.35 dB = curve index 10** **[V]** (stored in EEPROM at `0x120`). A USB host rewrites that gain ~0.13 s after the device enumerates **[V]**, so with a host attached the power-on value is almost never visible. The STM32's own default (master index 25) is live for only ~2 s, until the Conexant chip sends its first index **[V][C]**. For use *without* a USB host (Bluetooth/aux only) the effective startup volume should therefore be curve index 10 — an **inference [I]**, because that situation cannot be observed over USB.

## Why a normal "read the volume" test cannot work

macOS stores a per-device volume and restores it as soon as the device appears. Reading it back with CoreAudio gives the *restored* value:

* range reported by the device: **−54.0 … −4.0 dB** (matches the EEPROM range block, see [conexant-cx2070x.md](conexant-cx2070x.md)) [V]
* current: **−19.0 dB, scalar 0.49** — neither of the candidate defaults (and not a curve entry: 1 dB resolution). macOS's scalar↔dB mapping is not linear ((−19+54)/50 would be 0.70).

Reading the live RAM instead of asking the OS showed the structure [V]:

| RAM | Value | Meaning |
|---|---|---|
| `$12CC–$12CF` | `00 ED 00 ED` | live gain, two channels = `0xED00` = −19.0 dB |
| `$12D0–$12D7` | `A7 E5` ×4 | four copies of the power-on gain `0xE5A7` (survive the host's change) |
| `$12D8–$12DB` | `00 FB` ×2 | the second range group's default (`0xFB00`, −5 dB) |
| `$15F0` | `0x11` (17) | the index the patch derives from the live gain by reverse lookup — `0xED00` falls on curve index 17 (−19.34 dB), which confirms the lookup model |
| `$1637` | `5` | the resend counter's cap (`cpx #5` in the code) |

## The cold-boot experiment [V]

`tools/cx_boot_watch.py` was started with the USB cable connected; the speaker's **power cable** was pulled and re-inserted (the device disappeared from USB and reappeared, i.e. the Conexant chip really cold-booted). Timeline (seconds on the watcher's clock):

| t | Event |
|---:|---|
| 58.3 | device disappeared |
| 84.034 | device re-enumerated |
| **84.072** | **first read: live gain `E5A7 / E5A7`**, `$15F0 = 0xFF` (unset), frame length 0, counter 0 |
| 84.169 | left channel changed to `ED00` (macOS restoring the volume, +0.135 s) |
| 84.201 | right channel `ED00` (+0.167 s) |
| 86.227 | `$15F0 = 0x11`, frame length `0x04` (a `CC 00 01 11` message is being sent) |
| 86.385 … 86.964 | counter 1→5: the same index was sent 6 times, ~130–160 ms apart |
| 88.482 | frame length `0x13` (HID++ traffic) |

Conclusions:

1. **The power-on gain is `0xE5A7`** (curve index 10). [V]
2. The host overwrites it within ~0.13 s; the Conexant patch computes and sends the index only **~2.2 s** after enumeration. In this run it went straight from "unset" to 17 — an index of 10 was never sent because the host had already changed the gain. [V]
3. Without a host the gain would still be `0xE5A7` at that moment, the reverse lookup would give 10, and `CC 00 01 0A` would be sent. [I] — this is what the code says, but it was not observed.
4. The STM32's default index 25 (−23 dB on the satellite amplifier with the scale below) is thus only a ~2 s placeholder. [C][V]

## What the amplifier gets [I]

The MCU writes `table[idx]` to the TAS5731M master-volume register (`0.5 dB` per step, lower value = louder, `dB = 24 − value/2` — the scale is established for the TAS571x family in the Linux driver and assumed for the TAS5731M):

| Master index | Source | Satellite amp (0x36) | Sub path (0x34, before trim) |
|---:|---|---|---|
| 10 | Conexant power-on gain | table 1 `0x7C` → −38 dB | table 2 `0x78` → −36 dB |
| 17 | macOS-restored −19 dB in the test | `0x6E` → −31 dB | `0x6A` → −29 dB |
| 25 | STM32 placeholder | `0x5E` → −23 dB | `0x5A` → −21 dB |

so the two candidate defaults differ by about 15 dB at the amplifier.

## Which bytes decide the startup volume? [I]

* **Not** the STM32 byte at body offset `0x35AE` (`19 20`): it only matters for ~2 s.
* The Conexant EEPROM word at **`0x120–0x121`** (`A7 E5`). Whether the four RAM copies and the live gain are all derived from this word is likely but not proven. A new value should be an exact entry of the 51-step curve (the reverse lookup picks the largest index whose entry is ≤ the live gain).
* **Nothing was written.** See [risks-and-recovery.md](risks-and-recovery.md).
