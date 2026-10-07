// Reads/sets the volume of the G560 USB audio device (macOS CoreAudio).
// Finding: the USB device volume also changes the speaker's overall volume (Bluetooth included).
//
//   swift tools/g560_volume.swift get
//   swift tools/g560_volume.swift set 0.50      // 0.0 - 1.0
import CoreAudio
import Foundation

setvbuf(stdout, nil, _IONBF, 0)

func addr(_ sel: AudioObjectPropertySelector, _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal, _ el: UInt32 = kAudioObjectPropertyElementMain) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: sel, mScope: scope, mElement: el)
}

func findUSBDevice() -> AudioObjectID? {
    var a = addr(kAudioHardwarePropertyDevices)
    var size: UInt32 = 0
    AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &a, 0, nil, &size)
    var ids = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &a, 0, nil, &size, &ids)
    for id in ids {
        var nameRef: Unmanaged<CFString>? = nil
        var nsz = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        var na = addr(kAudioObjectPropertyName)
        AudioObjectGetPropertyData(id, &na, 0, nil, &nsz, &nameRef)
        let name = (nameRef?.takeRetainedValue() as String?) ?? ""
        var tr: UInt32 = 0
        var tsz = UInt32(4)
        var ta = addr(kAudioDevicePropertyTransportType)
        AudioObjectGetPropertyData(id, &ta, 0, nil, &tsz, &tr)
        var osz: UInt32 = 0
        var oa = addr(kAudioDevicePropertyStreams, kAudioObjectPropertyScopeOutput)
        AudioObjectGetPropertyDataSize(id, &oa, 0, nil, &osz)
        if osz > 0, name.lowercased().contains("g560"), tr == kAudioDeviceTransportTypeUSB { return id }
    }
    return nil
}

guard let dev = findUSBDevice() else {
    print("USB G560 audio device not found (is the cable plugged in?)")
    exit(1)
}

func getVol() -> Float32 {
    var va = addr(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, 1)
    var v: Float32 = 0
    var sz = UInt32(4)
    AudioObjectGetPropertyData(dev, &va, 0, nil, &sz, &v)
    return v
}

let args = CommandLine.arguments
switch args.count > 1 ? args[1] : "get" {
case "set":
    guard args.count > 2, let v = Float32(args[2]), v >= 0, v <= 1 else {
        print("usage: set <0.0-1.0>")
        exit(2)
    }
    var val = v
    for el: UInt32 in [1, 2] {
        var va = addr(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, el)
        AudioObjectSetPropertyData(dev, &va, 0, nil, UInt32(4), &val)
    }
    print("USB device volume set: \(getVol())")
default:
    print("USB device volume: \(getVol())")
}
