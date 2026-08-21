# 可编译的原生模块源码重建

本目录包含 Claude Code CLI `2.1.235` 内 5 个 `.node` 模块的独立 Rust/Swift 重建。目标是尽可能恢复可读、可编译、可由 Node 直接加载且对外行为兼容的源码，不把它表述为 Anthropic 构建前的原始源码仓库。

## 证据等级

- **Observed**：由 N-API 导出、JavaScript 调用点、Mach-O 依赖、字符串、Swift demangle、反汇编或原版运行探针直接证实。
- **Derived**：由已证实的调用签名、数据结构和上下游约束推导出的实现。
- **Compatible**：编译已经抹去原函数体后独立编写的兼容实现，通过原版/重建版双跑验证其外部行为。

逐模块证据和边界见 [`EVIDENCE.md`](EVIDENCE.md)。

## 目录

```text
reconstructed/
|-- Cargo.toml
|-- Cargo.lock
|-- contracts/module-exports.json
|-- rust/
|   |-- audio-capture/
|   |-- computer-use-input/
|   |-- image-processor/
|   `-- url-handler/
|-- swift/computer-use-swift/
|-- scripts/
|   |-- build_and_validate.sh
|   |-- compare_behaviors.mjs
|   |-- probe_swift.mjs
|   `-- validate_contracts.mjs
`-- EVIDENCE.md
```

## 已重建模块

| 发布模块 | 重建语言 | 主要能力 |
| --- | --- | --- |
| `audio-capture.node` | Rust | 录音、静音回调、PCM 播放、状态查询、麦克风授权状态 |
| `image-processor.node` | Rust | 图像元数据、resize、JPEG/PNG/WebP、一次性 buffer、剪贴板图像 |
| `computer-use-input.node` | Rust | 键盘、组合键、文本、鼠标、滚轮、坐标和前台应用 |
| `computer-use-swift.node` | Swift | 截图、显示器、应用发现/隐藏/激活、TCC、ESC hotkey |
| `url-handler.node` | Rust | macOS `GURL` Apple Event 等待与超时 |

Rust 依赖版本尽量对齐发布二进制保留的构建路径和字符串，包括 `napi 2.16.17`、`cpal 0.15.3`、`image 0.25.10`、`enigo 0.6.1`。Swift 模块使用 AppKit、ApplicationServices、CoreGraphics 和 ScreenCaptureKit，并导出 Node 可识别的 `_napi_register_module_v1`。

## 关键微小行为

- `ImageProcessor.resize/jpeg/png/webp` 返回同一个 JavaScript 对象，支持链式调用。
- `toBuffer` 或 `dispose` 后再次访问会返回原版错误：`ImageProcessor already consumed (toBuffer/dispose was called)`。
- 1x1 固定输入的 JPEG、PNG、WebP 输出字节和原版 SHA-256 完全一致。
- 输入模块拒绝空组合键，并保留原版参数错误文本；F1-F20、左右修饰键、媒体键、亮度键、Launchpad 等名称已映射。
- `microphoneAuthorizationStatus` 按原版动态加载 AVFoundation，而不是固定返回值。
- 已安装应用直接读取 Spotlight 的 bundle ID、路径和本地化显示名；保留顺序和重复项，不自行去重。
- 应用图标按反汇编恢复为透明 `64x64` bitmap 重绘，实测 Data URL 字节与原版一致。
- `appUnderPoint` 返回 `{ bundleId, displayName }`，不会多带 `pid`。
- 截图 `base64` 是裸 JPEG base64，不带 Data URL 前缀。
- `prepareDisplay` 和 `unhide` 保留 Promise 返回约定；可选整数 `undefined/null` 都映射为 Swift `nil`。
- `waitForUrlEvent(1)` 在未收到事件时与原版一样返回 `null`。

## 构建与双跑验证

一条命令会格式检查、构建 4 个 Rust 动态库和 1 个 Swift 动态库，然后创建全新的测试目录，将产物复制为原模块名，再分别验证原版和重建版：

```bash
reconstructed/scripts/build_and_validate.sh extracted /tmp
```

脚本故意使用 `mktemp` 创建唯一目录。不要覆盖已经被 Node 进程加载的 `.node` 文件；macOS 动态加载器可能仍在读取原 Mach-O 映射，原地替换会让测试进程卡住。

当前验证包括：

- 5 个模块的顶层导出、`ImageProcessor` prototype 和 `computerUse` 对象树；
- 图像元数据、链式返回、一次性消费错误和 JPEG/PNG/WebP 精确字节；
- 音频初始状态、麦克风授权值和 URL 超时；
- 鼠标/前台应用只读结果，以及 6 类无副作用输入错误；
- 显示器、TCC、运行/已安装应用、bundle ID 解析、窗口显示器、隐藏预览、命中应用和图标；
- 全屏/区域截图的字段、尺寸和 JPEG 格式。

当前 arm64 macOS 实测输出：

```text
native contract validation: PASS
modules checked: 5
native behavior comparison: PASS
checks passed: 23
reconstructed native validation: PASS
```

逐检查机器报告写入 [`analysis/runtime-probes/native-reconstruction.json`](../analysis/runtime-probes/native-reconstruction.json)。它不保存本机原始路径或实时桌面内容，只保存比较项、模块、比较模式、输入策略、PASS/FAIL 和架构覆盖。validator 要求 23 项全部通过，并要求 x86_64 边界保持显式。

## 重建边界

当前源码能在本机 arm64 macOS 编译和加载。发布产物中两个 Computer Use 模块还包含 x86-64 slice；仓库保留了该架构的完整静态分析，但没有在本机交叉构建和运行 x86-64 重建产物。机器报告分别标成 `runtime-and-static`、`static-only`、`build-and-runtime`、`not-built-or-run`，避免把 universal 原版模块误写成 universal 兼容重建。

没有源码级 DWARF、source map 或上游仓库时，原始注释、局部变量名、文件拆分、泛型写法、内部辅助类型以及编译器删除的代码无法逐字恢复。音频重采样/静音检测、部分窗口选择顺序和错误分支属于兼容重建；这些位置必须继续用 `Compatible` 标注，不能因测试通过而改称 Anthropic 原始源码。
