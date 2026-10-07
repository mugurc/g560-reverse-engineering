"""Print the HID report descriptor of a USB device and the report IDs/sizes it declares (macOS).

The descriptor is read from the I/O Registry (`ioreg`), i.e. from data the OS already cached.
Nothing is sent to the device.

Usage:  python3 -I hid_report_descriptor.py [vid_hex=046d] [pid_hex=0a78]

For the Logitech G560 (046d:0a78) this shows, among others:
  report 0x04 OUT 36 bytes and report 0x05 IN 32 bytes  -> the Conexant "memory access" reports,
  report 0x11 IN/OUT 19 bytes                           -> HID++ long report.
"""
import plistlib
import subprocess
import sys

USAGE_PAGES = {0x01: "GenericDesktop", 0x0B: "Telephony", 0x0C: "Consumer", 0xFF43: "Logitech-HID++"}


def find_descriptor(vid, pid):
    out = subprocess.run(["/usr/sbin/ioreg", "-r", "-c", "IOHIDDevice", "-a"], capture_output=True, check=True).stdout
    for dev in plistlib.loads(out):
        if dev.get("VendorID") == vid and dev.get("ProductID") == pid and "ReportDescriptor" in dev:
            return dev
    sys.exit(f"no HID device {vid:04x}:{pid:04x} with a ReportDescriptor found")


def parse(rd):
    """Minimal HID descriptor walker: prints Input/Output/Feature items and sums bits per report ID."""
    i, glob, loc, sizes = 0, {}, {}, {}
    while i < len(rd):
        b = rd[i]
        n = b & 3
        n = 4 if n == 3 else n
        kind, tag = (b >> 2) & 3, b >> 4
        val = int.from_bytes(rd[i + 1 : i + 1 + n], "little")
        i += 1 + n
        if kind == 1:  # global item
            key = {0: "page", 7: "size", 8: "rid", 9: "count"}.get(tag)
            if key:
                glob[key] = val
        elif kind == 2 and tag == 0:  # local item: usage
            loc["usage"] = val
        elif kind == 0:  # main item
            if tag in (8, 9, 11):
                name = {8: "IN", 9: "OUT", 11: "FEATURE"}[tag]
                bits = glob.get("size", 0) * glob.get("count", 0)
                key = (glob.get("rid", 0), name)
                sizes[key] = sizes.get(key, 0) + bits
                page = USAGE_PAGES.get(glob.get("page"), hex(glob.get("page", 0)))
                print(f"  [{name:7}] rid={glob.get('rid', 0):#04x} page={page} usage={loc.get('usage')} "
                      f"size={glob.get('size')}x{glob.get('count')} flags={val:#x}")
            loc = {}
    return sizes


def main():
    vid = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x046D
    pid = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x0A78
    dev = find_descriptor(vid, pid)
    rd = bytes(dev["ReportDescriptor"])
    print(f"{dev.get('Product')!r}: descriptor {len(rd)} bytes, MaxInput={dev.get('MaxInputReportSize')} "
          f"MaxOutput={dev.get('MaxOutputReportSize')} MaxFeature={dev.get('MaxFeatureReportSize')}")
    print(rd.hex(" "))
    sizes = parse(rd)
    print("\nreport sizes (data bytes, excluding the report-ID byte):")
    for (rid, name), bits in sorted(sizes.items()):
        print(f"  report {rid:#04x} {name:7}: {bits // 8} bytes")


if __name__ == "__main__":
    main()
