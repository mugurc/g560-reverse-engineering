# Reproducing the analysis

This repository contains **no vendor binaries**. Download them yourself from Logitech and verify the hashes below. Download links may disappear — Logitech has stopped maintaining these tools.

## 1. Get the vendor files

| Package | URL | SHA-256 |
|---|---|---|
| G560 firmware updater 122.3.23 (Windows) | `https://download01.logi.com/web/ftp/pub/techsupport/gaming/G560Update_122.3.23.exe` | `ce22b30517f8bc76ffc60d7b6ff5e5f1e1b17a287dba6770dc05dbf58cc3235f` |
| G560 firmware updater 122.2.22 (older) | previously on Logitech's support site | `a426fe202b0a389f51f0596d90d3d3f5c727b4e08003a5ce1c4b0a23853f3df2` |
| G560 Gaming Speaker Updater 1.0.13 (Bluetooth, zip) | `https://download01.logi.com/web/ftp/pub/techsupport/gaming/Logitech_G_G560_Gaming_Speaker_Updater_1.0.13.zip` | `ead6716a66f26778d292b3069c4d7a8c7ce5aa74b193be02fd4c34bfff74bb25` |

**Never run the downloaded installers.** Put each download into its own empty directory and analyse it statically. Run Python on untrusted data with `-I` and keep your scripts in a different directory from the data.

## 2. Extract the images

```sh
pip install -r requirements.txt
python3 -I tools/pe_extract.py G560Update_122.3.23.exe out323/    # writes out323/fw_10000.bin and fw_10001.bin
```

Expected SHA-256 of the extracted resources:

| Version | `fw_10000.bin` (Conexant S-record) | `fw_10001.bin` (STM32 `Muse_DfuImg`) |
|---|---|---|
| 122.3.23 | `5380b42274283bb936961d7350c9bd8e0f3b389025554cb675a935ec04b23a6c` | `0a5a557a95a2a2dc190333fe006dd34616c8c3e78d989690080b1b3be55123f6` |
| 122.2.22 | `3b0d073551d34cc8ba250f02b19e562352208a0f72b239b9d3bbe335804e15a3` | `af12f241151eb05d57df449783e8d246c805892cb6c977cf9ff5afcff4fdcb6e` |

Bluetooth package: `MUSE/firmware.bin` (719,638 B, encrypted) has SHA-256 `3330037f27820b45b4e63f6f754abae2acd838b47577167ab1df735fe4301e52`.

## 3. Conexant image

```sh
python3 -I tools/s37_decode.py out323/fw_10000.bin cx323.raw      # S-record → flat binary (base 0x2); verifies line checksums
python3 -I tools/cx_dis.py hooks cx323.raw                         # the patch's hook table
python3 -I tools/cx_dis.py dis cx323.raw 2041 2060                 # recursive-descent disassembly of a CPU address range
python3 -I tools/cx_dis.py regs cx323.raw                          # all absolute data addresses used by the patch
```

`cpu = image offset + 0x927` for code. The extended instructions (`D2/C2/F2 …`) are mis-decoded by the underlying disassembler; read `cx_dis.py`'s header.

## 4. STM32 image

```sh
python3 -I tools/uimg.py out323/fw_10001.bin mcu323.raw           # validates header/data CRC-16, writes the raw body (base 0x08004000)
python3 -I tools/mcu_dis.py dis mcu323.raw 080075a4 080075b8      # default volume init
python3 -I tools/mcu_dis.py periph mcu323.raw                     # peripheral constants really loaded by code
python3 -I tools/mcu_dis.py callers mcu323.raw 080081ac           # who calls the HID++ dispatcher
```

## 5. Bluetooth package

```sh
python3 -I tools/pe_func.py btlib.1562.64.dll 2338                # disassemble the function containing an RVA
python3 -I tools/pe_strxref.py btlib.1562.64.dll 6030             # code that references the string at a file offset
```

## 6. On a real speaker (optional, macOS-tested)

* `python3 -I tools/hid_report_descriptor.py` — host side only (`ioreg`); shows the Conexant memory-access reports.
* `python3 -I tools/cx_hid_read.py --dry-run ram 1000 9` — prints the packet that *would* be sent.
* `python3 -I tools/cx_hid_read.py eeprom 0 64` / `dump-eeprom out.bin 0x8000` / `ram 15a0 176` — **read requests** to the device. They are read-only by construction, but they do send HID output reports; use your own judgement. Do not read RAM areas you don't understand (some addresses may be hardware registers).
* `python3 -u -I tools/cx_boot_watch.py boot.log 300` — start it, pull the speaker's **power** cable (leave USB connected), plug it back in, and wait ~45 s; the log shows the power-on gain.
* Bluetooth tools (`sdp_dump.py`, `rfcomm_scan.py`) need macOS + pyobjc. `rfcomm_scan.py` opens data channels — don't run it on a device you can't afford to disturb.
* `g560.py`, `watch_hidpp.py`, `probe_hidpp.py` import each other: run them from inside `tools/` (`cd tools && python3 probe_hidpp.py`). **`g560.py` writes LED settings.**
