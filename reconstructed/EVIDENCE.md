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
- 原版 JS wrapper 只把 native callback 收到的 bytes 原样上抛，不声明采样率转换；SoX fallback 明确指定 `-r 16000 -e signed -b 16 -c 1`，Voice WebSocket query 声明 `encoding=linear16`、`sample_rate=16000`、`channels=1`。这些构成可观察的 fallback/wire 消费合同，不证明原版 native 内部采用了同一条转换实现。
- 导入 CoreAudio/AudioUnit；授权函数反汇编显示 `dlopen(AVFoundation)`、`dlsym(AVMediaTypeAudio)`、`AVCaptureDevice` 和 `authorizationStatusForMediaType:`。
- 原版初始探针为 `{ recording:false, playing:false, mic:0 }`；播放启动后 `isPlaying=true`，停止后立即为 `false`。

### Derived / Compatible

- CPAL stream 固定保存在专用音频线程，因为 macOS `Stream` 不能跨线程安全移动。
- 原版 native 内部是否以及怎样完成 16 kHz/mono/s16 重采样仍未从静态证据恢复。重建版的录音转换、静音阈值/持续时间和播放队列根据 SoX/wire 消费合同独立实现；测试通过也不把内部滤波和缓冲策略升级成原始源码事实。

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
- 原版错误文本已逐项运行确认，包括 `No keys provided`、invalid key/action/button/axis 和 Accessibility `NoPermission`；探针还确认不同 API 在创建 Enigo 前后的参数校验顺序并不相同。
- 原版链接 AppKit 并保留 `NSWorkspace`、`frontmostApplication`、`localizedName`、`bundleIdentifier`；重建直接使用同一路径。

### Derived / Compatible

- 键盘和鼠标实际注入交给同版本 Enigo；自动化验证只执行坐标/前台应用只读调用和输入校验错误，不主动发送真实键鼠事件。
- 发布模块包含 x86-64 + arm64；x86 报告验证 supplied compatible artifact 的架构、身份分离、load/export 和 Rosetta runtime，并对两个原版 slice 做同输入行为比较。Rust/Swift 命令只作为 build recipe 保存，报告不把它们写成本次构建证据。

## `computer-use-swift.node`

### Observed

- Swift 模块名 `ComputerUseSwift`；原模块每个架构保留 1,237 个 demangled Swift symbols。
- 顶层 `computerUse` 及 `screenshot`、`apps`、`tcc`、`display`、`hotkey`、`resolvePrepareCapture` 完整导出树。
- ScreenCaptureKit 的 display/application/window/filter/configuration/capture 路径；AppKit 应用管理；CGEvent tap；TCC APIs。
- Spotlight 反汇编直接读取 `kMDItemCFBundleIdentifier`、`NSMetadataItemPathKey`、`NSMetadataItemDisplayNameKey`，并检查 `LSBackgroundOnly` / `LSUIElement`。
- 图标函数反汇编显示 `64x64`、RGBA、device RGB、NSGraphicsContext、`.copy`、PNG。
- 原版应用列表保留 Spotlight 顺序和重复 bundle ID；发布二进制还保留 `NSMetadataQuery failed to start (Spotlight may be indexing or disabled)`。本次隔离运行中 Spotlight 无法启动，原版和重建版都以同一 rejected Promise 合同结束。
- `appUnderPoint` 返回 Dock 等覆盖窗口，不过滤系统 UI，并且结果没有 `pid`。
- `computeHideCandidates` 在调用方豁免集合上固定 union `com.apple.finder`，并从 `CGWindowListCopyWindowInfo` 结果中只接受 layer 0、alpha 严格大于 `0.1`、与目标显示器相交且可解析 PID 的窗口。该路径没有 `width/height > 1` 条件；源码里的尺寸门属于窗口显示器归属和普通激活候选逻辑。Swift 大字符串对象使用 cstring 前 `0x20` 字节的编码基址：arm64 静态项 `0x8000000000025220` 对应实际 cstring `0x25240 = com.apple.finder`，不能直接误读成从 `0x25220` 开始的 loginwindow。
- `previewHideSet` 把调用参数转成 Set，并把可选 display ID 解析成指定显示器；缺失或无效 ID 回退主显示器 frame。`prepareDisplay` 在调用公共 helper 前又额外把 host bundle ID 与 Finder 加入豁免集合，原版保留了这层冗余。
- [`validate_computer_use_semantics.mjs`](scripts/validate_computer_use_semantics.mjs) 把上述易误读点固化成发布门：同时检查 arm64/x86_64 原版常量、Finder 字符串对象编码、关键反汇编指令和兼容 Swift 源码结构。截图合同不是脚本内硬编码自证：发布门会从两个原版 slice 的静态数组对象逐项解码 8 个 Swift String，并核对数组初始化、元素数、`computeExcludedApps -> Set.contains` 消费链、full/region nil 分支、cstring 地址和 79/75 字节长度；兼容源码还按函数绑定对应错误文本、`captureScreen` 对 `systemChromeBundleIds` 的 union 和 `failureMessage` catch。脚本会在内存中分别删掉 union、替换 catch，证明两种漂移都会被拒绝。这样可避免仅凭一次桌面 Probe 掩盖静态语义漂移。
- 截图使用另一组精确的 8 项系统界面 bundle ID：Dock、Wallpaper Agent、Control Center、SystemUIServer、TextInputSwitcher、WiFiAgent、AccessibilityUIServer、loginwindow；不含 Finder、Notification Center 或 screencaptureui。
- full/region 截图底层返回 nil 时分别拒绝为 `Screenshot capture returned nil (permission missing or SCContentFilter failure)` 和 `Region capture returned nil (permission missing or SCContentFilter failure)`。
- TCC、optional integer、运行应用、显示器尺寸、命中应用、图标、Spotlight 失败合同及 full/region screenshot 结构已实测；动态 hide 候选按 bundle ID 归序后深比较完整成员和字段。截图比较字段、尺寸、显示器元数据、规范 Base64 及 JPEG SOI/EOI，并由对应原版/重建版图像模块实际解码，要求格式为 JPEG 且宽高等于截图返回值；不比较实时像素字节。只有双方返回同一条已知环境错误才记 `environment-boundary`。比较前旧报告会失效，PASS/FAIL 都原子写入，失败运行不会保留旧 PASS。

### Derived / Compatible

- N-API Promise/async work、Foundation JSON 转换和 main-run-loop pump 是根据导出行为独立重建。
- 屏幕像素会随桌面实时变化，因此截图验证比较字段、尺寸、显示器元数据、JPEG SOI/EOI 及真实解码后的格式/宽高，不比较连续两帧的完整字节。
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

arm64 归一化结果固化到 `analysis/runtime-probes/native-reconstruction.json`，x86_64/Rosetta 结果固化到 `analysis/runtime-probes/native-reconstruction-x86.json`。其中 `Observed` 只描述 original 发布模块和原版运行输出，`Compatible` 只描述独立重建。x86 报告把 5/5 supplied compatible artifact 的架构、非同 hash、load/export 验证与两个 original/compatible Computer Use slice 的同输入行为比较分开；其他三个模块没有 original x86 slice，测试通过也不会把 compatible-only 加载升级成 Observed 行为相同。该报告 method 为 `validated-artifacts-and-runtime`，不证明同次新鲜构建。
