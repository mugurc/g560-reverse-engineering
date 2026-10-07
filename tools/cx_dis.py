"""Conexant (CX20562, 65C02) patch image disassembler / cross-reference tool.

Input: binary image extracted with s37_decode.py (`s37_decode.py fw_10000.bin out.raw`, base 0x2).
Usage:  python3 -I cx_dis.py <subcommand> <out.raw> [arg...]

Address mapping (derived from the hook table targets): code CPU address = image offset + 0x927.
Variable/register addresses ($15F9, $1333...) appear to live in a data space SEPARATE from the code space.
This CPU is an extended derivative of the 65C02: it has custom 4-byte instructions such as `D2 nn aa bb`,
which Capstone decodes incorrectly (as CMP (zp) + AND (zp,x)). They have to be checked by hand.

Subcommands:
  hooks                  3-byte hook table at image offset 0xb5c (JMP target / RTS)
  dis <cpu_lo> <cpu_hi>  print the instructions found by recursive descent, with CPU addresses
  lin <cpu_lo> <cpu_hi>  linear (rough) disassembly, may be out of sync with the code
  refs <target>          places that JSR/JMP to an address (CPU addresses)
  abs <addr>             instructions that use $addr as an absolute/indexed operand
  regs                   all absolute data addresses used in the code (read/write counts)
Read-only; sends nothing to the device.
"""
import collections
import struct
import sys

from capstone import CS_ARCH_MOS65XX, CS_MODE_MOS65XX_65C02, Cs

BASE = 0x2
DELTA = 0x927
LO, HI = 0xB50, 0x4EBA  # patch region within the image
HOOK0, HOOKN = 0xB5C, 80

md = Cs(CS_ARCH_MOS65XX, CS_MODE_MOS65XX_65C02)
raw = b""


def load(path):
    global raw
    raw = open(path, "rb").read()


def b(a):
    return raw[a - BASE]


def cpu2img(c):
    return c - DELTA


def in_code(c):
    return LO <= c - DELTA < HI


def ins_at(img):
    for i in md.disasm(raw[img - BASE : img - BASE + 3], img + DELTA, 1):
        return i
    return None


def targets(img):
    """(does_flow_continue, [target CPU addresses], kind)"""
    op = b(img)
    if op == 0x20:
        return True, [b(img + 1) | b(img + 2) << 8], "jsr"
    if op == 0x4C:
        return False, [b(img + 1) | b(img + 2) << 8], "jmp"
    if op in (0x60, 0x40, 0x6C, 0x7C, 0xDB):
        return False, [], "end"
    if op == 0x80:  # BRA
        off = struct.unpack("b", bytes([b(img + 1)]))[0]
        return False, [img + 2 + off + DELTA], "bra"
    if op & 0x1F == 0x10:  # Bcc
        off = struct.unpack("b", bytes([b(img + 1)]))[0]
        return True, [img + 2 + off + DELTA], "bcc"
    if op & 0x0F == 0x0F:  # BBRn / BBSn
        off = struct.unpack("b", bytes([b(img + 2)]))[0]
        return True, [img + 3 + off + DELTA], "bb"
    return True, [], ""


def hooks():
    out = []
    a = HOOK0
    for k in range(HOOKN):
        if b(a) == 0x4C:
            out.append((k, a, b(a + 1) | b(a + 2) << 8))
        a += 3
    return out


def pattern_seeds():
    """JSR/JMP targets found by a byte scan; those immediately preceded by an RTS, RTI or JMP are treated as function starts."""
    out = set()
    for a in range(LO, HI - 2):
        if b(a) in (0x20, 0x4C):
            t = b(a + 1) | b(a + 2) << 8
            o = cpu2img(t)
            if LO + 3 <= o < HI and (b(o - 1) == 0x60 or b(o - 3) == 0x4C or b(o - 1) == 0x40):
                out.add(t)
    return out


def descend(seeds):
    code, work, calls = {}, list(seeds), []
    while work:
        c = work.pop()
        img = cpu2img(c)
        while LO <= img < HI and c not in code:
            i = ins_at(img)
            if i is None:
                break
            code[c] = i
            cont, tg, kind = targets(img)
            for t in tg:
                calls.append((c, t, kind))
                if in_code(t):
                    work.append(t)
            if not cont:
                break
            img += i.size
            c += i.size
    return code, calls


def analyze():
    seeds = {t for _, _, t in hooks() if in_code(t)} | pattern_seeds()
    return descend(seeds)


def fmt(c, i):
    img = cpu2img(c)
    raw_b = raw[img - BASE : img - BASE + i.size].hex(" ")
    note = ""
    if b(img) in (0x20, 0x4C):
        t = b(img + 1) | b(img + 2) << 8
        note = "" if in_code(t) else "   ; ROM/external"
    return f"{c:04x}: {raw_b:<9} {i.mnemonic:<4} {i.op_str}{note}"


def main():
    cmd = sys.argv[1]
    load(sys.argv[2])
    if cmd == "hooks":
        for k, a, t in hooks():
            print(f"[{k:2d}] image {a:#06x} -> JMP {t:#06x}" + ("" if in_code(t) else "  (ROM/external)"))
        return
    code, calls = analyze()
    if cmd == "dis":
        lo, hi = int(sys.argv[3], 16), int(sys.argv[4], 16)
        for c in sorted(code):
            if lo <= c < hi:
                print(fmt(c, code[c]))
    elif cmd == "lin":
        c, hi = int(sys.argv[3], 16), int(sys.argv[4], 16)
        while c < hi:
            i = ins_at(cpu2img(c))
            if i is None:
                print(f"{c:04x}: {b(cpu2img(c)):02x}  .byte")
                c += 1
                continue
            print(fmt(c, i))
            c += i.size
    elif cmd == "refs":
        want = int(sys.argv[3], 16)
        for c, t, kind in calls:
            if t == want:
                print(f"  {kind} @ {c:04x}")
    elif cmd == "abs":
        want = int(sys.argv[3], 16)
        for c in sorted(code):
            img = cpu2img(c)
            i = code[c]
            if i.size == 3 and (b(img + 1) | b(img + 2) << 8) == want and b(img) not in (0x20, 0x4C):
                print(fmt(c, i))
    elif cmd == "regs":
        cnt = collections.defaultdict(collections.Counter)
        for c, i in code.items():
            img = cpu2img(c)
            op = b(img)
            if i.size == 3 and op not in (0x20, 0x4C, 0x6C, 0x7C):
                a = b(img + 1) | b(img + 2) << 8
                m = i.mnemonic
                k = "W" if m.startswith("st") else "R" if m.startswith(("ld", "cmp", "bit", "and", "ora", "eor", "adc", "sbc")) else "M"
                cnt[a][k] += 1
        for a in sorted(cnt):
            print(f"{a:04x}  " + " ".join(f"{k}{n}" for k, n in sorted(cnt[a].items())))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
