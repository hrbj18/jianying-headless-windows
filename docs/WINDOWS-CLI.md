# Windows 正常调用入口

在项目根运行 `.\jianying.ps1 --help`。
这个入口使用项目 `.venv`，读取根目录 `local-settings.json`，配置当前进程的媒体工具路径。
本机路径不进入版本库；格式见 [配置示例](../local-settings.example.json)。

受支持构建是 **11.4.7.14462** 与 **11.5.0.14471**，各自绑定已审核 DLL SHA256。
会核对 EXE 的实际文件版本、DLL 指纹及官方发布者。没有通配版本或自动登记新哈希。
`preview` 另限精确 **11.4.7.14462**，并校验原生播放器的四个组件指纹。
编辑、预览和导出通过官方 CLI、VMSDK、原生服务 IPC 或 ExportService 执行；不使用鼠标、键盘
或桌面截图。官方编辑链需要已验签 GUI 宿主进程；原生预览和导出可独立运行。

## 体检和任务目录

```powershell
.\jianying.ps1 doctor
.\jianying.ps1 workspace --name demo
```

`doctor` 成功返回 `status: ready`。`workspace` 返回新的 `job`、`draft_root`、`blueprint`
和建议的 `local://` 引用。以下命令中的 `$job` 使用该返回值；目录应含 `work` 且为 ASCII。
官方本地引用名称可能跨父目录共享，工程名称应使用任务返回的唯一名称，避免重复 `local://demo`。
源码仓库可以放在中文目录；视频文件如在中文路径，先原样复制到任务目录再导入。
需要后续用官方 CLI 编辑的工程目录名也使用 ASCII。`preview` / `export-draft` 能读取中文源工程，
并将依赖复制到新的 ASCII 任务目录；这不改变官方 CLI 的路径限制。

## 从直播录像挑选片段

需要理解本地视频、直播或长录像时，先读[素材分析闭环](WINDOWS-MATERIAL-ANALYSIS.md)，
使用 `analyze prepare/read/submit/detail/assemble`。`prepare` 生成真实帧证据并可显式调用百炼 ASR；
Agent 查看多宫格、引用语句和格子后提交候选，再精查切点。`assemble --render` 接入下述同一原生
构建、预览和导出链。更改剪辑目标会建立新的审阅记录，并复用相同素材的截图与云端转写缓存。

选段后读[故事判断与干净粗剪](WINDOWS-STORY-EDITING.md)，用 `story compile` 编译原速原声
和普通字幕，先审因果、接话与回报，再比较各层处理的新增信息和注意力成本。

## 固定交付与存储

已有四位交付清单的修订使用[固定交付、归档与素材存储](WINDOWS-DELIVERIES.md)中的
`delivery inspect/promote`，替换对应交付位并归档旧版；试剪留在任务目录。首次独立交付才用
`publish`。同页提供 `media-store` 不可变素材复用和 `cache prepare/apply` 的清单回收边界，
原件、可编辑元数据和验收依据保持独立，空间报告区分逻辑大小与实际分配量。

## 官方编辑链

参考成片风格与直播风格复用使用 `style prepare/read/distill/inspect/assemble`，
读[剪辑风格蒸馏与复用](WINDOWS-EDITING-STYLE.md)。风格 profile 绑定真实参考、规则与范例，
`style assemble --render` 沿用同一原生输出链，作品验收后按上述固定交付分支登记或替换首页工程。


```powershell
$job = '<workspace返回的job绝对路径>'
$draftRoot = Join-Path $job 'drafts'
$workspace = Join-Path $job 'blueprint'
$draftName = Split-Path $job -Leaf
$draft = Join-Path $draftRoot $draftName
$ref = 'local://' + $draftName

.\jianying.ps1 lyra init --workspace $workspace
.\jianying.ps1 lyra create --draft-root $draftRoot --ref $ref
.\jianying.ps1 lyra sync --workspace $workspace --draft-root $draftRoot --ref $ref
.\jianying.ps1 lyra resource-import --workspace $workspace --draft-root $draftRoot --path (Join-Path $job 'source.mp4') --title 'Source'
```

读取该工作区 `resource_map.json` 的真实 `asset_id`。例如返回 `video1` 后，以下 Selection
会添加一个三秒视频和普通文字；素材实际时长需足够，引用使用本次返回值。

```javascript
draft.select("main").appendXml(`<video id="v1" ref="video1" volume="25"><time material_start="0" duration="3000" speed="1"/></video>`);
draft.select("multi").appendXml(`<text id="t1"><time start="0" duration="3000"/><content><sub text="示例文字" size="12"/></content></text>`);
draft.apply();
```

将其作为 UTF-8 保存到任务目录的 `edit.selection`，然后运行：

```powershell
.\jianying.ps1 lyra apply --workspace $workspace --draft-dir $draft --ref $ref --selection-file (Join-Path $job 'edit.selection')
.\jianying.ps1 lyra sync --workspace $workspace --draft-root $draftRoot --ref $ref
.\jianying.ps1 export-draft --draft-dir $draft --out (Join-Path $job 'render')
```

导出成功返回 `encoded-and-decoded`；`render/render.mp4` 由本机剪映 `ExportService` 生成，
经过流、时长、帧数及完整解码检查。交付前再看实际画面、检查声音。

导出沿用工程中已保存的画布宽高。官方草稿画布为空时，如果所有已使用视频素材的尺寸一致，
仅在本次导出的内存副本中采用该素材尺寸；否则需要明确传入 `--width 1920 --height 1080`。
草稿未保存帧率时默认 30 fps；`export-draft --fps 30` 可覆盖本次导出的帧率。
这些覆盖不会写回源工程，`--fps` 仅适用于直接草稿导出。

修改已有片段时，从 `current_draft.xml` 取得真实 ID，完整同步形成目标基线，再按 ID 修改。
Selection 使用毫秒。`--base-revision` 为 canonical XML 哈希字符串；可省略，让官方工作区判定。
`sync --current-only` 保留目标 XML，适合回读，不能当作下一轮编辑的新目标基线。

官方 `--dir` 指草稿的**父目录**；正常包装会根据明确的 `--draft-dir` 和 `local://目录名`
检查对应关系。支持任务内外部工程，无需为了剪辑登记到剪映首页。

动作命令会复用或启动经过签名验证的剪映宿主，并使用官方 VMSDK 和签名 Bun worker。
直接调用 `engine/draftediting_runtime.py` 时，用 `--start-editor` 请求自动启动。
只读 `lyra doctor` 不添加 Bun 副本或启动宿主。

## 关键帧、曲线与音频淡化

先完成上述结构性 Selection 编辑，再按 `id_map.json` 的真实 `seg_id` 编写
`jy-windows-edit-actions/v1` 动作计划，运行：

```powershell
.\jianying.ps1 edit-actions --plan (Join-Path $job 'actions.json') --out (Join-Path $job 'actions-audit')
```

`edit-actions` 直接调用官方 typed CLI，支持位置/缩放/旋转/透明度/音量关键帧、曲线、
视频变速、音频淡入淡出，以及已确认的调色和画布编辑字段。返回 `applied-and-read-back`
表示原生保存值已核对；它不等于导出验收。完整 schema、值域与状态见
[Windows 动作批处理](WINDOWS-EDIT-ACTIONS.md)。

11.4.7 的 Blueprint 在位置关键帧上存在内部协议冲突；直接 typed CLI 可正常落地。
带 X/Y 关键帧的官方回读 XML 又会阻止后续 Blueprint apply，因此结构性编辑应先完成，
之后继续用 typed 动作修改参数。变速会改变段长，关键帧和 fade 依据变速后的实际时长设置。
批次逐步即时提交，执行前保留 `before/`，失败后停止并保留证据，不声称原子事务。
并发变化检查不等于原子锁；执行期间让 GUI 与其他任务停止修改同一工程。
`audio.fade` 编辑允许单边为 0，但当前原生导出只验收 `fade_type:4` 的双边淡入淡出；
本机构建对 0/800 ms 生成 type 2，仍会被导出门禁拒绝。需要已验收范围时使用双边非零时长，
并以动作后的真实类型读回为准。

## 转场、滤镜、特效与蒙版

```powershell
.\jianying.ps1 vfx catalog
.\jianying.ps1 edit-actions --plan (Join-Path $job 'vfx-actions.json') --out (Join-Path $job 'vfx-audit')
.\jianying.ps1 vfx freeze-draft --draft-dir $draft --out (Join-Path $job 'vfx-freeze')
```

`vfx catalog` 核对本机冻结资源的完整文件树 SHA256，列出精确 preset、参数与绑定状态；
它不代替 `doctor`。本机 11.4.7 的已审核视觉能力包含白光快闪、叠化/雾化/左右推移四种本地兼容转场、四个滤镜及辉光/轻微抖动/模糊，以及蒙版尺寸、
位置及现代软边蒙版的五通道关键帧（含羽化）。使用 `video.mask.set` 新增，`video.mask.update` 修改已有
蒙版，`video.mask.keyframe` 按实际蒙版材质绑定动画。

完整动作 JSON、时长与参数值域、源余量、坐标、软边资源选择及资源重建流程统一见
[Windows 视觉效果](WINDOWS-VFX.md)。兼容转场在官方原生引擎执行保留的原始 shader；
项目没有声称修复了应用原本的 GeneralEffect 路由。

每步官方返回与主时间线原生读回必须符合计划；协议兼容模块只改已验证的指定字段或通道，
使用官方 EncryptUtils 保存并保留审计。正常声明主时间线的工程须直接读回成功；针对少数
历史草稿布局的窄范围协调不能概括为官方 CLI 的普遍写入故障。批次与兼容写入均非原子。

编辑后 `vfx freeze-draft` 保留完整工程自有资源，再预览和导出。带蒙版的导出仍检查并复制
48 文件内建运行时，向助手显式传入资源根。源文件在结束后复核；Windows 没有额外的网络
阻断沙箱。未知资源及未验证参数按门禁停止，不静默省略。GUI 保存和冷重开需单独验收。

## 原生帧预览

```powershell
.\jianying.ps1 preview --draft-dir $draft --out (Join-Path $job 'preview') --at 0.5 1.5 2.5 --width 960
.\jianying.ps1 export-draft --draft-dir $draft --out (Join-Path $job 'render-final')
```

`preview --build <已校验构建>` 也可读取 JSON 计划的快照。默认宽 960、高度按原画布推算；
`--at` 是秒，必须在工程结束前。返回 `native-frames-captured` 后查看 PNG；VEF1 原生包的
时间戳误差必须不超过一帧，源工程和依赖必须保持不变。此入口通过独立后台官方播放器取帧，
无需打开 GUI，详见 [Windows 原生帧预览](WINDOWS-NATIVE-PREVIEW.md)。

预览选定时点用于检查画面。正式交付仍运行 `export` / `export-draft`，确认
`encoded-and-decoded`，再检查实际成片画面及声音。

## JSON 计划构建

```powershell
.\jianying.ps1 build --plan C:\task\plan.json --out C:\task\work\build
.\jianying.ps1 verify-build --build C:\task\work\build
.\jianying.ps1 export --build C:\task\work\build --out C:\task\work\render
```

计划 schema 为 `jy14-headless-plan/v1`，时间字段使用整数微秒，具体见现有
[计划入口](../engine/jy14_headless.py)。构建本身不登记到首页；`publish` 会修改首页索引，
仅在用户需要首页可见时使用，执行前按命令要求保存并关闭剪映。

## 其他官方命令

```powershell
.\jianying.ps1 lyra run --cwd $draftRoot --read-write $job --timeout 60 -- media probe --path (Join-Path $job 'source.mp4')
```

用 `lyra run` 转发本机官方帮助中存在的命令；授权本次需要的读写目录和只读素材。
资源及功能受本机官方版本、资源完整性和已有权益约束，详见
[官方命令矩阵](LYRA-CLI-MATRIX.md)。矩阵的历史功能统计不代表本机全部验收。
其中 195 条是历史接口发现数量，不能当成本机当前构建全部功能实测成功的数量。

## Codex 技能

```powershell
.\.venv\Scripts\python.exe tools\install_codex_skill.py
```

将 `jianying-windows` 安装到当前 Codex 用户的技能目录，绑定当前项目路径。
技能默认可被自动选择，也可显式使用 `$jianying-windows`。
项目移动后，检查 `local-settings.json` 中的本机路径，再从新项目目录执行
`.\.venv\Scripts\python.exe tools\install_codex_skill.py --rebind`，将已管理技能明确绑定到新目录。
默认安装会拒绝覆盖绑定到其他项目目录的技能；`--rebind` 仍拒绝未管理目录和符号链接目标。

## 验收范围

本机 11.4.7 已验证草稿加解密、官方新建/导入/同步/Selection 编辑、typed 参数编辑、多轨
视频、程序化关键帧、变速、普通文字、静态本地 TTF/OTF 字体、音频淡入淡出的原生导出，
以及独立原生播放器帧预览。catalog 中的已审核视觉预设另有逐项命令、原生读回和像素证据；
具体组合仍需按 [Windows 视觉效果](WINDOWS-VFX.md) 检查实际成片。
源草稿、素材、字体和效果资源在只读预览/导出中保持不变。
读取的是已保存磁盘状态；GUI 内存中未保存的修改需要先保存。
已审核 catalog 范围外的复杂特效、滤镜、模板、蒙版、转场等仍按能力门禁失败关闭，不通过省略效果取得成功。
调色和画布动作的编辑读回与其导出范围分别验收；其它构建也需要各自证据。
