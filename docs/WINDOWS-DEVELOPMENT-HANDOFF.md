# Windows 换机继续开发

本次交接日期：2026-10-30。开发仓库：
<https://github.com/hrbj18/jianying-headless-windows>。
原仓库保留为 upstream：
<https://github.com/huangrunze168-sketch/jianying-headless-windows>。

压缩包中的 `jianying-headless-windows/` 是带完整 main 分支历史的 Git 工作副本，
可直接作为新电脑的开发项目。包内 `HANDOFF-MANIFEST.json` 记录精确提交、文件摘要、
打包验证和内容范围；`repository.bundle` 是独立的 Git 历史恢复副本。
打包时仅保存已提交的项目字节，不复制当前运行中的编辑会话。

## 1. 解压及核对版本

用支持 UTF-8 和隐藏文件的解压工具解压整个包，保留 `.git/`。
项目位置可以包含中文；实际工作区和官方 CLI 的素材/草稿路径仍使用 ASCII。

```powershell
Set-Location 'D:\Development\jianying-headless-windows'
git status --short
git log -1 --oneline
git remote -v
```

应无未提交修改，提交应与包根的 `HANDOFF-MANIFEST.json` 相同。
`origin` 指向 hrbj18 的开发仓库，`upstream` 指向原仓库。GitHub 凭据需在新电脑自行登录。
若解压工具遗漏 `.git`，可在一个不存在的新目录恢复历史：

```powershell
git clone 'D:\Transfer\repository.bundle' 'D:\Development\jianying-headless-restored'
git -C 'D:\Development\jianying-headless-restored' remote set-url origin https://github.com/hrbj18/jianying-headless-windows.git
git -C 'D:\Development\jianying-headless-restored' remote add upstream https://github.com/huangrunze168-sketch/jianying-headless-windows.git
```

不要直接复制旧 `.venv`；其解释器和脚本包含旧电脑路径。

## 2. 安装本机前提

- 64 位 Windows 10/11；本轮开发使用 Python 3.12.8 x64，建议以 Python 3.12 x64 恢复。
- 剪映专业版精确构建 **11.4.7.14462**：本轮实时编辑、原生预览与扩展使用此版本。
  11.5.0.14471 的离线范围见 [Windows 说明](WINDOWS.md)，不能代替实时编辑绑定。
- FFmpeg 与 ffprobe。
- Visual Studio 2022 Build Tools：MSVC x64、Windows SDK、LLVM 的 clang-cl。
- Git；需要继续 REA 研究时，另安装匹配 REA 及其 Ghidra/Java 工具链。

官方剪映安装包、DLL、效果资源、字体、原始视频、模型缓存和账号数据不在源码包内。
桥接 DLL `bridge/live-editor/live-qt-pipe-v02.dll` 是本项目自有组件，随源码按原摘要保留。
不要修改原生 ABI、官方签名检查或指纹来适配不同构建。

## 3. 重建 Python 环境

在项目根执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-production.txt
.\.venv\Scripts\python.exe -m pip check
```

生产依赖覆盖公共入口、素材分析、字体和原生调用。需要本地歌词/Whisper 时再安装
[requirements-lyrics.txt](../requirements-lyrics.txt)。
[requirements-dev-windows-observed.txt](../requirements-dev-windows-observed.txt) 是本机完整已安装
Python 包版本快照，包含可选分析依赖；它用于对照和尽量重建旧环境，不代表已完成干净机器安装验收。
需要恢复该快照时，在新环境中使用 `pip install -r requirements-dev-windows-observed.txt`。

## 4. 新建本机配置

复制 [local-settings.example.json](../local-settings.example.json) 为项目根的 `local-settings.json`，
填写新电脑的 `jianying_install_dir`、`ffmpeg_bin`、`workspace_root`、`draft_root` 与
`draft_index_path`。`workspace_root` 应使用例如 `D:\JianyingHeadless\work` 的 ASCII 路径。
草稿实际存放根和 AppData 下的首页索引可能不在同一磁盘，以新电脑实际配置为准。

百炼凭据单独恢复到本机私有环境或凭据文件；可用 `DASHSCOPE_API_KEY`、
`DASHSCOPE_WORKSPACE_ID` 环境变量，或在 `analysis.credential_files` 填写私有文件绝对路径。
凭据文件格式及任务恢复见 [素材分析](WINDOWS-MATERIAL-ANALYSIS.md)。
源码包不携带 API Key、上传授权、临时云地址或已登录会话。

## 5. 体检及源码检查

```powershell
.\jianying.ps1 agent --client codex doctor
.\.venv\Scripts\python.exe tools/check_package.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_package.py -v
```

doctor 必须返回 `ready`。本轮源电脑体检通过；这不代替新电脑的实际体检。
包根的校验脚本可独立核对解压内容；不要把文件摘要正确当作剪辑质量正确。
新电脑没有当前旧会话，所有 PID、birth、draft/session、QObject 指针和请求状态均需重新发现。
若要继续旧视频工程，需另行迁移工程及其完整媒体、Resources 并重新验收引用。

## 6. 安装 Agent 技能及继续研究

可将本项目技能绑定到新位置：

```powershell
.\.venv\Scripts\python.exe tools/install_codex_skill.py --name jianying-windows
```

若新电脑已存在同技能且绑定其他目录，先确认用途，再按安装器说明使用 `--rebind`。
公共入口与编辑约束见 [Agent 调用说明](AGENT-ENTRY.md)。
本轮深入研究方向和证据边界见 [后续开发题目](DEVELOPMENT-NEXT.md)。

`cli-anything`、`haike-workflow-2` 和 `rea` 是独立项目，不属于本源码仓库；
它们的完整工作副本、配置和凭据未合并进此包。现有 `analyze` 已将所需素材分析适配接入本项目，
基础剪映入口无需从旧电脑导入海客仓库。若继续跨项目修改，应另行克隆/迁移这些项目，
保留各自版本、许可证和原始素材。不要把旧文档中的本机证据绝对路径理解为随包存在。

## 交接范围

保留源码、测试、文档、公开示例、自有桥及哈希清单、main 分支历史、观察到的依赖版本。
不包含 `.venv`、运行缓存、用户草稿/素材、云任务私有记录、凭据与官方程序。
历史研究文档引用的外部原始证据目录未随包迁移；其结论仍保留原有验收边界。
完整新电脑运行、原生编辑与导出需在新环境重新验证。
