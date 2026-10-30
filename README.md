# Jianying Headless

**换机继续开发**：见 [Windows 开发交接](docs/WINDOWS-DEVELOPMENT-HANDOFF.md)，
包含 Git 历史恢复、Python 环境、本机配置和 [后续研究题目](docs/DEVELOPMENT-NEXT.md)。

**Codex / WorkBuddy 公共入口与实时编辑**：先读 [Agent 调用说明](docs/AGENT-ENTRY.md)，
运行 `jianying.ps1 agent doctor`。实时修改使用当前原生编辑会话，支持共享审计、请求去重和正常草稿发现。

面向剪映专业版的本地自动化工具。通过结构化剪辑计划生成可编辑草稿，
在独立副本中修改多轨工程，并调用本机剪映引擎导出 MP4。

**macOS：11.5.0 / 11.4.2；Windows：11.4.7.14462 / 11.5.0.14471（精确构建与 DLL 指纹）。**

**Windows 正常入口为 `jianying.ps1`**：读取本机配置，用官方 Lyra 创建、导入、同步和编辑已保存草稿，
再调用本机剪映引擎预览和导出视频。11.4.7 已验收多轨、关键帧、变速、本地静态字体和音频淡入淡出的
真实成片；`edit-actions` 提供精确参数编辑，`preview` 读取原生帧。11.4.7 另接入 14 个冻结视觉资源，
包括四种本地兼容转场及可调尺寸、位置、羽化和蒙版本体关键帧，逐项范围见
[Windows 视觉效果](docs/WINDOWS-VFX.md)。全部通过底层接口调用，
不依赖鼠标、键盘或桌面截图。
从 [Windows 调用指南](docs/WINDOWS-CLI.md) 开始，版本与验收边界见 [Windows 版本说明](docs/WINDOWS.md)。
直播切片先按[故事与干净粗剪](docs/WINDOWS-STORY-EDITING.md)审阅因果，再选择处理；
已有四位交付清单的修订、旧版恢复、素材去重及缓存回收见[固定交付与存储](docs/WINDOWS-DELIVERIES.md)。

macOS 首次使用可从 [从零生成第一个剪映草稿](docs/GETTING-STARTED.md) 开始。
教程包含安装前提、环境检查、拖入自己的视频、首页登记、保存重开和常见报错处理。
各平台均需匹配具体安装身份与工具链，尚不保证任意电脑安装即用。

项目适用于 AI 视频工作流的工程交接、批量草稿生成和 Agent 辅助剪辑。
提供 Python 命令行入口及配套 Agent Skill。它不是剪映官方 SDK，运行时需要安装匹配版本的剪映。

## 核心功能

| 功能 | 支持范围 |
| --- | --- |
| 生成可编辑草稿 | 视频分段、多轨组合、变速、音量、画中画、字幕和标题 |
| 导入本地素材 | 视频、PNG、JPEG、GIF、配音、音乐和音效 |
| 本地字体 | 新建文字或在副本中换字体，静态 OTF/TTF 随草稿保存；详见[字体说明](docs/LOCAL-FONTS.md) |
| 基础动画 | 位置、缩放、旋转、透明度和音量的线性关键帧 |
| 原生效果 | 六类静态几何蒙版、叠化转场、轻微抖动；需要匹配的本机资源与使用权限 |
| 官方能力 | 生成并应用 TTS、歌词动效和剪同款模板请求，并通过官方 Lyra 链路渲染；资源 ref 与执行上下文由当前官方 Agent 会话提供 |
| 自动歌词 | 使用本地 `faster-whisper` 从音频或 JYPACK 已用音乐区间生成逐词时间、SRT 和可直接构建的官方歌词计划 |
| JYPACK 检查 | 只读校验 JY/ZIP、加密时间线、TTS 音频、逐字歌词和官方模板包证据 |
| JYPACK 渲染 | 匹配剪映已导入的同一时间线，使用本机原生 ExportService 渲染 TTS、歌词模板、贴纸与动画 |
| 编辑已有工程 | 检查源草稿，在独立副本中修改，不覆盖原项目 |
| 原生视频导出 | 通过本机剪映引擎将已验证快照导出为 H.264/AAC MP4 |
| Windows 参数编辑 | `edit-actions` 直接调用官方 CLI，逐步核对位置/曲线关键帧、速度、音频淡化等原生保存值 |
| Windows 视觉效果 | 精确 11.4.7 的 14 个冻结资源，包含命名兼容转场和蒙版本体动画；用 `vfx catalog` 检查资源、`edit-actions` 写入并核对；见[资源与参数边界](docs/WINDOWS-VFX.md) |
| Windows 原生预览 | `preview` 在精确 11.4.7 上从官方播放器读取带时间戳帧，无需启动剪映 GUI |
| Windows 素材理解与剪辑 | `analyze` 将百炼云端 ASR、本地多宫格、Agent 证据审阅与候选精查接入原生构建、预览和导出；支持缓存与云任务恢复，见[素材分析闭环](docs/WINDOWS-MATERIAL-ANALYSIS.md) |
| 剪辑风格蒸馏与复用 | `style` 将真实参考片沉淀为条件规则、范例与冻结 profile，留出检验后应用于新素材；见[风格工作流](docs/WINDOWS-EDITING-STYLE.md) |
| 环境与工程检查 | 核对运行版本、组件身份、素材完整性和草稿保存结果 |

核心流程为：**素材与剪辑计划 → 可编辑剪映草稿 → 原生引擎导出**。
剪映中后续手工修改的内容不会自动同步回原计划或旧导出快照。
Windows 的 `export-draft` 读取已保存的磁盘工程；GUI 中未保存的修改需要先保存。
上表及案例中的复杂资源能力需结合各平台的验收范围使用，不能据此推定 Windows 已逐项验收。

剪映 11.5.0 自带 Agent Runtime 时，还可生成并应用 TTS、歌词动效和官方模板包的
`DraftEditing` 请求，再调用官方 Lyra 链路渲染。入口、计划格式和资源边界见[官方能力适配](docs/OFFICIAL-FEATURES.md)。

`engine/draftediting_runtime.py` 直接驱动官方 `lyra-cli` 的 blueprint 链路
（`init` → `sync` → `apply`），把 Selection Expression 应用到真实草稿。
宿主校验、命令契约、ASCII 路径、草稿根与主轨审计等实测硬约束见[官方 DraftEditing 链路](docs/DRAFTEDITING-RUNTIME.md)。

`engine/headless_pipeline.py` 把「自动识别 → 官方歌词模板 → TTS → 官方渲染」串成一条无人值守的命令，
对齐规则、每步产物与实测结果见[无头端到端流水线](docs/HEADLESS-PIPELINE.md)：

```powershell
python engine\headless_pipeline.py run `
  --draft "C:\...\com.lveditor.draft\my-draft" `
  --jypack C:\absolute\my-draft.jypack `
  --out C:\absolute\work\pipeline-run-1 --model large-v3 --render
```

Windows 可直接从音频或已导入的 JYPACK 自动生成歌词。JYPACK 模式会避开 TTS 轨，
识别实际使用的音乐区间，并把源音频时间换算到草稿时间轴：

```powershell
pip install -r requirements-lyrics.txt
python engine\lyrics_generate.py `
  --jypack C:\absolute\sample.jypack `
  --model large-v3 `
  --out C:\absolute\work\auto-lyrics
```

输出包含 `lyrics.json`、`lyrics.srt` 和 `official-features.plan.json`。模型默认只从本机缓存加载；
首次下载需显式添加 `--allow-download`。完整参数与调用链见[官方能力适配](docs/OFFICIAL-FEATURES.md)。

## Hypit 协作案例

一个约 **50.23 秒**的 IG 滚动动画教程展示了从 Hypit 到剪映的工程交接。
转换使用原工程的独立画面、配音、图片和文字时间安排，而不是仅导入一条最终成片。

| 工程内容 | 数量 |
| --- | --- |
| 原始素材 | 39 份 |
| 视频与图片 | 8 条轨道、38 个片段 |
| 独立配音 | 1 条轨道、7 个片段 |
| 可编辑文字 | 14 条轨道、109 个片段 |
| 合计 | 23 条轨道、154 个片段 |

该案例已在剪映 11.5.0 完成构建、打开播放、保存、完全退出、冷重开和结构回读，
并通过原生导出的 **1507 / 1507 帧**检查与完整解码检查。

### 画面对照

| Hypit 原成片 | 剪映工程原生导出 |
| --- | --- |
| ![Hypit 原成片六帧](docs/media/hypit-original-frames.png) | ![剪映导出六帧](docs/media/jianying-import-frames.png) |

两组图片均取自真实案例的 1、8、17、28、37、48 秒。展示的是可编辑工程交接，
**不是视觉无损转换**：特殊字体、逐词颜色动画、部分裁切与阴影未原样保留，
第 37 秒的补充画面也存在差异。完整主观视听验收尚未完成。

详见 [Hypit 协作案例](docs/HYPIT-COLLABORATION.md) 和 [媒体说明](docs/media/README.md)。
当前转换是单向、按项目实现；不提供任意 Hypit 工程的一键无损转换或双向同步。

## 运行环境

macOS：

- Apple Silicon Mac，macOS 26.0+；已验证环境为 macOS 26.5.1。
- 剪映专业版 11.5.0，或兼容配置对应的 11.4.2。
- Python 3.9+、FFmpeg / ffprobe、Xcode Command Line Tools。
- 已验证桥接工具链：Apple clang 21.0.0 / macOS SDK 26.5。

Windows：

- 64 位 Windows 10/11 与 64 位 Python 3.9+、FFmpeg / ffprobe。
- 剪映专业版 Windows **11.4.7.14462** 或 **11.5.0.14471**，分别绑定精确 DLL 哈希。
- Visual Studio 2022 Build Tools 的 MSVC x64、Windows SDK 和 `clang-cl`；原生助手按次编译。
- `local-settings.json` 配置安装目录、FFmpeg 和 ASCII 任务根目录，格式见 [配置示例](local-settings.example.json)。
- 支持官方 Lyra 编辑链及单时间线原生导出；11.4.7 另验收本地静态 TTF/OTF 字体、原生音频 fade 和帧预览，
  并提供 14 个逐项采集原生像素证据的视觉资源；资源及蒙版运行时均须匹配完整 SHA256 清单。
  旧 `native_edit` 副本编辑流程仍未在 Windows 验收。
- 完整说明见 [Windows 版本说明](docs/WINDOWS.md)。

应用版本、build、官方库哈希、签名与开发者身份均有检查。
未知版本或不匹配组件会被拒绝，不通过放宽校验强行运行。干净机器安装验收尚未完成。
官方引擎、账号数据、原始工程素材库和效果资源不随源码分发。

构建工具选择、安装诊断、登记恢复及字体支持的进展和待验限制见
[Issue 修复进展](docs/ISSUE-REMEDIATION.md)。环境检查通过不等于任意电脑兼容。

## 快速开始

macOS：

```bash
git clone https://github.com/mcncarl/jianying-headless.git
cd jianying-headless
python3 tools/build_native_codec.py
python3 skills/yichen-jianying-edit/scripts/headless_draft.py doctor
```

Windows 使用项目 `.venv` 与本机配置，先运行：

```powershell
.\jianying.ps1 doctor
.\jianying.ps1 workspace --name demo
.\jianying.ps1 lyra --help
.\jianying.ps1 vfx catalog
```

`doctor` 是**环境检查命令**：检查剪映版本、组件身份和必要工具。
检查通过表示环境符合运行条件，不代表任意草稿都已通过画面、声音或导出验收。

Windows 有两种导出输入：官方编辑后的已保存工程使用
`jianying.ps1 export-draft --draft-dir <工程目录> --out <新的ASCII工作目录>`；
JSON 计划先 `build`，再 `export --build <已验证构建> --out <新的ASCII工作目录>`。
完整创建、导入、Selection 编辑和回读示例见 [Windows 调用指南](docs/WINDOWS-CLI.md)。

需要程序化运动和淡入淡出时，先完成结构性 Selection 编辑，再按真实原生片段 ID 使用
[`edit-actions`](docs/WINDOWS-EDIT-ACTIONS.md)。随后用
[`preview`](docs/WINDOWS-NATIVE-PREVIEW.md) 检查选定时间点的原生画面，最后执行导出并检查声音。
`preview` 仅审核 11.4.7.14462 及四个精确组件指纹；少量帧预览不代替完整成片验收。
官方命令矩阵中 195 条是历史发现清单，不表示本机 195 条均已功能验收。

转场、滤镜、特效和蒙版使用 [Windows 视觉效果](docs/WINDOWS-VFX.md) 中的 14 个冻结资源，
共用动作计划、保存读回和审计。叠化、雾化通过独立命名的本地兼容包运行原始 shader，
应用原本的 GeneralEffect 路由未被修改；蒙版包含几何控制及现代软边资源的羽化动画。
准确 preset、参数与素材条件统一见该页。官方资源解析可能使用网络，预览和导出使用
本地依赖快照；Windows 没有额外网络沙箱，未审核资源继续按门禁停止。

桥接构建只编译项目源码并链接本机已安装程序库，不下载剪映、不修改官方库或账号权益。
编译结果必须匹配固定哈希，否则停止。

按 [计划格式](skills/yichen-jianying-edit/references/headless-macos.md) 准备 JSON，
或参考 [基础计划](examples/basic.plan.json) 和 [Hypit 交接格式示例](examples/hypit-handoff.plan.json)。
示例中的素材路径须替换为有权使用的本地文件。

```bash
python3 skills/yichen-jianying-edit/scripts/headless_draft.py build \
  --plan /absolute/path/to/plan.json --out "$PWD/work/new-build"
python3 skills/yichen-jianying-edit/scripts/headless_draft.py verify-build \
  --build "$PWD/work/new-build"
```

保存当前工作并完全退出剪映后，将新草稿登记到本机首页：

```bash
python3 skills/yichen-jianying-edit/scripts/headless_draft.py publish \
  --build "$PWD/work/new-build" --audit "$PWD/work/new-publish-audit"
```

`publish` 在此仅指本机首页登记，不是互联网发布。生成的草稿仍需实际打开、播放和保存检查。
需要成片时，可独立导出已验证快照：

```bash
python3 skills/yichen-jianying-edit/scripts/headless_draft.py export \
  --build "$PWD/work/new-build" --out "$PWD/work/new-export"
```

输出目录须不存在，成片为该目录下的 `render.mp4`。
导出在独立进程中运行；Windows 不提供 macOS `sandbox-exec` 的同等网络与文件隔离保证。

## Agent Skill

Windows 使用 `skills/jianying-windows/`，安装到当前 Codex 用户：

```powershell
.\.venv\Scripts\python.exe tools\install_codex_skill.py
```

技能绑定当前项目根目录并调用正常入口；项目移动后重新安装，个人路径保留在本地配置中。
可显式使用 `$jianying-windows`，流程见 [Windows 调用指南](docs/WINDOWS-CLI.md)。

`skills/yichen-jianying-edit/` 提供 Agent 调用入口、口播计划辅助脚本与操作参考。
Skill 不包含剪映引擎；独立安装后仍需检出核心项目，并指定其路径：

```bash
export JIANYING_HEADLESS_ROOT="/absolute/path/to/jianying-headless"
```

安装说明见 [独立 Skill](skills/yichen-jianying-edit/README.md)。
Skill 另收录于 [yichen-skills](https://github.com/mcncarl/yichen-skills/tree/main/yichen-jianying-edit)。

## 当前限制

- 复合片段仅支持实验性的离线修改与冻结快照导出，尚不能交付为保存可靠的可编辑嵌套草稿。
- 图片/GIF 样本曾出现间歇少一帧；严格帧数检查会拒绝缺帧输出，根因尚未解决。
- 不支持任意剪映版本、任意效果组合、在线模板、资源下载、云端工程或账号权益获取。
- 官方能力适配器不自行搜索或下载音色、歌词动画和模板；实际调用需要官方 Agent Runtime
  提供的 `blueprint_ref`，并继续受账号权益、资源许可和客户端版本约束。
- DraftEditing 的工作区、素材和 Selection 路径需为纯 ASCII。Windows 正常入口支持独立任务内的
  外部草稿父目录；官方 `--dir` 必须指向父目录，`local://名称` 对应其子目录。
- Windows 11.4.7 已验收本地单时间线多轨视频、源音频、基础文字、静态 TTF/OTF 字体、
  程序化关键帧与音频 fade，以及 [Windows 视觉效果](docs/WINDOWS-VFX.md) 的 14 个冻结资源。
  其范围外的复杂效果、蒙版、转场和模板仍按导出门禁拒绝未验组合，
  不会静默删掉效果；官方模板的多输入槽位文本分发尚未打通。
- 高清黑白滤镜与橙色描边花字已退出支持范围；含这些效果的计划或旧快照会明确报错。
- 工程结构检查、原生播放、视觉一致性、主观听感与素材许可是不同的验收项目。

详细结果及已知问题见 [验证状态](docs/VERIFICATION.md)。

## 项目结构与验证

| 目录 | 内容 |
| --- | --- |
| `engine/` | 草稿构建、独立副本编辑、资源校验与原生导出 |
| `bridge/` | 文件与管道桥接源码、保留来源声明的接口头文件 |
| `skills/` | Agent Skill 及配套参考 |
| `tools/`、`tests/` | 构建、源码包装检查与可移植测试 |
| `licenses/` | 第三方许可证 |

```bash
python3 tools/check_package.py
python3 -m unittest discover -s tests -v
```

专项原生测试的本机素材与证据不随仓库分发；源码检查不能替代实际工程验收。

## 许可与来源

原创部分采用 [个人学习和非商业使用许可](LICENSE)；商业使用需取得作者书面授权。
第三方内容继续适用原许可证，详见 [第三方声明](THIRD_PARTY_NOTICES.md)。
本项目不是 MIT / Apache-2.0 整包授权，代码许可也不包含剪映集成授权、账号权益或素材许可。
分发边界见 [分发范围](docs/DISTRIBUTION-SCOPE.md)。
