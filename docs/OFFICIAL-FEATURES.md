# 剪映官方能力适配

`engine/official_features.py` 为剪映 11.5.0 自带的 Agent / DraftEditing 链路生成严格请求，支持：

- 文字转语音：`<text>` 内的 `<speech ref="toneN">`；
- 歌词动效：可靠毫秒时间轴、`<subtitle>` 和 `anim_text` 字幕动画；
- 官方剪同款模板：`<template_package>` 及 media、text、sticker 槽位。

这些能力依赖剪映官方资源身份。`tone_ref`、`animation_ref`、`template_ref` 和槽位素材 `ref` 必须来自当前官方 Agent 会话的 `MaterialRecall.resolved_resources[].blueprint_ref`，或当前草稿中已存在的真实 ref。示例里的 `tone1`、`anim_text1`、`template1`、`video1` 都是结构占位，不能当成固定资源 ID。

## 检查安装

```powershell
$env:PYTHONUTF8 = "1"
python engine\official_features.py doctor
```

`doctor` 只检查固定版本运行时、`jianying-agent-cli.exe`、`lyra-cli.exe` 和官方 XML 时间线 Skill，不读取账号文件。

## 自动生成歌词

`engine/lyrics_generate.py` 使用本地 `faster-whisper` 识别歌词并生成逐词时间。先安装可选依赖：

```powershell
pip install -r requirements-lyrics.txt
```

直接识别音频：

```powershell
python engine\lyrics_generate.py `
  --audio C:\absolute\song.wav `
  --start-ms 0 `
  --duration-ms 60000 `
  --model large-v3 `
  --out C:\absolute\work\auto-lyrics
```

从 JYPACK 识别：

```powershell
python engine\lyrics_generate.py `
  --jypack C:\absolute\sample.jypack `
  --model large-v3 `
  --out C:\absolute\work\auto-lyrics
```

JYPACK 模式根据时间线 ID 查找剪映已导入的同一草稿，自动排除 `text_to_audio`，选择覆盖时间最长的音乐素材，只识别草稿实际使用的源音频区间，并按片段的 `source_timerange`、`target_timerange` 和速度换算为草稿时间。需要指定素材时可传 `--material-id`。

输出目录必须不存在，其中包含：

- `lyrics.json`：歌词、词级置信度、源音频哈希和完整时间映射；
- `lyrics.srt`：可人工校对或导入其它工具的字幕；
- `official-features.plan.json`：可直接交给下文 `official_features.py build` 的歌词计划。

默认只使用本机缓存模型，避免命令在不知情时联网。首次获取模型时显式增加 `--allow-download`。歌曲中的伴奏、拖音和同音字会降低 ASR 准确率，生成后应校对 `lyrics.srt`；`large-v3` 通常比 `small` 更准确，但 CPU 耗时和内存占用更高。传入当前官方会话返回的 `--animation-ref` 后，生成计划会同时绑定官方歌词动画；不传时生成普通官方字幕。

## 检查 JYPACK 样本

`engine/jypack_inspect.py` 可以只读检查剪映导出的 `.jypack`。它会校验 JY/ZIP 容器、全部 CRC、包内路径和草稿占位路径，使用当前已固定版本的 `videoeditor.dll` 在内存中解密 `draft_content.json`，并报告 TTS、逐字歌词与 `template_package` 证据：

```powershell
python engine\jypack_inspect.py `
  --input C:\absolute\sample.jypack `
  --out C:\absolute\work\sample-report.json
```

检查不会覆盖或解包原文件。`.wav` 扩展名的剪映 TTS 缓存可能实际保存 MP3；报告按文件头给出 `detected_format`。歌词文字模板 `text_template_lyrics` 与官方剪同款 `template_package` 是两类资源，检查器会分别报告，避免把歌词样式误判为可渲染的官方模板包。

JYPACK 中的部分素材会保持打包加密状态。剪映导入后会把这些素材重新绑定到本机可读取资源。`jypack_render.py` 按时间线 ID 查找对应的已导入草稿，以只读方式加载解析后的时间线，再调用固定指纹的本机 `videoeditor.dll` 导出：

```powershell
python engine\jypack_render.py `
  --input C:\absolute\sample.jypack `
  --out C:\absolute\work\sample-render
```

若尚未导入，可以显式增加 `--import-if-missing`。该选项通过剪映注册的 `-open-draft-pack` 参数启动导入，并等待同一时间线出现。命令不会修改已导入草稿；输出目录包含 `render.mp4`、`result.json`、`ffprobe.json`、编译日志和原生引擎日志。此路径不需要 `JIANYING_AGENT_RUNTIME_TOKEN`，但仍要求本机安装经过固定哈希与 Authenticode 校验的剪映 11.5.0.14471。

### 全功能检查与成片报告

检查报告只说明"模板里有什么"，成片才能证明"能否真的出片"。`tools/jypack_report.py` 把
检查结果、渲染产物与声轨实测汇总成一份可复核的 markdown：

```powershell
python engine\jypack_inspect.py --input C:\absolute\sample.jypack --out C:\absolute\work\inspect.json
python engine\jypack_render.py  --input C:\absolute\sample.jypack --out C:\absolute\work\render --import-if-missing
python tools\jypack_report.py --inspect C:\absolute\work\inspect.json `
  --render C:\absolute\work\render --audio C:\absolute\work\render\audio-check.wav `
  --out C:\absolute\work\REPORT.md
```

报告包含：容器与 CRC 完整性、模板要素清单、包内 TTS 配音、歌词、渲染产物规格、声轨
峰值/RMS 与抽帧清单。注意报告里的 `native_export_supported` 指的是**本项目自编译的简化
导出器**；`jypack_render.py` 走的是剪映官方 `videoeditor.dll`，贴纸、文字模板与动画都由
官方引擎处理，不受该字段限制。

## 生成 DraftEditing 请求

复制并填写 `examples/official-features.plan.json` 中的真实 ref 和模板 `source_slot_id`，然后执行：

```powershell
python engine\official_features.py build `
  --plan C:\absolute\official-features.plan.json `
  --out C:\absolute\work\draft-editing-request.json
```

输出 JSON 的 `tool` 固定为 `DraftEditing`，`arguments.selection_expression` 可直接作为官方工具参数。生成器会拒绝重复片段 ID、重叠歌词时间、路径/URL/resource_id 形式的伪 ref、重复模板槽位和未知字段。歌词时间不会按字数猜测；可由上面的自动歌词命令、其它可靠 ASR 或人工标注提供。

官方模板的 `source_slot_id` 必须来自当前模板资源的 `metadata.template_slots[]`。模板应用后仍需检查草稿 `Resources/draft_templates/*/template.json`，确认没有未替换槽位、空路径 chroma 或当前渲染链路无法处理的内置层。

## 应用并渲染

以下两个命令会产生真实副作用，只能由剪映官方 Agent Runtime 启动。`workspace`、`draft-dir`、`draft-ref` 和计划中的全部 `blueprint_ref` 必须来自同一轮官方编辑工作区，不能自行猜测或复用其它会话的值。

先应用 TTS、歌词动效和官方模板：

```powershell
python engine\official_features.py apply `
  --plan C:\absolute\official-features.plan.json `
  --workspace C:\absolute\official-blueprint-workspace `
  --draft-dir C:\absolute\official-draft-workspace `
  --draft-ref CURRENT_DRAFT_REF `
  --audit C:\absolute\official-draft-workspace\apply-audit-001
```

该命令调用官方 `lyra-cli draft blueprint apply`，保留 `request.json`、`selection.expr`、标准输出、标准错误和 `result.json`。

应用成功后渲染包含官方模板的 MP4：

```powershell
python engine\official_features.py render `
  --draft-dir C:\absolute\official-draft-workspace `
  --draft-ref CURRENT_DRAFT_REF `
  --out C:\absolute\work\official-template.mp4 `
  --timeout 600
```

该命令调用官方 `lyra-cli draft export`。成功时同时生成 `official-template.mp4.result.json`。如果当前进程不是由官方 Agent Runtime 启动，命令会在写草稿或渲染前明确拒绝。

## 调用官方 CLI

适配器也可以调用该版本自带的 `jianying-agent-cli.exe`：

```powershell
python engine\official_features.py call-agent `
  --command validate-patch `
  --input C:\absolute\patch.json `
  --out C:\absolute\work\validated.json
```

可用命令为 `fetch-feishu-doc`、`query-content`、`plan-patch`、`validate-patch` 和 `apply-patch`。官方 CLI 只允许在剪映 Agent Runtime 会话中运行，并要求进程环境已经包含 `JIANYING_AGENT_RUNTIME_TOKEN`；适配器不会从用户数据、日志或进程内存提取令牌。`apply-patch` 仍保留官方 PC 确认门禁。

生成 Selection Expression 本身不会修改草稿、下载资源或联网。实际 TTS、歌词动画与模板渲染由剪映官方 DraftEditing/渲染链路执行，并受当前账号权益、资源许可和客户端版本约束。

## GitHub 可选上游

下面的项目可以提供输入或参考实现，但没有作为本项目依赖打包：

- [`K07VN/capcut-tts-api`](https://github.com/K07VN/capcut-tts-api) 提供 CapCut TTS、STT 和带时间转写结果。它面向 CapCut Common Task API，不能视为剪映中国版 11.5 官方接口；适合作为可替换的音频/时间轴数据源。
- [`KhoaDayy/CapDraft-TTS`](https://github.com/KhoaDayy/CapDraft-TTS) 展示了从字幕批量生成 TTS、备份草稿并原子回写音频轨的完整流程。其目标是 CapCut 草稿，不能直接替代本项目的 11.5 版本校验与加密写入。
- [`aoguai/pyJianYingDraft`](https://github.com/aoguai/pyJianYingDraft) 提供 SRT 导入、模板草稿复制和素材/文字替换。公开说明中的新版验证范围主要到 10.8，复杂官方模板仍应先在当前 11.5 样本副本中验收。
- [`yinbaozong/Rough-cut-wiki-video`](https://github.com/yinbaozong/Rough-cut-wiki-video) 使用 `faster-whisper` 生成可靠时间文本，可作为歌词/字幕计划的本地离线来源。
- [`HTWMedia/JyDraft`](https://github.com/HTWMedia/JyDraft) 提供第三方云端草稿渲染。它会上传草稿和素材，且不是本机剪映官方渲染链路，因此没有接入默认流程。

推荐边界是：外部 TTS/ASR 只产出音频或可靠的歌词时间；`official_features.py` 负责把真实 `blueprint_ref` 与时间数据编译为官方 Selection Expression；最终继续使用本项目已固定版本的草稿发布和本机渲染流程。
