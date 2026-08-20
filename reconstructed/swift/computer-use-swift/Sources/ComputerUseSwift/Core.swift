import AppKit
import ApplicationServices
import CoreGraphics
import Foundation
import ScreenCaptureKit

struct DisplayInfo: Codable {
    let displayId: UInt32
    let width: Int
    let height: Int
    let scaleFactor: Double
    let originX: Int
    let originY: Int
    let label: String
    let isPrimary: Bool
}

struct RunningAppInfo: Codable {
    let bundleId: String
    let displayName: String
    let pid: Int32
}

struct PointAppInfo: Codable {
    let bundleId: String
    let displayName: String
}

struct InstalledApp: Codable {
    let bundleId: String
    let displayName: String
    let path: String
}

struct WindowDisplayInfo: Codable {
    let bundleId: String
    let displayIds: [UInt32]
}

struct HideCandidate: Codable {
    let bundleId: String
    let displayName: String
}

struct PrepareDisplayResult: Codable {
    let hidden: [String]
    let activated: String?
}

enum ComputerUseCore {
    private static let systemChromeBundleIds: Set<String> = [
        "com.apple.controlcenter",
        "com.apple.dock",
        "com.apple.loginwindow",
        "com.apple.NotificationCenter",
        "com.apple.screencaptureui",
        "com.apple.SystemUIServer",
        "com.apple.TextInputSwitcher",
        "com.apple.wallpaper.agent",
        "com.apple.wifi.WiFiAgent",
    ]

    static func listDisplays() -> [DisplayInfo] {
        var count: UInt32 = 0
        guard CGGetActiveDisplayList(0, nil, &count) == .success, count > 0 else {
            return []
        }
        var ids = [CGDirectDisplayID](repeating: 0, count: Int(count))
        guard CGGetActiveDisplayList(count, &ids, &count) == .success else {
            return []
        }
        let screens: [UInt32: (name: String, scale: Double)] = Dictionary(
            uniqueKeysWithValues: NSScreen.screens.compactMap { screen -> (UInt32, (String, Double))? in
            guard let number = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else {
                return nil
            }
            return (number.uint32Value, (screen.localizedName, Double(screen.backingScaleFactor)))
            }
        )
        return ids.prefix(Int(count)).map { id in
            let bounds = CGDisplayBounds(id)
            let logicalWidth = max(1, Int(bounds.width.rounded()))
            let scale = screens[id]?.scale ?? Double(CGDisplayPixelsWide(id)) / Double(logicalWidth)
            return DisplayInfo(
                displayId: id,
                width: logicalWidth,
                height: max(1, Int(bounds.height.rounded())),
                scaleFactor: scale,
                originX: Int(bounds.origin.x.rounded()),
                originY: Int(bounds.origin.y.rounded()),
                label: screens[id]?.name ?? "Display \(id)",
                isPrimary: CGDisplayIsMain(id) != 0
            )
        }
    }

    static func displayInfo(id: UInt32?) -> DisplayInfo? {
        let displays = listDisplays()
        if let id {
            return displays.first { $0.displayId == id }
        }
        return displays.first { $0.isPrimary } ?? displays.first
    }

    static func checkAccessibility() -> Bool {
        AXIsProcessTrusted()
    }

    static func requestAccessibility() -> Bool {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        return AXIsProcessTrustedWithOptions(options)
    }

    static func checkScreenRecording() -> Bool {
        CGPreflightScreenCaptureAccess()
    }

    static func requestScreenRecording() -> Bool {
        CGRequestScreenCaptureAccess()
    }

    static func listRunningApplications() -> [RunningAppInfo] {
        NSWorkspace.shared.runningApplications.compactMap { app in
            guard app.activationPolicy == .regular,
                  let bundleId = app.bundleIdentifier,
                  let name = app.localizedName,
                  !bundleId.isEmpty,
                  !name.isEmpty
            else {
                return nil
            }
            return RunningAppInfo(bundleId: bundleId, displayName: name, pid: app.processIdentifier)
        }
    }

    static func listInstalledApplications() -> [InstalledApp] {
        InstalledAppsCache.shared.list()
    }

    static func resolveBundleIds(names: [String]) -> [String] {
        let normalized = Set(names.map(normalizeName).filter { !$0.isEmpty })
        guard !normalized.isEmpty else { return [] }
        var resolved: [String] = []
        var seen = Set<String>()

        for app in listRunningApplications() {
            let candidate = normalizeName(app.displayName)
            if normalized.contains(candidate), seen.insert(app.bundleId).inserted {
                resolved.append(app.bundleId)
            }
        }
        return resolved
    }

    static func findWindowDisplays(bundleIds: [String]) -> [WindowDisplayInfo] {
        let wanted = Set(bundleIds)
        guard !wanted.isEmpty else { return [] }
        let displayFrames = listDisplays().map { display in
            (display.displayId, CGRect(
                x: display.originX,
                y: display.originY,
                width: display.width,
                height: display.height
            ))
        }
        var found: [String: Set<UInt32>] = [:]
        for window in windowInfo() {
            guard let pid = window[kCGWindowOwnerPID as String] as? Int32,
                  let bundleId = NSRunningApplication(processIdentifier: pid)?.bundleIdentifier,
                  wanted.contains(bundleId),
                  let bounds = windowBounds(window),
                  bounds.width > 1,
                  bounds.height > 1
            else {
                continue
            }
            for (displayId, frame) in displayFrames where frame.intersects(bounds) {
                found[bundleId, default: []].insert(displayId)
            }
        }
        return found.map { bundleId, displayIds in
            WindowDisplayInfo(bundleId: bundleId, displayIds: displayIds.sorted())
        }.sorted { $0.bundleId < $1.bundleId }
    }

    static func appUnderPoint(x: Double, y: Double) -> PointAppInfo? {
        let point = CGPoint(x: x, y: y)
        for window in windowInfo() {
            guard let bounds = windowBounds(window),
                  bounds.contains(point),
                  let pid = window[kCGWindowOwnerPID as String] as? Int32,
                  let app = NSRunningApplication(processIdentifier: pid),
                  let bundleId = app.bundleIdentifier,
                  let name = app.localizedName
            else {
                continue
            }
            return PointAppInfo(bundleId: bundleId, displayName: name)
        }
        return nil
    }

    static func previewHideSet(exemptBundleIds: [String], displayId: UInt32?) -> [HideCandidate] {
        _ = displayId
        return hideCandidates(exemptBundleIds: Set(exemptBundleIds), display: nil)
            .compactMap { app in
                guard let bundleId = app.bundleIdentifier, let name = app.localizedName else { return nil }
                return HideCandidate(bundleId: bundleId, displayName: name)
            }
    }

    static func prepareDisplay(
        allowedBundleIds: [String],
        hostBundleId: String,
        displayId: UInt32?
    ) -> PrepareDisplayResult {
        var exempt = Set(allowedBundleIds)
        exempt.insert(hostBundleId)
        let display = displayInfo(id: displayId)
        var hidden: [String] = []
        for app in hideCandidates(exemptBundleIds: exempt, display: display) {
            guard let bundleId = app.bundleIdentifier else { continue }
            if app.hide() {
                hidden.append(bundleId)
            }
        }

        let allowed = Set(allowedBundleIds)
        let candidates = NSWorkspace.shared.runningApplications.filter { app in
            guard let bundleId = app.bundleIdentifier else { return false }
            return allowed.contains(bundleId) && app.activationPolicy == .regular
        }
        let frontmost = NSWorkspace.shared.frontmostApplication
        let selected = candidates.first { $0.processIdentifier == frontmost?.processIdentifier }
            ?? candidates.first { appHasWindow($0, on: display) }
            ?? candidates.first
        selected?.activate(options: [])
        return PrepareDisplayResult(hidden: hidden, activated: selected?.bundleIdentifier)
    }

    static func unhide(bundleIds: [String]) {
        let wanted = Set(bundleIds)
        for app in NSWorkspace.shared.runningApplications {
            guard let bundleId = app.bundleIdentifier, wanted.contains(bundleId) else { continue }
            app.unhide()
        }
    }

    static func openApplication(bundleId: String) throws {
        guard let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleId) else {
            throw CoreError.message("No application found for bundle ID \(bundleId)")
        }
        let semaphore = DispatchSemaphore(value: 0)
        var launchError: Error?
        NSWorkspace.shared.openApplication(at: url, configuration: .init()) { _, error in
            launchError = error
            semaphore.signal()
        }
        if semaphore.wait(timeout: .now() + 15) == .timedOut {
            throw CoreError.message("Timed out opening application \(bundleId)")
        }
        if let launchError {
            throw launchError
        }
    }

    static func iconDataUrl(path: String) -> String? {
        let icon = NSWorkspace.shared.icon(forFile: path)
        guard let bitmap = NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: 64,
            pixelsHigh: 64,
            bitsPerSample: 8,
            samplesPerPixel: 4,
            hasAlpha: true,
            isPlanar: false,
            colorSpaceName: .deviceRGB,
            bytesPerRow: 0,
            bitsPerPixel: 0
        )
        else {
            return nil
        }
        bitmap.size = NSSize(width: 64, height: 64)
        NSGraphicsContext.saveGraphicsState()
        guard let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
            NSGraphicsContext.restoreGraphicsState()
            return nil
        }
        NSGraphicsContext.current = context
        icon.draw(
            in: NSRect(x: 0, y: 0, width: 64, height: 64),
            from: .zero,
            operation: .copy,
            fraction: 1
        )
        NSGraphicsContext.restoreGraphicsState()
        guard let png = bitmap.representation(using: .png, properties: [:]) else {
            return nil
        }
        return "data:image/png;base64," + png.base64EncodedString()
    }

    static func captureExcluding(
        allowedBundleIds: [String],
        jpegQuality: CGFloat,
        outputWidth: Int?,
        outputHeight: Int?,
        displayId: UInt32?
    ) throws -> [String: Any] {
        guard let display = displayInfo(id: displayId) else {
            throw CoreError.message("CU display unavailable")
        }
        let targetWidth = max(1, outputWidth ?? display.width)
        let targetHeight = max(1, outputHeight ?? display.height)
        let image = try captureScreen(
            display: display,
            sourceRect: nil,
            outputWidth: targetWidth,
            outputHeight: targetHeight,
            allowedBundleIds: allowedBundleIds,
            jpegQuality: jpegQuality
        )
        return [
            "base64": image.base64,
            "width": image.width,
            "height": image.height,
            "displayWidth": display.width,
            "displayHeight": display.height,
            "displayId": display.displayId,
            "originX": display.originX,
            "originY": display.originY,
        ]
    }

    static func captureRegion(
        allowedBundleIds: [String],
        x: Double,
        y: Double,
        width: Double,
        height: Double,
        outputWidth: Int,
        outputHeight: Int,
        jpegQuality: CGFloat,
        displayId: UInt32?
    ) throws -> [String: Any] {
        guard let display = displayInfo(id: displayId) else {
            throw CoreError.message("CU display unavailable")
        }
        let localRect = CGRect(
            x: x - Double(display.originX),
            y: y - Double(display.originY),
            width: width,
            height: height
        )
        let image = try captureScreen(
            display: display,
            sourceRect: localRect,
            outputWidth: max(1, outputWidth),
            outputHeight: max(1, outputHeight),
            allowedBundleIds: allowedBundleIds,
            jpegQuality: jpegQuality
        )
        return ["base64": image.base64, "width": image.width, "height": image.height]
    }

    static func resolvePrepareCapture(
        allowedBundleIds: [String],
        hostBundleId: String,
        jpegQuality: CGFloat,
        outputWidth: Int,
        outputHeight: Int,
        preferredDisplayId: UInt32?,
        autoResolve: Bool,
        doHide: Bool
    ) throws -> [String: Any] {
        let display = resolveTargetDisplay(
            allowedBundleIds: allowedBundleIds,
            preferredDisplayId: preferredDisplayId,
            autoResolve: autoResolve
        )
        guard let display else {
            throw CoreError.message("CU display unavailable")
        }
        let preparation = doHide
            ? prepareDisplay(
                allowedBundleIds: allowedBundleIds,
                hostBundleId: hostBundleId,
                displayId: display.displayId
            )
            : prepareDisplayWithoutHiding(allowedBundleIds: allowedBundleIds, display: display)
        do {
            var result = try captureExcluding(
                allowedBundleIds: allowedBundleIds + [hostBundleId],
                jpegQuality: jpegQuality,
                outputWidth: outputWidth,
                outputHeight: outputHeight,
                displayId: display.displayId
            )
            result["hidden"] = preparation.hidden
            if let activated = preparation.activated {
                result["activated"] = activated
            }
            return result
        } catch {
            return [
                "hidden": preparation.hidden,
                "activated": preparation.activated as Any,
                "displayId": display.displayId,
                "displayWidth": display.width,
                "displayHeight": display.height,
                "originX": display.originX,
                "originY": display.originY,
                "width": outputWidth,
                "height": outputHeight,
                "base64": "",
                "captureError": error.localizedDescription,
            ]
        }
    }

    private static func resolveTargetDisplay(
        allowedBundleIds: [String],
        preferredDisplayId: UInt32?,
        autoResolve: Bool
    ) -> DisplayInfo? {
        if !autoResolve {
            return displayInfo(id: preferredDisplayId)
        }
        let windowDisplays = findWindowDisplays(bundleIds: allowedBundleIds)
        let counts = windowDisplays.flatMap(\.displayIds).reduce(into: [UInt32: Int]()) { counts, id in
            counts[id, default: 0] += 1
        }
        if let best = counts.max(by: { $0.value < $1.value })?.key,
           let display = displayInfo(id: best)
        {
            return display
        }
        return displayInfo(id: preferredDisplayId)
    }

    private static func prepareDisplayWithoutHiding(
        allowedBundleIds: [String],
        display: DisplayInfo
    ) -> PrepareDisplayResult {
        let allowed = Set(allowedBundleIds)
        let candidates = NSWorkspace.shared.runningApplications.filter { app in
            guard let bundleId = app.bundleIdentifier else { return false }
            return allowed.contains(bundleId) && app.activationPolicy == .regular
        }
        let frontmost = NSWorkspace.shared.frontmostApplication
        let selected = candidates.first { $0.processIdentifier == frontmost?.processIdentifier }
            ?? candidates.first { appHasWindow($0, on: display) }
            ?? candidates.first
        selected?.activate(options: [])
        return PrepareDisplayResult(hidden: [], activated: selected?.bundleIdentifier)
    }

    private static func hideCandidates(
        exemptBundleIds: Set<String>,
        display: DisplayInfo?
    ) -> [NSRunningApplication] {
        NSWorkspace.shared.runningApplications.filter { app in
            guard !app.isHidden,
                  let bundleId = app.bundleIdentifier,
                  !exemptBundleIds.contains(bundleId),
                  !systemChromeBundleIds.contains(bundleId)
            else {
                return false
            }
            return appHasWindow(app, on: display)
        }
    }

    private static func appHasWindow(_ app: NSRunningApplication, on display: DisplayInfo?) -> Bool {
        let frame = display.map {
            CGRect(x: $0.originX, y: $0.originY, width: $0.width, height: $0.height)
        }
        return windowInfo().contains { window in
            guard let pid = window[kCGWindowOwnerPID as String] as? Int32,
                  pid == app.processIdentifier,
                  (window[kCGWindowLayer as String] as? Int) == 0,
                  let bounds = windowBounds(window)
            else {
                return false
            }
            return bounds.width > 1
                && bounds.height > 1
                && (frame.map { bounds.intersects($0) } ?? true)
        }
    }

    private static func windowInfo() -> [[String: Any]] {
        CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
            as? [[String: Any]] ?? []
    }

    private static func windowBounds(_ window: [String: Any]) -> CGRect? {
        guard let dictionary = window[kCGWindowBounds as String] as? NSDictionary else { return nil }
        return CGRect(dictionaryRepresentation: dictionary)
    }

    private static func normalizeName(_ value: String) -> String {
        value.folding(options: [.caseInsensitive, .diacriticInsensitive, .widthInsensitive], locale: .current)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func captureScreen(
        display: DisplayInfo,
        sourceRect: CGRect?,
        outputWidth: Int,
        outputHeight: Int,
        allowedBundleIds: [String],
        jpegQuality: CGFloat
    ) throws -> (base64: String, width: Int, height: Int) {
        try waitForAsync {
            let content = try await SCShareableContent.excludingDesktopWindows(
                false,
                onScreenWindowsOnly: true
            )
            guard let scDisplay = content.displays.first(where: { $0.displayID == display.displayId }) else {
                throw CoreError.message("Display not found for the given ID")
            }
            let allowed = Set(allowedBundleIds).union(systemChromeBundleIds)
            let excluded = content.applications.filter { application in
                !allowed.contains(application.bundleIdentifier)
            }
            let filter = SCContentFilter(
                display: scDisplay,
                excludingApplications: excluded,
                exceptingWindows: []
            )
            let configuration = SCStreamConfiguration()
            configuration.width = outputWidth
            configuration.height = outputHeight
            configuration.showsCursor = true
            configuration.capturesAudio = false
            if let sourceRect {
                configuration.sourceRect = sourceRect
            }
            let cgImage = try await SCScreenshotManager.captureImage(
                contentFilter: filter,
                configuration: configuration
            )
            let bitmap = NSBitmapImageRep(cgImage: cgImage)
            guard let data = bitmap.representation(
                using: .jpeg,
                properties: [.compressionFactor: max(0, min(1, jpegQuality))]
            ) else {
                throw CoreError.message("Screenshot capture returned no image")
            }
            return (data.base64EncodedString(), cgImage.width, cgImage.height)
        }
    }

    private static func waitForAsync<T>(
        timeout: TimeInterval = 30,
        operation: @escaping () async throws -> T
    ) throws -> T {
        let semaphore = DispatchSemaphore(value: 0)
        let resultBox = SynchronousResultBox<T>()
        Task {
            let result: Result<T, Error>
            do {
                result = .success(try await operation())
            } catch {
                result = .failure(error)
            }
            resultBox.store(result)
            semaphore.signal()
        }
        guard semaphore.wait(timeout: .now() + timeout) == .success else {
            throw CoreError.message("ScreenCaptureKit did not call back within the watchdog window")
        }
        guard let outcome = resultBox.load() else {
            throw CoreError.message("Screenshot capture returned no image")
        }
        return try outcome.get()
    }
}

private final class SynchronousResultBox<T>: @unchecked Sendable {
    private let lock = NSLock()
    private var outcome: Result<T, Error>?

    func store(_ result: Result<T, Error>) {
        lock.lock()
        outcome = result
        lock.unlock()
    }

    func load() -> Result<T, Error>? {
        lock.lock()
        defer { lock.unlock() }
        return outcome
    }
}

private final class InstalledAppsCache {
    static let shared = InstalledAppsCache()

    private let lock = NSLock()
    private var cached: [InstalledApp]?
    private var cachedAt = Date.distantPast

    func list() -> [InstalledApp] {
        lock.lock()
        if let cached, Date().timeIntervalSince(cachedAt) < 60 {
            lock.unlock()
            return cached
        }
        lock.unlock()

        let spotlightApps = spotlightList()
        let apps = spotlightApps.isEmpty ? fileSystemList() : spotlightApps
        lock.lock()
        cached = apps
        cachedAt = Date()
        lock.unlock()
        return apps
    }

    private func spotlightList() -> [InstalledApp] {
        let query = NSMetadataQuery()
        query.predicate = NSPredicate(format: "kMDItemContentType == %@", "com.apple.application-bundle")
        query.searchScopes = [NSMetadataQueryLocalComputerScope]
        let stateLock = NSLock()
        var finished = false
        let observer = NotificationCenter.default.addObserver(
            forName: .NSMetadataQueryDidFinishGathering,
            object: query,
            queue: nil
        ) { _ in
            stateLock.lock()
            finished = true
            stateLock.unlock()
        }
        defer {
            NotificationCenter.default.removeObserver(observer)
            query.stop()
        }
        guard query.start() else { return [] }
        let deadline = Date().addingTimeInterval(15)
        while Date() < deadline {
            stateLock.lock()
            let done = finished
            stateLock.unlock()
            if done { break }
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.02))
        }
        stateLock.lock()
        let done = finished
        stateLock.unlock()
        guard done else { return [] }
        query.disableUpdates()

        var apps: [InstalledApp] = []
        for result in query.results {
            guard let item = result as? NSMetadataItem,
                  let bundleId = item.value(forAttribute: NSMetadataItemCFBundleIdentifierKey) as? String,
                  !bundleId.isEmpty,
                  let path = item.value(forAttribute: NSMetadataItemPathKey) as? String,
                  let bundle = Bundle(path: path),
                  !isBackground(bundle)
            else {
                continue
            }
            let metadataName = item.value(forAttribute: NSMetadataItemDisplayNameKey) as? String
            let pathName = NSString(string: path).lastPathComponent
            let displayName = (metadataName ?? pathName).hasSuffix(".app")
                ? String((metadataName ?? pathName).dropLast(4))
                : (metadataName ?? pathName)
            apps.append(InstalledApp(bundleId: bundleId, displayName: displayName, path: path))
        }
        return apps
    }

    private func fileSystemList() -> [InstalledApp] {
        let roots = [
            "/Applications",
            "/System/Applications",
            "/System/Library/CoreServices",
            NSString(string: "~/Applications").expandingTildeInPath,
        ]
        var paths: [String] = []
        let keys: [URLResourceKey] = [.isDirectoryKey, .isPackageKey]
        for root in roots where FileManager.default.fileExists(atPath: root) {
            guard let enumerator = FileManager.default.enumerator(
                at: URL(fileURLWithPath: root),
                includingPropertiesForKeys: keys,
                options: [.skipsHiddenFiles],
                errorHandler: { _, _ in true }
            ) else {
                continue
            }
            for case let url as URL in enumerator {
                guard url.pathExtension.caseInsensitiveCompare("app") == .orderedSame else { continue }
                enumerator.skipDescendants()
                paths.append(url.path)
            }
        }
        return appsFromPaths(paths, shouldSort: true)
    }

    private func appsFromPaths(_ paths: [String], shouldSort: Bool) -> [InstalledApp] {
        var apps: [InstalledApp] = []
        for path in paths {
            let url = URL(fileURLWithPath: path)
            guard let bundle = Bundle(url: url),
                  let bundleId = bundle.bundleIdentifier,
                  !bundleId.isEmpty,
                  !isBackground(bundle)
            else {
                continue
            }
            let localized = bundle.localizedInfoDictionary
            let info = bundle.infoDictionary
            let displayName = localized?["CFBundleDisplayName"] as? String
                ?? localized?["CFBundleName"] as? String
                ?? info?["CFBundleDisplayName"] as? String
                ?? info?["CFBundleName"] as? String
                ?? url.deletingPathExtension().lastPathComponent
            apps.append(InstalledApp(bundleId: bundleId, displayName: displayName, path: path))
        }
        if shouldSort {
            apps.sort {
                $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
            }
        }
        return apps
    }

    private func isBackground(_ bundle: Bundle) -> Bool {
        isTrue(bundle.object(forInfoDictionaryKey: "LSBackgroundOnly"))
            || isTrue(bundle.object(forInfoDictionaryKey: "LSUIElement"))
    }

    private func isTrue(_ value: Any?) -> Bool {
        if let bool = value as? Bool {
            return bool
        }
        if let number = value as? NSNumber {
            return number.boolValue
        }
        return (value as? NSString)?.boolValue == true
    }
}

enum CoreError: LocalizedError {
    case message(String)

    var errorDescription: String? {
        switch self {
        case let .message(message): message
        }
    }
}
