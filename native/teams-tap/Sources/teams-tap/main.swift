// teams-tap: captura o áudio emitido por um processo (ex.: Microsoft Teams) via
// Core Audio Process Tap (macOS 14.2+) e grava em WAV até receber SIGINT/SIGTERM
// ou até o processo alvo encerrar.
//
// Uso: teams-tap --pid <pid> --out <arquivo.wav> [--verbose]
// Saída: código 0 em sucesso; mensagens de erro em stderr.

import AVFoundation
import CoreAudio
import Foundation

// MARK: - Utilidades

func log(_ message: String) {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
}

func fail(_ message: String, code: Int32 = 1) -> Never {
    log("teams-tap: " + message)
    exit(code)
}

func check(_ status: OSStatus, _ what: String) {
    if status != noErr {
        fail("\(what) falhou (OSStatus \(status))")
    }
}

struct Arguments {
    var pid: pid_t = 0
    var out: URL?
    var verbose = false
    var waitAudioSeconds: Double = 20   // tempo para o processo alvo virar cliente de áudio
    var list = false                    // só lista os processos clientes de áudio e sai
    var includeDescendants = true       // inclui processos filhos do alvo (Teams toca áudio por um helper)

    static func parse(_ argv: [String]) -> Arguments {
        var args = Arguments()
        var it = argv.dropFirst().makeIterator()
        while let a = it.next() {
            switch a {
            case "--pid":
                guard let v = it.next(), let p = Int32(v) else { fail("--pid exige um número") }
                args.pid = p
            case "--out":
                guard let v = it.next() else { fail("--out exige um caminho") }
                args.out = URL(fileURLWithPath: v)
            case "--verbose", "-v":
                args.verbose = true
            case "--wait-audio":
                guard let v = it.next(), let secs = Double(v) else { fail("--wait-audio exige segundos") }
                args.waitAudioSeconds = secs
            case "--list":
                args.list = true
            case "--no-descendants":
                args.includeDescendants = false
            case "--help", "-h":
                print("Uso: teams-tap --pid <pid> --out <arquivo.wav> [--wait-audio <s>] [--no-descendants] [--verbose]")
                print("     teams-tap --list        lista os processos que são clientes de áudio (pid, pai, bundle, emitindo?)")
                exit(0)
            default:
                fail("argumento desconhecido: \(a)")
            }
        }
        if args.list { return args }
        guard args.pid > 0 else { fail("--pid é obrigatório") }
        guard args.out != nil else { fail("--out é obrigatório") }
        return args
    }
}

// MARK: - Processos de áudio

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

/// Todos os processos registrados no Core Audio (clientes de áudio).
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

/// Verdadeiro se `pid` é `root` ou descende dele (sobe pela cadeia de pais).
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
    print("pid\tppid\temitindo\tbundle")
    for p in procs {
        print("\(p.pid)\t\(parentPID(of: p.pid) ?? 0)\t\(p.isRunningOutput ? "sim" : "não")\t\(p.bundleID)")
    }
}

// MARK: - Gravador

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
        log("teams-tap: capturando \(targets.count) processo(s) de áudio: " + targets.map { "\($0.pid)\($0.bundleID.isEmpty ? "" : "[\($0.bundleID)]")" }.joined(separator: ", "))

        let tapDescription = CATapDescription(stereoMixdownOfProcesses: targets.map { $0.object })
        tapDescription.uuid = UUID()
        tapDescription.name = "teams-tap \(pid)"
        tapDescription.isPrivate = true
        tapDescription.muteBehavior = .unmuted
        check(AudioHardwareCreateProcessTap(tapDescription, &tapID), "criar process tap")
        if verbose { log("tap criado: \(tapID)") }

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
        check(AudioHardwareCreateAggregateDevice(description as CFDictionary, &aggregateID), "criar dispositivo agregado")
        if verbose { log("dispositivo agregado criado: \(aggregateID)") }

        var asbd = tapStreamFormat()
        guard let fmt = AVAudioFormat(streamDescription: &asbd) else { fail("formato do tap inválido") }
        format = fmt
        if verbose { log("formato: \(fmt.sampleRate) Hz, \(fmt.channelCount) canais, \(fmt.commonFormat.rawValue)") }

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
            fail("não consegui criar \(url.path): \(error)")
        }

        let status = AudioDeviceCreateIOProcIDWithBlock(&ioProcID, aggregateID, queue) { [weak self] _, inInputData, _, _, _ in
            guard let self, let file = self.file, let fmt = self.format else { return }
            guard let buffer = AVAudioPCMBuffer(pcmFormat: fmt, bufferListNoCopy: inInputData, deallocator: nil) else { return }
            do {
                try file.write(from: buffer)
                self.framesWritten += Int64(buffer.frameLength)
            } catch {
                log("teams-tap: erro ao escrever áudio: \(error)")
            }
        }
        check(status, "criar IOProc")
        check(AudioDeviceStart(aggregateID, ioProcID), "iniciar captura")
        log("teams-tap: gravando processo \(pid) em \(url.path)")
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
        log(String(format: "teams-tap: encerrado, %.1f s gravados", seconds))
    }

    // MARK: Core Audio helpers

    /// Processos de áudio que são o alvo ou descendem dele. O Teams (Electron) toca o som por
    /// um processo auxiliar, não pelo principal; e pode levar alguns segundos entre o início da
    /// chamada e a inicialização do áudio. Espera até existir ao menos um.
    private func matchingAudioProcesses() -> [AudioProcess] {
        audioProcesses().filter { $0.pid == pid || (includeDescendants && isDescendant($0.pid, of: pid)) }
    }

    private func waitForAudioClients() -> [AudioProcess] {
        let deadline = Date().addingTimeInterval(waitAudioSeconds)
        var attempt = 0
        while true {
            attempt += 1
            if kill(pid, 0) != 0 { fail("processo \(pid) não existe") }
            let found = matchingAudioProcesses()
            if !found.isEmpty {
                if attempt > 1 { log("teams-tap: áudio do processo \(pid) disponível após \(attempt) tentativas") }
                return found
            }
            if Date() >= deadline { fail("processo \(pid) (e descendentes) sem cliente de áudio após \(Int(waitAudioSeconds)) s") }
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
        check(AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &deviceID), "obter saída padrão")

        address.mSelector = kAudioDevicePropertyDeviceUID
        var uid: CFString = "" as CFString
        size = UInt32(MemoryLayout<CFString>.size)
        let status = withUnsafeMutablePointer(to: &uid) { ptr in
            AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, ptr)
        }
        check(status, "obter UID da saída padrão")
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
        check(AudioObjectGetPropertyData(tapID, &address, 0, nil, &size, &asbd), "ler formato do tap")
        return asbd
    }
}

// MARK: - main

let args = Arguments.parse(CommandLine.arguments)

if args.list {
    listAudioProcesses()
    exit(0)
}

let recorder = ProcessTapRecorder(pid: args.pid, url: args.out!, verbose: args.verbose, waitAudioSeconds: args.waitAudioSeconds, includeDescendants: args.includeDescendants)
recorder.start()

// Encerramento limpo por sinal.
signal(SIGINT, SIG_IGN)
signal(SIGTERM, SIG_IGN)
let signalSources: [DispatchSourceSignal] = [SIGINT, SIGTERM].map { sig in
    let source = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    source.setEventHandler {
        recorder.stop()
        exit(0)
    }
    source.resume()
    return source
}

// Encerra sozinho se o processo alvo morrer.
let watchdog = DispatchSource.makeTimerSource(queue: .main)
watchdog.schedule(deadline: .now() + 1, repeating: 1)
watchdog.setEventHandler {
    if kill(args.pid, 0) != 0 {
        log("teams-tap: processo \(args.pid) encerrou")
        recorder.stop()
        exit(0)
    }
}
watchdog.resume()

dispatchMain()
