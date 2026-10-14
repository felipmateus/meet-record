// teams-tap: captures the audio emitted by a process (e.g. Microsoft Teams) via
// Core Audio Process Tap (macOS 14.2+) and records it to WAV until it receives
// SIGINT/SIGTERM or until the target process exits.
//
// Usage: teams-tap --pid <pid> --out <file.wav> [--epoch <unix s>] [--bits 16|32] [--stats <file.json>] [--verbose]
// Output: exit code 0 on success; error messages on stderr.

import AVFoundation
import CoreAudio
import Foundation

// MARK: - Utilities

func log(_ message: String) {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
}

func fail(_ message: String, code: Int32 = 1) -> Never {
    log("teams-tap: " + message)
    exit(code)
}

func check(_ status: OSStatus, _ what: String) {
    if status != noErr {
        fail("\(what) failed (OSStatus \(status))")
    }
}

struct Arguments {
    var pid: pid_t = 0
    var out: URL?
    var verbose = false
    var waitAudioSeconds: Double = 20   // time for the target process to become an audio client
    var list = false                    // only list the audio client processes and exit
    var includeDescendants = true       // include the target's child processes (Teams plays audio through a helper)
    var mic: String?                    // microphone mode: "default" (follows the default input) or a device name
    var epoch: Double?                  // shared start instant (Unix seconds): both tracks are aligned to it
    var bits = 16                       // WAV sample format: 16 (integer PCM) or 32 (float)
    var stats: URL?                     // JSON written at stop: seconds written, padding, gaps, device rates

    static func parse(_ argv: [String]) -> Arguments {
        var args = Arguments()
        var it = argv.dropFirst().makeIterator()
        while let a = it.next() {
            switch a {
            case "--pid":
                guard let v = it.next(), let p = Int32(v) else { fail("--pid requires a number") }
                args.pid = p
            case "--out":
                guard let v = it.next() else { fail("--out requires a path") }
                args.out = URL(fileURLWithPath: v)
            case "--verbose", "-v":
                args.verbose = true
            case "--wait-audio":
                guard let v = it.next(), let secs = Double(v) else { fail("--wait-audio requires seconds") }
                args.waitAudioSeconds = secs
            case "--list":
                args.list = true
            case "--no-descendants":
                args.includeDescendants = false
            case "--mic":
                guard let v = it.next() else { fail("--mic requires 'default' or a device name") }
                args.mic = v
            case "--epoch":
                guard let v = it.next(), let e = Double(v) else { fail("--epoch requires Unix seconds") }
                args.epoch = e
            case "--bits":
                guard let v = it.next(), let b = Int(v), b == 16 || b == 32 else { fail("--bits requires 16 or 32") }
                args.bits = b
            case "--stats":
                guard let v = it.next() else { fail("--stats requires a path") }
                args.stats = URL(fileURLWithPath: v)
            case "--help", "-h":
                print("Usage: teams-tap --pid <pid> --out <file.wav> [--epoch <unix s>] [--bits 16|32] [--stats <file.json>] [--wait-audio <s>] [--no-descendants] [--verbose]")
                print("       records the process at 48 kHz, resampling from whatever rate the output device runs at (16 kHz for a Bluetooth headset in a call)")
                print("       teams-tap --mic <default|name> --out <file.wav> [--epoch <unix s>] [--bits 16|32] [--stats <file.json>] [--verbose]   records the microphone (48 kHz mono), surviving format/device changes")
                print("       --bits: WAV sample format, 16-bit integer (default) or 32-bit float")
                print("       --stats: writes seconds written, silence padded and device rates as JSON when recording stops")
                print("       --epoch aligns the file to a shared start instant; time without audio is written as silence")
                print("       teams-tap --list        lists the processes that are audio clients (pid, parent, bundle, emitting?)")
                exit(0)
            default:
                fail("unknown argument: \(a)")
            }
        }
        if args.list { return args }
        if args.mic != nil {
            guard args.out != nil else { fail("--out is required") }
            return args
        }
        guard args.pid > 0 else { fail("--pid is required") }
        guard args.out != nil else { fail("--out is required") }
        return args
    }
}

/// WAV file settings. Audio is processed as Float32 and AVAudioFile converts on write, so 16-bit
/// files halve the size (32-bit float adds nothing audible for speech or transcription).
func wavSettings(sampleRate: Double, channels: AVAudioChannelCount, bits: Int) -> [String: Any] {
    [
        AVFormatIDKey: kAudioFormatLinearPCM,
        AVSampleRateKey: sampleRate,
        AVNumberOfChannelsKey: channels,
        AVLinearPCMBitDepthKey: bits,
        AVLinearPCMIsFloatKey: bits == 32,
        AVLinearPCMIsBigEndianKey: false,
        AVLinearPCMIsNonInterleaved: false,
    ]
}

// MARK: - Audio processes

struct AudioProcess {
    let object: AudioObjectID
    let pid: pid_t
    let bundleID: String
    let isRunningOutput: Bool
}

func getProperty<T>(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector, _ initial: T) -> T? {
    var address = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var value = initial
    var size = UInt32(MemoryLayout<T>.size)
    let status = AudioObjectGetPropertyData(object, &address, 0, nil, &size, &value)
    return status == noErr ? value : nil
}

/// All processes registered with Core Audio (audio clients).
func audioProcesses() -> [AudioProcess] {
    var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyProcessObjectList, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size) == noErr else { return [] }
    var objects = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &objects) == noErr else { return [] }
    return objects.compactMap { obj in
        guard let pid: pid_t = getProperty(obj, kAudioProcessPropertyPID, pid_t(0)) else { return nil }
        let bundle = (getProperty(obj, kAudioProcessPropertyBundleID, "" as CFString) as String?) ?? ""
        let running = (getProperty(obj, kAudioProcessPropertyIsRunningOutput, UInt32(0)) ?? 0) != 0
        return AudioProcess(object: obj, pid: pid, bundleID: bundle, isRunningOutput: running)
    }
}

func parentPID(of pid: pid_t) -> pid_t? {
    var info = kinfo_proc()
    var size = MemoryLayout<kinfo_proc>.size
    var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_PID, pid]
    guard sysctl(&mib, 4, &info, &size, nil, 0) == 0, size > 0 else { return nil }
    return info.kp_eproc.e_ppid
}

/// True if `pid` is `root` or descends from it (walks up the parent chain).
func isDescendant(_ pid: pid_t, of root: pid_t) -> Bool {
    var current = pid
    var hops = 0
    while current > 1 && hops < 32 {
        if current == root { return true }
        guard let parent = parentPID(of: current) else { return false }
        current = parent
        hops += 1
    }
    return false
}

func listAudioProcesses() {
    let procs = audioProcesses().sorted { $0.pid < $1.pid }
    print("pid\tppid\temitting\tbundle")
    for p in procs {
        print("\(p.pid)\t\(parentPID(of: p.pid) ?? 0)\t\(p.isRunningOutput ? "yes" : "no")\t\(p.bundleID)")
    }
}

// MARK: - Timeline writer

/// Writes audio buffers keeping the file aligned to wall-clock time.
///
/// Core Audio delivers buffers with the host time of their first sample. When delivery
/// pauses (observed on a real call: ~17 s missing with no error), a plain writer would glue
/// what comes after onto what came before, so speech looks cut and the Teams and microphone
/// tracks drift apart. Here every buffer is placed at its timestamp: missing time is filled
/// with silence and logged. With `epoch`, the timeline starts at that shared instant, so both
/// recorders produce tracks aligned to the same origin.
///
/// Padding below `logGapSeconds` is counted apart (`shortPaddedSeconds`): it is normally jitter, a
/// fraction of a percent of the track. When buffers carry fewer frames per second than `format`
/// says (the device runs at 16 kHz and the file at 48 kHz), the writer falls behind the clock by
/// 2/3 of every second and pads it 0.2 s at a time, never logging a gap: speech comes out sped up
/// and chopped. A large short-padding share is the signature of that rate mismatch.
final class TimelineWriter {
    let file: AVAudioFile
    let format: AVAudioFormat
    private let startHostNanos: UInt64
    private let epochOffset: Double          // seconds from epoch to this writer's start
    private let lock = NSLock()
    private(set) var framesWritten: Int64 = 0
    private(set) var paddedSeconds: Double = 0
    private(set) var shortPaddedSeconds = 0.0 // the part of paddedSeconds in pads under logGapSeconds
    private(set) var gaps = 0
    static let minPadSeconds = 0.2           // jitter below this is ignored
    static let logGapSeconds = 0.5           // gaps from this size up are logged
    static let rateWarningShare = 0.05       // short padding above this share of the track: the rate is likely wrong
    static let rateWarningMinSeconds = 60.0  // ...on tracks at least this long

    init(file: AVAudioFile, format: AVAudioFormat, epoch: Double?) {
        self.file = file
        self.format = format
        startHostNanos = AudioConvertHostTimeToNanos(AudioGetCurrentHostTime())
        epochOffset = epoch.map { max(0, Date().timeIntervalSince1970 - $0) } ?? 0
    }

    private func expectedFrame(hostTime: UInt64) -> Int64 {
        let nanos = AudioConvertHostTimeToNanos(hostTime)
        let elapsed = nanos > startHostNanos ? Double(nanos - startHostNanos) / 1e9 : 0
        return Int64((epochOffset + elapsed) * format.sampleRate)
    }

    func write(_ buffer: AVAudioPCMBuffer, hostTime: UInt64?) {
        lock.lock(); defer { lock.unlock() }
        if let hostTime { padLocked(to: expectedFrame(hostTime: hostTime)) }
        do {
            try file.write(from: buffer)
            framesWritten += Int64(buffer.frameLength)
        } catch {
            log("teams-tap: error writing audio: \(error)")
        }
    }

    /// Pads the end of the file up to "now" (call after capture has stopped).
    func finish() {
        lock.lock(); defer { lock.unlock() }
        padLocked(to: expectedFrame(hostTime: AudioGetCurrentHostTime()))
    }

    private func padLocked(to target: Int64) {
        let missing = target - framesWritten
        guard Double(missing) / format.sampleRate >= Self.minPadSeconds else { return }
        let seconds = Double(missing) / format.sampleRate
        let at = Double(framesWritten) / format.sampleRate
        if framesWritten == 0 {
            log(String(format: "teams-tap: start offset %.1f s (padded with silence)", seconds))
        } else if seconds >= Self.logGapSeconds {
            gaps += 1
            log(String(format: "teams-tap: gap of %.1f s at %.1f s (padded with silence)", seconds, at))
        }
        var remaining = missing
        let chunk = AVAudioFrameCount(format.sampleRate)          // one second per write
        while remaining > 0 {
            let n = AVAudioFrameCount(min(Int64(chunk), remaining))
            guard let silence = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: n) else { return }
            silence.frameLength = n
            for b in UnsafeMutableAudioBufferListPointer(silence.mutableAudioBufferList) {
                if let data = b.mData { memset(data, 0, Int(b.mDataByteSize)) }
            }
            do { try file.write(from: silence) } catch { log("teams-tap: error writing silence: \(error)"); return }
            framesWritten += Int64(n)
            remaining -= Int64(n)
        }
        if framesWritten > 0 && seconds >= Self.minPadSeconds && at > 0 {
            paddedSeconds += seconds
            if seconds < Self.logGapSeconds { shortPaddedSeconds += seconds }
        }
    }

    var writtenSeconds: Double { Double(framesWritten) / format.sampleRate }

    var summary: String {
        var text = String(format: "%.1f s written, %d gap(s), %.1f s of silence padded (%.1f s in short pads)", writtenSeconds, gaps, paddedSeconds, shortPaddedSeconds)
        if writtenSeconds >= Self.rateWarningMinSeconds && shortPaddedSeconds / writtenSeconds > Self.rateWarningShare {
            text += String(format: "; WARNING: %.0f%% of the track is short padding with no logged gap, the device likely delivered fewer frames per second than %.0f Hz", 100 * shortPaddedSeconds / writtenSeconds, format.sampleRate)
        }
        return text
    }

    /// Writes the counters, plus `extra`, as JSON (call after `finish`). The pipeline reads it to flag a
    /// transcript made from a track with a rate mismatch.
    func writeStats(to url: URL, extra: [String: Any] = [:]) {
        var stats: [String: Any] = [
            "written_seconds": writtenSeconds,
            "padded_seconds": paddedSeconds,
            "short_padded_seconds": shortPaddedSeconds,
            "gaps": gaps,
            "file_rate": format.sampleRate,
        ]
        stats.merge(extra) { _, new in new }
        do {
            let data = try JSONSerialization.data(withJSONObject: stats, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: url, options: .atomic)
        } catch {
            log("teams-tap: could not write \(url.path): \(error)")
        }
    }
}

/// Measures the rate the device really runs at, from its sample clock (or buffer sizes) against host time.
///
/// The format properties are not always right: the tap reported 48 kHz while the aggregate device
/// delivered 16 kHz (2026-10-13/14, Bluetooth headset in a call), and the track came out 3x fast.
/// The device's sample time is preferred to counting frames: it keeps advancing through IO cycles the
/// process misses under load, which counting frames would read as a slower device. Intervals longer
/// than `maxInterval` are delivery pauses, and intervals implying an impossible rate are clock
/// discontinuities; neither is a rate sample. Two windows in a row away from the assumed rate by more
/// than `tolerance` give a corrected rate, but only when the measurement sits within `snapTolerance`
/// of a standard rate: anything in between is a disturbed window, not a device rate.
struct RateMeter {
    static let window = 2.0
    static let maxInterval = 0.5
    static let tolerance = 0.05
    static let snapTolerance = 0.015
    static let windowsToSwitch = 2
    static let plausibleRates = 4000.0...400_000.0
    static let standardRates: [Double] = [8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 88200, 96000, 176400, 192000]

    private var lastHost: UInt64?
    private var lastSample: Double?
    private var frames = 0.0
    private var seconds = 0.0
    private var strikes = 0
    private var loggedIgnored = false        // under sustained load every window can be disturbed: say so once

    mutating func reset() {
        lastHost = nil
        lastSample = nil
        frames = 0
        seconds = 0
        strikes = 0
    }

    /// The standard rate within `snapTolerance` of `measured`, if any.
    static func standardRate(near measured: Double) -> Double? {
        guard let nearest = standardRates.min(by: { abs($0 - measured) < abs($1 - measured) }) else { return nil }
        return abs(measured / nearest - 1) <= snapTolerance ? nearest : nil
    }

    /// Feeds one buffer: its size, the host time of its first frame and, when valid, the device sample
    /// time of that frame. Returns the rate to switch to when the device is clearly not at `assumed`.
    mutating func add(frames n: AVAudioFrameCount, hostTime: UInt64, sampleTime: Double?, assumed: Double) -> Double? {
        let previousSample = lastSample
        defer { lastHost = hostTime; lastSample = sampleTime }
        guard let last = lastHost, hostTime > last else { return nil }
        let dt = Double(AudioConvertHostTimeToNanos(hostTime - last)) / 1e9
        guard dt < Self.maxInterval else { return nil }
        // Frames since the previous buffer: from the sample clock, or else the previous buffer's size (this
        // buffer's own size is the best stand-in, as buffers keep one size).
        let advanced = sampleTime.flatMap { now in previousSample.map { now - $0 } } ?? Double(n)
        guard Self.plausibleRates.contains(advanced / dt) else { return nil }
        frames += advanced
        seconds += dt
        guard seconds >= Self.window else { return nil }
        let measured = frames / seconds
        frames = 0
        seconds = 0
        guard abs(measured / assumed - 1) > Self.tolerance else { strikes = 0; return nil }
        guard let snapped = Self.standardRate(near: measured) else {
            if !loggedIgnored {
                loggedIgnored = true
                log(String(format: "teams-tap: device ran at ~%.0f Hz for %.0f s, not %.0f Hz; no standard rate near it, ignored (logged once)", measured, Self.window, assumed))
            }
            strikes = 0
            return nil
        }
        strikes += 1
        guard strikes >= Self.windowsToSwitch else { return nil }
        strikes = 0
        log(String(format: "teams-tap: device runs at ~%.0f Hz, not %.0f Hz", measured, assumed))
        return snapped == assumed ? nil : snapped
    }
}

// MARK: - Tap converter

/// Turns what the aggregate device delivers into file-format buffers: picks the tap's streams, reads
/// them at the device's real rate, and resamples them to the file rate.
///
/// The rate is whatever `setRate` was last given (the device's nominal rate), corrected by `RateMeter`
/// when the frames really delivered disagree. Not thread-safe: use it from one queue.
final class TapConverter {
    let tapASBD: AudioStreamBasicDescription
    let outFormat: AVAudioFormat
    private(set) var inFormat: AVAudioFormat
    private(set) var rates: [Double] = []      // every rate used, in order
    private var converter: AVAudioConverter
    private var meter = RateMeter()
    private var loggedBufferLayout = false

    /// `tap`: the layout the tap reports (its sample rate is not trusted); `deviceRate`: the rate buffers arrive at.
    init?(tap: AudioStreamBasicDescription, deviceRate: Double, fileRate: Double) {
        let channels = AVAudioChannelCount(max(1, tap.mChannelsPerFrame))
        var asbd = tap
        asbd.mSampleRate = deviceRate
        guard let out = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: fileRate, channels: channels, interleaved: false),
              let fmt = AVAudioFormat(streamDescription: &asbd),
              let conv = AVAudioConverter(from: fmt, to: out) else { return nil }
        tapASBD = tap
        outFormat = out
        inFormat = fmt
        converter = conv
        rates = [deviceRate]
    }

    /// Reads buffers at `rate` from now on. False (and the previous rate kept) when no converter can be built for it.
    @discardableResult
    func setRate(_ rate: Double) -> Bool {
        guard rate != inFormat.sampleRate else { return true }
        var asbd = tapASBD
        asbd.mSampleRate = rate
        guard let fmt = AVAudioFormat(streamDescription: &asbd), let conv = AVAudioConverter(from: fmt, to: outFormat) else {
            log(String(format: "teams-tap: no converter from %.0f Hz; keeping %.0f Hz", rate, inFormat.sampleRate))
            return false
        }
        inFormat = fmt
        converter = conv
        meter.reset()
        rates.append(rate)
        log(String(format: "teams-tap: device rate is now %.0f Hz; resampling to %.0f Hz", rate, outFormat.sampleRate))
        return true
    }

    /// One device buffer in the file format; nil when there is nothing to write (no tap stream, a rate switch).
    func convert(_ input: UnsafePointer<AudioBufferList>, hostTime: UInt64?, sampleTime: Double? = nil) -> AVAudioPCMBuffer? {
        guard let buffer = tapBuffer(input) else { return nil }
        if let hostTime, let rate = meter.add(frames: buffer.frameLength, hostTime: hostTime, sampleTime: sampleTime, assumed: inFormat.sampleRate) {
            setRate(rate)
            return nil  // this one buffer (~10 ms) is dropped; the writer pads it
        }
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * outFormat.sampleRate / inFormat.sampleRate) + 32
        guard let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: capacity) else { return nil }
        var consumed = false
        var error: NSError?
        let status = converter.convert(to: out, error: &error) { _, outStatus in
            if consumed { outStatus.pointee = .noDataNow; return nil }
            consumed = true
            outStatus.pointee = .haveData
            return buffer
        }
        return status != .error && out.frameLength > 0 ? out : nil
    }

    /// The tap's buffers within what the aggregate delivers. Normally that is all of it; if the output
    /// device also has an input (a headset microphone in call mode), its streams come along and the
    /// tap's are the last ones with the tap's layout.
    private func tapBuffer(_ input: UnsafePointer<AudioBufferList>) -> AVAudioPCMBuffer? {
        let all = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input))
        let needed = inFormat.isInterleaved ? 1 : Int(inFormat.channelCount)
        let perBuffer = inFormat.isInterleaved ? inFormat.channelCount : 1
        if all.count == needed {
            return AVAudioPCMBuffer(pcmFormat: inFormat, bufferListNoCopy: input, deallocator: nil)
        }
        let matching = all.filter { $0.mNumberChannels == perBuffer }
        if !loggedBufferLayout {
            loggedBufferLayout = true
            log("teams-tap: the device delivers \(all.count) buffer(s) with " + all.map { "\($0.mNumberChannels)" }.joined(separator: "/") + " channel(s); using the last \(needed) with \(perBuffer)")
        }
        guard matching.count >= needed else { return nil }
        let list = AudioBufferList.allocate(maximumBuffers: needed)
        for (i, b) in matching.suffix(needed).enumerated() { list[i] = b }
        // The deallocator is handed AVAudioPCMBuffer's own copy of the list, not ours: free ours by capture.
        return AVAudioPCMBuffer(pcmFormat: inFormat, bufferListNoCopy: list.unsafePointer) { _ in free(list.unsafeMutablePointer) }
    }
}

// MARK: - Recorder

/// Records the audio of a process through a Core Audio tap, at 48 kHz whatever the output device runs at.
///
/// The tap sits in a private aggregate device whose clock is the default output, and the aggregate
/// delivers buffers at that device's rate, not at the rate the tap format reports: with a Bluetooth
/// headset in a call (HFP) the output runs at 16 kHz while kAudioTapPropertyFormat still says 48 kHz.
/// Writing those buffers as 48 kHz made the Teams track 3x fast and chopped (three meetings,
/// 2026-10-13/14). So the input format takes the tap's layout and the aggregate's nominal rate, follows
/// rate changes (kAudioDevicePropertyNominalSampleRate listener, e.g. the headset switching to call
/// mode mid-call), is checked against the frames really delivered (`RateMeter`), and is resampled to
/// the file rate with AVAudioConverter, as the microphone path does.
final class ProcessTapRecorder {
    static let fileRate: Double = 48000

    let pid: pid_t
    let url: URL
    let verbose: Bool
    let waitAudioSeconds: Double
    let includeDescendants: Bool
    let epoch: Double?
    let bits: Int
    let statsURL: URL?

    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?
    private var writer: TimelineWriter?
    private var converter: TapConverter?      // used on `queue` once capture runs (the IOProc and the rate listener both run there)
    private var rateListener: AudioObjectPropertyListenerBlock?
    private let queue = DispatchQueue(label: "local.teams-recorder.teams-tap.io")
    private var stopped = false               // main thread: stop() ran
    private var capturing = true              // `queue`: false once stop() has drained it, so late callbacks do nothing
    private static var rateAddress = AudioObjectPropertyAddress(
        mSelector: kAudioDevicePropertyNominalSampleRate, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)

    init(pid: pid_t, url: URL, verbose: Bool, waitAudioSeconds: Double, includeDescendants: Bool, epoch: Double?, bits: Int, statsURL: URL?) {
        self.bits = bits
        self.pid = pid
        self.url = url
        self.verbose = verbose
        self.waitAudioSeconds = waitAudioSeconds
        self.includeDescendants = includeDescendants
        self.epoch = epoch
        self.statsURL = statsURL
    }

    func start() {
        let targets = waitForAudioClients()
        log("teams-tap: capturing \(targets.count) audio process(es): " + targets.map { "\($0.pid)\($0.bundleID.isEmpty ? "" : "[\($0.bundleID)]")" }.joined(separator: ", "))

        let tapDescription = CATapDescription(stereoMixdownOfProcesses: targets.map { $0.object })
        tapDescription.uuid = UUID()
        tapDescription.name = "teams-tap \(pid)"
        tapDescription.isPrivate = true
        tapDescription.muteBehavior = .unmuted
        check(AudioHardwareCreateProcessTap(tapDescription, &tapID), "create process tap")
        if verbose { log("tap created: \(tapID)") }

        let outputUID = defaultOutputDeviceUID()
        let description: [String: Any] = [
            kAudioAggregateDeviceNameKey: "teams-tap aggregate",
            kAudioAggregateDeviceUIDKey: UUID().uuidString,
            kAudioAggregateDeviceMainSubDeviceKey: outputUID,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
            kAudioAggregateDeviceTapAutoStartKey: true,
            kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
            kAudioAggregateDeviceTapListKey: [[
                kAudioSubTapDriftCompensationKey: true,
                kAudioSubTapUIDKey: tapDescription.uuid.uuidString,
            ]],
        ]
        check(AudioHardwareCreateAggregateDevice(description as CFDictionary, &aggregateID), "create aggregate device")
        if verbose { log("aggregate device created: \(aggregateID)") }

        let tapASBD = tapStreamFormat()
        let deviceRate = aggregateNominalRate() ?? tapASBD.mSampleRate
        log(String(format: "teams-tap: tap format %.0f Hz, %d channel(s); output device %@ runs at %.0f Hz; file %.0f Hz", tapASBD.mSampleRate, Int(tapASBD.mChannelsPerFrame), outputUID, deviceRate, Self.fileRate))
        guard let conv = TapConverter(tap: tapASBD, deviceRate: deviceRate, fileRate: Self.fileRate) else { fail("could not create audio converter") }
        converter = conv
        let out = conv.outFormat
        let settings = wavSettings(sampleRate: out.sampleRate, channels: out.channelCount, bits: bits)
        do {
            let file = try AVAudioFile(forWriting: url, settings: settings, commonFormat: .pcmFormatFloat32, interleaved: false)
            writer = TimelineWriter(file: file, format: out, epoch: epoch)
        } catch {
            fail("could not create \(url.path): \(error)")
        }

        let listener: AudioObjectPropertyListenerBlock = { [weak self] _, _ in self?.nominalRateChanged() }
        if AudioObjectAddPropertyListenerBlock(aggregateID, &Self.rateAddress, queue, listener) == noErr {
            rateListener = listener
        } else {
            log("teams-tap: could not watch the device's sample rate; relying on the measured rate")
        }

        let status = AudioDeviceCreateIOProcIDWithBlock(&ioProcID, aggregateID, queue) { [weak self] _, inInputData, inInputTime, _, _ in
            self?.process(inInputData, inInputTime.pointee)
        }
        check(status, "create IOProc")
        check(AudioDeviceStart(aggregateID, ioProcID), "start capture")
        log("teams-tap: recording process \(pid) to \(url.path) (\(bits)-bit)")
    }

    func stop() {
        guard !stopped else { return }
        stopped = true
        if let ioProcID {
            AudioDeviceStop(aggregateID, ioProcID)
            AudioDeviceDestroyIOProcID(aggregateID, ioProcID)
        }
        if let rateListener {
            AudioObjectRemovePropertyListenerBlock(aggregateID, &Self.rateAddress, queue, rateListener)
        }
        // Drain `queue` before the device and the tap go away: a callback still in flight reads their buffers,
        // and one queued behind it finds `capturing` false.
        let rates = queue.sync { () -> [Double] in
            capturing = false
            return converter?.rates ?? []
        }
        if aggregateID != kAudioObjectUnknown { AudioHardwareDestroyAggregateDevice(aggregateID) }
        if tapID != kAudioObjectUnknown { AudioHardwareDestroyProcessTap(tapID) }
        writer?.finish()                        // pad the tail up to the stop instant
        let rateList: String = rates.map { String(format: "%.0f", $0) }.joined(separator: " → ")
        let summary: String = writer?.summary ?? "nothing written"
        log("teams-tap: stopped, \(summary), device rate(s) \(rateList) Hz")
        if let statsURL, let writer {
            writer.writeStats(to: statsURL, extra: ["device_rates": rates, "rate_changes": max(0, rates.count - 1)])
        }
        writer = nil
    }

    // MARK: Capture (on `queue`)

    private func nominalRateChanged() {
        guard capturing, let rate = aggregateNominalRate() else { return }
        converter?.setRate(rate)
    }

    private func process(_ input: UnsafePointer<AudioBufferList>, _ time: AudioTimeStamp) {
        let hostTime = time.mFlags.contains(.hostTimeValid) ? time.mHostTime : nil
        let sampleTime = time.mFlags.contains(.sampleTimeValid) ? time.mSampleTime : nil
        guard capturing, let writer, let out = converter?.convert(input, hostTime: hostTime, sampleTime: sampleTime) else { return }
        writer.write(out, hostTime: hostTime)
    }

    // MARK: Core Audio helpers

    /// Audio processes that are the target or descend from it. Teams (Electron) plays sound
    /// through a helper process, not the main one; and it can take a few seconds between the
    /// start of the call and the audio initialization. Waits until at least one exists.
    private func matchingAudioProcesses() -> [AudioProcess] {
        audioProcesses().filter { $0.pid == pid || (includeDescendants && isDescendant($0.pid, of: pid)) }
    }

    private func waitForAudioClients() -> [AudioProcess] {
        let deadline = Date().addingTimeInterval(waitAudioSeconds)
        var attempt = 0
        while true {
            attempt += 1
            if kill(pid, 0) != 0 { fail("process \(pid) does not exist") }
            let found = matchingAudioProcesses()
            if !found.isEmpty {
                if attempt > 1 { log("teams-tap: audio of process \(pid) available after \(attempt) attempts") }
                return found
            }
            if Date() >= deadline { fail("process \(pid) (and descendants) has no audio client after \(Int(waitAudioSeconds)) s") }
            Thread.sleep(forTimeInterval: 0.5)
        }
    }


    private func defaultOutputDeviceUID() -> String {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var deviceID = AudioObjectID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioObjectID>.size)
        check(AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &deviceID), "get default output")

        address.mSelector = kAudioDevicePropertyDeviceUID
        var uid: CFString = "" as CFString
        size = UInt32(MemoryLayout<CFString>.size)
        let status = withUnsafeMutablePointer(to: &uid) { ptr in
            AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, ptr)
        }
        check(status, "get default output UID")
        return uid as String
    }

    private func aggregateNominalRate() -> Double? {
        guard let rate: Float64 = getProperty(aggregateID, kAudioDevicePropertyNominalSampleRate, Float64(0)), rate > 0 else { return nil }
        return rate
    }

    private func tapStreamFormat() -> AudioStreamBasicDescription {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioTapPropertyFormat,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var asbd = AudioStreamBasicDescription()
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        check(AudioObjectGetPropertyData(tapID, &address, 0, nil, &size, &asbd), "read tap format")
        return asbd
    }
}

// MARK: - Microphone (AVAudioEngine)

/// Records the microphone to 48 kHz mono WAV (16-bit or 32-bit float, see --bits). Uses AVAudioEngine because it notifies
/// configuration changes (Teams reconfigures the input device when it opens the microphone;
/// capture via ffmpeg/avfoundation stopped receiving frames at that moment) and because it
/// follows the system's default input when the user switches to a headset.
final class MicRecorder {
    let url: URL
    let deviceName: String
    let verbose: Bool
    let epoch: Double?
    let bits: Int
    let statsURL: URL?
    private let engine = AVAudioEngine()
    private let outFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48000, channels: 1, interleaved: false)!
    private var writer: TimelineWriter?
    private var converter: AVAudioConverter?
    private var observer: NSObjectProtocol?
    private var restarts = 0
    private var stopped = false

    init(url: URL, deviceName: String, verbose: Bool, epoch: Double?, bits: Int, statsURL: URL?) {
        self.bits = bits
        self.statsURL = statsURL
        self.url = url
        self.deviceName = deviceName
        self.verbose = verbose
        self.epoch = epoch
    }

    func start() {
        let settings = wavSettings(sampleRate: 48000, channels: 1, bits: bits)
        do {
            let file = try AVAudioFile(forWriting: url, settings: settings, commonFormat: .pcmFormatFloat32, interleaved: false)
            writer = TimelineWriter(file: file, format: outFormat, epoch: epoch)
        } catch {
            fail("could not create \(url.path): \(error)")
        }
        if deviceName != "default" {
            selectInputDevice(named: deviceName)
        }
        observer = NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main) { [weak self] _ in
            guard let self, !self.stopped else { return }
            self.restarts += 1
            log("teams-tap: audio configuration changed (\(self.restarts)); restarting microphone capture")
            self.engine.inputNode.removeTap(onBus: 0)
            self.installTapAndRun(retrying: true)
        }
        installTapAndRun(retrying: false)
        log("teams-tap: recording microphone (\(deviceName)) to \(url.path) (\(bits)-bit)")
    }

    private func installTapAndRun(retrying: Bool) {
        let input = engine.inputNode
        let inFormat = input.inputFormat(forBus: 0)
        guard inFormat.sampleRate > 0, inFormat.channelCount > 0 else {
            if retrying {
                log("teams-tap: input has no valid format; retrying in 1 s")
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in self?.installTapAndRun(retrying: true) }
                return
            }
            fail("input device has no valid format (microphone unavailable or permission denied)")
        }
        if verbose { log("microphone: \(inFormat.sampleRate) Hz, \(inFormat.channelCount) channels") }
        guard let conv = AVAudioConverter(from: inFormat, to: outFormat) else { fail("could not create audio converter") }
        converter = conv
        let outFormat = self.outFormat
        input.installTap(onBus: 0, bufferSize: 4096, format: inFormat) { [weak self] buffer, when in
            guard let self, let writer = self.writer, let converter = self.converter else { return }
            let ratio = outFormat.sampleRate / inFormat.sampleRate
            let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32
            guard let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: capacity) else { return }
            var consumed = false
            var error: NSError?
            let status = converter.convert(to: out, error: &error) { _, outStatus in
                if consumed { outStatus.pointee = .noDataNow; return nil }
                consumed = true
                outStatus.pointee = .haveData
                return buffer
            }
            guard status != .error, out.frameLength > 0 else { return }
            writer.write(out, hostTime: when.isHostTimeValid ? when.hostTime : nil)
        }
        do {
            engine.prepare()
            try engine.start()
        } catch {
            if retrying {
                log("teams-tap: failed to restart the audio engine (\(error)); retrying in 1 s")
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in self?.installTapAndRun(retrying: true) }
                return
            }
            fail("could not start microphone capture: \(error)")
        }
    }

    private func selectInputDevice(named name: String) {
        guard let deviceID = inputDeviceID(named: name) else {
            log("teams-tap: microphone '\(name)' not found; using the default input")
            return
        }
        var id = deviceID
        let status = AudioUnitSetProperty(engine.inputNode.audioUnit!, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0, &id, UInt32(MemoryLayout<AudioDeviceID>.size))
        if status != noErr { log("teams-tap: could not select '\(name)' (OSStatus \(status)); using the default input") }
    }

    private func inputDeviceID(named name: String) -> AudioDeviceID? {
        var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDevices, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size) == noErr else { return nil }
        var devices = [AudioDeviceID](repeating: 0, count: Int(size) / MemoryLayout<AudioDeviceID>.size)
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &devices) == noErr else { return nil }
        for dev in devices {
            var nameAddr = AudioObjectPropertyAddress(mSelector: kAudioObjectPropertyName, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
            var cfName: CFString = "" as CFString
            var nameSize = UInt32(MemoryLayout<CFString>.size)
            let ok = withUnsafeMutablePointer(to: &cfName) { AudioObjectGetPropertyData(dev, &nameAddr, 0, nil, &nameSize, $0) }
            guard ok == noErr, (cfName as String) == name else { continue }
            // does it have input channels?
            var inAddr = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyStreamConfiguration, mScope: kAudioDevicePropertyScopeInput, mElement: kAudioObjectPropertyElementMain)
            var inSize: UInt32 = 0
            if AudioObjectGetPropertyDataSize(dev, &inAddr, 0, nil, &inSize) == noErr, inSize > 0 {
                return dev
            }
        }
        return nil
    }

    func stop() {
        guard !stopped else { return }
        stopped = true
        if let observer { NotificationCenter.default.removeObserver(observer) }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        writer?.finish()                        // pad the tail up to the stop instant
        log("teams-tap: microphone stopped, " + (writer?.summary ?? "nothing written") + ", \(restarts) restart(s)")
        if let statsURL { writer?.writeStats(to: statsURL, extra: ["restarts": restarts]) }
        writer = nil
    }
}

// MARK: - main

let args = Arguments.parse(CommandLine.arguments)

if args.list {
    listAudioProcesses()
    exit(0)
}

var stopAll: () -> Void = {}

if let micName = args.mic {
    let mic = MicRecorder(url: args.out!, deviceName: micName, verbose: args.verbose, epoch: args.epoch, bits: args.bits, statsURL: args.stats)
    mic.start()
    stopAll = { mic.stop() }
} else {
    let recorder = ProcessTapRecorder(pid: args.pid, url: args.out!, verbose: args.verbose, waitAudioSeconds: args.waitAudioSeconds, includeDescendants: args.includeDescendants, epoch: args.epoch, bits: args.bits, statsURL: args.stats)
    recorder.start()
    stopAll = { recorder.stop() }
}

// Clean shutdown on signal.
signal(SIGINT, SIG_IGN)
signal(SIGTERM, SIG_IGN)
let signalSources: [DispatchSourceSignal] = [SIGINT, SIGTERM].map { sig in
    let source = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    source.setEventHandler {
        stopAll()
        exit(0)
    }
    source.resume()
    return source
}

// Exits on its own if the target process dies (tap mode only).
let watchdog = DispatchSource.makeTimerSource(queue: .main)
if args.mic == nil {
    watchdog.schedule(deadline: .now() + 1, repeating: 1)
    watchdog.setEventHandler {
        if kill(args.pid, 0) != 0 {
            log("teams-tap: process \(args.pid) exited")
            stopAll()
            exit(0)
        }
    }
    watchdog.resume()
}

dispatchMain()
