import sys
mem = {}
recs = {}
bad = 0
for line in open(sys.argv[1], "r", errors="replace"):
    line = line.strip()
    if not line.startswith("S"):
        continue
    t = line[1]
    b = bytes.fromhex(line[2:])
    cnt, body, chk = b[0], b[1:-1], b[-1]
    if (sum(b[:-1]) + chk) & 0xFF != 0xFF:
        bad += 1
    recs[t] = recs.get(t, 0) + 1
    alen = {"0": 2, "1": 2, "2": 3, "3": 4, "7": 4, "8": 3, "9": 2}[t]
    if t in "123":
        addr = int.from_bytes(body[:alen], "big")
        for i, v in enumerate(body[alen:]):
            mem[addr + i] = v
    elif t == "0":
        print("S0 header:", body[alen:])
print("record types:", recs, "| bad checksums:", bad)
addrs = sorted(mem)
runs, start, prev = [], addrs[0], addrs[0]
for a in addrs[1:]:
    if a != prev + 1:
        runs.append((start, prev)); start = a
    prev = a
runs.append((start, prev))
print("total bytes:", len(mem))
print("memory ranges:", [(hex(a), hex(b), b - a + 1) for a, b in runs][:12])
lo, hi = addrs[0], addrs[-1]
img = bytearray(b"\xff" * (hi - lo + 1))
for a, v in mem.items():
    img[a - lo] = v
open(sys.argv[2], "wb").write(img)
print("binary image:", sys.argv[2], len(img), "bytes, base", hex(lo))
