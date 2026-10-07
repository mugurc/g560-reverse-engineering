"""G560 boot-sound watcher (READ ONLY): captures the first values when the device disappears and reappears.

Memory windows read (all within the address ranges the user approved): $12CC..$12D3 (gain + copies of the defaults),
$15F0 (sound index), $1636..$1637 (frame length + retransmit counter). No write/park/reset;
the only path to the device is cx_hid_read._send() (which structurally rejects the write bit).

Usage:  python3 -u -I cx_boot_watch.py <log_file> [max_duration_s=900]
Behavior: while the device is present, polls slowly (4 Hz, only changes are logged); when the device
          disappears and reappears, polls as fast as possible for 40 s from the moment it reappears
          (every sample is timestamped).
"""
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("cxr", os.path.join(HERE, "cx_hid_read.py"))
cxr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cxr)
import hid

logf = open(sys.argv[1], "a", buffering=1)
T0 = time.time()


def log(msg):
    line = f"[{time.time()-T0:8.3f}s] {msg}"
    print(line, flush=True)
    logf.write(line + "\n")


def present():
    return any(d["usage_page"] == 0xFF43 for d in hid.enumerate(cxr.VID, cxr.PID))


def sample(dev):
    g = cxr.read_mem
    gain = g(dev, False, 0x12CC, 8)
    idx = g(dev, False, 0x15F0, 1)
    fl = g(dev, False, 0x1636, 2)
    w = lambda b, i: f"{b[i+1]:02X}{b[i]:02X}"
    return (f"live={w(gain,0)}/{w(gain,2)} default-copy={w(gain,4)}/{w(gain,6)} "
            f"idx=0x{idx[0]:02X}({idx[0]}) frame_len=0x{fl[0]:02X} counter={fl[1]}")


def main():
    max_s = float(sys.argv[2]) if len(sys.argv) > 2 else 900
    was_present = present()
    log(f"start: device {'PRESENT' if was_present else 'ABSENT'}")
    last, fast_until, dev, errs = None, 0.0, None, 0
    while time.time() - T0 < max_s:
        now = time.time()
        p = present()
        if p != was_present:
            log("device " + ("APPEARED" if p else "DISAPPEARED"))
            if p:
                fast_until = now + 40
            else:
                if dev:
                    try:
                        dev.close()
                    except Exception:
                        pass
                    dev = None
                last = None
            was_present = p
        if p:
            try:
                if dev is None:
                    dev = cxr.open_dev()
                s = sample(dev)
                if errs:
                    log(f"(first successful read after {errs} transient read errors)")
                    errs = 0
                if s != last:
                    log(("FAST " if now < fast_until else "") + s)
                    last = s
            except Exception as e:  # device just appeared and is not ready yet / transient error
                dev = None
                errs += 1
                if errs == 1:
                    log(f"read error (repeats are counted): {e}")
            time.sleep(0.0 if now < fast_until else 0.25)
        else:
            time.sleep(0.05)
    log("time limit reached, exiting")


if __name__ == "__main__":
    main()
