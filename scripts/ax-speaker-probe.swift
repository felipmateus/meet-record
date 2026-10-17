// ax-speaker-probe.swift — spike for option A of docs/SPEAKER-ATTRIBUTION.md (speaker attribution
// from the Teams UI through the macOS Accessibility API). Not wired to the pipeline.
//
// Run it DURING a Teams call where other people talk, from a terminal that has Accessibility
// permission (System Settings > Privacy & Security > Accessibility; the first run asks for it):
//
//     swift scripts/ax-speaker-probe.swift [seconds] [out.jsonl] [--all] [--tree] [--watch] [--window <part of its title>]
//
// It lists the Teams windows and polls their accessibility trees twice a second. Only call windows
// are logged: those showing a participant tile ("Vídeo de …" / "Video of …"), the waiting message or
// the leave button, plus the compact meeting view (the small window Teams keeps on top when the
// meeting window loses focus); --window forces one window by a part of its title.
//
// What gets logged, one JSON line each:
//   default  every element seen for the first time whose text mentions a tile, speaking or muted
//            state (English and Portuguese) or whose DOM classes mention speaking or muting;
//   --all    every text of the call window, the first time it is seen;
//   --tree   the whole tree of the call window once, with depth, role, subrole, text, DOM id and DOM
//            classes (Chromium exposes AXDOMIdentifier and AXDOMClassList), then --watch;
//   --watch  every TRANSITION: an element whose text or DOM classes differ from the previous pass,
//            with what was added and removed (a tile's frame changing classes when its participant
//            speaks shows up here, as many times as it flips). The clock texts (mm:ss) are skipped.
// Table rows (chat lists) and texts over 200 characters (messages) are never logged. Each line
// carries the wall-clock time, so it can be aligned with a recording's epoch. The output stays on
// this Mac and contains participant names; keep it out of git.
//
// KEEP THE CALL WINDOW VISIBLE while the probe runs (next to the terminal, not behind it): Chromium
// only updates the accessibility tree of a page that is being rendered, and a fully covered window
// is not, so its tree freezes (run 6: not even the meeting timer changed in 60 s; run 7, window
// visible: the timer changed every second).
//
// Runs so far (2026-10-16, see docs/SPEAKER-ATTRIBUTION.md §6): Teams answers kAXErrorNotImplemented
// (-25208) for AXEnhancedUserInterface, yet the web content, DOM ids and classes are exposed as soon
// as the tree is read. The own tile is an AXImage "Vídeo de mim mesmo, <name>, …, Mudo desativado,
// Tem menu de contexto"; a remote tile is an AXMenuItem "<name>, …, O menu de contexto está
// disponível" with the name as AXStaticText inside and, as last child, an empty group whose classes
// changed once while the remote participant talked.
import Cocoa
import ApplicationServices

var logAll = false
var dumpTree = false
var watch = false
var windowFilter: String? = nil
var positional: [String] = []
var arguments = CommandLine.arguments.dropFirst().makeIterator()
while let argument = arguments.next() {
    if argument == "--all" { logAll = true }
    else if argument == "--tree" { dumpTree = true; watch = true }
    else if argument == "--watch" { watch = true }
    else if argument == "--window" { windowFilter = arguments.next()?.lowercased() }
    else { positional.append(argument) }
}
let seconds = positional.count > 0 ? (Double(positional[0]) ?? 60) : 60
let outPath = positional.count > 1 ? positional[1] : "ax-speaker-probe.jsonl"

let stateWords = ["speaking", "falando", "talking", "muted", "mudo", "mute", "unmute"]
let classWords = ["speak", "talk", "dominant", "mute"]
let tileMarkers = ["vídeo de ", "video of ", "menu de contexto", "context menu"]
let callMarkers = ["vídeo de ", "video of ", "sair da reunião", "sair da chamada", "leave meeting", "leave call", "aguardando o ingresso", "waiting for others"]
let callTitles = ["modo de exibição compacto", "compact view", "compact meeting"]   // the floating meeting window
let skippedRoles: Set<String> = ["AXTable", "AXRow"]   // chat lists
let maxTextLength = 200
let maxTreeLines = 4000
let teamsBundle = "com.microsoft.teams2"

func attr(_ el: AXUIElement, _ name: String) -> AnyObject? {
    var value: CFTypeRef?
    return AXUIElementCopyAttributeValue(el, name as CFString, &value) == .success ? value : nil
}

func text(_ el: AXUIElement) -> String {
    [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute, kAXHelpAttribute]
        .compactMap { attr(el, $0) as? String }
        .filter { !$0.isEmpty }
        .joined(separator: " | ")
}

func classes(_ el: AXUIElement) -> [String] {
    if let list = attr(el, "AXDOMClassList") as? [String] { return list }
    if let one = attr(el, "AXDOMClassList") as? String, !one.isEmpty { return [one] }
    return []
}

/// The participant's name in a tile's text: "Vídeo de mim mesmo, <name>, …" → <name>; "<name>, Tem controle…" → <name>.
func tileName(_ t: String) -> String {
    let parts = t.components(separatedBy: " | ")[0].components(separatedBy: ", ").map { $0.trimmingCharacters(in: .whitespaces) }
    guard let first = parts.first else { return t }
    let lower = first.lowercased()
    if (lower.hasPrefix("vídeo de") || lower.hasPrefix("video of")) && parts.count > 1 { return parts[1] }
    return first
}

func isClock(_ t: String) -> Bool {
    !t.isEmpty && t.contains(":") && t.allSatisfy { $0.isNumber || $0 == ":" }
}

let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
guard AXIsProcessTrustedWithOptions(options) else {
    print("This process has no Accessibility permission. Grant it to your terminal under System Settings > Privacy & Security > Accessibility, then run again.")
    exit(1)
}
guard let teams = NSRunningApplication.runningApplications(withBundleIdentifier: teamsBundle).first else {
    print("Teams (\(teamsBundle)) is not running.")
    exit(1)
}

let app = AXUIElementCreateApplication(teams.processIdentifier)
let enhanced = AXUIElementSetAttributeValue(app, "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)
print("AXEnhancedUserInterface on Teams (pid \(teams.processIdentifier)): \(enhanced == .success ? "set" : "not accepted (\(enhanced.rawValue)); the tree is exposed anyway once it is read")")
usleep(1_500_000)

let clock = ISO8601DateFormatter()
clock.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
FileManager.default.createFile(atPath: outPath, contents: nil)
guard let out = FileHandle(forWritingAtPath: outPath) else { print("cannot write \(outPath)"); exit(1) }

func emit(_ record: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: record), let line = String(data: data, encoding: .utf8) else { return }
    out.write((line + "\n").data(using: .utf8)!)
}

struct Node {
    let path: String       // child indices from the window, a stable identity across passes
    let tile: String       // the participant whose tile contains this element, when known
    let depth: Int
    let role: String
    let subrole: String
    let text: String
    let domId: String
    let classes: [String]

    var key: String { "\(role)\u{1}\(text)\u{1}\(domId)\u{1}\(classes.joined(separator: " "))" }

    func record(time: String, window: String) -> [String: Any] {
        var r: [String: Any] = ["t": time, "window": window, "role": role, "depth": depth, "path": path]
        if !tile.isEmpty { r["tile"] = tile }
        if !subrole.isEmpty { r["subrole"] = subrole }
        if !text.isEmpty { r["text"] = text }
        if !domId.isEmpty { r["id"] = domId }
        if !classes.isEmpty { r["classes"] = classes }
        return r
    }

    var line: String {
        var s = "[\(role)\(subrole.isEmpty ? "" : "/" + subrole)]"
        if !text.isEmpty { s += " \(text.prefix(120))" }
        if !domId.isEmpty { s += " #\(domId)" }
        if !classes.isEmpty { s += " ." + classes.joined(separator: " .") }
        return s
    }
}

var roles: [String: Int] = [:]
var visited = 0

func collect(_ el: AXUIElement, path: String, depth: Int, tile: String, into nodes: inout [Node]) {
    if depth > 40 || visited > 60_000 { return }
    visited += 1
    let role = (attr(el, kAXRoleAttribute) as? String) ?? "?"
    roles[role, default: 0] += 1
    if skippedRoles.contains(role) { return }
    let t = text(el)
    let lower = t.lowercased()
    let isTile = role == "AXMenuItem" || tileMarkers.contains { lower.contains($0) }
    let myTile = isTile && !t.isEmpty ? tileName(t) : tile
    nodes.append(Node(path: path, tile: myTile, depth: depth, role: role, subrole: (attr(el, kAXSubroleAttribute) as? String) ?? "",
                      text: t, domId: (attr(el, "AXDOMIdentifier") as? String) ?? "", classes: classes(el)))
    if let children = attr(el, kAXChildrenAttribute) as? [AXUIElement] {
        for (i, child) in children.enumerated() { collect(child, path: "\(path)/\(i)", depth: depth + 1, tile: myTile, into: &nodes) }
    }
}

func isCallWindow(title: String, nodes: [Node]) -> Bool {
    if let filter = windowFilter { return title.lowercased().contains(filter) }
    if callTitles.contains(where: { title.lowercased().contains($0) }) { return true }
    return nodes.contains { node in let lower = node.text.lowercased(); return callMarkers.contains { lower.contains($0) } }
}

func worthLogging(_ node: Node) -> Bool {
    if node.text.count > maxTextLength { return false }
    if logAll { return !node.text.isEmpty }
    let lower = node.text.lowercased()
    let classText = node.classes.joined(separator: " ").lowercased()
    return tileMarkers.contains { lower.contains($0) } || stateWords.contains { lower.contains($0) } || classWords.contains { classText.contains($0) }
}

var seen: [String: String] = [:]          // window + node key -> first time seen (first-sight logging)
var previous: [String: Node] = [:]        // window + path -> the node in the previous pass (transition logging)
var transitions = 0
var changesAfterFirstPass = 0
let deadline = Date().addingTimeInterval(seconds)
var passes = 0
while Date() < deadline {
    let now = clock.string(from: Date())
    visited = 0
    var callWindows = 0
    if let windows = attr(app, kAXWindowsAttribute) as? [AXUIElement] {
        if passes == 0 { print("Teams windows: \(windows.count)") }
        for window in windows {
            let title = (attr(window, kAXTitleAttribute) as? String) ?? ""
            var nodes: [Node] = []
            collect(window, path: "", depth: 0, tile: "", into: &nodes)
            let call = isCallWindow(title: title, nodes: nodes)
            if passes == 0 { print("  window: \(title)  [\(call ? "call window, logged" : "not a call window, skipped")]") }
            guard call else { continue }
            callWindows += 1
            if passes == 0 && dumpTree {
                let r = AXUIElementSetAttributeValue(window, "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)
                print("AXEnhancedUserInterface on the window: \(r == .success ? "set" : "not accepted (\(r.rawValue))")")
                let withClasses = nodes.filter { !$0.classes.isEmpty || !$0.domId.isEmpty }.count
                print("elements with DOM id or classes: \(withClasses) of \(nodes.count)\(withClasses == 0 ? " (none: the tree is in basic mode; names and roles only)" : "")")
                print("--- tree of the call window (\(nodes.count) elements) ---")
                for node in nodes.prefix(maxTreeLines) {
                    print(String(repeating: "  ", count: node.depth) + node.line)
                    var r = node.record(time: now, window: title); r["tree"] = true
                    emit(r)
                }
                print("--- end of tree; changes follow ---")
            }
            // First-sight logging (default and --all modes).
            if !watch || logAll {
                for node in nodes where worthLogging(node) {
                    let key = "\(title)\u{1}\(node.key)"
                    if seen[key] == nil {
                        if passes > 0 { changesAfterFirstPass += 1 }
                        if !(passes == 0 && dumpTree) {
                            emit(node.record(time: now, window: title))
                            print("\(now)  \(node.line.prefix(220))")
                        }
                    }
                    seen[key] = now
                }
            }
            // Transition logging (--watch and --tree): the same element, by path, with other text or classes.
            if watch {
                for node in nodes {
                    let id = "\(title)\u{1}\(node.path)"
                    defer { previous[id] = node }
                    guard let before = previous[id], before.key != node.key else { continue }
                    if isClock(node.text) || isClock(before.text) { continue }
                    if node.text.count > maxTextLength { continue }
                    transitions += 1
                    changesAfterFirstPass += 1
                    let added = node.classes.filter { !before.classes.contains($0) }
                    let removed = before.classes.filter { !node.classes.contains($0) }
                    var r = node.record(time: now, window: title)
                    r["transition"] = true
                    if before.text != node.text { r["prev_text"] = before.text }
                    if !added.isEmpty { r["added"] = added }
                    if !removed.isEmpty { r["removed"] = removed }
                    emit(r)
                    let windowTag = callTitles.contains(where: { title.lowercased().contains($0) }) ? "compact" : "main"
                    var line = "\(now)  Δ \(windowTag)"
                    if added.contains("vdi-frame-occlusion") { line += " SPEAKING" } else if removed.contains("vdi-frame-occlusion") { line += " silent  " }
                    if !node.tile.isEmpty { line += " [\(node.tile)]" }
                    line += " [\(node.role)] \(node.text.prefix(80))"
                    if before.text != node.text { line += "  (was: \(before.text.prefix(60)))" }
                    if !added.isEmpty { line += "  +\(added.joined(separator: " +"))" }
                    if !removed.isEmpty { line += "  -\(removed.joined(separator: " -"))" }
                    print(line.prefix(300))
                }
            }
        }
    }
    if passes == 0 {
        print("first pass: \(visited) elements; roles: " + roles.sorted { $0.value > $1.value }.prefix(12).map { "\($0.key)=\($0.value)" }.joined(separator: ", "))
        if roles["AXWebArea"] == nil { print("no AXWebArea seen: the web content is not exposed; check the permission and that Teams shows a window") }
        if callWindows == 0 { print("no call window found: join the call first, or pass --window <part of the meeting window's title>") }
    }
    passes += 1
    usleep(500_000)
}

_ = AXUIElementSetAttributeValue(app, "AXEnhancedUserInterface" as CFString, kCFBooleanFalse)
out.closeFile()
print("done: \(passes) passes, \(seen.count) distinct elements seen, \(transitions) transitions, logged to \(outPath)")
if changesAfterFirstPass == 0 && passes > 20 {
    print("nothing changed after the first pass: if people talked, the call window was probably covered; keep it visible next to the terminal and run again")
}
