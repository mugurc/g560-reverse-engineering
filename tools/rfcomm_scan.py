"""RFCOMM channel scan: for each channel it only attempts a connection and, if the channel opens, closes it WITHOUT SENDING ANYTHING.

Usage: python3 -u -I rfcomm_scan.py <AA-BB-CC-DD-EE-FF> [first=1] [last=30]

Uses the synchronous openRFCOMMChannelSync (Async + delegate callbacks are not reachable from pyobjc).
Writes no data (there is no write call). WARNING: this is an attempt to open a data channel and, unlike SDP,
is not read-only; run it only with the user's approval.

Note on interpreting the results: in this call macOS does not distinguish "refused" from "API not permitted";
both return 0xE00002BC (the same code for PSM 1 as well). Without a positive control (a known device that
offers RFCOMM), "error" does not definitively mean "no service".
"""
import sys
import time

import IOBluetooth
from Foundation import NSObject


class Del(NSObject):
    pass


def main():
    addr = sys.argv[1]
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    last = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    dev = IOBluetooth.IOBluetoothDevice.deviceWithAddressString_(addr)
    print("name:", dev.name(), "| connected:", dev.isConnected(), flush=True)
    opened = []
    for ch_id in range(first, last + 1):
        d = Del.alloc().init()
        t0 = time.time()
        r = dev.openRFCOMMChannelSync_withChannelID_delegate_(None, ch_id, d)
        ret = r[0] if isinstance(r, tuple) else r
        ch = r[1] if isinstance(r, tuple) else None
        is_open = bool(ch.isOpen()) if ch is not None else False
        print(f"channel {ch_id:2d}: ret=0x{ret & 0xFFFFFFFF:08x} open={is_open} time={time.time()-t0:.1f}s", flush=True)
        if is_open:
            opened.append(ch_id)
            ch.closeChannel()
    print("\nopened channels:", opened or "none")
    print("speaker still connected:", dev.isConnected())


if __name__ == "__main__":
    main()
