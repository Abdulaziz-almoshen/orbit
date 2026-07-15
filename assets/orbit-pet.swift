import Cocoa
import WebKit

final class ReporterDelegate: NSObject, NSApplicationDelegate {
    private var panel: NSPanel!
    private var web: WKWebView!

    func applicationDidFinishLaunching(_ notification: Notification) {
        let raw = CommandLine.arguments.dropFirst().first ?? "http://127.0.0.1:8765/pet"
        guard let url = URL(string: raw) else { NSApp.terminate(nil); return }
        let frame = NSRect(x: 0, y: 0, width: 430, height: 210)
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
        web = WKWebView(frame: frame, configuration: config)
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

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
}

let app = NSApplication.shared
ProcessInfo.processInfo.disableAutomaticTermination("Orbit reporter is active")
ProcessInfo.processInfo.disableSuddenTermination()
app.setActivationPolicy(.accessory)
let delegate = ReporterDelegate()
app.delegate = delegate
app.run()
