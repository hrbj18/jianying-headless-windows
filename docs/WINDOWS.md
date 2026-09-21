# Windows 版本说明

本分支在原项目（面向剪映专业版 macOS 的自动化工具）基础上增加 Windows 支持。
Windows 版直接把剪映 Windows 安装目录里的 `videoeditor.dll` 当作草稿加解密引擎，
并针对 Win32 重新实现了事务锁、文件身份校验、安全描述符复制与排他放置。

**已审核版本：剪映专业版 Windows 11.5.0.14471。**

## 支持矩阵

| 能力 | Windows 10/11 x64 | macOS |
| --- | --- | --- |
| 环境体检 `doctor` | 支持 | 支持 |
| 生成可编辑草稿 `build` / `create` | 支持 | 支持 |
| 构建快照校验 `verify-build` | 支持 | 支持 |
| 登记到剪映首页 `publish` / `resume-publish` | 支持 | 支持 |
| 首页回读 `verify` | 支持 | 支持 |
| 离线计划编译与音频审听 `edit_plan.py` | 支持 | 支持 |
| 编辑已有工程副本 `edit` | 未验证 | 支持 |
| 原生导出 MP4 `export` | **支持（固定 ABI，见限制）** | 支持 |
| 源码包完整性检查 `tools/check_package.py` | 支持 | 支持 |

Windows 原生导出只对 `videoeditor.dll` SHA-256
`37cadef37daff82e2ecdcd65080b9cbd7f6f9436f5e56c1ffb90c52c408eb7fb` 启用。
适配层在隔离子进程中构造时间线、等待 `restoreDraft` 完成，再调用剪映自身的 `ExportService`；
版本或指纹不同会在加载原生地址前失败关闭（fail closed）。逆向证据和验收记录见
[Windows 原生导出 ABI 证据](WINDOWS_NATIVE_EXPORT.md)。

## 环境要求

| 项目 | 要求 |
| --- | --- |
| 系统 | 64 位 Windows 10 / 11 |
| Python | 3.9 或以上，且必须是 **64 位** |
| 剪映 | 剪映专业版 Windows **11.5.0.14471**，安装在默认位置 |
| 安装位置 | `%LOCALAPPDATA%\JianyingPro\Apps\11.5.0.14471\`（含 `videoeditor.dll` 与 `JianyingPro.exe`） |
| 草稿目录 | `%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft` |
| 其它工具 | `ffmpeg`、`ffprobe`、`clang-cl` 在 `PATH` 中；Visual Studio 2022 Build Tools（MSVC x64） |

安装目录也可用环境变量显式指定：

```powershell
$env:JIANYING_INSTALL_DIR = "C:\path\to\11.5.0.14471"
```

版本号、`videoeditor.dll` 的 SHA-256 和 `JianyingPro.exe` 的 Authenticode 发布者
（深圳市脸萌科技有限公司）都会被校验。版本不一致时直接拒绝，**不会**放宽校验强行运行。

## 快速开始

```powershell
git clone https://github.com/mcncarl/jianying-headless.git
cd jianying-headless
$env:PYTHONUTF8 = "1"
python tools\start_here.py check
```

`check` 会逐项输出 `PASS` / `WARN` / `FAIL`。没有 `FAIL` 后，用一段至少 2 秒的
H.264 / yuv420p 视频生成第一个草稿：

```powershell
python tools\start_here.py build --source "D:\videos\clip.mp4"
```

成功标志是输出 `"status": "build-verified"`，并在 `work\first-draft-*\` 中留下
`next-steps.md`（本次命令）与 `next-steps.json`（机器可读记录）。

保存剪映中的工作并**完全退出剪映**（关闭窗口不等于退出），然后执行 `next-steps.md`
里的 **publish** 命令登记到本机首页：

```powershell
python skills\yichen-jianying-edit\scripts\headless_draft.py publish `
  --build work\first-draft-xxxx\build --audit work\first-draft-xxxx\publish-audit
```

打开剪映，首页应出现该草稿；播放、保存、退出再冷重开后，执行 **verify** 命令回读校验。

`publish` 只表示“登记到本机剪映首页”，不会上传到互联网。

导出已验证构建（输出目录必须是新的绝对 `work` 目录）：

```powershell
python engine\native_export.py `
  --build (Resolve-Path work\first-draft-xxxx\build) `
  --out "$PWD\work\native-export-001" `
  --bitrate 8000000 --timeout 600
```

成功时 `result.json` 为 `encoded-and-decoded`，且 `render.mp4` 已通过 `ffprobe`、帧数/时长校验和
`ffmpeg -xerror` 完整解码。原生助手按次从源码编译，不会把剪映官方 DLL 放进仓库。

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
- `tests/test_windows_runtime.py` — 真机事务、加解密回环与平台门禁测试。

macOS 的 `engine/native_export.cpp` 与 `tools/build_toolchain.py` 保持原样；运行时按平台选择适配层。

## 安全边界

- 官方引擎、账号数据、原始素材与效果资源**不随源码分发**；加解密全部调用本机已安装的剪映。
- 草稿加解密和原生导出均在隔离子进程中执行，避免 ABI 不匹配导致主进程崩溃。
- Windows 导出在 Python 侧先校验版本、DLL SHA-256 与 Authenticode；C++ 中的 RVA 只对该指纹启用。
- `restoreDraft` 使用经 RTTI 与 `.pdata` 确认的客户端封装 RVA `0x11c41a0`；不会调用
  含 member `this`、hidden sret 和请求 `shared_ptr` 的 handler RVA `0x1e263d0`。
- 首页登记是事务性的：先准备并校验索引与安全描述符，再放置草稿，最后替换索引；
  任一步失败都会保留审计目录（`failure.json`）并给出恢复建议，**不会**回滚或删除已完成部分。
- 复制的是文件 DACL 而非扩展属性；登记过程中不会剥离任何安全属性。

## 已知限制

- 仅支持 **11.5.0.14471**。其它 11.5.x 补丁版本需要重新采集应用身份、草稿根与结构基线后才能加入。
- `edit`（在副本中修改已有工程）在 Windows 上仍未验证。
- Windows 原生导出当前只验收了本地单时间线的视频、源音频与基础文本；蒙版会明确拒绝，
  复合片段、转场、特效等资源仍需分别补充 Windows 像素级验收。
- 未在第二台独立的 Windows 机器上完成完整验收；`project.json` 的
  `clean_machine_acceptance` 仍为 `not-completed`。
- Windows 没有 macOS `sandbox-exec` 的等价文件/网络沙箱；输入仍复制到新建 job，且源构建在导出后重新验哈希。

## 排错

| 看到什么 | 原因或下一步 |
| --- | --- |
| `未找到已审核的 Windows 剪映 11.5.0.14471` | 安装版本不匹配；用 `JIANYING_INSTALL_DIR` 指定 11.5.0.14471 目录，或升级/降级到该版本 |
| `videoeditor.dll` 指纹不匹配 | 该补丁版本的库与已审版本不同；需要重新采集并登记新 profile，不要修改期望哈希 |
| `Windows 剪映 Authenticode 签名或发布者验证失败` | 安装包来源可疑或文件被改动；请从官方渠道重新安装 |
| `剪映默认本地草稿目录尚未初始化` | 先打开剪映、创建并保存一个空白工程、正常退出 |
| `剪映主进程仍在运行` | 通过剪映菜单完全退出，而不是只关闭窗口 |
| `提交前无法保留文件 DACL` | 安全描述符在快照之后发生变化；检查是否有其它程序在改 `root_meta_info.json` |
| `No reviewed native export ABI` | 构建 profile 与当前安装不一致；在当前已审核版本重新构建草稿 |
| `Windows 原生导出暂未审核蒙版` | 当前固定 ABI 不导出蒙版/特效；先移除该资源或在剪映界面导出 |
| `未找到 clang-cl` / `未找到 Visual Studio x64 C++ 工具链` | 安装 LLVM for Windows 与 Visual Studio 2022 Build Tools 的 Desktop C++ 组件 |
| 中文输出乱码 | 设置 `$env:PYTHONUTF8 = "1"` 与 UTF-8 代码页 `chcp 65001` |

## 验证命令

```powershell
python tools\check_package.py
python -m unittest discover -s tests -v
python engine\jy14_headless.py doctor
python tools\start_here.py check
```
