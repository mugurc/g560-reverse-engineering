"""Muse_DfuImg (U-Boot-like 64-byte header) verifier / unpacker.

Usage: python3 -I uimg.py <fw_10001.bin> [out.raw]

The crc fields in the header are 32 bits wide, but only the low 16 bits are
populated: CRC-16/XMODEM (poly 0x1021, init 0). The header CRC is computed with
the header's crc field zeroed.
"""
import collections
import datetime
import math
import struct
import sys


def crc16_xmodem(data, crc=0):
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


d = open(sys.argv[1], "rb").read()
magic, hcrc, ts, size, load, entry, dcrc, os_, arch, typ, comp = struct.unpack(">IIIIIIIBBBB", d[:32])
name = d[32:64].rstrip(b"\0").decode(errors="replace")
print(f"magic=0x{magic:08x} size={size} load=0x{load:08x} entry=0x{entry:08x}")
print(f"date={datetime.datetime.fromtimestamp(ts, datetime.UTC):%Y-%m-%d} os={os_} arch={arch} type={typ} compression={comp} name={name!r}")
hdr = bytearray(d[:64])
hdr[4:8] = b"\0\0\0\0"
body = d[64 : 64 + size]
print("header CRC16:", "valid" if crc16_xmodem(bytes(hdr)) == hcrc else "INVALID", f"(0x{hcrc:08x})")
print("data CRC16  :", "valid" if crc16_xmodem(body) == dcrc else "INVALID", f"(0x{dcrc:08x})")
print("file size == 64 + size:", len(d) == 64 + size)
c = collections.Counter(body)
n = len(body)
print("data entropy:", round(-sum(v / n * math.log2(v / n) for v in c.values()), 3))
if len(sys.argv) > 2:
    open(sys.argv[2], "wb").write(body)
    print("raw body written:", sys.argv[2], len(body), "bytes (base", hex(load) + ")")
