#!/usr/bin/env swift
// Trigger macOS TCC permission prompts for the running process (Terminal, Python, etc.).
// Usage: swift scripts/trigger-tcc.swift [--files] [--automation]
import ApplicationServices
import CoreGraphics
import Foundation

let args = Set(CommandLine.arguments.dropFirst())
let home = FileManager.default.homeDirectoryForCurrentUser.path

// 1. Accessibility (shows system dialog)
let axOpts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
let axTrusted = AXIsProcessTrustedWithOptions(axOpts)
fputs("Accessibility: \(axTrusted ? "already granted" : "prompt shown — enable in Settings if asked")\n", stderr)

// 2. Post Event / keystroke synthesis (macOS 15+)
let postGranted = CGPreflightPostEventAccess()
if !postGranted {
    CGRequestPostEventAccess()
    fputs("Post Event: prompt registered — check Accessibility → Post Event\n", stderr)
} else {
    fputs("Post Event: already granted\n", stderr)
}

// 3. Protected folder access (Files and Folders prompts)
if args.contains("--files") {
    let probes = [
        home + "/Desktop",
        home + "/Documents",
        home + "/Downloads",
        home + "/Library/Application Support/Cursor",
    ]
    for path in probes {
        var isDir: ObjCBool = false
        if FileManager.default.fileExists(atPath: path, isDirectory: &isDir) {
            _ = try? FileManager.default.contentsOfDirectory(atPath: path)
            fputs("Files probe: \(path)\n", stderr)
        }
    }
}

// 4. Automation (Apple Events — "X wants to control Y")
if args.contains("--automation") {
    let script = """
    tell application "System Events"
        try
            get name of first process whose frontmost is true
        end try
    end tell
    try
        tell application "Cursor" to get name
    end try
    """
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    proc.arguments = ["-e", script]
    try? proc.run()
    proc.waitUntilExit()
    fputs("Automation: Apple Events sent (approve if prompted)\n", stderr)
}

print("ok")
