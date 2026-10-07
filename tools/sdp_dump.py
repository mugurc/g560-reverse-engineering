"""Lists the speaker's SDP service records (read-only).

Usage: python3 -I sdp_dump.py <AA-BB-CC-DD-EE-FF> [query [uuid16,uuid16...]]
  Without 'query', only the cached records are shown (nothing is sent).
  With 'query', the records are read from the SDP server via IOBluetooth
  performSDPQuery (SDP GET requests; does not change the device state).
"""
import sys

import IOBluetooth
from Foundation import NSDate, NSObject, NSRunLoop


def uuid_str(u):
    return " ".join(f"{b:02x}" for b in bytes(u.getBytes_length_(None, 0) if False else u.bytes()))


def walk(v, depth=0):
    """Walk the SDP data elements (IOBluetoothSDPDataElement)."""
    pad = "  " * depth
    t = v.getTypeDescriptor()
    ts = v.getSizeDescriptor()
    val = v.getValue()
    if t == 6 or t == 7:  # sequence / alternative
        print(f"{pad}[sequence]")
        for e in v.getArrayValue() or []:
            walk(e, depth + 1)
    elif t == 3:  # UUID
        print(f"{pad}uuid {val}")
    else:
        print(f"{pad}t{t}: {val!r}")


def dump_record(i, rec):
    name = rec.getServiceName()
    print(f"\n--- record {i}: {name!r}")
    attrs = rec.attributes()
    for aid in sorted(attrs.keys()):
        el = attrs[aid]
        print(f"  attr 0x{int(aid):04x}:")
        walk(el.getDataElement() if hasattr(el, "getDataElement") else el, 2)


class D(NSObject):
    def sdpQueryComplete_status_(self, dev, status):
        self.done = True
        self.status = status


def main():
    addr = sys.argv[1]
    dev = IOBluetooth.IOBluetoothDevice.deviceWithAddressString_(addr)
    print("name:", dev.name(), "| connected:", dev.isConnected(), "| paired:", dev.isPaired())
    if len(sys.argv) > 2:
        d = D.alloc().init()
        d.done = False
        if len(sys.argv) > 3:
            pats = [IOBluetooth.IOBluetoothSDPUUID.uuid16_(int(x, 16)) for x in sys.argv[3].split(",")]
            r = dev.performSDPQuery_uuids_(d, pats)
        else:
            r = dev.performSDPQuery_(d)
        print("performSDPQuery ->", hex(r) if isinstance(r, int) else r)
        end = NSDate.dateWithTimeIntervalSinceNow_(25)
        while not d.done and NSDate.date().compare_(end) < 0:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.2))
        print("done:", d.done, "status:", getattr(d, "status", None))
    recs = dev.services()
    print("record count:", len(recs) if recs else 0)
    for i, rec in enumerate(recs or []):
        dump_record(i, rec)


if __name__ == "__main__":
    main()
