import Cocoa
import WebKit

final class ReporterDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    private var panel: NSPanel!
    private var web: WKWebView!
    private var reporterURL: URL!

    private let terminalBundles = [
        "Apple_Terminal": "com.apple.Terminal", "iTerm.app": "com.googlecode.iterm2",
        "vscode": "com.microsoft.VSCode", "WarpTerminal": "dev.warp.Warp-Stable",
        "ghostty": "com.mitchellh.ghostty", "WezTerm": "com.github.wez.wezterm"
    ]

    func applicationDidFinishLaunching(_ notification: Notification) {
        let raw = CommandLine.arguments.dropFirst().first ?? "http://127.0.0.1:8765/pet"
        guard let url = URL(string: raw) else { NSApp.terminate(nil); return }
        reporterURL = url
        // Launch small (just the pet). The page grows the window to the full card only when Claude
        // needs the user, and shrinks it back on dismiss — so the reporter stays out of the way.
        let frame = NSRect(x: 0, y: 0, width: 132, height: 150)
        panel = NSPanel(contentRect: frame, styleMask: [.borderless, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.isMovableByWindowBackground = true
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false

        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(self, name: "orbit")
        web = WKWebView(frame: frame, configuration: config)
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        web.autoresizingMask = [.width, .height]
        panel.contentView = web
        web.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 5))

        if let saved = restoredOrigin(size: frame.size) {
            panel.setFrameOrigin(saved)
        } else if let screen = NSScreen.main?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: screen.maxX - frame.width - 18,
                                         y: screen.minY + 24))
        }
        panel.orderFrontRegardless()
    }

    private func value(_ name: String, in url: URL) -> String {
        URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?
            .first(where: { $0.name == name })?.value ?? ""
    }

    private func activate(bundle identifier: String) -> Bool {
        if let app = NSWorkspace.shared.runningApplications.first(where: {
            $0.bundleIdentifier == identifier
        }) {
            app.activate(options: [.activateAllWindows])
            return true
        }
        guard let appURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: identifier) else {
            return false
        }
        NSWorkspace.shared.openApplication(at: appURL, configuration: .init())
        return true
    }

    private func focusSession(_ url: URL) {
        let explicit = value("terminal_bundle", in: url)
        let program = value("terminal_program", in: url)
        let bundle = explicit.isEmpty ? terminalBundles[program] : explicit
        if let bundle = bundle, activate(bundle: bundle) { return }
        // Honest fallback: focus an already-running terminal instead of pretending we selected an
        // exact tab. Session id + project remain visible in the Reporter so the user can identify it.
        for identifier in terminalBundles.values where activate(bundle: identifier) { return }
        _ = activate(bundle: "com.apple.Terminal")
    }

    private func openBoard() {
        guard var parts = URLComponents(url: reporterURL, resolvingAgainstBaseURL: false) else { return }
        parts.path = "/"
        if let url = parts.url { NSWorkspace.shared.open(url) }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url, url.scheme == "orbit-action" else {
            decisionHandler(.allow); return
        }
        decisionHandler(.cancel)
        switch url.host {
        case "focus-session": focusSession(url)
        case "open-board": openBoard()
        default: break
        }
    }

    func userContentController(_ userContentController: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard message.name == "orbit", let payload = message.body as? [String: Any],
              let type = payload["type"] as? String else { return }
        switch type {
        case "transition":
            // Attention only: bring the card forward. Never a native OS notification (card-only).
            panel.orderFrontRegardless()
        case "drag":
            // The WKWebView covers the panel, so isMovableByWindowBackground never fires. The page
            // reports raw cursor deltas (screen pixels, +y = down) and we move the panel to match.
            let dx = (payload["dx"] as? NSNumber)?.doubleValue ?? 0
            let dy = (payload["dy"] as? NSNumber)?.doubleValue ?? 0
            var o = panel.frame.origin
            o.x += dx
            o.y -= dy          // Cocoa origin is bottom-left, so screen-down means a lower y.
            panel.setFrameOrigin(clamp(o, size: panel.frame.size))
            savePosition()
        case "resize":
            // Collapse to just the pet, or expand to the full card, keeping the pet corner anchored
            // (bottom-right) so the window never jumps out from under the cursor.
            let w = (payload["w"] as? NSNumber)?.doubleValue ?? panel.frame.width
            let h = (payload["h"] as? NSNumber)?.doubleValue ?? panel.frame.height
            let right = panel.frame.origin.x + panel.frame.width
            let bottom = panel.frame.origin.y
            var f = panel.frame
            f.size = NSSize(width: w, height: h)
            f.origin = clamp(NSPoint(x: right - w, y: bottom), size: f.size)
            panel.setFrame(f, display: true)
            savePosition()
        default:
            break
        }
    }

    // Keep the window on a visible screen so a drag can never strand it off-screen.
    private func clamp(_ origin: NSPoint, size: NSSize) -> NSPoint {
        guard let vis = (NSScreen.screens.first { $0.frame.contains(origin) }?.visibleFrame)
                ?? NSScreen.main?.visibleFrame else { return origin }
        let x = min(max(origin.x, vis.minX), vis.maxX - size.width)
        let y = min(max(origin.y, vis.minY), vis.maxY - size.height)
        return NSPoint(x: x, y: y)
    }

    private var posURL: URL {
        let home = ProcessInfo.processInfo.environment["ORBIT_HOME"]
            ?? (NSHomeDirectory() as NSString).appendingPathComponent(".orbit")
        return URL(fileURLWithPath: home).appendingPathComponent("pet-pos.json")
    }

    private func savePosition() {
        let o = panel.frame.origin
        let data = try? JSONSerialization.data(withJSONObject: ["x": o.x, "y": o.y])
        try? FileManager.default.createDirectory(at: posURL.deletingLastPathComponent(),
                                                 withIntermediateDirectories: true)
        try? data?.write(to: posURL)
    }

    private func restoredOrigin(size: NSSize) -> NSPoint? {
        guard let data = try? Data(contentsOf: posURL),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let x = (obj["x"] as? NSNumber)?.doubleValue,
              let y = (obj["y"] as? NSNumber)?.doubleValue else { return nil }
        return clamp(NSPoint(x: x, y: y), size: size)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
}

let app = NSApplication.shared
ProcessInfo.processInfo.disableAutomaticTermination("Orbit reporter is active")
ProcessInfo.processInfo.disableSuddenTermination()
app.setActivationPolicy(.accessory)
let delegate = ReporterDelegate()
app.delegate = delegate
app.run()
