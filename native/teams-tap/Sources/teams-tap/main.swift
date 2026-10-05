// teams-tap: captures the audio emitted by a process (e.g. Microsoft Teams) via
// Core Audio Process Tap (macOS 14.2+) and records it to WAV until it receives
// SIGINT/SIGTERM or until the target process exits.
//
// Usage: teams-tap --pid <pid> --out <file.wav> [--verbose]
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
            case "--help", "-h":
                print("Usage: teams-tap --pid <pid> --out <file.wav> [--wait-audio <s>] [--no-descendants] [--verbose]")
                print("       teams-tap --mic <default|name> --out <file.wav> [--verbose]   records the microphone (48 kHz mono), surviving format/device changes")
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

// MARK: - Recorder

final class ProcessTapRecorder {
    let pid: pid_t
    let url: URL
    let verbose: Bool
    let waitAudioSeconds: Double
    let includeDescendants: Bool

    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?
    private var file: AVAudioFile?
    private var format: AVAudioFormat?
    private let queue = DispatchQueue(label: "local.teams-recorder.teams-tap.io")
    private(set) var framesWritten: Int64 = 0
    private var stopped = false

    init(pid: pid_t, url: URL, verbose: Bool, waitAudioSeconds: Double, includeDescendants: Bool) {
        self.pid = pid
        self.url = url
        self.verbose = verbose
        self.waitAudioSeconds = waitAudioSeconds
        self.includeDescendants = includeDescendants
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
            file = try AVAudioFile(forWriting: url, settings: settings, commonFormat: fmt.commonFormat, interleaved: fmt.isInterleaved)
        } catch {
            fail("could not create \(url.path): \(error)")
        }

        let status = AudioDeviceCreateIOProcIDWithBlock(&ioProcID, aggregateID, queue) { [weak self] _, inInputData, _, _, _ in
            guard let self, let file = self.file, let fmt = self.format else { return }
            guard let buffer = AVAudioPCMBuffer(pcmFormat: fmt, bufferListNoCopy: inInputData, deallocator: nil) else { return }
            do {
                try file.write(from: buffer)
                self.framesWritten += Int64(buffer.frameLength)
            } catch {
                log("teams-tap: error writing audio: \(error)")
            }
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
        file = nil
        let seconds = format.map { Double(framesWritten) / $0.sampleRate } ?? 0
        log(String(format: "teams-tap: stopped, %.1f s recorded", seconds))
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
    private let engine = AVAudioEngine()
    private let outFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48000, channels: 1, interleaved: false)!
    private var file: AVAudioFile?
    private var converter: AVAudioConverter?
    private var observer: NSObjectProtocol?
    private(set) var framesWritten: Int64 = 0
    private var restarts = 0
    private var stopped = false

    init(url: URL, deviceName: String, verbose: Bool) {
        self.url = url
        self.deviceName = deviceName
        self.verbose = verbose
    }

    func start() {
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 48000.0, AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true, AVLinearPCMIsBigEndianKey: false, AVLinearPCMIsNonInterleaved: false,
        ]
        do {
            file = try AVAudioFile(forWriting: url, settings: settings, commonFormat: .pcmFormatFloat32, interleaved: false)
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
        input.installTap(onBus: 0, bufferSize: 4096, format: inFormat) { [weak self] buffer, _ in
            guard let self, let file = self.file, let converter = self.converter else { return }
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
            do {
                try file.write(from: out)
                self.framesWritten += Int64(out.frameLength)
            } catch {
                log("teams-tap: error writing microphone: \(error)")
            }
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
        file = nil
        log(String(format: "teams-tap: microphone stopped, %.1f s recorded, %d restart(s)", Double(framesWritten) / outFormat.sampleRate, restarts))
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
    let mic = MicRecorder(url: args.out!, deviceName: micName, verbose: args.verbose)
    mic.start()
    stopAll = { mic.stop() }
} else {
    let recorder = ProcessTapRecorder(pid: args.pid, url: args.out!, verbose: args.verbose, waitAudioSeconds: args.waitAudioSeconds, includeDescendants: args.includeDescendants)
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
