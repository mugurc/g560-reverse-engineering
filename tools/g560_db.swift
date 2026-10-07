// Reads the dB values of the G560 USB audio device READ-ONLY (no Set calls at all).
// What it reads: VolumeScalar, VolumeDecibels, VolumeRangeDecibels (min/max), and
// macOS's scalar<->dB conversion (ScalarToDecibels: a pure conversion, it never goes to the device).
import CoreAudio
import Foundation

setvbuf(stdout, nil, _IONBF, 0)

func addr(_ sel: AudioObjectPropertySelector, _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeOutput, _ el: UInt32 = 1) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: sel, mScope: scope, mElement: el)
}

func findUSBDevice() -> AudioObjectID? {
    var a = addr(kAudioHardwarePropertyDevices, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain)
    var size: UInt32 = 0
    AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &a, 0, nil, &size)
    var ids = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &a, 0, nil, &size, &ids)
    for id in ids {
        var nameRef: Unmanaged<CFString>? = nil
        var nsz = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        var na = addr(kAudioObjectPropertyName, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain)
        AudioObjectGetPropertyData(id, &na, 0, nil, &nsz, &nameRef)
        let name = (nameRef?.takeRetainedValue() as String?) ?? ""
        var tr: UInt32 = 0
        var tsz = UInt32(4)
        var ta = addr(kAudioDevicePropertyTransportType, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain)
        AudioObjectGetPropertyData(id, &ta, 0, nil, &tsz, &tr)
        var osz: UInt32 = 0
        var oa = addr(kAudioDevicePropertyStreams)
        AudioObjectGetPropertyDataSize(id, &oa, 0, nil, &osz)
        if osz > 0, name.lowercased().contains("g560"), tr == kAudioDeviceTransportTypeUSB { return id }
    }
    return nil
}

guard let dev = findUSBDevice() else { print("USB G560 audio device not found"); exit(1) }

func getF(_ sel: AudioObjectPropertySelector, _ el: UInt32) -> Float32? {
    var a = addr(sel, kAudioObjectPropertyScopeOutput, el)
    var v: Float32 = 0
    var sz = UInt32(4)
    let r = AudioObjectGetPropertyData(dev, &a, 0, nil, &sz, &v)
    return r == noErr ? v : nil
}

func toDb(_ s: Float32, _ el: UInt32) -> Float32? {
    var a = addr(kAudioDevicePropertyVolumeScalarToDecibels, kAudioObjectPropertyScopeOutput, el)
    var v = s
    var sz = UInt32(4)
    let r = AudioObjectGetPropertyData(dev, &a, 0, nil, &sz, &v)
    return r == noErr ? v : nil
}

for el: UInt32 in [0, 1, 2] {
    var ra = addr(kAudioDevicePropertyVolumeRangeDecibels, kAudioObjectPropertyScopeOutput, el)
    var rng = AudioValueRange()
    var rsz = UInt32(MemoryLayout<AudioValueRange>.size)
    let rr = AudioObjectGetPropertyData(dev, &ra, 0, nil, &rsz, &rng)
    let sc = getF(kAudioDevicePropertyVolumeScalar, el)
    let db = getF(kAudioDevicePropertyVolumeDecibels, el)
    print("element \(el): scalar=\(sc.map { String($0) } ?? "n/a")  dB=\(db.map { String($0) } ?? "n/a")  range=" + (rr == noErr ? "\(rng.mMinimum)…\(rng.mMaximum) dB" : "n/a"))
}

// macOS's scalar -> dB conversion (curve): is it linear or not
print("scalar -> dB (element 1):")
for s in stride(from: Float32(0), through: 1, by: 0.1) {
    print(String(format: "  %.2f -> %@", s, toDb(s, 1).map { String(format: "%.2f dB", $0) } ?? "n/a"))
}
