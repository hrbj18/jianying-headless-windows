# Windows 版本说明

本分支在原项目（面向剪映专业版 macOS 的自动化工具）基础上增加 Windows 支持。
Windows 版直接把剪映 Windows 安装目录里的 `videoeditor.dll` 当作草稿加解密引擎，
并针对 Win32 重新实现了事务锁、文件身份校验、安全描述符复制与排他放置。

**已审核构建：剪映专业版 Windows 11.4.7.14462 和 11.5.0.14471。**

正常调用使用项目根目录的 `jianying.ps1`；首次操作从 [Windows 调用指南](WINDOWS-CLI.md) 开始。
本机路径填写在根目录 `local-settings.json`，该文件不进入版本库。

## 支持矩阵

| 能力 | Windows 10/11 x64 | macOS |
| --- | --- | --- |
| 环境体检 `doctor` | 支持 | 支持 |
| JSON 构建 `build` / 官方新建 `lyra create` | 支持 | 使用对应平台入口 |
| 构建快照校验 `verify-build` | 支持 | 支持 |
| 登记到剪映首页 `publish` / `resume-publish` | 支持 | 支持 |
| 首页回读 `verify` | 支持 | 支持 |
| 离线计划编译与音频审听 `edit_plan.py` | 支持 | 支持 |
| 官方 Lyra 新建、导入、同步与 Selection 编辑 | 11.4.7 已完成真实闭环 | 使用对应官方运行时 |
| 官方 typed 参数批处理 `edit-actions` | 11.4.7 已验收位置/曲线关键帧、变速、音频淡化，逐步原生读回 | 使用对应平台入口 |
| 视觉资源 `vfx catalog` / `edit-actions` | 精确 11.4.7 的 14 个冻结资源，含兼容转场、蒙版几何及羽化动画；完整摘要和逐项像素证据；见 [VFX 范围](WINDOWS-VFX.md) | 使用对应平台资源 |
| 编辑已有工程副本 `edit` | 未验证 | 支持 |
| 原生导出 MP4 `export` | **支持（固定 ABI，见限制）** | 支持 |
| 导出已保存的磁盘工程 `export-draft` | 11.4.7 已验收多轨、基础文字、静态 TTF/OTF 字体及原生音频 fade | 使用对应平台入口 |
| 原生播放器帧预览 `preview` | 仅精确 11.4.7.14462，独立后台服务，无需 GUI | 使用对应平台入口 |
| 源码包完整性检查 `tools/check_package.py` | 支持 | 支持 |

Windows 运行时和原生导出只对以下精确身份启用：

| EXE 文件版本及版本目录名 | `videoeditor.dll` SHA-256 |
| --- | --- |
| `11.4.7.14462` | `fa89997a94e96cf97c8ee436a56ab028ea5f87731214696ba43ff74c0fdc0fa0` |
| `11.5.0.14471` | `37cadef37daff82e2ecdcd65080b9cbd7f6f9436f5e56c1ffb90c52c408eb7fb` |

适配层在隔离子进程中构造时间线、等待 `restoreDraft` 完成，再调用剪映自身的 `ExportService`；
版本或指纹不同会在加载原生地址前失败关闭（fail closed）。逆向证据和验收记录见
[Windows 原生导出 ABI 证据](WINDOWS_NATIVE_EXPORT.md)。

## 环境要求

| 项目 | 要求 |
| --- | --- |
| 系统 | 64 位 Windows 10 / 11 |
| Python | 3.9 或以上，且必须是 **64 位** |
| 剪映 | 剪映专业版 Windows **11.4.7.14462** 或 **11.5.0.14471** |
| 安装位置 | 配置的精确版本目录，或默认 `%LOCALAPPDATA%\JianyingPro\Apps\<build>\`，包含 `videoeditor.dll` 与 `JianyingPro.exe` |
| 草稿目录 | `%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft` |
| 其它工具 | FFmpeg / ffprobe；Visual Studio 2022 Build Tools 的 MSVC x64、Windows SDK 和 `clang-cl` |

参考 [配置示例](../local-settings.example.json) 填写 `jianying_install_dir`、`ffmpeg_bin`、
`workspace_root`。入口自动使用项目 `.venv` 并配置当前进程路径，不必更改系统 PATH。
发现顺序为显式环境变量、个人配置、默认 Apps 版本目录。环境变量设置后只使用该指定目录：

```powershell
$env:JIANYING_INSTALL_DIR = "C:\path\to\11.4.7.14462"
```

版本目录名、`JianyingPro.exe` 的真实 PE 文件版本、`videoeditor.dll` 的 SHA-256 和 EXE 的 Authenticode 发布者
（深圳市脸萌科技有限公司）都会被校验。版本不一致时直接拒绝，**不会**放宽校验强行运行。

## 快速开始

```powershell
.\jianying.ps1 doctor
.\jianying.ps1 workspace --name demo
.\jianying.ps1 lyra --help
```

`doctor` 返回 `status: ready` 表示精确构建、签名、FFmpeg 及原生工具链已通过检查。
`workspace` 创建独立 ASCII 任务，随后按 [Windows 调用指南](WINDOWS-CLI.md) 执行
`lyra init/create/resource-import/sync/apply`。官方动作会复用或启动已验签的剪映宿主；
编辑对象为已保存磁盘状态，GUI 内未保存的修改需先保存。

结构性 Selection 编辑完成后，位置关键帧、曲线、速度及淡入淡出使用
[`edit-actions`](WINDOWS-EDIT-ACTIONS.md) 的精确原生片段 ID 动作计划。它通过官方 typed CLI
规避 11.4.7 Blueprint 的 X/Y 关键帧协议冲突，每步核对真实保存值，并保留执行前工程副本；
失败立即停止，批次不保证原子提交。
动作间的并发变化检查不等于原子锁；执行期间不要让 GUI 或其他任务同时修改同一工程。

转场、滤镜、特效和蒙版另读 [Windows 视觉效果](WINDOWS-VFX.md)：先 `vfx catalog`
检查 14 个冻结资源，再将视觉动作放入同一 `edit-actions` 计划。四种命名兼容转场在官方原生
引擎运行原始 shader；蒙版可调几何、现代软边包羽化及五个本体动画通道的准确范围统一见该页。
源包及所需 48 文件内建运行时须匹配完整摘要。官方资源解析可能使用网络。
蒙版的指定字段、协议及现代包路径由项目兼容模块调用官方 `EncryptUtils` 协调到声明主时间线，
保留前后密文和审计。根镜像不自动整体同步；正常主时间线读回、原生渲染与 GUI 冷重开是不同
验收，GUI 冷重开尚未完成。

需要检查画面时，使用 [`preview`](WINDOWS-NATIVE-PREVIEW.md) 从官方播放器取得原生帧：

```powershell
.\jianying.ps1 preview --draft-dir C:\task\work\drafts\demo `
  --out C:\task\work\preview --at 0.5 1.5 --width 960
```

预览另校验四个官方播放器组件 SHA256，只启用精确 11.4.7.14462；成功返回
`native-frames-captured`，验证帧包、时间戳和源数据不变。编辑、预览和导出均为底层接口调用，
没有鼠标、键盘或桌面截图控制。预览和导出可独立于 GUI 宿主运行。

官方编辑后直接导出工程：

```powershell
.\jianying.ps1 export-draft --draft-dir C:\task\work\drafts\demo `
  --out C:\task\work\render-from-draft
```

也可从 JSON 计划构建不可变快照，再导出该快照：

```powershell
.\jianying.ps1 build --plan C:\task\plan.json --out C:\task\work\build
.\jianying.ps1 verify-build --build C:\task\work\build
.\jianying.ps1 export --build C:\task\work\build --out C:\task\work\render-from-build
```

输出目录必须不存在、为绝对路径且位于 `work` 目录下；官方 CLI 的任务、素材和工程路径使用 ASCII。
原生预览和 `export-draft` 可读取中文源工程，复制媒体和字体到 ASCII 输出任务；需要继续
用官方 CLI 编辑的工程应使用 ASCII 目录名。
构建和任务内官方编辑不要求登记到剪映首页。只有用户需要首页可见时，才保存工作并完全退出剪映后运行：

```powershell
.\jianying.ps1 publish --build C:\task\work\build --audit C:\task\work\publish-audit
```

`publish` 只表示本机首页登记；打开、保存、冷重开后仍需回读检查。
导出成功时 `result.json` 为 `encoded-and-decoded`，且 `render.mp4` 已通过 `ffprobe`、
帧数/时长校验和 `ffmpeg -xerror` 完整解码。原生助手按次从源码编译，源工程与素材导出后重新验哈希。
实际画面和声音还需验收。

为 Codex 安装正常调用技能：

```powershell
.\.venv\Scripts\python.exe tools\install_codex_skill.py
```

`jianying-windows` 绑定当前项目并调用 `jianying.ps1`，项目移动后重新安装。

## 与原 macOS 版的差异

| 方面 | macOS | Windows |
| --- | --- | --- |
| 应用身份 | `Info.plist` + `libvideoeditor.dylib` SHA-256 | PE 版本资源 + `videoeditor.dll` SHA-256 |
| 签名校验 | `codesign` + `TeamIdentifier` | Authenticode (`WinVerifyTrust`) + 发布者证书主体 |
| 草稿加密 | 编译 `jy14_codec.cpp` 链接 `.dylib` | 由 `bridge/windows_crypto.py` 隔离子进程调用 `videoeditor.dll` |
| 时间线文件 | `draft_info.json` | `draft_content.json` |
| 安全属性 | 扩展属性（`xattr`） | 文件 DACL（整对象复制，提交前逐字节校验） |
| 事务锁 | `fcntl.flock`（目录 fd） | `msvcrt.locking`（`.jianying-headless.lock`） |
| 排他放置 | `renamex_np(RENAME_EXCL)` | `os.rename`（目标存在即失败） |
| 原生导出 | `xcrun` + `sandbox-exec` | `clang-cl /MD` + 隔离子进程 + 固定 DLL RVA |

新增文件：

- `engine/windows_runtime.py` — Windows 运行时适配（发现安装、体检、签名、加密桥接、锁、DACL、快照）。
- `bridge/windows_crypto.py` — 调用 `videoeditor.dll` 的 `EncryptUtils` 导出符号进行加解密。
- `engine/native_export_windows.cpp` — Windows MSVC ABI 原生恢复与导出桥接。
- `tools/windows_native_toolchain.py` — 发现 `vcvars64.bat` 与 `clang-cl`，按次构建隔离助手。
- `jianying.ps1` / `jianying.py` — 使用本机配置的正常命令入口。
- `engine/local_config.py` — 读取不入库的个人路径与任务目录。
- `engine/windows_edit_actions.py` — 严格动作计划、官方 typed CLI 和逐步原生读回。
- `engine/windows_native_preview.py` / `windows_preview_client.mjs` — 官方播放器 IPC、VEF1 校验和 PNG 预览。
- `engine/windows_vfx.py` / `windows-vfx-catalog.json` — 14 个精确视觉资源、参数、绑定与完整摘要门禁。
- `engine/windows_mask_controls.py` / `windows_mask_keyframes.py` — 蒙版几何、羽化、本体动画及窄范围读回协调。
- `engine/windows_mask_protocol.py` / `windows-mask-runtime.json` — 蒙版协议兼容及 48 文件运行时清单。
- `engine/windows_transition_compat.py` / `windows_transition_adapters/` — 可复现构建四种命名兼容转场，保留原 shader 与来源证据。
- `skills/jianying-windows/` — Codex 调用流程。
- `tests/test_windows_runtime.py` — 真机事务、加解密回环与平台门禁测试。

macOS 的 `engine/native_export.cpp` 与 `tools/build_toolchain.py` 保持原样；运行时按平台选择适配层。

## 安全边界

- 官方引擎、账号数据、原始素材与效果资源**不随源码分发**；加解密全部调用本机已安装的剪映。
- 草稿加解密和原生导出均在隔离子进程中执行，避免 ABI 不匹配导致主进程崩溃。
- Windows 导出在 Python 侧先校验精确版本、DLL SHA-256 与 Authenticode；C++ 中的 RVA 只对已审核构建启用。
- `restoreDraft` 使用经 RTTI 与 `.pdata` 确认的客户端封装 RVA `0x11c41a0`；不会调用
  含 member `this`、hidden sret 和请求 `shared_ptr` 的 handler RVA `0x1e263d0`。
- 首页登记是事务性的：先准备并校验索引与安全描述符，再放置草稿，最后替换索引；
  任一步失败都会保留审计目录（`failure.json`）并给出恢复建议，**不会**回滚或删除已完成部分。
- 复制的是文件 DACL 而非扩展属性；登记过程中不会剥离任何安全属性。

## 已知限制

- 仅支持上表的两个精确构建。其它补丁版本需要重新采集应用身份、ABI、草稿结构与成片证据后加入。
- `edit`（在副本中修改已有工程）在 Windows 上仍未验证。
- 上述 `edit` 指旧 `native_edit` 路线；官方 Lyra 的已保存工程 Selection 编辑已在 11.4.7 验收。
- Windows 11.4.7 原生导出已验收本地单时间线的多轨视频、程序化关键帧、源音频、基础文本、
  静态本地 TTF/OTF 字体和双边原生音频 fade（type 4）。视觉扩展开放 14 个精确冻结资源，
  具体参数、素材余量和动画时序见 [VFX 范围](WINDOWS-VFX.md)，组合后仍需查看正式输出。
  GeneralEffect 原包直接路由的兼容缺口由单独命名的叠化/雾化资源包适配，不宣称修改了应用原路由。
  其它特效、滤镜、蒙版、复合片段和模板等未验组合保持失败关闭；这些扩展不自动继承到 11.5。
- 蒙版支持两种已审核 circle 资源的尺寸、位置和本体关键帧；现代 `mask/circle-soft` 支持羽化
  及其动画，旧 circle 羽化仍固定为 0。等宽高归一化参数在 16:9 画布上会呈椭圆。
  跟踪、反转、任意形状及其它时序条件不由这些资源自动获得支持。
- `audio.fade` 的单边 0 值可完成官方编辑，但本机构建会产生尚未验收的 fade type 2/3；
  当前原生导出仅支持已验收的双边 type 4，仍检查实际保存类型。
- 未在第二台独立的 Windows 机器上完成完整验收；`project.json` 的
  `clean_machine_acceptance` 仍为 `not-completed`。
- 不同步 GUI 中未保存的内存时间线；复杂资源和未测试的官方命令不因基础闭环通过而自动视为支持。
- [官方命令矩阵](LYRA-CLI-MATRIX.md) 的 195 条为历史接口发现清单，不表示本机全部功能验收。
- `edit-actions` 的官方转场/蒙版资源解析可能使用网络；预览和导出使用本地依赖快照。
  Windows 没有 macOS `sandbox-exec` 的等价文件/网络沙箱；输入仍复制到新建 job，且源构建与依赖在导出后重新验哈希。

## 排错

| 看到什么 | 原因或下一步 |
| --- | --- |
| `未找到已审核的 Windows 剪映构建` | 检查个人配置或 `JIANYING_INSTALL_DIR`；目录、EXE 文件版本和 DLL 哈希须同时匹配上表 |
| `videoeditor.dll` 指纹不匹配 | 该补丁版本的库与已审版本不同；需要重新采集并登记新 profile，不要修改期望哈希 |
| `Windows 剪映 Authenticode 签名或发布者验证失败` | 安装包来源可疑或文件被改动；请从官方渠道重新安装 |
| `剪映默认本地草稿目录尚未初始化` | 先打开剪映、创建并保存一个空白工程、正常退出 |
| `剪映主进程仍在运行` | 通过剪映菜单完全退出，而不是只关闭窗口 |
| `提交前无法保留文件 DACL` | 安全描述符在快照之后发生变化；检查是否有其它程序在改 `root_meta_info.json` |
| `No reviewed native export ABI` | 构建 profile 与当前安装不一致；在当前已审核版本重新构建草稿 |
| 未审核的 Windows VFX 材质或资源摘要不匹配 | 运行 `vfx catalog` 检查本机绑定；只使用 [VFX 范围](WINDOWS-VFX.md) 的已审核资源和参数，保留工程并报告未知资源，不静默删效果 |
| `未找到 clang-cl` / `未找到 Visual Studio x64 C++ 工具链` | 安装 LLVM for Windows 与 Visual Studio 2022 Build Tools 的 Desktop C++ 组件 |
| 中文输出乱码 | 设置 `$env:PYTHONUTF8 = "1"` 与 UTF-8 代码页 `chcp 65001` |

## 验证命令

```powershell
python tools\check_package.py
python -m unittest discover -s tests -v
.\jianying.ps1 doctor
python tools\smoke_windows.py
```
