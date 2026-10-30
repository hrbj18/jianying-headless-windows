# 官方 DraftEditing / Blueprint 链路

`engine/draftediting_runtime.py` 通过剪映自带的官方 VMSDK 调用 `lyra-cli.exe`，
让 Selection Expression 经官方草稿编译与写回链路执行。它不实现资源服务、不读取
账号数据、不提取运行令牌，也不分发任何官方二进制。

Windows 正常入口是 `jianying.ps1 lyra ...`，使用项目 `.venv` 与根目录的个人
`local-settings.json`。已审核构建为 `11.4.7.14462` 和 `11.5.0.14471`，分别绑定精确 DLL 指纹，
并验证 EXE 文件版本与签名。完整操作流程和 Codex 的 `jianying-windows` 技能见
[Windows 调用指南](WINDOWS-CLI.md)。处理的是已保存磁盘草稿，不同步 GUI 内未保存的内存时间线。

命令契约取自同版本 `Resources/canvas_agent/runtime/app-server.mjs`：

| 命令 | 用途 |
| --- | --- |
| `draft project create --dir R --ref local://N` | 在父目录 R 中创建名为 N 的独立工程 |
| `draft blueprint init --workspace W` | 初始化工作区（生成 blueprint.json、target/current XML、id_map、resource_map） |
| `draft blueprint sync --workspace W --ref local://N [--current-only]` | 把草稿编译为 canonical XML |
| `draft blueprint apply --workspace W --dir D --ref local://N --selection-file F --allow-existing-main-deletion --allow-existing-subtitle-changes` | 应用 Selection Expression 并回写草稿 |
| `draft blueprint resource --workspace W --import local:///<abs-path> --title T` | 导入本地媒体为可引用资源 |
| `draft blueprint resource --workspace W --search <json>` | 官方资源检索（联网，需账号权益） |

## 三项前置条件

官方宿主校验要求同时满足，缺一即返回 `unauthorized host process`：

1. **剪映主进程**（`JianyingPro.exe`）作为受信任宿主；
2. **官方 VMSDK**（`agent_runtime_addon.node` 与 `vm_sdk`）；
3. 签名有效、以 **`bun-packaged-server.exe` 名称运行**的官方 Bun 副本。

第 3 项的实现方式是把安装目录里的官方 `bun.exe` 复制为同名副本（字节一致、
Authenticode 仍有效）。`ensure_packaged_bun()` 校验其与官方 `bun.exe` 的 SHA-256 一致且签名有效。
这会在安装目录按需新增 Bun 副本，不修改原 `bun.exe` 内容，也不伪造父进程或开启开发信任开关。

自检：

```powershell
.\jianying.ps1 doctor
.\jianying.ps1 lyra doctor
```

总入口 `doctor` 检查精确身份、签名、媒体工具与导出编译器；`lyra doctor` 只读检查组件与
宿主状态，不启动剪映、不新增 Bun 副本。动作命令通过总入口执行时会自动复用或启动已验签宿主；
直接使用 Python 子入口时可加 `--start-editor`。

## 运行

```powershell
# 1. 生成任务目录；使用输出中的 job、draft_root 和 blueprint
.\jianying.ps1 workspace --name demo
$job = '<返回的job绝对路径>'
$draftRoot = Join-Path $job 'drafts'
$workspace = Join-Path $job 'blueprint'
$draft = Join-Path $draftRoot 'demo'
$ref = 'local://demo'

# 2. 初始化空工作区并新建任务内工程
.\jianying.ps1 lyra init --workspace $workspace
.\jianying.ps1 lyra create --draft-root $draftRoot --ref $ref
.\jianying.ps1 lyra sync --workspace $workspace --ref $ref --draft-root $draftRoot

# 3. 导入任务内素材，并按真实资源ref及片段ID编写Selection
.\jianying.ps1 lyra resource-import --workspace $workspace --draft-root $draftRoot `
  --path (Join-Path $job 'source.mp4') --title Source
.\jianying.ps1 lyra apply --workspace $workspace --draft-dir $draft --ref $ref `
  --selection-file (Join-Path $job 'edit.selection')
.\jianying.ps1 lyra sync --workspace $workspace --draft-root $draftRoot --ref $ref
.\jianying.ps1 export-draft --draft-dir $draft --out (Join-Path $job 'render')
```

`run_lyra()` 是唯一入口：它按官方沙箱规则声明只读/读写路径后，在官方 worker 中
执行一次 `lyra-cli` 命令，并要求 `err_code == 0`。失败时把完整 envelope 写入
`work/draftediting-traces/`，同时保留 worker 的逐步进度（官方 bridge 是同步阻塞
调用，卡住时进度文件是唯一证据）。

官方 `--dir` 指向草稿的父目录，工程名由 `local://N` 解析；包装入口会核对 `--draft-dir`
与该名称一致。独立任务工程无需先登记到剪映首页。修改已有片段前使用完整 `sync` 建立目标基线；
`--current-only` 用于保留目标 XML 的回读，不替代下一轮编辑基线。

## 实测硬约束

以下约束来自 11.5.0.14471 历史验证和 11.4.7.14462 正式入口测试：

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `unauthorized host process` | 剪映未运行，或 Bun 副本名/签名不符 | 先启动剪映；用官方 `bun.exe` 的字节副本 |
| lyra-cli 崩溃 `0xC0000005`，日志里路径显示为乱码 | **沙箱策略无法处理非 ASCII 路径**（本仓库位于中文目录） | 工作区、草稿目录、Selection 文件全部使用纯 ASCII 路径 |
| `workspace path is invalid (not a directory or already non-empty)` | `init` 只接受空目录或不存在的路径 | 换新工作区，或先清空 |
| `invalid --ref, expected local://<name> or cloud://<name>` | `--ref` 是引用而不是目录路径 | 用 `local://<名称>` 配合 `--draft-root` |
| `segment not found: <id>`，草稿未被写入 | `--dir` 错传工程目录，或引用父根与同步基线不一致 | `--dir` 使用父目录、`local://N` 使用工程名称，修改前完整 `sync`；已验证外部任务工程 |
| `expression must end with draft.apply()` | CLI 直连模式要求显式收尾 | Selection 末尾加 `draft.apply();` |
| `XMLDRAFT_ATTRIBUTE_OWNER_INVALID: font_ref` | `font_ref` 的所有者是 `text|sub|slot|style|text_style`，不是 `<subtitle>` | 迁移到 `<sub>` |
| `font_ref ... does not exist in the resource library` | `font_ref` 必须是资源库引用，而 `blueprint resource --import` 不支持字体 | 移除字体引用（回退默认字体），见 `tools/normalize_canonical_xml.py --mode drop` |
| `main.source_range.exceeds_resource on v2` | 主轨片段时长超出素材时长，官方目标审计拒绝 | 按官方给出的修复指令拆分片段，见 `--fix-main-range` |
| `--base-revision does not match canonical XML` | 该参数是 canonical XML 的哈希，不是数字版本 | 默认不传，交由 lyra-cli 自行判定 |

## 配套工具

| 工具 | 作用 |
| --- | --- |
| `tools/normalize_canonical_xml.py` | 修正属性所有者（`font_ref`）与主轨素材越界，使 canonical XML 通过 apply 的协议校验与目标审计 |
| `tools/build_lyrics_template_selection.py` | 按显式对齐把本地歌词填入官方歌词模板卡，生成带 `draft.apply()` 的 Selection 与对账报告 |

歌词模板的完整闭环：

```powershell
python engine\lyrics_generate.py --jypack SAMPLE.jypack --model large-v3 --out C:\absolute\work\auto-lyrics
python engine\draftediting_runtime.py init  --workspace C:\Temp\jy-ws
python engine\draftediting_runtime.py sync  --workspace C:\Temp\jy-ws `
  --ref local://my-draft --draft-root "C:\...\com.lveditor.draft"
python tools\normalize_canonical_xml.py --workspace C:\Temp\jy-ws --mode drop --fix-main-range
python tools\build_lyrics_template_selection.py --workspace C:\Temp\jy-ws `
  --map C:\absolute\work\auto-lyrics\template-map.json
python engine\draftediting_runtime.py apply --workspace C:\Temp\jy-ws `
  --draft-dir "C:\...\com.lveditor.draft\my-draft" --ref local://my-draft `
  --selection-file C:\Temp\jy-ws\edit.selection
```

`examples/lyrics-template-map.json` 是映射文件的格式示例，`cues` 索引按
`lyrics_generate.py` 输出的 `lyrics.json` 逐卡核对。

## 已知限制

- **不同工程的活动时间线位置不同。** 11.4.7 官方新建外部工程只包含根目录
  `draft_content.json`，没有 `Timelines` 目录；历史 11.5 工程的 apply 则可能只更新
  `Timelines/<id>/draft_content.json`。正常 `export-draft` 根据工程声明解析主时间线后复制导出，
  不为导出改写源工程镜像。旧歌词流水线的镜像处理见 [无头端到端流水线](HEADLESS-PIPELINE.md)。
- **模板多输入槽位的文本分发不完整。** 官方转换器把同一宿主上的多个 `<sub>` 合并为一条
  `draft edit --update "text=1;target=A|B|C"`，实测结果是把整串 `A|B|C` 写入模板共享的
  text material，且不重分配 `text_info_resources[].word_index`，于是每个输入框都显示整串。
  多输入框模板请用 `engine/headless_pipeline.py --slot-mode direct`，它在官方 apply 之后
  按槽位比例重写草稿文本（模板 ref 与动画 ref 不变）。
- **官方歌词动效模板卡依赖模板资源里的 `content.json`，且该资源可能在官方侧就是坏的。**
  本例 resource_id `7591420714515844395` 的本地缓存缺少 `content.json`，渲染日志出现
  `InfoStickerManager::addTemplate content path not invalid`，模板卡被整卡跳过且不报错；
  同一 resource id 经官方 `blueprint resource --search` 检索，官方同样返回
  `text template resource has no readable content.json`。修复方式是改用资源完整的官方模板
  （`engine/headless_pipeline.py --lyric-target template` 会自动检索替换）。
- **整段替换 `<content>` 会让 apply 重算模板卡时长。** 实测 t11 从 7800ms 收缩到 300ms，
  使其后的识别结果落不进卡窗。Selection 里应显式写回每张卡的 `start` 与 `duration`。
- 移除 `<subtitle>` 的样式属性会丢失原有阴影等设置（官方会下发
  `text_shadow=0;shadow_enable=0`）。
- `blueprint resource --import` 只支持媒体，不支持字体；因此带自定义导入字体的
  草稿必须先去字体引用才能通过 apply。
- 官方资源检索（`--search`）需要联网与账号权益，本模块只保留命令，不代做授权。

## 实测记录

### 11.4.7.14462 正常入口

通过 `jianying.ps1` 完成独立任务的 `init → create → resource-import → sync → apply → sync`：

- 新建外部工程并导入本地合成 MP4，所有路径保留在任务内。
- 两轮官方 apply 分别执行 `4/4` 条命令，随后官方 canonical 回读确认视频时长 3000 ms、
  音量 25，以及普通文字 `Normal CLI 11.4.7 passed`。
- `jianying.ps1 export-draft` 使用上述真实编辑后的已保存工程，调用本机 `ExportService` 生成
  1920×1080、30 fps、90 帧、3.000 秒 H.264/AAC MP4，完整解码和源文件未变检查通过。
- 未使用实验 monkeypatch、开发信任开关、父进程伪造或白名单关闭；正式入口绑定精确版本和 DLL 哈希。

该验证覆盖基础视频、源音频和普通文字，不代表复杂模板、在线资源或全部官方命令逐项验收。
旧 `native_edit` 副本编辑流程与官方 Selection 链是不同入口，前者在 Windows 仍未验收。

### 11.5.0.14471 历史记录

`init → sync → apply` 已在剪映 11.5.0.14471 上完整跑通：

- `init` 生成 6 个文件，`target_state: uninitialized`；
- `sync` 编译 25 个片段、11 个资源，含 6 张歌词模板卡与 8 个动画，
  `target_state: applied`、`target_revision: 1`；
- `apply` 返回 `err_code: 0`、`executed_count: 28`、`planned_count: 28`、
  `xmldraft_validation: "Applied; live draft validation passed."`，
  并按目标审计要求把主轨拆成 17600ms + 7533ms 两段后写入草稿。

用于该验证的草稿副本是 `com.lveditor.draft/headless-lyrics-apply`（测试工程副本，
可在剪映首页删除），原始工程 `测试` 未被修改。
