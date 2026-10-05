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
            case "--help", "-h":
                print("Uso: teams-tap --pid <pid> --out <arquivo.wav> [--verbose]")
                exit(0)
            default:
                fail("argumento desconhecido: \(a)")
            }
        }
        guard args.pid > 0 else { fail("--pid é obrigatório") }
        guard args.out != nil else { fail("--out é obrigatório") }
        return args
    }
}

// MARK: - Gravador

final class ProcessTapRecorder {
    let pid: pid_t
    let url: URL
    let verbose: Bool

    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?
    private var file: AVAudioFile?
    private var format: AVAudioFormat?
    private let queue = DispatchQueue(label: "local.teams-recorder.teams-tap.io")
    private(set) var framesWritten: Int64 = 0
    private var stopped = false

    init(pid: pid_t, url: URL, verbose: Bool) {
        self.pid = pid
        self.url = url
        self.verbose = verbose
    }

    func start() {
        let processObject = translatePID(pid)
        if verbose { log("processo \(pid) → AudioObjectID \(processObject)") }

        let tapDescription = CATapDescription(stereoMixdownOfProcesses: [processObject])
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

    private func translatePID(_ pid: pid_t) -> AudioObjectID {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyTranslatePIDToProcessObject,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var pidValue = pid
        var object = AudioObjectID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioObjectID>.size)
        let status = withUnsafeMutablePointer(to: &pidValue) { pidPtr in
            AudioObjectGetPropertyData(
                AudioObjectID(kAudioObjectSystemObject), &address,
                UInt32(MemoryLayout<pid_t>.size), pidPtr, &size, &object
            )
        }
        check(status, "traduzir PID \(pid) para objeto de áudio")
        guard object != kAudioObjectUnknown else { fail("processo \(pid) não existe ou não emite áudio") }
        return object
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

let recorder = ProcessTapRecorder(pid: args.pid, url: args.out!, verbose: args.verbose)
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
