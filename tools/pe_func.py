"""Finds the function containing the given RVA (via .pdata) and disassembles all of it.
Usage: python3 -I pe_func.py <dll> <rva_hex> [start_rva_hex end_rva_hex]
"""
import sys
import pefile
from capstone import CS_ARCH_X86, CS_MODE_64, Cs
pe = pefile.PE(sys.argv[1]); base = pe.OPTIONAL_HEADER.ImageBase
rva = int(sys.argv[2], 16)
fn = next(f for f in pe.DIRECTORY_ENTRY_EXCEPTION if f.struct.BeginAddress <= rva < f.struct.EndAddress)
b, e = fn.struct.BeginAddress, fn.struct.EndAddress
print(f"function {b:#x}-{e:#x} ({e-b} bytes)")
lo = int(sys.argv[3], 16) if len(sys.argv) > 3 else b
hi = int(sys.argv[4], 16) if len(sys.argv) > 4 else e
text = next(s for s in pe.sections if s.Name.startswith(b".text")); data = text.get_data(); tb = text.VirtualAddress
md = Cs(CS_ARCH_X86, CS_MODE_64)
for i in md.disasm(data[b - tb : e - tb], b):
    if lo <= i.address < hi:
        print(f"{i.address:#07x}: {i.mnemonic:<7} {i.op_str}")
