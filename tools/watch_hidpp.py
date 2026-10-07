#!/usr/bin/env python3
"""Read-only watcher for the G560: polls a fixed list of reads and prints any changes.

Only makes the getter calls in the WATCH list below (writes no settings) and
lists any HID++ reports (notifications) that arrive in between and do not
belong to our own requests as 'EVENT'.

Usage:  python3 -u watch_hidpp.py [seconds]
"""
import sys
import time

import hid

from probe_hidpp import SW_ID, find_path, request

# (feature ID, function, label) -- all reads
WATCH = [
    (0x8040, 1, "BrightnessControl.getBrightness"),
    (0x8305, 0, "0x8305.fn0 (unknown)"),
    (0x8310, 0, "EQUALIZER.fn0"),
    (0x8320, 0, "HEADSET_OUT.fn0"),
]


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    dev = hid.device()
    dev.open_path(find_path(verbose=False))
    dev.set_nonblocking(False)
    try:
        targets = []
        for fid, fn, label in WATCH:
            idx = request(dev, 0x00, 0, fid.to_bytes(2, "big"))[0]
            targets.append((idx, fn, label))
        last = {}
        t0 = time.time()
        print(f"watching ({secs:.0f} s) ...", flush=True)
        while time.time() - t0 < secs:
            for idx, fn, label in targets:
                msg = bytearray(20)
                msg[0], msg[1], msg[2], msg[3] = 0x11, 0xFF, idx, (fn << 4) | SW_ID
                dev.write(bytes(msg))
                end = time.time() + 0.3
                while time.time() < end:
                    r = dev.read(64, 100)
                    if not r:
                        continue
                    r = bytes(r)
                    t = time.time() - t0
                    if r[0] == 0x11 and r[2] == idx and r[3] == ((fn << 4) | SW_ID):
                        val = r[4:8].hex(" ")
                        if last.get(label) != val:
                            old = last.get(label, "-")
                            print(f"[{t:6.1f}s] {label}: {old} -> {val}", flush=True)
                            last[label] = val
                        break
                    print(f"[{t:6.1f}s] EVENT: {r.hex(' ')}", flush=True)
            time.sleep(0.2)
        print("done", flush=True)
    finally:
        dev.close()


if __name__ == "__main__":
    main()
