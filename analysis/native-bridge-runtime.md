# Native Bridge 与 JavaScript Runtime

Claude Code 的主控制面在 bundled JavaScript 中，但图像、音频、键鼠、截图、应用/TCC 和 URL event 等能力通过 5 个 `.node` 模块进入 macOS 原生框架。要理解这些功能，必须把三层连起来：JavaScript 调用点定义产品语义，N-API export 定义 ABI 合同，Rust/Swift/Mach-O 分析解释底层实现。

## 五个 native module 在运行时的位置

`reverse/javascript/cli.readable.js` 45-57 通过 Bun standalone 虚拟路径加载：

| Module | 语言证据 | JavaScript 侧用途 |
| --- | --- | --- |
| `image-processor.node` | Rust + `image` ecosystem | 图像 metadata、resize、JPEG/PNG/WebP、clipboard image |
| `computer-use-swift.node` | Swift + AppKit/ScreenCaptureKit/CoreGraphics | 截图、显示器、应用发现、TCC、ESC hotkey |
| `computer-use-input.node` | Rust + Enigo/AppKit | 键盘、鼠标、滚轮、前台应用 |
| `audio-capture.node` | Rust + CPAL/CoreAudio/AVFoundation | 录音、播放、PCM、麦克风授权 |
| `url-handler.node` | Rust + Carbon Apple Events | 等待 `GURL` URL event |

```text
bundled JS
   |
   | require('/$bunfs/root/<module>.node')
   v
N-API exports / objects / prototypes / Promise callbacks
   |
   v
Rust or Swift runtime
   |
   v
macOS frameworks / devices / TCC / event loop
```

Native module 不是独立服务。它们在同一个进程地址空间内运行；panic、ABI mismatch、线程/回调错误可以直接影响 CLI 进程。

## 三种证据等级不能混淆

- **Observed**：发布字节、N-API export、Mach-O import/export、字符串、Swift demangle、反汇编或原版 probe 直接证实。
- **Derived**：由调用参数、上下游结构和底层依赖推导。
- **Compatible**：独立重写后通过行为双跑，但不等于上游原函数体。

完整逐模块分类见 [reconstructed/EVIDENCE.md](../reconstructed/EVIDENCE.md)。没有源码级 DWARF/source map 时，原始注释、局部名、文件边界、泛型写法和优化删除的分支无法逐字恢复。

## JavaScript wrapper 为什么是产品合同

`.node` export 只说明函数存在。真正的产品语义还由 JS wrapper 决定：

- 何时 lazy load；
- 不支持平台时返回 null、false 还是抛错；
- 参数如何归一化；
- Promise/stream callback 如何接入 React/Agent Loop；
- 资源何时 dispose；
- native error 如何转成用户提示；
- 权限检查发生在调用前还是 native 内部。

因此 native 逆向不能只输出 symbol/strings。每个 export 都要回到主 JS 找 consumer。

## Image processor：一次性资源对象

JavaScript wrapper 在 `reverse/javascript/cli.readable.js` 198380-198392：

1. 读取 native module；
2. module 不可用时抛 `Native image processor module not available`；
3. 调用 `processImage(input)` 得到 native `ImageProcessor`；
4. 再调用 `metadata/resize/jpeg/png/webp/toBuffer/dispose`。

原版 probe 证实 transform 方法返回同一 JavaScript 对象，支持链式调用；`toBuffer` 或 `dispose` 后再次访问会返回统一 consumed error。这说明对象持有 native buffer/decoder state，`toBuffer` 是消费边界，而不是无状态纯函数。

### 生命周期

```text
input Buffer/Data URL
      -> processImage
      -> native ImageProcessor owns decoded state
      -> resize/encode mutate or configure same object
      -> toBuffer OR dispose
      -> consumed; later calls fail
```

用户影响：忘记消费/释放会延长内存占用；重复调用不能假设幂等。重建验证对固定 1x1 RGBA PNG 的 JPEG、PNG、WebP 输出做了精确字节比较。

## Computer Use Swift：高层 macOS 能力树

`computer-use-swift.node` 顶层导出 `computerUse`，再分为：

- `screenshot.captureExcluding/captureRegion`；
- `apps.listInstalled/listRunning/open/iconDataUrl/appUnderPoint/...`；
- `tcc.checkAccessibility/checkScreenRecording/request...`；
- `display.listAll/getSize`；
- `hotkey.registerEscape/unregister/notifyExpectedEscape`；
- `resolvePrepareCapture` 与测试/run-loop helper。

每个架构保留 1,237 个 demangled Swift symbols。静态证据显示 ScreenCaptureKit、AppKit、CoreGraphics、Spotlight metadata、CGEvent tap 与 TCC API。

### 截图不是简单 `CGDisplayCreateImage`

调用链需要处理 display、window/application exclusion、目标尺寸、JPEG quality、权限和异步 capture。结果字段包含 base64、width、height；base64 是裸 JPEG，不带 Data URL prefix。连续桌面帧不稳定，因此 probe 验证字段、尺寸、JPEG magic 和语义，不比较两次真实截图的完整 SHA-256。

### App discovery 的微小语义

- installed apps 使用 Spotlight metadata；
- 保留 Spotlight 顺序和重复 bundle ID；
- icon 路径重绘为透明 64x64 PNG；
- `appUnderPoint` 可返回 Dock 等覆盖窗口；
- 结果是 `{bundleId, displayName}`，不额外返回 `pid`。

这些小行为决定 UI/自动化调用者的兼容性，不能被“列出应用”四个字替代。

### TCC 是显式状态，不是异常文本

Accessibility 与 Screen Recording 有 check/request 两套调用。用户拒绝、未决定、已允许应映射成稳定状态；请求授权通常需要主线程/run loop 协调。Native bridge 不能把 TCC dialog 当成普通工具 permission：前者是 macOS 系统权限，后者是 Claude Code 的动作授权，两层都可能阻止执行。

## Computer Use Input：实际外部副作用边界

`computer-use-input.node` 导出：

- `key/keys/typeText`；
- `moveMouse/mouseButton/mouseScroll/mouseLocation`；
- `getFrontmostAppInfo`。

原模块保留 Enigo key mapping，包括 F1-F20、左右修饰键、媒体/亮度/照明、Launchpad、Mission Control 和 numpad。输入校验错误已用无副作用 probe 验证，例如空 keys、invalid key/action/button/axis。

这里的风险边界很清楚：schema/permission/hook 通过后，native call 会向 OS 注入真实输入，之后的 model fallback 或 transcript rewind不能撤销点击、按键和已触发的外部应用动作。自动测试默认只跑只读状态和校验错误，不主动发送真实键鼠事件。

## Audio capture：线程、采样与授权

`reverse/javascript/cli.readable.js` 362436-362498 展示 audio bridge：

- 尝试 embedded/相对路径 module；
- module 不可用返回 null；
- forward `startRecording/stopRecording/isRecording`；
- forward playback 与 `microphoneAuthorizationStatus`；
- 在 voice app state 中缓存 lazy-load Promise 和 module。

静态证据保留 `napi-2.16.17`、`cpal-0.15.3`、`coreaudio-rs-0.11.3`。CPAL stream 需要专用音频线程；CLI 侧消费 16kHz mono signed 16-bit PCM。授权路径动态加载 AVFoundation 并调用 `authorizationStatusForMediaType:`。

### 音频状态机

```text
lazy load module
  -> query microphone authorization
  -> startRecording(callback)
  -> native audio thread emits PCM/silence events
  -> JS forwards into voice state
  -> stopRecording

playback: startPlayback -> writePlaybackData* -> stopPlayback
```

原版 probe 证实初始 `{recording:false, playing:false, mic:0}`，播放启动后 `isPlaying=true`，停止后立即 false。音频重采样、静音阈值和内部 buffer policy 属于兼容重建，不声明逐指令相同。

## URL handler：Apple Event 与超时

JS wrapper 在 `reverse/javascript/cli.readable.js` 604122-604133 lazy load module；不可用返回 null，否则调用 `waitForUrlEvent(timeout)`。Mach-O import/反汇编显示 `AEInstallEventHandler`、`AEGetParamPtr`、`GURL` direct object 和 UTF-8 decode。

这条能力用于 macOS URL scheme/登录回调一类事件。原版与重建版 `waitForUrlEvent(1)` 在无事件时都返回 null。超时是正常结果，不应自动当成 module crash。

## N-API 边界要检查什么

每个版本至少比较：

1. 顶层 export 名；
2. object tree 和 prototype method；
3. sync/Promise/callback 形态；
4. 参数数量、可选值、null/undefined 语义；
5. 返回 object 字段；
6. error type/message；
7. resource ownership/dispose；
8. thread-safe function 和 abort；
9. 每个 architecture slice；
10. linked framework/dependency version。

只比较 `_napi_register_module_v1` 或导出数量无法发现字段/生命周期漂移。

## 原版与重建版双跑

[module-exports.json](../reconstructed/contracts/module-exports.json) 固化 5 个模块的 function/object/prototype contract。[build_and_validate.sh](../reconstructed/scripts/build_and_validate.sh) 会：

- 格式/编译 4 个 Rust crate 和 1 个 Swift package；
- 把产物复制到全新临时目录并改成原 `.node` 文件名；
- 分别加载 original 与 reconstructed；
- 比较 exports 和 23 组行为；
- 避免覆盖已经映射的 Mach-O。

当前 arm64 结果：

```text
native contract validation: PASS
modules checked: 5
native behavior comparison: PASS
checks passed: 23
reconstructed native validation: PASS
```

通过说明重建实现满足当前检查过的外部合同，不说明内部算法等同原始源码。

## 架构与平台边界

发布产物中 `computer-use-input.node` 和 `computer-use-swift.node` 含 arm64 + x86_64 slice；其他模块的归档架构见 [native-architectures.txt](../reverse/index/native-architectures.txt)。当前可编译重建只在 arm64 macOS 实际运行。

跨版本应分别比较 slice。universal module 的一个 slice 未变化，不代表另一个 slice 未变化；arm64 probe 也不能替代 x86_64 execution evidence。

## 失败与恢复

| 失败 | JS 层应观察到 | 恢复方向 |
| --- | --- | --- |
| module 缺失/加载失败 | null/false 或明确 unavailable error | 平台/安装检查，禁用 surface |
| N-API shape 漂移 | method undefined / argument error | 版本成套安装 |
| TCC 未授权 | check state/request failure | 用户在系统设置授权 |
| screenshot capture fail | rejected Promise/null | display/window/permission 诊断 |
| audio device fail | start false/error callback | 设备/采样/授权诊断 |
| input validation fail | 稳定参数错误 | 模型或 schema 修正 |
| native crash | CLI 进程退出 | crash report + exact module hash |

Native 操作已经改变外部状态时，Agent Loop 的 message tombstone、resume repair 和 fallback 不能撤销它。键鼠/应用打开需要幂等策略或人工确认。

## 微小但关键的特性

- `ImageProcessor` 是一次性消费对象，不是每次调用重新 decode。
- screenshot base64 不带 Data URL prefix。
- installed apps 保留重复 bundle ID 和 Spotlight 顺序。
- `appUnderPoint` 结果不带 pid。
- optional integer 的 null/undefined 都映射 Swift nil。
- URL timeout 返回 null，是正常无事件状态。
- audio module lazy-load 后缓存在 app state。
- module unavailable 的 JS 行为因模块而异：有的抛错，有的返回 null/false。
- 已加载 `.node` 不能在原路径热替换后继续可靠测试。

## 证据与边界

结构化证据条目：`native.bundle-entrypoints`、`native.image-call`、`native.audio-call`、`native.url-call`。完整 Mach-O 证据在 [reverse/native](../reverse/native)，归一化 ABI/依赖/Swift symbol diff 在 [reverse/index](../reverse/index)。

本仓库已经尽可能恢复发布物可观察合同和兼容源码；它不是 Anthropic 构建前的原始 C/C++/Rust/Swift 仓库。缺失源码级 debug info 后，内部文件布局、注释、优化前函数体和被编译器删除的代码不能逐字恢复。
