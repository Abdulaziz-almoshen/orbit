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
        let frame = NSRect(x: 0, y: 0, width: 590, height: 310)
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

        if let screen = NSScreen.main?.visibleFrame {
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
              payload["type"] as? String == "transition" else { return }
        panel.orderFrontRegardless()
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
