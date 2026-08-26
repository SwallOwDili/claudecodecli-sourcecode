# Browser and release QA

实现图、交互或发布时使用。

## SVG

- 优先复用 release-local SVG 和 editable source。
- `visualTarget` 命中 node id 或直接子 `<title>`。
- Graphviz 原始字号默认保留。
- 检查文字 bbox 落在 node shape 内。
- `rect/polygon/ellipse/path` 都适配深浅色。
- Root graph background 在深色模式透明。
- Portrait 图放在固定高度、内部纵向滚动的 region。
- 初始 viewport 至少有一个 node 可见。
- Active node 每一步都与 graph region 相交。
- 自动定位只改变 graph container scroll，不改变 document scroll。

## Keyboard and accessibility

- Tabs 使用 roving `tabindex`。
- 支持 ArrowLeft、ArrowRight、Home、End。
- 每个 `aria-controls` 指向真实 panel。
- Progressbar 有 accessible name。
- Space 快捷键不劫持 link、button、input、select、textarea、contenteditable 或 ARIA control。
- Reset 恢复默认输入、控制项、错误、tab 和回放位置。
- Heading level 与文章 H2/H3 层级一致。
- `prefers-reduced-motion: reduce` 禁用平滑动画。

## Mobile

在 `390x844` 检查：

- page `scrollWidth == clientWidth`；
- lab `scrollWidth == clientWidth`；
- 每个 scenario control bbox 完全在 lab bbox 内；
- 最长按钮、select、tab 和标题不被裁切；
- hidden overflow 不能掩盖内容；
- examples、tabs、graph、code、diff 只在自己的命名 region 滚动。

## Static fallback

- Fallback 是 custom element 直接 light-DOM child。
- 生成 HTML 中 custom element 的 parent 不是 `p`。
- JavaScript upgrade 后 fallback 隐藏。
- 禁用 JavaScript 后 fallback 可见，且没有运行按钮。
- 静态正文和 SVG 继续解释完整机制。

## Runtime boundary

- 浏览器内存 fixture；
- 不调用模型 API；
- 不要求 API key；
- 不访问真实工作区；
- 不运行真实 shell；
- 不发送输入到外部服务；
- 不使用 `eval`、iframe、远程 runtime CDN 或 sourcemap。

非 Lab 页不得加载 `cc-agent-lab.js`。用浏览器 resource entries 验证，不只看静态 script 标签。

生产 bundle 当前上限：`50 KiB gzip`。新增场景先复用 helper、减少重复或移除不必要依赖，不抬预算。

## Browser matrix

至少操作：

- 自定义成功路径；
- deny before side effect；
- failure after side effect；
- compact block/no Boundary；
- sandbox rejection；
- disk drift；
- light/dark；
- desktop/390px；
- reduced motion；
- no JavaScript；
- non-Lab lazy load。

## Clean CI

用 Workflow 的 sparse checkout 清单建立全新副本：

1. `npm ci`；
2. `npm run check:labs`；
3. 完整 Pages pipeline；
4. 隐私扫描；
5. actionlint。

测试本地 clone 时注入真实 GitHub repository URL；否则临时 clone 的本机 origin 会被隐私扫描正确拒绝。

## Live release

推送后验证：

- Workflow build/deploy success；
- deployment SHA 等于目标 commit；
- 线上 bundle SHA 等于本地；
- 线上代表场景可操作；
- 线上 390px/深色正常；
- 线上普通文章不加载 lab runtime。
