#!/usr/bin/env python3
"""G560 light control: HID++ 0x8070 ColorLEDEffects, fn3 = setZoneEffect.

WARNING: this tool writes settings to the device (and --save makes them persistent). Use at your own risk.

Request body (16 bytes): [zone, effect, p0..p9 (10 bytes), persistence, 0, 0, 0]
If `persistence` = 1, the setting is written to the device's persistent memory
(verified on the G560: with no USB connection, over Bluetooth, the setting is
still there after a power cycle). The default 0 = temporary.
Pass --save to write persistently.

Note: g560-led's `intro on|off` command is a leftover from the G403 mouse
script; on the G560 it does not turn off the startup animation, it writes an
almost-black solid color to zone 0. DO NOT USE IT.

Zones: 0 rear left, 1 rear right, 2 front left, 3 front right (g560-led naming).
The effect indices were read with getZoneEffectInfo: 0 off, 1 solid, 2 cycle,
3 audio visualizer, 4 breathe.

Examples:
  python3 g560.py set --effect solid --color 0000ff --save
  python3 g560.py set --effect solid --color ff0000,00ff00,0000ff,ffff00
  python3 g560.py set --effect breathe --color ff00aa --rate 4000
  python3 g560.py set --effect cycle --rate 10000 --brightness 60
"""
import argparse
import sys

import hid

from probe_hidpp import find_path, request

EFFECTS = {"off": 0, "solid": 1, "cycle": 2, "breathe": 4}
FEAT_COLOR_LED = 0x8070
FEAT_BRIGHTNESS = 0x8040


def open_dev():
    dev = hid.device()
    dev.open_path(find_path(verbose=False))
    dev.set_nonblocking(False)
    return dev


def effect_params(effect, rgb, rate, brightness):
    if effect == "solid":
        return rgb
    if effect == "breathe":  # color, period (ms), wave=0, brightness
        return rgb + rate.to_bytes(2, "big") + b"\x00" + bytes([brightness])
    if effect == "cycle":  # period (ms), brightness
        return bytes(5) + rate.to_bytes(2, "big") + bytes([brightness])
    return b""


def set_zone_effect(dev, feat_idx, zone, effect, params, persist):
    payload = bytearray(16)
    payload[0], payload[1] = zone, effect
    payload[2 : 2 + len(params)] = params
    payload[12] = persist
    try:
        return request(dev, feat_idx, 3, bytes(payload), timeout=0.5)
    except TimeoutError:
        return None  # the write may have gone through even without a response; check visually


def parse_colors(arg, zones):
    colors = [bytes.fromhex(c.lstrip("#")) for c in arg.split(",")]
    if any(len(c) != 3 for c in colors):
        sys.exit("--color must be RRGGBB (or a comma-separated list with one entry per zone)")
    if len(colors) == 1:
        return colors * len(zones)
    if len(colors) != len(zones):
        sys.exit(f"{len(colors)} colors given for {len(zones)} zones")
    return colors


def brightness(value):
    """0x8040 BrightnessControl: fn1 = getBrightness, fn2 = setBrightness (2 bytes BE).

    Layout taken from Solaar (read 0x10, write 0x20); getInfo: max=100, 4 steps, min=0.
    """
    dev = open_dev()
    try:
        idx = request(dev, 0x00, 0, FEAT_BRIGHTNESS.to_bytes(2, "big"))[0]
        if idx == 0:
            sys.exit("0x8040 not found")
        before = int.from_bytes(request(dev, idx, 1)[0:2], "big")
        try:
            request(dev, idx, 2, max(0, min(100, value)).to_bytes(2, "big"), timeout=0.5)
        except TimeoutError:
            pass  # even if no response arrives, the read-back shows what actually happened
        after = int.from_bytes(request(dev, idx, 1)[0:2], "big")
        print(f"brightness: {before} -> {after}")
    finally:
        dev.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set", help="write an effect to the zone(s)")
    s.add_argument("--effect", choices=EFFECTS, default="solid")
    s.add_argument("--color", default="ffffff", help="RRGGBB or a comma-separated list with one entry per zone")
    s.add_argument("--zones", default="0,1,2,3", help="comma-separated list of zones (0-3)")
    s.add_argument("--rate", type=int, default=10000, help="period in ms (100-60000)")
    s.add_argument("--brightness", type=int, default=100, help="1-100 (cycle/breathe)")
    s.add_argument("--save", action="store_true", help="write to the device's persistent memory")
    b = sub.add_parser("brightness", help="global brightness (0x8040; levels 0/25/50/100)")
    b.add_argument("value", type=int, help="0-100")
    a = ap.parse_args()

    if a.cmd == "brightness":
        return brightness(a.value)

    zones = [int(z) for z in a.zones.split(",")]
    if any(z not in range(4) for z in zones):
        sys.exit("zones must be 0-3")
    colors = parse_colors(a.color, zones)
    rate = max(100, min(60000, a.rate))
    level = max(1, min(100, a.brightness))
    persist = 1 if a.save else 0

    dev = open_dev()
    try:
        feat_idx = request(dev, 0x00, 0, FEAT_COLOR_LED.to_bytes(2, "big"))[0]
        if feat_idx == 0:
            sys.exit("0x8070 not found")
        for z, rgb in zip(zones, colors):
            params = effect_params(a.effect, rgb, rate, level)
            r = set_zone_effect(dev, feat_idx, z, EFFECTS[a.effect], params, persist)
            ack = "ok" if r is not None else "no response"
            print(f"zone {z}: {a.effect} {rgb.hex()} storage={'persistent' if persist else 'temporary'} -> {ack}")
    finally:
        dev.close()


if __name__ == "__main__":
    main()
