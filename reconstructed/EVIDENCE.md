# 原生源码重建证据

## 共同边界

5 个 Mach-O 模块都没有可用的源码级 DWARF `.debug_info`。重建输入来自：

- `extracted/*.node` 的原始发布字节；
- `reverse/native/` 的多架构 headers、依赖、imports、exports、symbols、strings、Objective-C runtime、Swift demangle 和完整 text disassembly；
- `extracted/cli.js` / `reverse/javascript/cli.readable.js` 的真实调用点；
- 原版 `.node` 与重建 `.node` 的 Node 运行双探针。

原始注释、私有文件布局、被优化的局部名和编译器删除的分支不在发布产物中。下面每项使用 `Observed`、`Derived`、`Compatible` 分类。

## `audio-capture.node`

### Observed

- Rust、`napi-2.16.17`、`cpal-0.15.3`、`coreaudio-rs-0.11.3` 构建路径和错误字符串。
- 导出：`isPlaying`、`isRecording`、`stopPlayback`、`startPlayback`、`stopRecording`、`startRecording`、`writePlaybackData`、`microphoneAuthorizationStatus`。
- CLI 以 16 kHz、单声道、signed 16-bit PCM 消费录音数据。
- 导入 CoreAudio/AudioUnit；授权函数反汇编显示 `dlopen(AVFoundation)`、`dlsym(AVMediaTypeAudio)`、`AVCaptureDevice` 和 `authorizationStatusForMediaType:`。
- 原版初始探针为 `{ recording:false, playing:false, mic:0 }`；播放启动后 `isPlaying=true`，停止后立即为 `false`。

### Derived / Compatible

- CPAL stream 固定保存在专用音频线程，因为 macOS `Stream` 不能跨线程安全移动。
- 录音转换为 16 kHz mono PCM、静音阈值/持续时间和播放队列是根据 CLI 消费约定独立实现；内部滤波和缓冲策略不声明逐指令一致。

## `image-processor.node`

### Observed

- Rust、`image-0.25.10`、`image-webp-0.2.4`、`png-0.18.1`、`zune-jpeg-0.5.13` 路径。
- 导出：`processImage`、`hasClipboardImage`、`readClipboardImage`、`ImageProcessor`。
- prototype：`metadata`、`resize`、`jpeg`、`png`、`webp`、`toBuffer`、`dispose`。
- 原版返回 `{ width, height, format }`；变换方法返回同一对象；`toBuffer/dispose` 后使用统一 consumed 错误。
- 固定 1x1 RGBA PNG 双跑中，JPEG、PNG、WebP 的长度和 SHA-256 与原版逐字节相同。

### Derived / Compatible

- resize 的 `fit` 与 `withoutEnlargement` 分支由调用参数和 `image` crate 能力推导。
- 剪贴板尺寸字段由 loader/调用点和运行形状恢复；平台剪贴板错误按无图返回处理。

## `computer-use-input.node`

### Observed

- `enigo-0.6.1`、`objc2-app-kit` 和项目路径 `claude-native/src/input/enigo_wrap.rs`。
- 导出：`key`、`keys`、`typeText`、`moveMouse`、`mouseButton`、`mouseScroll`、`mouseLocation`、`getFrontmostAppInfo`。
- 二进制保留 F1-F20、左右修饰键、媒体/亮度/照明/Launchpad/Mission Control/Numpad 等 Enigo key 名。
- 原版错误文本已逐项运行确认，包括 `No keys provided`、invalid key/action/button/axis。
- 原版链接 AppKit 并保留 `NSWorkspace`、`frontmostApplication`、`localizedName`、`bundleIdentifier`；重建直接使用同一路径。

### Derived / Compatible

- 键盘和鼠标实际注入交给同版本 Enigo；自动化验证只执行坐标/前台应用只读调用和输入校验错误，不主动发送真实键鼠事件。
- 发布模块包含 x86-64 + arm64；当前重建只在 arm64 实际构建运行。

## `computer-use-swift.node`

### Observed

- Swift 模块名 `ComputerUseSwift`；原模块每个架构保留 1,237 个 demangled Swift symbols。
- 顶层 `computerUse` 及 `screenshot`、`apps`、`tcc`、`display`、`hotkey`、`resolvePrepareCapture` 完整导出树。
- ScreenCaptureKit 的 display/application/window/filter/configuration/capture 路径；AppKit 应用管理；CGEvent tap；TCC APIs。
- Spotlight 反汇编直接读取 `kMDItemCFBundleIdentifier`、`NSMetadataItemPathKey`、`NSMetadataItemDisplayNameKey`，并检查 `LSBackgroundOnly` / `LSUIElement`。
- 图标函数反汇编显示 `64x64`、RGBA、device RGB、NSGraphicsContext、`.copy`、PNG。
- 原版应用列表保留 Spotlight 顺序和重复 bundle ID；当前机器两版语义列表均为 247 条且逐项一致。
- `appUnderPoint` 返回 Dock 等覆盖窗口，不过滤系统 UI，并且结果没有 `pid`。
- 显示器、TCC、optional integer、运行应用、图标、全屏截图和区域截图已实测。

### Derived / Compatible

- N-API Promise/async work、Foundation JSON 转换和 main-run-loop pump 是根据导出行为独立重建。
- 屏幕像素会随桌面实时变化，因此截图验证比较字段、尺寸和 JPEG magic，不比较连续两帧的完整字节。
- 窗口/隐藏集合按原版探针恢复为 layer 0 可见窗口语义；同优先级窗口的内部枚举顺序不作为稳定接口。
- ESC event tap 已实现，但自动验证不注入真实 Escape 事件。

## `url-handler.node`

### Observed

- Rust/N-API 导出 `waitForUrlEvent`。
- `AEInstallEventHandler`、`AEGetParamPtr`、`GURL`、direct object 和 UTF-8 Apple Event 路径。
- CLI 调用 `waitForUrlEvent(5000)`；原版和重建版 `1ms` 无事件超时都返回 `null`。

### Derived / Compatible

- 广播 channel 容量、内部 URL buffer 上限和并发等待组织方式是独立实现；公开的事件/超时结果保持兼容。

## 验证命令

```bash
reconstructed/scripts/build_and_validate.sh extracted /tmp
```

脚本每次创建唯一加载目录，避免覆盖已映射的 Mach-O。契约定义在 `contracts/module-exports.json`，行为比较实现在 `scripts/compare_behaviors.mjs`。

归一化结果固化到 `analysis/runtime-probes/native-reconstruction.json`。其中 `Observed` 只描述 original 发布模块和原版运行输出，`Compatible` 只描述独立重建；arm64 实际双跑与 x86_64 静态-only 边界分别记录，测试通过不会把 Compatible 升格成 Observed。
