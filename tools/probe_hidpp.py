#!/usr/bin/env python3
"""Read-only HID++ 2.0 discovery tool for the G560.

Enumerates the HID++ features the device exposes (IRoot 0x0000, IFeatureSet 0x0001),
then calls a few known *getter* functions (firmware version, device name,
0x8040 brightness, 0x8070 LED info). Does not call any setter or unknown
function and writes no settings to the device.

Usage:  python3 -I probe_hidpp.py
"""
import sys
import time

import hid

VID, PID = 0x046D, 0x0A78
HIDPP_USAGE_PAGE = 0xFF43  # Logitech HID++ (usage 0x0202 = long report 0x11)
DEV_IDX = 0xFF  # device connected directly over USB
SW_ID = 0x0A
LONG = 0x11

# Known HID++ 2.0 feature names (sourced from Solaar / libratbag / ltunify)
NAMES = {
    0x0000: "IRoot",
    0x0001: "IFeatureSet",
    0x0002: "IFeatureInfo",
    0x0003: "DeviceFWVersion",
    0x0005: "DeviceNameType",
    0x0007: "DeviceFriendlyName",
    0x0020: "ConfigChange",
    0x1000: "BatteryStatus",
    0x1004: "UnifiedBattery",
    0x1814: "ChangeHost",
    0x1815: "HostsInfo",
    0x1B04: "ReprogControlsV4",
    0x1D4B: "WirelessDeviceStatus",
    0x1E00: "HiddenFeatures",
    0x8040: "BrightnessControl",
    0x8070: "ColorLEDEffects",
    0x8071: "RGBEffects",
    0x8080: "PerKeyLightingV1",
    0x8081: "PerKeyLighting",
    0x8100: "OnboardProfiles",
    0x8110: "MouseButtonSpy",
}


def find_path(verbose=True):
    cands = [d for d in hid.enumerate(VID, PID)]
    if not cands:
        sys.exit("G560 (046d:0a78) not found - check the USB cable.")
    if verbose:
        print("HID interfaces:")
        for d in cands:
            print(
                f"  iface={d['interface_number']} usage_page=0x{d['usage_page']:04x} "
                f"usage=0x{d['usage']:04x} path={d['path'].decode(errors='replace')}"
            )
    hp = [d for d in cands if d["usage_page"] == HIDPP_USAGE_PAGE]
    if not hp:
        sys.exit(f"no interface with usage_page 0x{HIDPP_USAGE_PAGE:04x} (HID++).")
    return hp[0]["path"]


def request(dev, feat_idx, func, params=b"", timeout=1.0):
    """Send a HID++ 2.0 long request and return the matching response (payload, 16 bytes)."""
    msg = bytearray(20)
    msg[0], msg[1], msg[2] = LONG, DEV_IDX, feat_idx
    msg[3] = (func << 4) | SW_ID
    msg[4 : 4 + len(params)] = params
    dev.write(bytes(msg))
    end = time.time() + timeout
    while time.time() < end:
        r = dev.read(64, 100)
        if not r:
            continue
        r = bytes(r)
        if len(r) < 4 or r[0] not in (0x10, 0x11, 0x12):
            continue
        if r[2] == 0xFF:  # HID++ 2.0 error response: [.. FF feat func|sw err]
            if r[3] == feat_idx and (r[4] >> 4) == func:
                raise RuntimeError(f"HID++ error code 0x{r[5]:02x}: {r.hex()}")
            continue
        if r[2] == feat_idx and (r[3] >> 4) == func and (r[3] & 0x0F) == SW_ID:
            return r[4:]
    raise TimeoutError(f"no response (feat_idx={feat_idx} func={func})")


def main():
    path = find_path()
    dev = hid.device()
    try:
        dev.open_path(path)
    except OSError as e:
        sys.exit(
            f"Could not open interface: {e}\n"
            "macOS: allow Terminal under System Settings > Privacy & Security > "
            "Input Monitoring, then try again."
        )
    dev.set_nonblocking(False)
    try:
        # IRoot.ping (func 1): protocol version
        pr = request(dev, 0x00, 1, b"\x00\x00\x5a")
        print(f"\nHID++ protocol version: {pr[0]}.{pr[1]} (ping echo=0x{pr[2]:02x})")

        # IRoot.getFeature(0x0001) -> index of IFeatureSet
        fs = request(dev, 0x00, 0, b"\x00\x01")
        fs_idx = fs[0]
        if fs_idx == 0:
            sys.exit("IFeatureSet not found.")
        # IFeatureSet.getCount (func 0)
        count = request(dev, fs_idx, 0)[0]
        print(f"IFeatureSet index={fs_idx}, feature count (excluding IRoot)={count}\n")
        print("idx  feature ID  ver    type  name")
        print("---  ----------  -----  ----  ----------------------------")
        print(f"{0:>3}  0x0000      -      -     IRoot")
        feats = {0x0000: 0}
        for i in range(1, count + 1):
            # IFeatureSet.getFeatureID (func 1): [idx] -> [id_hi id_lo type ver]
            r = request(dev, fs_idx, 1, bytes([i]))
            fid = (r[0] << 8) | r[1]
            ftype, fver = r[2], r[3]
            feats[fid] = i
            name = NAMES.get(fid, "?  (unknown)")
            print(f"{i:>3}  0x{fid:04x}      {fver:>3}    0x{ftype:02x}  {name}")
        deep(dev, feats)
    finally:
        dev.close()


def try_call(dev, label, feat_idx, func, params=b""):
    """Read-only getter call; prints the raw result and continues on error."""
    try:
        r = request(dev, feat_idx, func, params)
        print(f"  {label:<34} -> {r.hex(' ')}")
        return r
    except (RuntimeError, TimeoutError) as e:
        print(f"  {label:<34} !! {e}")
        return None


def deep(dev, feats):
    """Info (getter) functions of the standard features and of 0x8070/0x8040."""
    if 0x0003 in feats:
        i = feats[0x0003]
        print("\n[0x0003 DeviceFWVersion]")
        r = try_call(dev, "getEntityCount (fn0)", i, 0)
        n = r[0] if r else 0
        for e in range(n):
            r = try_call(dev, f"getFWInfo({e}) (fn1)", i, 1, bytes([e]))
            if r:
                print(
                    f"      type={r[0] & 0x0F} prefix={bytes(r[1:4]).decode(errors='replace')!r} "
                    f"version={r[4]:02x}.{r[5]:02x} build=0x{r[6]:02x}{r[7]:02x} active={r[8]}"
                )
    if 0x0005 in feats:
        i = feats[0x0005]
        print("\n[0x0005 DeviceNameType]")
        r = try_call(dev, "getCount (fn0)", i, 0)
        if r:
            r2 = try_call(dev, "getDeviceName(0) (fn1)", i, 1, b"\x00")
            if r2:
                print(f"      name={bytes(r2).split(b'\\x00')[0].decode(errors='replace')!r}")
        try_call(dev, "getDeviceType (fn2)", i, 2)
    if 0x8040 in feats:
        i = feats[0x8040]
        print("\n[0x8040 BrightnessControl]")
        try_call(dev, "getInfo (fn0)", i, 0)
        try_call(dev, "getBrightness (fn1)", i, 1)
    if 0x8070 in feats:
        i = feats[0x8070]
        print("\n[0x8070 ColorLEDEffects]  (g560-led: fn3 = setZoneEffect)")
        r = try_call(dev, "getInfo (fn0)", i, 0)
        zones = r[0] if r else 0
        for z in range(min(zones, 8)):
            zi = try_call(dev, f"getZoneInfo({z}) (fn1)", i, 1, bytes([z]))
            # getZoneInfo response: [zone, location(2), effectCount, effectCapability(2)]
            n_eff = zi[3] if zi else 0
            for e in range(min(n_eff, 12)):
                try_call(dev, f"getZoneEffectInfo({z},{e}) (fn2)", i, 2, bytes([z, e]))


if __name__ == "__main__":
    main()
