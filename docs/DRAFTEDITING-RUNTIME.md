# 官方 DraftEditing / Blueprint 链路

`engine/draftediting_runtime.py` 通过剪映自带的官方 VMSDK 调用 `lyra-cli.exe`，
从而获得与编辑器内部完全一致的草稿编译与渲染链路。它不实现资源服务、不读取
账号数据、不提取运行令牌，也不分发任何官方二进制。

命令契约取自同版本 `Resources/canvas_agent/runtime/app-server.mjs`：

| 命令 | 用途 |
| --- | --- |
| `draft blueprint init --workspace W` | 初始化工作区（生成 blueprint.json、target/current XML、id_map、resource_map） |
| `draft blueprint sync --workspace W --ref local://N [--current-only]` | 把草稿编译为 canonical XML |
| `draft blueprint apply --workspace W --dir D --ref local://N --selection-file F --allow-existing-main-deletion --allow-existing-subtitle-changes` | 应用 Selection Expression 并回写草稿 |
| `draft blueprint resource --workspace W --import local:///<abs-path> --title T` | 导入本地媒体为可引用资源 |
| `draft blueprint resource --workspace W --search <json>` | 官方资源检索（联网，需账号权益） |

## 三项前置条件

官方宿主校验要求同时满足，缺一即返回 `unauthorized host process`：

1. **剪映主进程**（`JianyingPro.exe`）作为受信任宿主；
2. **官方 VMSDK**（`agent_runtime_addon.node` 与 `vm_sdk`）；
3. 签名有效、且 **PE 内部名为 `bun-packaged-server.exe`** 的官方 Bun 副本。

第 3 项的实现方式是把安装目录里的官方 `bun.exe` 复制为同名副本（字节一致、
Authenticode 仍有效）。仅改文件名不足以通过，复制官方字节可以。整个过程由
`ensure_packaged_bun()` 校验 SHA-256 与签名后使用，不修改官方文件内容。

自检：

```powershell
$env:PYTHONUTF8 = "1"
python engine\draftediting_runtime.py doctor
```

## 运行

```powershell
# 1. 初始化（工作区必须是纯 ASCII 的空目录或不存在）
python engine\draftediting_runtime.py init --workspace C:\Temp\jy-ws

# 2. 把草稿编译为 canonical XML（--ref 是引用，解析根为 --draft-root）
python engine\draftediting_runtime.py sync --workspace C:\Temp\jy-ws `
  --ref local://my-draft --draft-root "C:\...\com.lveditor.draft"

# 3. 应用 Selection（草稿必须在剪映草稿根下）
python engine\draftediting_runtime.py apply --workspace C:\Temp\jy-ws `
  --draft-dir "C:\...\com.lveditor.draft\my-draft" --ref local://my-draft `
  --selection-file C:\Temp\jy-ws\edit.selection
```

`run_lyra()` 是唯一入口：它按官方沙箱规则声明只读/读写路径后，在官方 worker 中
执行一次 `lyra-cli` 命令，并要求 `err_code == 0`。失败时把完整 envelope 写入
`work/draftediting-traces/`，同时保留 worker 的逐步进度（官方 bridge 是同步阻塞
调用，卡住时进度文件是唯一证据）。

## 实测硬约束

以下约束都来自本机 11.5.0.14471 的真实失败与修复，不是推测：

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `unauthorized host process` | 剪映未运行，或 Bun 副本名/签名不符 | 先启动剪映；用官方 `bun.exe` 的字节副本 |
| lyra-cli 崩溃 `0xC0000005`，日志里路径显示为乱码 | **沙箱策略无法处理非 ASCII 路径**（本仓库位于中文目录） | 工作区、草稿目录、Selection 文件全部使用纯 ASCII 路径 |
| `workspace path is invalid (not a directory or already non-empty)` | `init` 只接受空目录或不存在的路径 | 换新工作区，或先清空 |
| `invalid --ref, expected local://<name> or cloud://<name>` | `--ref` 是引用而不是目录路径 | 用 `local://<名称>` 配合 `--draft-root` |
| `segment not found: <id>`，草稿未被写入 | **草稿必须在剪映草稿根下**；放在临时目录时 apply 会当作空草稿 | 把草稿副本放进 `com.lveditor.draft` 下 |
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

- **apply 只写 `Timelines/<id>/draft_content.json`。** 草稿根目录的 `draft_content.json`
  与 `template-2.tmp` 不会更新，而渲染读取时优先取根文件，因此必须显式同步镜像，
  否则会出现"草稿改了、成片没变"的假象。见
  [无头端到端流水线](HEADLESS-PIPELINE.md) 的镜像同步一节。
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

`init → sync → apply` 已在剪映 11.5.0.14471 上完整跑通：

- `init` 生成 6 个文件，`target_state: uninitialized`；
- `sync` 编译 25 个片段、11 个资源，含 6 张歌词模板卡与 8 个动画，
  `target_state: applied`、`target_revision: 1`；
- `apply` 返回 `err_code: 0`、`executed_count: 28`、`planned_count: 28`、
  `xmldraft_validation: "Applied; live draft validation passed."`，
  并按目标审计要求把主轨拆成 17600ms + 7533ms 两段后写入草稿。

用于该验证的草稿副本是 `com.lveditor.draft/headless-lyrics-apply`（测试工程副本，
可在剪映首页删除），原始工程 `测试` 未被修改。
