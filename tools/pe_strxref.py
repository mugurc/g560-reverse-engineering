"""Finds where a string is used, given its file offset, by locating rip-relative (lea) references to it.
Usage: python3 -I pe_strxref.py <dll> <file_offset_hex>...
"""
import struct, sys
import pefile
from capstone import CS_ARCH_X86, CS_MODE_64, Cs
pe = pefile.PE(sys.argv[1])
text = next(s for s in pe.sections if s.Name.startswith(b".text")); data = text.get_data(); tb = text.VirtualAddress
def off2rva(o):
    for s in pe.sections:
        if s.PointerToRawData <= o < s.PointerToRawData + s.SizeOfRawData:
            return s.VirtualAddress + o - s.PointerToRawData
fns = [(f.struct.BeginAddress, f.struct.EndAddress) for f in pe.DIRECTORY_ENTRY_EXCEPTION]
def owner(r):
    for b, e in fns:
        if b <= r < e: return b
for a in sys.argv[2:]:
    o = int(a, 16); rv = off2rva(o)
    hits = []
    for i in range(len(data) - 7):
        if data[i] in (0x48, 0x4C) and data[i+1] == 0x8D and (data[i+2] & 0xC7) == 0x05:
            rel = struct.unpack_from("<i", data, i + 3)[0]
            if tb + i + 7 + rel == rv: hits.append(tb + i)
    print(f"string @file {o:#x} rva {rv:#x}: uses {[hex(h) for h in hits]} -> functions {[hex(owner(h)) for h in hits]}")
