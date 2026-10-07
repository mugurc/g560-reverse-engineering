"""Conexant (CX2070x family) HID memory access — READ ONLY.

Protocol (from fwupd synaptics-cxaudio; the G560 HID report descriptor has report ID 4 OUT 36 B, ID 5 IN 32 B):
  OUT report ID 0x04: [0]=0x04 [1]=flags [2]=length(<=32) [3..4]=address(BE) [5..36]=data (zero for reads)
      flags: bit4 = address >= 64 KiB, bit5 = EEPROM, bit6 = WRITE  <-- this script NEVER sets bit6
  IN  report ID 0x05: [1..32] = data read back (GET_REPORT)

Safety: the ONLY code path to the device is _send(); before every packet, ID==0x04, length==37 and
flags&0x40==0 are verified (ValueError otherwise). Write/park/reset addresses are not used; there are no
other subcommands.

Usage:
  python3 -I cx_hid_read.py [--dry-run] ram <addr_hex> <length>
  python3 -I cx_hid_read.py [--dry-run] eeprom <addr_hex> <length>
  python3 -I cx_hid_read.py dump-eeprom <output.bin> [bytes=0x8000]
"""
import sys
import time

import hid

VID, PID = 0x046D, 0x0A78
OUT_ID, IN_ID = 0x04, 0x05
OUT_LEN, IN_LEN = 37, 33  # including the report ID (36 / 32 data bytes in the report descriptor)
FLAG_ADDR64K, FLAG_EEPROM, FLAG_WRITE = 1 << 4, 1 << 5, 1 << 6
DRY = False


def build_read(eeprom, addr, length):
    if not 1 <= length <= 32:
        raise ValueError("length must be 1..32")
    if not 0 <= addr <= 0xFFFF:
        raise ValueError("address must be 0..0xFFFF (>=64K is not supported)")
    flags = FLAG_EEPROM if eeprom else 0
    pkt = bytearray(OUT_LEN)
    pkt[0], pkt[1], pkt[2] = OUT_ID, flags, length
    pkt[3], pkt[4] = addr >> 8, addr & 0xFF
    return bytes(pkt)


def _send(dev, pkt):
    """The ONLY path to the device. Rejects write requests."""
    if len(pkt) != OUT_LEN or pkt[0] != OUT_ID:
        raise ValueError("unexpected packet format")
    if pkt[1] & FLAG_WRITE:
        raise ValueError("WRITE bit is set: rejected")
    if any(pkt[5:]):
        raise ValueError("data field must be zero in a read request: rejected")
    if DRY:
        print("  [dry-run] would send:", pkt[:8].hex(" "), "...", f"({len(pkt)} bytes)")
        return
    n = dev.write(pkt)
    if n < 0:
        raise OSError("write failed: " + str(dev.error()))


def open_dev():
    path = next(d["path"] for d in hid.enumerate(VID, PID) if d["usage_page"] == 0xFF43)
    dev = hid.device()
    dev.open_path(path)
    dev.set_nonblocking(False)
    return dev


def read_mem(dev, eeprom, addr, length, retries=5):
    pkt = build_read(eeprom, addr, length)
    if DRY:
        _send(dev, pkt)
        return b"\0" * length
    last = None
    for _ in range(retries):
        _send(dev, pkt)
        time.sleep(0.005)
        r = dev.get_input_report(IN_ID, IN_LEN)
        if r and len(r) >= 1 + length and r[0] == IN_ID:
            return bytes(r[1 : 1 + length])
        last = r
        time.sleep(0.02)
    raise OSError(f"invalid read response: {last!r}")


def read_range(dev, eeprom, addr, length):
    out = bytearray()
    while length > 0:
        n = min(32, length)
        out += read_mem(dev, eeprom, addr, n)
        addr += n
        length -= n
    return bytes(out)


def hexdump(base, data):
    for i in range(0, len(data), 16):
        row = data[i : i + 16]
        print(f"{base+i:05x}: {row.hex(' '):<47}  {''.join(chr(c) if 32 <= c < 127 else '.' for c in row)}")


def main():
    global DRY
    args = sys.argv[1:]
    if args and args[0] == "--dry-run":
        DRY = True
        args = args[1:]
    if not args:
        sys.exit(__doc__)
    cmd = args[0]
    dev = None if DRY else open_dev()
    try:
        if cmd in ("ram", "eeprom"):
            addr, length = int(args[1], 16), int(args[2], 0)
            data = read_range(dev, cmd == "eeprom", addr, length)
            hexdump(addr, data)
        elif cmd == "dump-eeprom":
            size = int(args[2], 0) if len(args) > 2 else 0x8000
            data = read_range(dev, True, 0, size)
            open(args[1], "wb").write(data)
            print(f"{len(data)} bytes written: {args[1]}")
        else:
            sys.exit(__doc__)
    finally:
        if dev:
            dev.close()


if __name__ == "__main__":
    main()
