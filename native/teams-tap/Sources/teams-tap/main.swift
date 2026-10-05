// teams-tap: captures the audio emitted by a process (e.g. Microsoft Teams) via
// Core Audio Process Tap (macOS 14.2+) and records it to WAV until it receives
// SIGINT/SIGTERM or until the target process exits.
//
// Usage: teams-tap --pid <pid> --out <file.wav> [--epoch <unix s>] [--verbose]
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
            case "--help", "-h":
                print("Usage: teams-tap --pid <pid> --out <file.wav> [--epoch <unix s>] [--wait-audio <s>] [--no-descendants] [--verbose]")
                print("       teams-tap --mic <default|name> --out <file.wav> [--epoch <unix s>] [--verbose]   records the microphone (48 kHz mono), surviving format/device changes")
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
final class TimelineWriter {
    let file: AVAudioFile
    let format: AVAudioFormat
    private let startHostNanos: UInt64
    private let epochOffset: Double          // seconds from epoch to this writer's start
    private let lock = NSLock()
    private(set) var framesWritten: Int64 = 0
    private(set) var paddedSeconds: Double = 0
    private(set) var gaps = 0
    static let minPadSeconds = 0.2           // jitter below this is ignored
    static let logGapSeconds = 0.5           // gaps from this size up are logged

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
        if framesWritten > 0 && seconds >= Self.minPadSeconds && at > 0 { paddedSeconds += seconds }
    }

    var summary: String {
        String(format: "%.1f s written, %d gap(s), %.1f s of silence padded", Double(framesWritten) / format.sampleRate, gaps, paddedSeconds)
    }
}

// MARK: - Recorder

final class ProcessTapRecorder {
    let pid: pid_t
    let url: URL
    let verbose: Bool
    let waitAudioSeconds: Double
    let includeDescendants: Bool
    let epoch: Double?

    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?
    private var writer: TimelineWriter?
    private var format: AVAudioFormat?
    private let queue = DispatchQueue(label: "local.teams-recorder.teams-tap.io")
    private var stopped = false

    init(pid: pid_t, url: URL, verbose: Bool, waitAudioSeconds: Double, includeDescendants: Bool, epoch: Double?) {
        self.pid = pid
        self.url = url
        self.verbose = verbose
        self.waitAudioSeconds = waitAudioSeconds
        self.includeDescendants = includeDescendants
        self.epoch = epoch
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

        var asbd = tapStreamFormat()
        guard let fmt = AVAudioFormat(streamDescription: &asbd) else { fail("invalid tap format") }
        format = fmt
        if verbose { log("format: \(fmt.sampleRate) Hz, \(fmt.channelCount) channels, \(fmt.commonFormat.rawValue)") }

        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: fmt.sampleRate,
            AVNumberOfChannelsKey: fmt.channelCount,
            AVLinearPCMBitDepthKey: 32,
            AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false,
        ]
        do {
            let file = try AVAudioFile(forWriting: url, settings: settings, commonFormat: fmt.commonFormat, interleaved: fmt.isInterleaved)
            writer = TimelineWriter(file: file, format: fmt, epoch: epoch)
        } catch {
            fail("could not create \(url.path): \(error)")
        }

        let status = AudioDeviceCreateIOProcIDWithBlock(&ioProcID, aggregateID, queue) { [weak self] _, inInputData, inInputTime, _, _ in
            guard let self, let writer = self.writer, let fmt = self.format else { return }
            guard let buffer = AVAudioPCMBuffer(pcmFormat: fmt, bufferListNoCopy: inInputData, deallocator: nil) else { return }
            let ts = inInputTime.pointee
            writer.write(buffer, hostTime: ts.mFlags.contains(.hostTimeValid) ? ts.mHostTime : nil)
        }
        check(status, "create IOProc")
        check(AudioDeviceStart(aggregateID, ioProcID), "start capture")
        log("teams-tap: recording process \(pid) to \(url.path)")
    }

    func stop() {
        guard !stopped else { return }
        stopped = true
        if let ioProcID {
            AudioDeviceStop(aggregateID, ioProcID)
            AudioDeviceDestroyIOProcID(aggregateID, ioProcID)
        }
        if aggregateID != kAudioObjectUnknown { AudioHardwareDestroyAggregateDevice(aggregateID) }
        if tapID != kAudioObjectUnknown { AudioHardwareDestroyProcessTap(tapID) }
        writer?.finish()                        // pad the tail up to the stop instant
        log("teams-tap: stopped, " + (writer?.summary ?? "nothing written"))
        writer = nil
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

/// Records the microphone to 48 kHz mono Float32 WAV. Uses AVAudioEngine because it notifies
/// configuration changes (Teams reconfigures the input device when it opens the microphone;
/// capture via ffmpeg/avfoundation stopped receiving frames at that moment) and because it
/// follows the system's default input when the user switches to a headset.
final class MicRecorder {
    let url: URL
    let deviceName: String
    let verbose: Bool
    let epoch: Double?
    private let engine = AVAudioEngine()
    private let outFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48000, channels: 1, interleaved: false)!
    private var writer: TimelineWriter?
    private var converter: AVAudioConverter?
    private var observer: NSObjectProtocol?
    private var restarts = 0
    private var stopped = false

    init(url: URL, deviceName: String, verbose: Bool, epoch: Double?) {
        self.url = url
        self.deviceName = deviceName
        self.verbose = verbose
        self.epoch = epoch
    }

    func start() {
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 48000.0, AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true, AVLinearPCMIsBigEndianKey: false, AVLinearPCMIsNonInterleaved: false,
        ]
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
        log("teams-tap: recording microphone (\(deviceName)) to \(url.path)")
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
    let mic = MicRecorder(url: args.out!, deviceName: micName, verbose: args.verbose, epoch: args.epoch)
    mic.start()
    stopAll = { mic.stop() }
} else {
    let recorder = ProcessTapRecorder(pid: args.pid, url: args.out!, verbose: args.verbose, waitAudioSeconds: args.waitAudioSeconds, includeDescendants: args.includeDescendants, epoch: args.epoch)
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
