import AppKit
import CNodeAPI
import CoreGraphics
import Foundation

private final class AsyncWorkBox {
    let operation: () throws -> Any
    var outcome: Result<Any, Error>?
    var deferred: OpaquePointer?
    var work: OpaquePointer?

    init(operation: @escaping () throws -> Any) {
        self.operation = operation
    }
}

private let asyncExecute: napi_async_execute_callback = { _, data in
    guard let data else { return }
    let box = Unmanaged<AsyncWorkBox>.fromOpaque(data).takeUnretainedValue()
    do {
        box.outcome = .success(try box.operation())
    } catch {
        box.outcome = .failure(error)
    }
}

private let asyncComplete: napi_async_complete_callback = { env, status, data in
    guard let data else { return }
    let box = Unmanaged<AsyncWorkBox>.fromOpaque(data).takeRetainedValue()
    defer {
        if let work = box.work {
            napi_delete_async_work(env, work)
        }
    }
    guard status == napi_ok, let deferred = box.deferred else {
        if let deferred = box.deferred {
            napi_reject_deferred(env, deferred, makeError(env, "Native async work was cancelled"))
        }
        return
    }
    switch box.outcome {
    case let .success(value):
        napi_resolve_deferred(env, deferred, makeValue(env, value))
    case let .failure(error):
        napi_reject_deferred(env, deferred, makeError(env, error.localizedDescription))
    case .none:
        napi_reject_deferred(env, deferred, makeError(env, "Native async work returned no result"))
    }
}

private func createAsyncPromise(
    _ env: OpaquePointer?,
    resourceName: String,
    operation: @escaping () throws -> Any
) -> OpaquePointer? {
    var deferred: OpaquePointer?
    var promise: OpaquePointer?
    guard napi_create_promise(env, &deferred, &promise) == napi_ok else {
        return throwError(env, "Failed to create promise")
    }
    let box = AsyncWorkBox(operation: operation)
    box.deferred = deferred
    let data = Unmanaged.passRetained(box).toOpaque()
    var work: OpaquePointer?
    let resource = makeString(env, resourceName)
    let status = napi_create_async_work(
        env,
        nil,
        resource,
        asyncExecute,
        asyncComplete,
        data,
        &work
    )
    guard status == napi_ok, let work else {
        Unmanaged<AsyncWorkBox>.fromOpaque(data).release()
        return throwError(env, "Failed to create native async work")
    }
    box.work = work
    guard napi_queue_async_work(env, work) == napi_ok else {
        napi_delete_async_work(env, work)
        Unmanaged<AsyncWorkBox>.fromOpaque(data).release()
        return throwError(env, "Failed to queue native async work")
    }
    return promise
}

private func resolvedPromise(_ env: OpaquePointer?, value: Any) -> OpaquePointer? {
    var deferred: OpaquePointer?
    var promise: OpaquePointer?
    guard napi_create_promise(env, &deferred, &promise) == napi_ok, let deferred else {
        return throwError(env, "Failed to create promise")
    }
    napi_resolve_deferred(env, deferred, makeValue(env, value))
    return promise
}

private func args(_ env: OpaquePointer?, _ info: OpaquePointer?, max: Int = 12) -> [OpaquePointer?] {
    var count = max
    var values = [OpaquePointer?](repeating: nil, count: max)
    _ = values.withUnsafeMutableBufferPointer { buffer in
        napi_get_cb_info(env, info, &count, buffer.baseAddress, nil, nil)
    }
    return Array(values.prefix(count))
}

private func valueType(_ env: OpaquePointer?, _ value: OpaquePointer?) -> napi_valuetype {
    var type = napi_undefined
    napi_typeof(env, value, &type)
    return type
}

private func stringValue(_ env: OpaquePointer?, _ value: OpaquePointer?) -> String? {
    guard valueType(env, value) == napi_string else { return nil }
    var length = 0
    napi_get_value_string_utf8(env, value, nil, 0, &length)
    var bytes = [CChar](repeating: 0, count: length + 1)
    _ = bytes.withUnsafeMutableBufferPointer { buffer in
        napi_get_value_string_utf8(env, value, buffer.baseAddress, buffer.count, &length)
    }
    return String(cString: bytes)
}

private func doubleValue(_ env: OpaquePointer?, _ value: OpaquePointer?) -> Double? {
    guard valueType(env, value) == napi_number else { return nil }
    var number = 0.0
    guard napi_get_value_double(env, value, &number) == napi_ok else { return nil }
    return number
}

private func intValue(_ env: OpaquePointer?, _ value: OpaquePointer?) -> Int? {
    doubleValue(env, value).map { Int($0) }
}

private func boolValue(_ env: OpaquePointer?, _ value: OpaquePointer?) -> Bool? {
    guard valueType(env, value) == napi_boolean else { return nil }
    var result = false
    guard napi_get_value_bool(env, value, &result) == napi_ok else { return nil }
    return result
}

private func optionalInt(_ env: OpaquePointer?, _ values: [OpaquePointer?], index: Int) -> Int? {
    guard index < values.count else { return nil }
    let type = valueType(env, values[index])
    if type == napi_null || type == napi_undefined { return nil }
    return intValue(env, values[index])
}

private func stringArray(_ env: OpaquePointer?, _ value: OpaquePointer?) -> [String]? {
    var isArray = false
    guard napi_is_array(env, value, &isArray) == napi_ok, isArray else { return nil }
    var length: UInt32 = 0
    guard napi_get_array_length(env, value, &length) == napi_ok else { return nil }
    var result: [String] = []
    for index in 0..<length {
        var element: OpaquePointer?
        guard napi_get_element(env, value, index, &element) == napi_ok,
              let string = stringValue(env, element)
        else {
            return nil
        }
        result.append(string)
    }
    return result
}

private func makeUndefined(_ env: OpaquePointer?) -> OpaquePointer? {
    var value: OpaquePointer?
    napi_get_undefined(env, &value)
    return value
}

private func makeNull(_ env: OpaquePointer?) -> OpaquePointer? {
    var value: OpaquePointer?
    napi_get_null(env, &value)
    return value
}

private func makeString(_ env: OpaquePointer?, _ string: String) -> OpaquePointer? {
    var value: OpaquePointer?
    _ = string.withCString { pointer in
        napi_create_string_utf8(env, pointer, string.lengthOfBytes(using: .utf8), &value)
    }
    return value
}

private func makeBool(_ env: OpaquePointer?, _ bool: Bool) -> OpaquePointer? {
    var value: OpaquePointer?
    napi_get_boolean(env, bool, &value)
    return value
}

private func makeNumber(_ env: OpaquePointer?, _ number: Double) -> OpaquePointer? {
    var value: OpaquePointer?
    napi_create_double(env, number, &value)
    return value
}

private func makeError(_ env: OpaquePointer?, _ message: String) -> OpaquePointer? {
    var error: OpaquePointer?
    napi_create_error(env, nil, makeString(env, message), &error)
    return error
}

private func makeValue(_ env: OpaquePointer?, _ value: Any) -> OpaquePointer? {
    if value is NSNull { return makeNull(env) }
    if let value = value as? String { return makeString(env, value) }
    if let value = value as? NSNumber {
        if CFGetTypeID(value) == CFBooleanGetTypeID() {
            return makeBool(env, value.boolValue)
        }
        return makeNumber(env, value.doubleValue)
    }
    if let value = value as? Bool { return makeBool(env, value) }
    if let value = value as? Int { return makeNumber(env, Double(value)) }
    if let value = value as? Int32 { return makeNumber(env, Double(value)) }
    if let value = value as? UInt32 { return makeNumber(env, Double(value)) }
    if let value = value as? Double { return makeNumber(env, value) }
    if let value = value as? CGFloat { return makeNumber(env, Double(value)) }
    if let values = value as? [Any] {
        var array: OpaquePointer?
        napi_create_array_with_length(env, values.count, &array)
        for (index, item) in values.enumerated() {
            napi_set_element(env, array, UInt32(index), makeValue(env, item))
        }
        return array
    }
    if let dictionary = value as? [String: Any] {
        var object: OpaquePointer?
        napi_create_object(env, &object)
        for (key, item) in dictionary {
            napi_set_named_property(env, object, key, makeValue(env, item))
        }
        return object
    }
    if let encodable = value as? any Encodable,
       let object = try? foundationObject(encodable)
    {
        return makeValue(env, object)
    }
    return makeUndefined(env)
}

private struct AnyEncodable: Encodable {
    let value: any Encodable

    func encode(to encoder: Encoder) throws {
        try value.encode(to: encoder)
    }
}

private func foundationObject(_ value: any Encodable) throws -> Any {
    let data = try JSONEncoder().encode(AnyEncodable(value: value))
    return try JSONSerialization.jsonObject(with: data)
}

@discardableResult
private func throwError(_ env: OpaquePointer?, _ message: String) -> OpaquePointer? {
    _ = message.withCString { pointer in
        napi_throw_error(env, nil, pointer)
    }
    return nil
}

private func setFunction(
    _ env: OpaquePointer?,
    object: OpaquePointer?,
    name: String,
    callback: napi_callback
) {
    var function: OpaquePointer?
    _ = name.withCString { pointer in
        napi_create_function(
            env,
            pointer,
            name.lengthOfBytes(using: .utf8),
            callback,
            nil,
            &function
        )
    }
    napi_set_named_property(env, object, name, function)
}

private func makeObject(_ env: OpaquePointer?) -> OpaquePointer? {
    var object: OpaquePointer?
    napi_create_object(env, &object)
    return object
}

private let drainMainRunLoopMethod: napi_callback = { env, _ in
    _ = RunLoop.main.run(mode: .default, before: Date())
    return makeUndefined(env)
}

private let testEchoOptionalIntMethod: napi_callback = { env, info in
    let values = args(env, info, max: 1)
    guard let value = optionalInt(env, values, index: 0) else {
        return makeUndefined(env)
    }
    return makeNumber(env, Double(value))
}

private let listDisplaysMethod: napi_callback = { env, _ in
    makeValue(env, ComputerUseCore.listDisplays())
}

private let getDisplaySizeMethod: napi_callback = { env, info in
    let values = args(env, info, max: 1)
    let displayId = optionalInt(env, values, index: 0).map(UInt32.init)
    guard let display = ComputerUseCore.displayInfo(id: displayId) else {
        return throwError(env, "CU display unavailable")
    }
    return makeValue(env, [
        "width": display.width,
        "height": display.height,
        "scaleFactor": display.scaleFactor,
        "displayId": display.displayId,
        "originX": display.originX,
        "originY": display.originY,
    ] as [String: Any])
}

private let checkAccessibilityMethod: napi_callback = { env, _ in
    makeBool(env, ComputerUseCore.checkAccessibility())
}

private let requestAccessibilityMethod: napi_callback = { env, _ in
    makeBool(env, ComputerUseCore.requestAccessibility())
}

private let checkScreenRecordingMethod: napi_callback = { env, _ in
    makeBool(env, ComputerUseCore.checkScreenRecording())
}

private let requestScreenRecordingMethod: napi_callback = { env, _ in
    makeBool(env, ComputerUseCore.requestScreenRecording())
}

private let listRunningMethod: napi_callback = { env, _ in
    makeValue(env, ComputerUseCore.listRunningApplications())
}

private let listInstalledMethod: napi_callback = { env, _ in
    createAsyncPromise(env, resourceName: "computerUse.listInstalled") {
        try ComputerUseCore.listInstalledApplications()
    }
}

private let resolveBundleIdsMethod: napi_callback = { env, info in
    let values = args(env, info, max: 1)
    guard let names = values.first.flatMap({ stringArray(env, $0) }) else {
        return throwError(env, "resolveBundleIds: expected names: string[]")
    }
    return makeValue(env, ComputerUseCore.resolveBundleIds(names: names))
}

private let findWindowDisplaysMethod: napi_callback = { env, info in
    let values = args(env, info, max: 1)
    guard let bundleIds = values.first.flatMap({ stringArray(env, $0) }) else {
        return throwError(env, "findWindowDisplays: expected bundleIds: string[]")
    }
    return makeValue(env, ComputerUseCore.findWindowDisplays(bundleIds: bundleIds))
}

private let appUnderPointMethod: napi_callback = { env, info in
    let values = args(env, info, max: 2)
    guard values.count >= 2,
          let x = doubleValue(env, values[0]),
          let y = doubleValue(env, values[1])
    else {
        return throwError(env, "appUnderPoint: expected (x: number, y: number)")
    }
    guard let app = ComputerUseCore.appUnderPoint(x: x, y: y) else {
        return makeNull(env)
    }
    return makeValue(env, app)
}

private let previewHideSetMethod: napi_callback = { env, info in
    let values = args(env, info, max: 2)
    guard let exempt = values.first.flatMap({ stringArray(env, $0) }) else {
        return throwError(env, "previewHideSet: expected exemptBundleIds: string[]")
    }
    let displayId = optionalInt(env, values, index: 1).map(UInt32.init)
    return makeValue(env, ComputerUseCore.previewHideSet(exemptBundleIds: exempt, displayId: displayId))
}

private let prepareDisplayMethod: napi_callback = { env, info in
    let values = args(env, info, max: 3)
    guard values.count >= 2,
          let allowed = stringArray(env, values[0]),
          let host = stringValue(env, values[1])
    else {
        return throwError(env, "prepareDisplay: expected (allowedBundleIds: string[], hostBundleId: string)")
    }
    let displayId = optionalInt(env, values, index: 2).map(UInt32.init)
    let result = ComputerUseCore.prepareDisplay(
        allowedBundleIds: allowed,
        hostBundleId: host,
        displayId: displayId
    )
    return resolvedPromise(env, value: result)
}

private let unhideMethod: napi_callback = { env, info in
    let values = args(env, info, max: 1)
    guard let bundleIds = values.first.flatMap({ stringArray(env, $0) }) else {
        return throwError(env, "unhide: expected bundleIds: string[]")
    }
    ComputerUseCore.unhide(bundleIds: bundleIds)
    return resolvedPromise(env, value: NSNull())
}

private let openMethod: napi_callback = { env, info in
    let values = args(env, info, max: 1)
    guard let bundleId = values.first.flatMap({ stringValue(env, $0) }) else {
        return throwError(env, "open: expected bundleId: string")
    }
    return createAsyncPromise(env, resourceName: "computerUse.open") {
        try ComputerUseCore.openApplication(bundleId: bundleId)
        return NSNull()
    }
}

private let iconDataUrlMethod: napi_callback = { env, info in
    let values = args(env, info, max: 1)
    guard let path = values.first.flatMap({ stringValue(env, $0) }) else {
        return throwError(env, "iconDataUrl: expected path: string")
    }
    guard let dataUrl = ComputerUseCore.iconDataUrl(path: path) else {
        return makeNull(env)
    }
    return makeString(env, dataUrl)
}

private let captureExcludingMethod: napi_callback = { env, info in
    let values = args(env, info, max: 5)
    guard let allowed = values.first.flatMap({ stringArray(env, $0) }) else {
        return throwError(env, "captureExcluding: expected allowedBundleIds: string[]")
    }
    let quality = CGFloat(doubleValue(env, values[safe: 1] ?? nil) ?? 0.6)
    let outputWidth = optionalInt(env, values, index: 2)
    let outputHeight = optionalInt(env, values, index: 3)
    let displayId = optionalInt(env, values, index: 4).map(UInt32.init)
    return createAsyncPromise(env, resourceName: "computerUse.captureExcluding") {
        try ComputerUseCore.captureExcluding(
            allowedBundleIds: allowed,
            jpegQuality: quality,
            outputWidth: outputWidth,
            outputHeight: outputHeight,
            displayId: displayId
        )
    }
}

private let captureRegionMethod: napi_callback = { env, info in
    let values = args(env, info, max: 9)
    guard values.count >= 7,
          let allowed = stringArray(env, values[0]),
          let x = doubleValue(env, values[1]),
          let y = doubleValue(env, values[2]),
          let width = doubleValue(env, values[3]),
          let height = doubleValue(env, values[4]),
          let outputWidth = intValue(env, values[5]),
          let outputHeight = intValue(env, values[6])
    else {
        return throwError(
            env,
            "captureRegion: expected (allowedBundleIds, regionX, regionY, regionW, regionH, outputWidth, outputHeight)"
        )
    }
    let quality = CGFloat(doubleValue(env, values[safe: 7] ?? nil) ?? 0.6)
    let displayId = optionalInt(env, values, index: 8).map(UInt32.init)
    return createAsyncPromise(env, resourceName: "computerUse.captureRegion") {
        try ComputerUseCore.captureRegion(
            allowedBundleIds: allowed,
            x: x,
            y: y,
            width: width,
            height: height,
            outputWidth: outputWidth,
            outputHeight: outputHeight,
            jpegQuality: quality,
            displayId: displayId
        )
    }
}

private let resolvePrepareCaptureMethod: napi_callback = { env, info in
    let values = args(env, info, max: 8)
    guard values.count >= 2,
          let allowed = stringArray(env, values[0]),
          let host = stringValue(env, values[1])
    else {
        return throwError(env, "resolvePrepareCapture: expected (allowedBundleIds: string[], hostBundleId: string)")
    }
    let quality = CGFloat(doubleValue(env, values[safe: 2] ?? nil) ?? 0.6)
    let display = ComputerUseCore.displayInfo(id: optionalInt(env, values, index: 5).map(UInt32.init))
    let outputWidth = optionalInt(env, values, index: 3) ?? display?.width ?? 1
    let outputHeight = optionalInt(env, values, index: 4) ?? display?.height ?? 1
    let preferredDisplayId = optionalInt(env, values, index: 5).map(UInt32.init)
    let autoResolve = boolValue(env, values[safe: 6] ?? nil) ?? false
    let doHide = boolValue(env, values[safe: 7] ?? nil) ?? false
    return createAsyncPromise(env, resourceName: "computerUse.resolvePrepareCapture") {
        try ComputerUseCore.resolvePrepareCapture(
            allowedBundleIds: allowed,
            hostBundleId: host,
            jpegQuality: quality,
            outputWidth: outputWidth,
            outputHeight: outputHeight,
            preferredDisplayId: preferredDisplayId,
            autoResolve: autoResolve,
            doHide: doHide
        )
    }
}

private final class EscapeHotkeyState {
    static let shared = EscapeHotkeyState()

    let lock = NSLock()
    var eventTap: CFMachPort?
    var runLoopSource: CFRunLoopSource?
    var callback: OpaquePointer?
    var expectedEscapes = 0

    func unregister() {
        lock.lock()
        defer { lock.unlock() }
        if let source = runLoopSource {
            CFRunLoopRemoveSource(CFRunLoopGetMain(), source, .commonModes)
        }
        if let eventTap {
            CGEvent.tapEnable(tap: eventTap, enable: false)
        }
        if let callback {
            napi_release_threadsafe_function(callback, napi_tsfn_release)
        }
        runLoopSource = nil
        eventTap = nil
        callback = nil
        expectedEscapes = 0
    }
}

private let escapeCallJs: napi_threadsafe_function_call_js = { env, callback, _, _ in
    guard let callback else { return }
    var global: OpaquePointer?
    var result: OpaquePointer?
    napi_get_global(env, &global)
    napi_call_function(env, global, callback, 0, nil, &result)
}

private let escapeEventCallback: CGEventTapCallBack = { _, type, event, _ in
    if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
        if let tap = EscapeHotkeyState.shared.eventTap {
            CGEvent.tapEnable(tap: tap, enable: true)
        }
        return Unmanaged.passUnretained(event)
    }
    guard type == .keyDown,
          event.getIntegerValueField(.keyboardEventKeycode) == 53
    else {
        return Unmanaged.passUnretained(event)
    }
    let state = EscapeHotkeyState.shared
    state.lock.lock()
    if state.expectedEscapes > 0 {
        state.expectedEscapes -= 1
        state.lock.unlock()
        return Unmanaged.passUnretained(event)
    }
    let callback = state.callback
    state.lock.unlock()
    if let callback {
        napi_call_threadsafe_function(callback, nil, napi_tsfn_nonblocking)
    }
    return Unmanaged.passUnretained(event)
}

private let registerEscapeMethod: napi_callback = { env, info in
    let values = args(env, info, max: 1)
    guard let callback = values.first ?? nil, valueType(env, callback) == napi_function else {
        return makeBool(env, false)
    }
    let state = EscapeHotkeyState.shared
    state.unregister()
    var threadsafe: OpaquePointer?
    let resource = makeString(env, "cu-esc-hotkey")
    guard napi_create_threadsafe_function(
        env,
        callback,
        nil,
        resource,
        0,
        1,
        nil,
        nil,
        nil,
        escapeCallJs,
        &threadsafe
    ) == napi_ok, let threadsafe
    else {
        return makeBool(env, false)
    }
    let mask = CGEventMask(1 << CGEventType.keyDown.rawValue)
    guard let tap = CGEvent.tapCreate(
        tap: .cgSessionEventTap,
        place: .headInsertEventTap,
        options: .defaultTap,
        eventsOfInterest: mask,
        callback: escapeEventCallback,
        userInfo: nil
    ), let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
    else {
        napi_release_threadsafe_function(threadsafe, napi_tsfn_release)
        return makeBool(env, false)
    }
    state.lock.lock()
    state.callback = threadsafe
    state.eventTap = tap
    state.runLoopSource = source
    state.lock.unlock()
    CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
    CGEvent.tapEnable(tap: tap, enable: true)
    return makeBool(env, true)
}

private let unregisterEscapeMethod: napi_callback = { env, _ in
    EscapeHotkeyState.shared.unregister()
    return makeUndefined(env)
}

private let notifyExpectedEscapeMethod: napi_callback = { env, _ in
    let state = EscapeHotkeyState.shared
    state.lock.lock()
    state.expectedEscapes += 1
    state.lock.unlock()
    return makeUndefined(env)
}

private extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}

@_cdecl("napi_register_module_v1")
public func napiRegisterModule(_ env: OpaquePointer?, _ exports: OpaquePointer?) -> OpaquePointer? {
    let computerUse = makeObject(env)
    let screenshot = makeObject(env)
    let apps = makeObject(env)
    let tcc = makeObject(env)
    let display = makeObject(env)
    let hotkey = makeObject(env)

    setFunction(env, object: computerUse, name: "_drainMainRunLoop", callback: drainMainRunLoopMethod)
    setFunction(env, object: computerUse, name: "_testEchoOptionalInt", callback: testEchoOptionalIntMethod)
    setFunction(env, object: computerUse, name: "resolvePrepareCapture", callback: resolvePrepareCaptureMethod)

    setFunction(env, object: screenshot, name: "captureExcluding", callback: captureExcludingMethod)
    setFunction(env, object: screenshot, name: "captureRegion", callback: captureRegionMethod)

    setFunction(env, object: apps, name: "appUnderPoint", callback: appUnderPointMethod)
    setFunction(env, object: apps, name: "findWindowDisplays", callback: findWindowDisplaysMethod)
    setFunction(env, object: apps, name: "iconDataUrl", callback: iconDataUrlMethod)
    setFunction(env, object: apps, name: "listInstalled", callback: listInstalledMethod)
    setFunction(env, object: apps, name: "listRunning", callback: listRunningMethod)
    setFunction(env, object: apps, name: "open", callback: openMethod)
    setFunction(env, object: apps, name: "prepareDisplay", callback: prepareDisplayMethod)
    setFunction(env, object: apps, name: "previewHideSet", callback: previewHideSetMethod)
    setFunction(env, object: apps, name: "resolveBundleIds", callback: resolveBundleIdsMethod)
    setFunction(env, object: apps, name: "unhide", callback: unhideMethod)

    setFunction(env, object: tcc, name: "checkAccessibility", callback: checkAccessibilityMethod)
    setFunction(env, object: tcc, name: "checkScreenRecording", callback: checkScreenRecordingMethod)
    setFunction(env, object: tcc, name: "requestAccessibility", callback: requestAccessibilityMethod)
    setFunction(env, object: tcc, name: "requestScreenRecording", callback: requestScreenRecordingMethod)

    setFunction(env, object: display, name: "getSize", callback: getDisplaySizeMethod)
    setFunction(env, object: display, name: "listAll", callback: listDisplaysMethod)

    setFunction(env, object: hotkey, name: "notifyExpectedEscape", callback: notifyExpectedEscapeMethod)
    setFunction(env, object: hotkey, name: "registerEscape", callback: registerEscapeMethod)
    setFunction(env, object: hotkey, name: "unregister", callback: unregisterEscapeMethod)

    napi_set_named_property(env, computerUse, "screenshot", screenshot)
    napi_set_named_property(env, computerUse, "apps", apps)
    napi_set_named_property(env, computerUse, "tcc", tcc)
    napi_set_named_property(env, computerUse, "display", display)
    napi_set_named_property(env, computerUse, "hotkey", hotkey)
    napi_set_named_property(env, exports, "computerUse", computerUse)
    return exports
}
