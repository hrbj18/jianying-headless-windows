# 无头端到端流水线

`engine/headless_pipeline.py` 把「自动识别 → 歌词落地 → 官方渲染」串成一条无人值守的命令。
它只编排既有能力，不重复实现：

| 环节 | 复用模块 |
| --- | --- |
| 自动识别（ASR） | `engine/lyrics_generate.py`（JYPACK 音乐轨解析 + 时间映射） |
| 歌词↔模板卡对齐 | `engine/lyrics_align.py`（确定性规则） |
| 官方应用 | `engine/draftediting_runtime.py` + `tools/normalize_canonical_xml.py` |
| 模板槽位修正 | `engine/lyrics_slot_direct.py` |
| 官方渲染 | `engine/jypack_render.py`（本机原生 ExportService） |

## 运行

```powershell
$env:PYTHONUTF8 = "1"
python engine\headless_pipeline.py run `
  --draft "C:\...\com.lveditor.draft\my-draft" `
  --jypack "C:\...\my-draft.jypack" `
  --out "C:\absolute\work\pipeline-run-1" `
  --model large-v3 `
  --render
```

`--draft` 是剪映草稿根下的源草稿；默认复制成 ASCII 名的工作副本再操作，源草稿不被修改
（`--no-copy` 可关闭）。`--audio` 可替代 `--jypack` 作为识别源，但此时不能用 `--render`
（渲染需要 JYPACK 作为时间线来源）。

## 歌词落地模式

`--lyric-target` 决定识别出的歌词怎么写进草稿：

| 模式 | 行为 | 实测 |
| --- | --- | --- |
| `template`（默认） | 走官方歌词模板卡；原模板不可用时自动检索可用的官方歌词模板并逐句重建 | **渲染可见**，成片带模板动效出歌词 |
| `style` | 从草稿里 `lyric_animation` 类模板的 `LyricStyle.json` 提取样式（配色、字号、斜体、排版），生成等效字幕 | **渲染可见**，配色沿用原模板 |
| `subtitle` | 每个识别句生成一张普通 `<subtitle>`（白字黑边大字） | 渲染可见；不依赖模板资源，可离线使用 |

`template` 模式依赖官方资源检索（需要网络与账号权益）。相关参数：

| 参数 | 作用 |
| --- | --- |
| `--template-keyword` | 检索可用官方歌词模板的关键词（默认"歌词"） |
| `--template-ref` | 直接指定模板 ref，跳过检索 |
| `--template-search-timeout` | 检索超时（默认 300 秒） |

原工程的模板卡仍保留在草稿里，流水线新增的模板卡是独立的歌词层。

## 原工程的歌词模板为什么不出字

排查结论：**该模板在官方资源侧本身就是坏的**。

渲染日志（`06-render/native.stdout.log`）：

```
FileUtil: readFile: file .../Cache/artistEffect/7591420714515844395/1a5679120e5f1a4e8db7f06d83f05378/content.json is not exist
ERROR [AE_EFFECT_TAG]InfoStickerManager::addTemplate content path not invalid: .../content.json
```

`content.json` 是 EffectSDK 的模板描述，渲染引擎必须读它；读不到就报错并**静默跳过整张卡**。

用官方资源检索接口查同一个 resource id，**官方返回的错误与本地一致**：

```
resource_id: 7591420714515844395
metadata.text_template_slots_error: "text template resource has no readable content.json"
```

同一次检索同时返回了多个**资源完整**的官方歌词模板（能读出输入槽）：

| asset_id | resource_id | 标题 | 槽位 |
| --- | --- | --- | --- |
| `subtitle_template1` | 7665743129114397976 | 英文歌词字幕-错落位置逐词下滑 | 1 |
| `subtitle_template2` | **7591420714515844395** | （无标题，即原模板） | **不可读** |
| `subtitle_template3` | 7638543120313142553 | 歌词-梦幻发光上滑字幕 | 1 |
| `subtitle_template4` | 7661815391794154777 | 网感字幕-复古描边字幕 | 1 |

因此本地补下没有意义——资源在服务端就是坏的。流水线改为**自动替换**：
`search_usable_template()` 检索资源完整的候选，取第一个可用项，用
`lyric_template_selection()` 为每个识别句生成一张模板卡（`<text>` + `<template ref>`），
再走官方 apply。检索到的 ref 会写进工作区 `resource_map`，因此可以直接被 Selection 引用。

实测替换为"歌词-梦幻发光上滑字幕"后：11 句歌词写入、apply 12 条命令通过，成片第 21 秒显示
识别出的"还会等到有理想"，并带该模板的发光上滑动效。

官方对带 `<template>` 的歌词卡同样执行"句级字幕不得重叠"校验，因此这里复用同一套
`fit_subtitle_cues()` 裁剪。

## `lyric_animation` 类模板的支持边界

剪映的歌词模板分两类，走**两条完全不同的链路**：

| 类型 | 效果定义 | 客户端缓存 | 无头 CLI 缓存 | 无头渲染 |
| --- | --- | --- | --- | --- |
| `text_template` | `content.json` + `anim.prefab` + `algorithmConfig.json` | `Cache\artistEffect\<id>\<hash>\` | `Cache\lyra-cli\material-cache\text_template\<id>\` | **支持** |
| `lyric_animation` | `LyricStyle.json` | 同上 | `Cache\lyra-cli\material-cache\lyric_animation\<id>\` | **不支持** |

实测过程与证据：

1. 用**未经任何修改的原草稿**直接渲染，模板歌词不出现——与草稿数据无关。
2. 按客户端方式，从剪映自己的材料缓存取资源包地址（`item_urls`，该模板为 `is_vip: true`
   的 Pro 订阅资源）下载校验：资源包 7.7 MB、14 个条目，**本来就不含 `content.json`**。
   也就是说资源没有缺失，`content.json` 不属于这类模板。
3. 渲染日志里引擎仍走了 `InfoStickerManager::addTemplate`，它要求 `<path>/content.json`：
   `content path not invalid` → 卡片实例化失败 → 不产出文字。
4. 官方 CLI 的槽位探测同样只认 `content.json`，因此对这类模板返回
   `text template resource has no readable content.json`，`blueprint static-layout` 随之失败。

结论：这是**无头链路的类型边界**，不是缺文件，补文件也无效——`LyricStyle` 由剪映客户端的
歌词引擎执行，而 EffectSDK 的 ExportService 不解析它。

因此 `style` 模式改为**按原模板的样式生成等效字幕**：从 `LyricStyle.json` 取配色
（本例 `["#FFFFFF", "#fd629e"]`）、字号（12）、斜体、行距与每行字数，逐句生成字幕并按模板
的取色方式交替上色。能复现配色、字号与排版意图；**无法**复现的是模板自带字体（官方协议
不允许普通字幕引用物理字体路径，`blueprint resource --import` 也不支持字体）与逐词动效。

### 句级字幕不得重叠

官方 apply 会拒绝与草稿已有字幕重叠的新字幕：

```
Subtitle segments 't1' and 'lyric_01' overlap by 866ms. Sentence-level subtitles
must not overlap and must follow the actual speech order.
```

因此 `fit_subtitle_cues()` 会把每个识别句裁剪到遮挡字幕之后，裁完不足 200ms 的直接丢弃，
并保证句与句之间不重叠。被丢弃的句子记录在 `subtitle_plan.dropped`。

## 草稿镜像必须同步（关键坑）

官方 `blueprint apply` **只写** `Timelines/<id>/draft_content.json`，而草稿根目录的
`draft_content.json` 与 `template-2.tmp` 保持旧内容。渲染读取时优先取根文件，于是出现
"草稿数据明明改了、成片却毫无变化"的假象——本项目排查歌词不显示时，前四轮渲染全部踩在
这一点上：

| 文件 | 修改时间 | 大小 |
| --- | --- | --- |
| `Timelines/E1C00739-.../draft_content.json`（apply 写入） | 20:15:14 | 553032 |
| `draft_content.json`（渲染实际读取） | 15:24:59 | 535112 |

流水线因此在渲染前执行 `sync_draft_mirrors()`，把最新时间线同步到根文件与
`template-2.tmp`，并在报告中记录 `mirrors` 步骤。同步前后渲染结果不同（输出大小从
2251343 变为 2259358 字节，画面出现歌词字幕）。

## 每步产物

```
<out>/
├── 01-recognize/lyrics.json          识别结果（句级 + 字级时间戳）
├── 01-recognize/lyrics.srt
├── 01-recognize/official-features.plan.json
├── 03-subtitle-cues.json             字幕模式：最终写入的字幕与冲突统计
├── 03-alignment.json                 模板模式：每张卡的归属句、词数、交叠率与判定
├── 06-render/render.mp4              启用 --render 时
├── 06-render/result.json
└── pipeline-report.json              全流程状态、耗时与命令清单
```

`pipeline-report.json` 在每步之后都会重写，中途失败也能看到已完成到哪一步。

## 对齐规则（模板模式）

识别时间轴与原草稿歌词时间存在数十到数百毫秒偏移。按"区间重叠贪心"会串入相邻句，
按"最少句优先"又会漏掉卡片尾句。因此采用：

1. 一句歌词归属**其时间中心所在**的模板卡；中心不落在任何卡窗内的句子不属于歌词区
   （例如片头口播），记入 `outside_cue_indices`。
2. 每张卡消费归属它的全部句子。
3. 逐卡校验词数 ≥ 槽位、交叠率 ≥ 50%；不满足即 `skipped` 并给出原因，不回退猜测。

槽位切分沿用模板原有槽位的字符比例，不改变模板的视觉分词设计。

## 实测

同一工程（`测试 (1)` + `测试.jypack`）的完整验证：

| 运行 | 参数 | 结果 |
| --- | --- | --- |
| template（原模板） | `--model large-v3 --slot-mode direct --render` | 6/6 卡对齐、apply 18 条命令通过，但成片**没有**歌词：`lyric_animation` 类模板不被无头链路支持 |
| subtitle | `--model large-v3 --lyric-target subtitle --render` | 11 句字幕写入、apply 13 条命令通过；同步镜像后成片显示歌词 |
| template（自动替换） | `--model large-v3 --lyric-target template --render` | 自动替换为"歌词-梦幻发光上滑字幕"，apply 12 条命令通过；成片第 21 秒显示"还会等到有理想"并带模板动效 |
| style（原模板样式） | `--model large-v3 --lyric-target style --render` | 提取"浪漫氛围"样式（字号 12、白/粉随机、斜体），11 句写入、apply 13 条命令通过；成片第 10 秒显示"它掠过我空袖口春风"，配色为原模板的粉色 `#fd629e` |

字幕模式最终产物：`render.mp4` 31.6 s，第 10 秒画面显示"它掠过我空袖口春风"。片头一句因与
已有 TTS 字幕冲突被丢弃（`dropped: 1`）。

## 清理

流水线会在剪映草稿根下留下工作副本（`<prefix>-<时间戳>`），可在剪映首页直接打开核对，
确认后删除目录即可。Blueprint 工作区位于
`%LOCALAPPDATA%\Temp\jianying-draftediting\`，可随时清空。

## 边界

- 不修改源草稿；不做云端/账号操作；不下载模型（`--allow-download` 需显式开启）。
- 对齐与字幕覆盖率取决于识别质量；模型漏识会表现为 `skipped` / `dropped` 上升，
  而不是错误内容。建议用 `--model large-v3`（本机缓存）。
- 官方链路要求剪映主进程运行、路径纯 ASCII、草稿位于剪映草稿根——流水线内部已自动满足。
- 官方歌词动效模板卡在离线原生渲染中不出字；需要动效时请在剪映里使用该模板，
  或改用 `subtitle` 模式保证歌词可见。
