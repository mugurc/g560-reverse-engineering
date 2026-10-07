"""Disassembler / cross-reference tool (capstone) for the Muse MCU image (Cortex-M3, Thumb-2).

Input: the raw body extracted with uimg.py (`uimg.py fw_10001.bin out.raw`).
Usage:  python3 -I mcu_dis.py <subcommand> <body.raw> [arg...]

Subcommands:
  periph <raw>            peripheral constants actually loaded by the code (ldr pc-rel + movw/movt)
  dis <raw> <start> <end> disassemble an address range (hex addresses, 8 digits)
  funcs <raw>             number of function starts derived from BL targets
  xref <raw> <value>      instructions that load a 32-bit constant, and the function they belong to
  imm <raw> <value>...    instructions with a '#value' immediate operand (movw/cmp/...)
  callers <raw> <addr>    bl/b calls whose target is addr + 4-byte data pointers
Base address 0x08004000. Read-only: sends nothing to the device.
"""
import collections
import struct
import sys

from capstone import CS_ARCH_ARM, CS_MODE_MCLASS, CS_MODE_THUMB, Cs
from capstone.arm import ARM_OP_IMM

BASE = 0x08004000
cmd = sys.argv[1]
raw = open(sys.argv[2], "rb").read()
END = BASE + len(raw)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
md.detail = True


def u32(addr):
    return struct.unpack_from("<I", raw, addr - BASE)[0]


def sweep():
    """Linear sweep; skip 2 bytes on an invalid encoding. (address -> insn)"""
    out = {}
    pc = BASE + 0xF0  # just past the vector table (60 entries)
    while pc < END:
        chunk = raw[pc - BASE : pc - BASE + 4]
        got = False
        for insn in md.disasm(chunk, pc, 1):
            out[pc] = insn
            pc += insn.size
            got = True
        if not got:
            pc += 2
    return out


def pc_literal(insn):
    """ldr Rt, [pc, #imm] -> address of the loaded constant (parsed from op_str)"""
    ms = insn.mnemonic
    if not ms.startswith("ldr") or "[pc" not in insn.op_str:
        return None
    off = 0
    if "#" in insn.op_str:
        t = insn.op_str.split("#")[1].rstrip("]!").strip()
        off = int(t, 0)
    return ((insn.address + 4) & ~3) + off


insns = sweep()
addrs = sorted(insns)

if cmd == "callers":
    # instructions whose bl/b.w target is the given address + a search for a 4-byte LE pointer (with the Thumb bit set)
    want = int(sys.argv[3], 16)
    for a in addrs:
        i = insns[a]
        if i.mnemonic in ("bl", "b.w", "b") and i.operands and i.operands[0].type == ARM_OP_IMM and i.operands[0].imm == want:
            print(f"  call   {a:08x}: {i.mnemonic} {want:#x}")
    p = struct.pack("<I", want | 1)
    j = 0
    while (j := raw.find(p, j)) >= 0:
        print(f"  data-pointer @ {BASE + j:08x}")
        j += 1
    sys.exit()

if cmd == "imm":
    # looks for the immediate in op_str, written as '#0x..' or '#dec' (movw/cmp/mov...)
    for w in sys.argv[3:]:
        want = int(w, 0)
        pats = {f"#{want:#x}", f"#{want}"}
        print(f"-- {want:#06x}")
        for a in addrs:
            i = insns[a]
            if any(p == o.strip() or o.strip().startswith(p + "]") for o in i.op_str.split(",") for p in pats):
                print(f"   {a:08x}: {i.mnemonic} {i.op_str}")
    sys.exit()

if cmd == "dis":
    lo, hi = int(sys.argv[3], 16), int(sys.argv[4], 16)
    for a in addrs:
        if lo <= a < hi:
            i = insns[a]
            extra = ""
            t = pc_literal(i)
            if t is not None and BASE <= t < END - 3:
                extra = f"   ; ={u32(t):#010x}"
            print(f"{a:08x}: {i.mnemonic:<8} {i.op_str}{extra}")
    sys.exit()

# function starts: BL targets + vector table entries + push {..., lr}
funcs = set()
for i, v in enumerate(struct.unpack_from("<60I", raw, 0)[1:], 1):
    if BASE <= (v & ~1) < END:
        funcs.add(v & ~1)
for a, i in insns.items():
    if i.mnemonic == "bl" and i.operands and i.operands[0].type == ARM_OP_IMM:
        t = i.operands[0].imm
        if BASE <= t < END:
            funcs.add(t)
fl = sorted(funcs)


def owner(a):
    lo = 0
    for f in fl:
        if f <= a:
            lo = f
        else:
            break
    return lo


if cmd == "funcs":
    print(len(fl), "function starts (BL targets + vectors)")
    sys.exit()

# constants: pc-literal and movw/movt
consts = collections.defaultdict(list)  # value -> [addresses]
movw = {}
for a in addrs:
    i = insns[a]
    t = pc_literal(i)
    if t is not None and BASE <= t <= END - 4:
        consts[u32(t)].append(a)
    if i.mnemonic in ("movw", "mov.w") and i.op_str.count(",") == 1 and "#" in i.op_str:
        rd, imm = i.op_str.split(",")
        try:
            movw[(rd.strip())] = (a, int(imm.strip().lstrip("#"), 0))
        except ValueError:
            pass
    if i.mnemonic == "movt" and "#" in i.op_str:
        rd, imm = i.op_str.split(",")
        rd = rd.strip()
        if rd in movw and a - movw[rd][0] <= 8:
            val = (int(imm.strip().lstrip("#"), 0) << 16) | movw[rd][1]
            consts[val].append(a)

if cmd == "xref":
    want = int(sys.argv[3], 0)
    for a in consts.get(want, []):
        print(f"{a:08x} (func {owner(a):08x}): {insns[a].mnemonic} {insns[a].op_str}")
    sys.exit()

if cmd == "periph":
    PER = [(0x40000000, 0x60000000), (0xE0000000, 0xE0100000)]
    for v in sorted(consts):
        if any(lo <= v < hi for lo, hi in PER):
            fs = sorted({owner(a) for a in consts[v]})
            print(f"{v:#010x}  x{len(consts[v])}  func: {' '.join(f'{f:08x}' for f in fs[:6])}")
