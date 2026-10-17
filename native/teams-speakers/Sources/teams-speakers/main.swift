// teams-speakers: reads the Microsoft Teams meeting windows through the macOS Accessibility API
// and appends one JSON line per event (who is on screen, who is speaking) to a file the recorder
// reads after the call (docs/tasks/speaker-attribution/_spec.md, ADR-001).
//
// Usage: teams-speakers --out <speakers.jsonl> --epoch <unix s> [--interval 0.5] [--bundle com.microsoft.teams2] [--verbose]
//        teams-speakers --check [--prompt]
// Exit codes: 0 stopped normally (or permission granted) | 2 bad arguments | 3 Accessibility permission missing
//             | 4 the output file could not be written.
//
// What it reads: a participant tile is an AXMenuItem whose text mentions the context menu; the own
// tile is an AXImage "Vídeo de mim mesmo, <name>, ...". A remote participant is speaking while any
// direct child of the tile (its frame element) has "vdi-frame-occlusion" in AXDOMClassList. The tree
// only updates while a Teams window is rendered, so a fully covered window stops reporting; the
// compact view Teams keeps on top counts as a call window too. A window whose call timer text (the
// element with DOM id "call-duration-custom") has not changed for 3 s is "frozen": its open speaking
// states close first, and its tiles are not read again until the timer moves. A "heartbeat" event every
// 5 s tells the reader the helper is alive, so a turn left open by a dead helper or a frozen window
// ends at the last sign of life instead of being credited to the speaker for the rest of the meeting.
//
// Read-only: this file only reads attributes. It never sets focus, an attribute or a value on any
// element (safety invariant 4; a unit test and scripts/build-native.sh grep the sources for the
// attribute-setting call). Every event line is written with a single write(2) on an O_APPEND file
// descriptor, so it is readable by other processes the moment it is written and survives a SIGKILL.
// Logs go to stderr with timestamps; the spawner redirects them to data/log/speakers.log.
import Cocoa
import ApplicationServices

// MARK: - Constants

let tool = "teams-speakers"
let frameClass = "vdi-frame-occlusion"                     // ADR-001: the tile frame's speaking class set
let eventsVersion = 1
let defaultBundle = "com.microsoft.teams2"
let defaultInterval = 0.5
let permissionPath = "System Settings > Privacy & Security > Accessibility"
let tileContextMarkers = ["menu de contexto", "context menu"]
let ownTileMarkers = ["vídeo de mim mesmo", "video of myself"]
let callMarkers = ["sair da reunião", "sair da chamada", "leave meeting", "leave call", "aguardando o ingresso", "waiting for others"]
let imageCallMarkers = ["vídeo de ", "video of "]            // only on images (the tiles' video): in a chat they match any message or file name
let compactTitles = ["modo de exibição compacto", "compact view", "compact meeting"]   // the floating meeting window
let skippedRoles: Set<String> = ["AXTable", "AXRow"]       // chat lists
let maxMarkerTextLength = 200
let maxDepth = 40
let maxElementsPerWindow = 60_000
let slowPassSeconds = 1.0
let lostAfterPasses = 3                                     // passes a window may be missing before it counts as lost
let noWindowAfterSeconds = 30.0
let heartbeatSeconds = 5.0                                  // between "heartbeat" events: the reader's proof that the helper is alive
let frozenAfterSeconds = 3.0                                // a call timer unchanged this long means the window is not being rendered
let callTimerDomId = "call-duration-custom"                 // the call timer element's DOM id (spike run 7)
let reportEverySeconds = 60.0
let axMessagingTimeout: Float = 2.0                         // seconds an unresponsive Teams may hold one read

// MARK: - Logging

let stampFormatter: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    f.timeZone = TimeZone.current
    return f
}()

func log(_ message: String) {
    let line = "\(stampFormatter.string(from: Date())) \(tool): \(message)\n"
    FileHandle.standardError.write(line.data(using: .utf8)!)
}

func fail(_ message: String, code: Int32) -> Never {
    log(message)
    exit(code)
}

// MARK: - Arguments

struct Arguments {
    var out: String?
    var epoch: Double?
    var interval = defaultInterval
    var bundle = defaultBundle
    var verbose = false
    var check = false
    var prompt = false
}

let usage = """
Usage: \(tool) --out <speakers.jsonl> --epoch <unix s> [--interval 0.5] [--bundle com.microsoft.teams2] [--verbose]
       \(tool) --check [--prompt]
"""

func usageError(_ message: String) -> Never {
    FileHandle.standardError.write("\(tool): \(message)\n\(usage)\n".data(using: .utf8)!)
    exit(2)
}

func parseArguments(_ argv: [String]) -> Arguments {
    var args = Arguments()
    var it = argv.dropFirst().makeIterator()
    while let a = it.next() {
        switch a {
        case "--out":
            guard let v = it.next() else { usageError("--out requires a path") }
            args.out = v
        case "--epoch":
            guard let v = it.next(), let e = Double(v), e.isFinite else { usageError("--epoch requires Unix seconds") }
            args.epoch = e
        case "--interval":
            guard let v = it.next(), let i = Double(v), i >= 0.1, i <= 60 else { usageError("--interval requires seconds between 0.1 and 60") }
            args.interval = i
        case "--bundle":
            guard let v = it.next(), !v.isEmpty else { usageError("--bundle requires a bundle identifier") }
            args.bundle = v
        case "--verbose", "-v":
            args.verbose = true
        case "--check":
            args.check = true
        case "--prompt":
            args.prompt = true
        case "--help", "-h":
            print(usage)
            exit(0)
        default:
            usageError("unknown argument: \(a)")
        }
    }
    if args.prompt && !args.check { usageError("--prompt only goes with --check") }
    if args.check { return args }
    if args.out == nil { usageError("--out is required") }
    if args.epoch == nil { usageError("--epoch is required") }
    return args
}

// MARK: - Permission

func accessibilityTrusted(prompt: Bool) -> Bool {
    if !prompt { return AXIsProcessTrusted() }
    let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    return AXIsProcessTrustedWithOptions(options)
}

let args = parseArguments(CommandLine.arguments)

if args.check {
    if accessibilityTrusted(prompt: args.prompt) {
        print("Accessibility permission: granted")
        exit(0)
    }
    if args.prompt {
        print("Accessibility permission: missing. Allow \(tool) under \(permissionPath), then run --check again.")
    } else {
        print("Accessibility permission: missing. Run with --prompt to request it, then allow \(tool) under \(permissionPath).")
    }
    exit(3)
}

guard accessibilityTrusted(prompt: false) else {
    fail("Accessibility permission missing; run \(tool) --check --prompt and allow \(tool) under \(permissionPath)", code: 3)
}

// MARK: - Event writer

let outPath = args.out!
let epoch = args.epoch!
let outFd = open(outPath, O_WRONLY | O_CREAT | O_APPEND, 0o644)
if outFd < 0 { fail("cannot write \(outPath): \(String(cString: strerror(errno)))", code: 4) }

enum J {
    case s(String), i(Int), d(Double), b(Bool), null
}

func encode(_ value: J) -> String {
    switch value {
    case .s(let s):
        let data = try? JSONSerialization.data(withJSONObject: s, options: [.fragmentsAllowed, .withoutEscapingSlashes])
        return data.flatMap { String(data: $0, encoding: .utf8) } ?? "\"\""
    case .i(let i): return String(i)
    case .d(let d): return d.description            // the shortest text that reads back as the same number
    case .b(let b): return b ? "true" : "false"
    case .null: return "null"
    }
}

func appendLine(_ line: String) {
    let bytes = Array((line + "\n").utf8)
    var offset = 0
    while offset < bytes.count {
        let written = bytes[offset...].withUnsafeBytes { write(outFd, $0.baseAddress, $0.count) }
        if written < 0 {
            if errno == EINTR { continue }
            fail("cannot write \(outPath): \(String(cString: strerror(errno)))", code: 4)
        }
        offset += written
    }
}

func emit(_ event: String, _ fields: [(String, J)] = []) {
    var parts = ["\"t\":" + String(format: "%.3f", Date().timeIntervalSince1970), "\"event\":" + encode(.s(event))]
    for (key, value) in fields { parts.append(encode(.s(key)) + ":" + encode(value)) }
    appendLine("{" + parts.joined(separator: ",") + "}")
}

// MARK: - Counters and signals

var passes = 0
var transitions = 0
var axErrors = 0
var slowPasses = 0
var errorsThisMinute = 0
var stopSignal: Int32 = 0

signal(SIGINT) { sig in stopSignal = sig }
signal(SIGTERM) { sig in stopSignal = sig }

// MARK: - Accessibility reads (read-only)

func attr(_ el: AXUIElement, _ name: String) -> AnyObject? {
    var value: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(el, name as CFString, &value)
    if result == .success { return value }
    switch result {
    case .noValue, .attributeUnsupported, .notImplemented:
        break                                       // the element just has no such attribute
    default:
        axErrors += 1
        errorsThisMinute += 1
    }
    return nil
}

func text(_ el: AXUIElement) -> String {
    [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute, kAXHelpAttribute]
        .compactMap { attr(el, $0) as? String }
        .filter { !$0.isEmpty }
        .joined(separator: " | ")
}

func classes(_ el: AXUIElement) -> [String] {
    let value = attr(el, "AXDOMClassList")
    if let list = value as? [String] { return list }
    if let one = value as? String, !one.isEmpty { return [one] }
    return []
}

func children(_ el: AXUIElement) -> [AXUIElement] {
    (attr(el, kAXChildrenAttribute) as? [AXUIElement]) ?? []
}

/// The texts of the AXStaticText elements under a tile: one of them is the display name.
func staticTexts(_ el: AXUIElement, depth: Int, into out: inout [String]) {
    if depth > 6 { return }
    if (attr(el, kAXRoleAttribute) as? String) == "AXStaticText" {
        let t = text(el)
        if !t.isEmpty { out.append(t) }
    }
    for child in children(el) { staticTexts(child, depth: depth + 1, into: &out) }
}

/// The display name at the start of a tile's text ("<name>, Tem controle…, O menu de contexto…"). A static
/// text under the tile that the description starts with wins (names may contain a comma); else the text up to
/// the first comma.
func pickName(_ description: String, candidates: [String]) -> String {
    let matching = candidates.filter { description == $0 || description.hasPrefix($0 + ",") }
    if let best = matching.max(by: { $0.count < $1.count }) { return best }
    return (description.components(separatedBy: ", ")[0]).trimmingCharacters(in: .whitespaces)
}

var nameCache: [String: String] = [:]               // tile text -> display name (a tile's text rarely changes)

func tileName(_ el: AXUIElement, description: String) -> String {
    if let cached = nameCache[description] { return cached }
    var candidates: [String] = []
    staticTexts(el, depth: 0, into: &candidates)
    let name = pickName(description, candidates: candidates)
    if nameCache.count < 5_000 { nameCache[description] = name }
    return name
}

struct Tile {
    let name: String
    var me: Bool
    var speaking: Bool
}

final class Scan {
    var tiles: [Tile] = []
    var callMarker = false
    var timer: String?          // the call timer's text, when the window shows one
    var elements = 0
    private var index: [String: Int] = [:]

    func add(name: String, me: Bool, speaking: Bool) {
        if name.isEmpty { return }
        if let i = index[name] {
            tiles[i].me = tiles[i].me || me
            tiles[i].speaking = tiles[i].speaking || speaking
        } else {
            index[name] = tiles.count
            tiles.append(Tile(name: name, me: me, speaking: speaking))
        }
    }
}

func walk(_ el: AXUIElement, depth: Int, scan: Scan) {
    if stopSignal != 0 || depth > maxDepth || scan.elements > maxElementsPerWindow { return }
    scan.elements += 1
    let role = (attr(el, kAXRoleAttribute) as? String) ?? "?"
    if skippedRoles.contains(role) { return }
    let t = text(el)
    // Markers are matched on the first " | " part only: a tile's text repeats its title and description, which
    // together pass 200 characters (219 and 255 in the 2026-10-16 spike), while each part stays near 110.
    let firstPart = t.components(separatedBy: " | ")[0]
    let lower = firstPart.count <= maxMarkerTextLength ? firstPart.lowercased() : ""
    let kids = children(el)
    if role == "AXMenuItem" && !t.isEmpty && tileContextMarkers.contains(where: { lower.contains($0) }) {
        let head = t.components(separatedBy: " | ")[0]
        let speaking = kids.contains { classes($0).contains(frameClass) }
        scan.callMarker = true
        scan.add(name: tileName(el, description: head), me: false, speaking: speaking)
        return
    }
    if role == "AXImage", let marker = ownTileMarkers.first(where: { lower.hasPrefix($0) }) {
        let head = t.components(separatedBy: " | ")[0]
        let rest = String(head.dropFirst(marker.count)).trimmingCharacters(in: CharacterSet(charactersIn: ", "))
        scan.callMarker = true
        scan.add(name: tileName(el, description: rest), me: true, speaking: false)
        return
    }
    if !scan.callMarker && (callMarkers.contains(where: { lower.contains($0) })
        || (role == "AXImage" && imageCallMarkers.contains(where: { lower.contains($0) }))) { scan.callMarker = true }
    if scan.timer == nil && (attr(el, "AXDOMIdentifier") as? String) == callTimerDomId {
        // the timer's text sits on the element or on a static text under it
        var parts: [String] = []
        if !t.isEmpty { parts.append(t) }
        staticTexts(el, depth: 0, into: &parts)
        if !parts.isEmpty { scan.timer = parts.joined(separator: " | ") }   // no text: nothing to judge by, so no freeze can follow
    }
    for child in kids { walk(child, depth: depth + 1, scan: scan) }
}

// MARK: - Window state

func isCompact(title: String) -> Bool {
    let lower = title.lowercased()
    return compactTitles.contains { lower.contains($0) }
}

/// The meeting subject in a Teams window title: its first " | " part, the second for the compact view.
func subject(title: String, compact: Bool) -> String? {
    let parts = title.components(separatedBy: " | ").map { $0.trimmingCharacters(in: .whitespaces) }
    let index = compact ? 1 : 0
    return parts.count > index && !parts[index].isEmpty ? parts[index] : nil
}

final class WindowState {
    var title: String
    var misses = 0
    var seen: Set<String> = []
    var present: Set<String> = []
    var speaking: Set<String> = []
    var timer: String?                  // the call timer's last text, and when it last changed
    var timerChangedAt = Date()
    var frozen = false                  // the timer stood still: the tree is not being rendered
    init(title: String) { self.title = title }
}

var states: [String: WindowState] = [:]             // by window kind: "main" or "compact"
var lastSubject: String?

func noteSubject(title: String, kind: String) {
    guard let s = subject(title: title, compact: kind == "compact"), s != lastSubject else { return }
    lastSubject = s
    emit("title", [("subject", .s(s))])
    log("meeting subject: \(s)")
}

func setSpeaking(_ kind: String, _ state: WindowState, _ name: String, _ on: Bool) {
    if on == state.speaking.contains(name) { return }
    if on { state.speaking.insert(name) } else { state.speaking.remove(name) }
    transitions += 1
    emit("speaking", [("name", .s(name)), ("speaking", .b(on)), ("window", .s(kind))])
    log("\(on ? "speaking" : "silent"): \(name) (\(kind))")
}

func apply(_ kind: String, title: String, scan: Scan) {
    let state: WindowState
    if let existing = states[kind] {
        state = existing
        state.misses = 0
        if title != state.title {
            state.title = title
            noteSubject(title: title, kind: kind)
        }
    } else {
        state = WindowState(title: title)
        states[kind] = state
        emit("window", [("kind", .s(kind)), ("state", .s("found")), ("title", .s(title))])
        log("window found (\(kind)): \(title)")
        noteSubject(title: title, kind: kind)
    }
    if !trackTimer(kind, state, scan: scan) { return }
    var present = Set<String>()
    for tile in scan.tiles {
        present.insert(tile.name)
        if !state.seen.contains(tile.name) {
            state.seen.insert(tile.name)
            emit("seen", [("name", .s(tile.name)), ("me", .b(tile.me)), ("window", .s(kind))])
            log("tile seen: \(tile.name)\(tile.me ? " (me)" : "") (\(kind))")
        }
        if !tile.me { setSpeaking(kind, state, tile.name, tile.speaking) }
    }
    for name in state.present.subtracting(present).sorted() {
        log("tile lost: \(name) (\(kind))")
        setSpeaking(kind, state, name, false)
    }
    state.present = present
}

/// Follows the call timer of a window. Returns false when the tiles of this pass must not be read: the window is
/// frozen (its tree is not being rendered, so its speaking states are stale), or it has just moved again and the
/// states are read from the next pass on.
func trackTimer(_ kind: String, _ state: WindowState, scan: Scan) -> Bool {
    let now = Date()
    guard let timer = scan.timer else {
        state.timer = nil                       // no timer in sight: nothing to judge by, so the window counts as live
        return thaw(kind, state)
    }
    if timer != state.timer {
        state.timer = timer
        state.timerChangedAt = now
        return thaw(kind, state)
    }
    if !state.frozen && now.timeIntervalSince(state.timerChangedAt) >= frozenAfterSeconds {
        for name in state.speaking.sorted() { setSpeaking(kind, state, name, false) }
        state.frozen = true
        emit("window", [("kind", .s(kind)), ("state", .s("frozen")), ("title", .s(state.title))])
        log("window frozen (\(kind)): the call timer has not changed for \(Int(frozenAfterSeconds)) s; the window is covered or not rendering")
    }
    return !state.frozen
}

/// A frozen window whose timer moved (or vanished) is found again; its tiles are read from the next pass.
func thaw(_ kind: String, _ state: WindowState) -> Bool {
    if !state.frozen { return true }
    state.frozen = false
    emit("window", [("kind", .s(kind)), ("state", .s("found")), ("title", .s(state.title))])
    log("window live again (\(kind)): the call timer moved")
    return false
}

func closeWindow(_ kind: String, _ state: WindowState) {
    for name in state.speaking.sorted() { setSpeaking(kind, state, name, false) }
    emit("window", [("kind", .s(kind)), ("state", .s("lost")), ("title", .s(state.title))])
    log("window lost (\(kind)): \(state.title)")
    states[kind] = nil
}

// MARK: - Teams process

var teamsPid: pid_t = 0
var teamsElement: AXUIElement?
var lastNotRunningLog = Date.distantPast

func resolveTeams() -> AXUIElement? {
    let running = NSRunningApplication.runningApplications(withBundleIdentifier: args.bundle).first { !$0.isTerminated }
    guard let app = running else {
        if teamsPid != 0 {
            log("Teams (pid \(teamsPid)) exited; waiting for it")
            teamsPid = 0
            teamsElement = nil
        }
        if Date().timeIntervalSince(lastNotRunningLog) >= reportEverySeconds {
            lastNotRunningLog = Date()
            log("Teams (\(args.bundle)) is not running; waiting")
        }
        return nil
    }
    if app.processIdentifier != teamsPid {
        teamsPid = app.processIdentifier
        teamsElement = AXUIElementCreateApplication(teamsPid)
        log("Teams pid \(teamsPid)")
    }
    return teamsElement
}

// MARK: - One pass

func scanPass(app: AXUIElement?) -> Int {
    var found: [String: (title: String, scan: Scan)] = [:]
    var markerOnly: (title: String, scan: Scan)?   // the first main window with a call marker and no tiles
    var elements = 0
    if let app = app, let windows = attr(app, kAXWindowsAttribute) as? [AXUIElement] {
        for window in windows {
            if stopSignal != 0 { return elements }
            let title = (attr(window, kAXTitleAttribute) as? String) ?? ""
            let kind = isCompact(title: title) ? "compact" : "main"
            if found[kind] != nil { continue }      // the compact view is found by its title; a main window with tiles is the best one there is
            let scan = Scan()
            walk(window, depth: 0, scan: scan)
            elements += scan.elements
            if stopSignal != 0 { return elements }  // a walk cut short by a signal must not close windows or tiles
            if kind == "compact" || !scan.tiles.isEmpty {
                found[kind] = (title, scan)
            } else if scan.callMarker && markerOnly == nil {
                markerOnly = (title, scan)          // not final: a window behind it may be the meeting, and a chat window can carry a marker word
            }
        }
    }
    if found["main"] == nil, let marked = markerOnly { found["main"] = marked }
    for kind in ["main", "compact"] {
        if let hit = found[kind] {
            apply(kind, title: hit.title, scan: hit.scan)
        } else if let state = states[kind] {
            state.misses += 1
            if state.misses >= lostAfterPasses { closeWindow(kind, state) }
        }
    }
    return elements
}

// MARK: - Run

emit("start", [
    ("epoch", .d(epoch)), ("interval", .d(args.interval)),
    ("teams_pid", NSRunningApplication.runningApplications(withBundleIdentifier: args.bundle).first.map { .i(Int($0.processIdentifier)) } ?? .null),
    ("version", .i(eventsVersion)),
])
let pidText = NSRunningApplication.runningApplications(withBundleIdentifier: args.bundle).first.map { "pid \($0.processIdentifier)" } ?? "not running yet"
log("Accessibility permission granted; watching Teams (\(pidText)) every \(args.interval) s; events → \(outPath)")
log("arguments: bundle=\(args.bundle) interval=\(args.interval) epoch=\(epoch) verbose=\(args.verbose)")

AXUIElementSetMessagingTimeout(AXUIElementCreateSystemWide(), axMessagingTimeout)

// A timer keeps the main run loop alive, so waiting in slices below blocks instead of spinning and
// NSRunningApplication stays current.
_ = Timer.scheduledTimer(withTimeInterval: 3600, repeats: true) { _ in }

func wait(_ seconds: Double) {
    let end = Date().addingTimeInterval(seconds)
    while stopSignal == 0 && Date() < end {
        RunLoop.main.run(until: min(end, Date().addingTimeInterval(0.05)))
    }
}

var lastCallWindowAt = Date()
var lastNoWindowLog = Date.distantPast
var lastReport = Date()
var lastHeartbeat = Date()

while stopSignal == 0 {
    let began = Date()
    let app = resolveTeams()
    let elements = scanPass(app: app)
    let seconds = Date().timeIntervalSince(began)
    if stopSignal != 0 { break }
    passes += 1
    if args.verbose { log("pass \(passes): \(elements) elements in \(String(format: "%.3f", seconds)) s") }
    if seconds > slowPassSeconds {
        slowPasses += 1
        log("slow pass: \(String(format: "%.2f", seconds)) s for \(elements) elements")
    }
    let now = Date()
    if !states.isEmpty {
        lastCallWindowAt = now
    } else if app != nil, now.timeIntervalSince(lastCallWindowAt) >= noWindowAfterSeconds, now.timeIntervalSince(lastNoWindowLog) >= reportEverySeconds {
        lastNoWindowLog = now
        log("no Teams meeting window found; waiting (\(Int(now.timeIntervalSince(lastCallWindowAt))) s without a call window with tiles)")
    }
    if now.timeIntervalSince(lastReport) >= reportEverySeconds {
        lastReport = now
        if errorsThisMinute > 0 { log("\(errorsThisMinute) accessibility errors in the last minute") }
        errorsThisMinute = 0
        if !AXIsProcessTrusted() { log("Accessibility permission lost; reads fail until it is granted again") }
    }
    if now.timeIntervalSince(lastHeartbeat) >= heartbeatSeconds {
        lastHeartbeat = now
        emit("heartbeat")
    }
    wait(args.interval)
}

emit("stop", [("reason", .s("signal")), ("passes", .i(passes)), ("transitions", .i(transitions)), ("ax_errors", .i(axErrors)), ("slow_passes", .i(slowPasses))])
log("stopping (signal); \(passes) passes, \(transitions) transitions, \(axErrors) accessibility errors, \(slowPasses) slow passes")
close(outFd)
exit(0)
