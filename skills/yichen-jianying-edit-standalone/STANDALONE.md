# 独立分发副本

本目录是 `skills/yichen-jianying-edit/` 的独立分发副本，两者内容同源，均取自本项目的
Windows 适配版本。设立本目录的唯一目的是便于**单独拷出安装**，不必从项目子目录中取出。

## 两个目录的关系

| 目录 | 用途 | 是否被校验 |
| --- | --- | --- |
| `skills/yichen-jianying-edit/` | 随项目分发的主副本；`tools/check_package.py` 与测试通过固定哈希校验它的入口脚本 | 是 |
| `skills/yichen-jianying-edit-standalone/` | 供单独拷贝到 Agent 的 skills 目录；不参与项目校验 | 否 |

**两者不是两个功能版本。** 校验只覆盖 `skills/yichen-jianying-edit/`，因此修改内置版后必须
同步本目录，否则独立副本的固定哈希会与内置版脱节，届时入口脚本会直接报
`Headless component changed`。

## 安装

1. 把本目录整体拷贝到 Agent 的 skills 目录，例如项目内的 `.agents/skills/`
   或用户级 skills 目录，并重命名为 `yichen-jianying-edit`。
2. 本 Skill **不含剪辑后端**，需要另行检出本项目，并把检出路径告诉 Skill：

```powershell
$env:JIANYING_HEADLESS_ROOT = "<本项目检出的绝对路径>"
```

macOS 用 `export JIANYING_HEADLESS_ROOT=...`，路径必须是绝对路径。

3. 校验入口：

```powershell
python scripts\headless_draft.py --help
```

`scripts/headless_draft.py` 会核对检出目录下 `engine/` 的 17 个组件固定哈希。
任一组件不同都会明确报错并停止，不会静默继续，也不接受相对路径。

## 支持范围

- **Windows**：剪映专业版 Windows 11.5.0.14471，支持草稿构建、首页登记、结构回读、离线计划，
  以及固定 DLL 指纹下的基础单时间线原生导出。
- **macOS**：Apple Silicon + 剪映 11.5.0 / 11.4.2，支持在副本中编辑已有工程与原生导出。
- Windows 原生导出暂不放行蒙版、转场、特效、复合片段和自定义字体。

完整说明见本项目 `docs/WINDOWS.md`；计划格式见 `references/headless-macos.md`。

## 上游与许可

`yichen-jianying-edit` 最初发布在 [mcncarl/yichen-skills](https://github.com/mcncarl/yichen-skills)。
该处的快照早于本副本：缺少 `references/hypit-handoff.md`，固定哈希对应旧 engine，
也没有 Windows 适配，因此**不能**与当前检出混用。

许可沿用本项目根目录的 `LICENSE`（个人学习和非商业使用），第三方内容见
`references/dependencies-and-notices.md` 与项目根目录的 `THIRD_PARTY_NOTICES.md`。
