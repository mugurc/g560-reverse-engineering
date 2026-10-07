# Risks and recovery (a plan — nothing was written)

> **No byte was ever written to the speaker by this project.** This page analyses what *would* be involved in changing the startup volume
> (EEPROM word at `0x120–0x121`) and what could go wrong. It is **not** a how-to and it is **untested**.
> There is no official recovery procedure for the G560, Logitech states that its firmware update tools are no longer supported,
> and I found no public report of a G560 being bricked or recovered. Everything below about recovery is indirect evidence.

## What the minimal change would be

* **Target:** EEPROM `0x120–0x121` (currently `A7 E5` = `0xE5A7`, curve index 10), 2 bytes, written in a single chunk. A new value must be an exact entry of the 51-step curve ([conexant-cx2070x.md](conexant-cx2070x.md#51-the-51-entry-curve-gain-in-1256-db-signed-16-bit)).
* **Never write:** `0x00–0x01` (`'L'` + size code), `0x14` (`'P'` patch signature), `0x29` (`'S'` layout signature), `0xBC`, serial-number string/pointer, `0x7FFD`, the patch region `0xB50…`, or the whole image.
* **Not covered:** the STM32 — it sits behind the Conexant chip on I²C and cannot be reached with the HID memory protocol.

## How `fwupd` writes this family (for reference)

From the public [`synaptics-cxaudio`](https://github.com/fwupd/fwupd/tree/main/plugins/synaptics-cxaudio) plugin: set bit 7 of RAM `0x1000` ("park" the firmware) → write 32-byte chunks to the EEPROM, reading each back and comparing → (for full images) invalidate the old patch → clear the park bit. The plugin refuses to proceed on a blank/disabled EEPROM or wrong magic byte, never writes to ROM, and has no rollback if a write fails midway. The vendor's Windows tool additionally waits after each write on CX2070x and uses an "invalidate header → write → validate header" order (the S-record file itself ends with `0x14 ← 'P'`).

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Software bug writes the wrong bytes/address | low | corrupts a small region | dry-run first; hard-coded address/length checks; compare a full EEPROM dump before and after (exactly 2 bytes must differ) |
| Power/USB glitch **during a 2-byte write** | very low | worst case one wrong/half-written byte → another startup volume; device keeps working | don't touch cables during the write. Unlike large multi-chunk writes this is not a brick scenario |
| Script dies between "park" and "unpark" | low | firmware left parked, audio/HID may stall | `try/finally` unpark; park is RAM state, a power cycle clears it |
| **Hidden integrity check** over the EEPROM contents | low, **unknown** | ROM may treat the EEPROM as invalid and fall back to its built-in identity `0572:1410` | no CRC/checksum was found in `fwupd` or in the vendor tool (only `'L'`, `'P'`, `'S'`, `CX4` markers), and the vendor S-records carry arbitrary per-product bytes — but the ROM's boot code was not disassembled |
| Recovery path fails (device doesn't re-enumerate usefully) | unknown | hardware work | see below |
| Warranty / support | — | unofficial; modifying firmware may void the warranty; vendor tool unsupported | your call |

## Recovery ladder (lightest first)

1. **Power cycle** — clears the parked state.
2. **Write the original bytes back** the same way (keep a full EEPROM dump; the original word is `A7 E5`).
3. **If the device comes up with the ROM identity `0572:1410`** (EEPROM treated as invalid): restore the saved full EEPROM dump over the HID memory interface. This relies on an unverified assumption — but there is supporting evidence: the **ROM's built-in default HID descriptor already contains the memory-access reports (0x04–0x07)** (at ROM `0xEF20`), and `fwupd` has a dedicated "EEPROM is missing or blank" error path, which suggests the interface remains reachable with an empty EEPROM.
4. **Hardware:** an external programmer on the EEPROM (it is an external I²C EEPROM of 32 KiB per the size code; its exact location and write-protect wiring on the speaker are unknown — the teardown reports that every screw is covered by black hot-glue seals), or the vendor tool's I²C/UART bootloader paths (`I2C bootloader`, `UART bootloader`, `ROM bootloader` strings in the Windows updater; the ROM contains a UART download routine).
5. **Vendor support / replacement.**

Steps 1–2 would resolve the realistic failure modes of a 2-byte change. Whether 3 works can only be learned from an actual failure.

## A sensible staging (if someone chooses to try)

1. Take **your own** full EEPROM dump (`tools/cx_hid_read.py dump-eeprom`) and keep two copies; verify it equals your updater image or understand every difference.
2. **No-op write**: write back the identical bytes. This exercises the write path, shows whether the EEPROM is write-protected and whether the delay is sufficient, without changing any content.
3. The real 2-byte change; re-dump and diff (exactly 2 bytes); power-cycle; confirm the device returns as `046d:0a78` and that `tools/cx_boot_watch.py` reports the new power-on gain.
4. Revert test.

`tools/cx_hid_read.py` deliberately cannot do steps 2–4: its only send routine rejects any packet with the write bit set.

## Benefit is modest

The startup volume only shows when no USB host overrides it (a host rewrites the gain ~0.13 s after enumeration), i.e. for Bluetooth/aux-only use, and the MCU-side placeholder (index 25) is overwritten after ~2 s anyway ([startup-volume.md](startup-volume.md)).
