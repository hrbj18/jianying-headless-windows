# Windows 11.4.7 原生音频材料与隔离调用研究

本次是只读静态研究：未操作剪映 GUI、未调用活跃编辑页、未执行 JS、未提交云任务、未读取凭据。结论用于独立试样实验，不能当作已出片或效果可用的证明。

## 结论

1. 实时降噪有比 `draft algo denoise` 更直接的现成原生服务路径：`edit` 域的 `audio.denoiseOn` / `audio.denoiseOff`。真实参数和材料字段已从本机发布 JS 找到。
2. 音频响度平衡材料 `audio_balance`、新版 `loudness` 及其子对象字段均存在；但单位、参数来源和本机构建渲染结果没有确定，暂不能把它们当作完成的响度标准化功能。
3. 本机 `audioeffect.dll` 含压缩器、限制器和参数均衡器的实现线索；目前尚未找到可信的“剪映草稿材料 → 这些 DSP 参数”绑定。不能用变声、混响或外部烘焙 WAV 冒充 EQ/压缩原生可调。
4. 独立官方 `videoeditor-service` 的 `player.create` / `player.load` 返回并绑定自己的 `sessionId`，可避免误操作 GUI 中的 R4；本项目已有原生预览基础设施可复用，但当前预览 transport 的允许列表没有开放编辑动作，应该单独增加受审计的窄范围音频编辑路径。

## 一手来源与复现文件

安装根：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462`。

主要发布物：

- `Resources/canvas_agent/app/static/js/ai-creation~2.2895c133.js`：72974 模块，音频降噪 action。
- `Resources/canvas_agent/app/static/js/ai-creation~3.fbc221b2.js`：70362 模块，音频服务动作映射。
- `Resources/canvas_agent/app/static/js/ai-creation~8.7b43c1ad.js`：30793、88091、90673、39975 模块，原生材料序列化。
- `Resources/canvas_agent/app/static/js/ai-creation~5.38151757.js`：30472 模块，旧草稿降噪迁移样例。
- `Resources/canvas_agent/runtime/app-server.mjs`：独立 draft session、行为请求与保存绑定。
- `Resources/canvas_agent/runtime/videoeditor-service.mjs`：协议信封将 `targetId` 绑定到官方服务 session。

任务证据目录：`D:\JianyingHeadless\work\native-av-upgrade-20261028-004610-32bec1\research-native-audio`。其中 `artifact-identities.json` 记录发布 JS、原生服务及模型文件 SHA256；`audio-static-modules.json`、`denoise-action-72974.js.txt`、`app-server-target-dispatch-excerpts.json`、`native-draft-session-factory.txt` 保留精确节选。

REA 静态分析原始 Evidence：

- `ev_c5aad698bc151e235a6605f3f5348d5241565f0d7ad37058181991e1442e93bd`：选取 ~8、~11、~5 三个文件。
- `ev_07524b6f936de1b72a158cdf6a8f5fb4edfae5664eb911bc6ab0f428708415e3`：选取 ~2、~3、~4 三个文件。

REA 仅解析惰性语法，没有执行 Webpack 工厂或 bootstrap。每次分析只覆盖所选 3 个文件，未选择的文件、动态关系和运行时可达性仍未知。直接字节检索的 DLL 字符串候选不等同于 REA 反编译或运行证据。

## 实时降噪：已观察到的精确字段

~8 的 30793 模块序列化如下：

```json
{
  "id": "UUID",
  "type": "realtime_denoise",
  "is_denoise": true,
  "denoise_mode": 0,
  "denoise_rate": 0.85,
  "path": "待验证的本机模型路径",
  "sami_name": "denoise_v2",
  "sami_version": "1.0",
  "sami_type": 2
}
```

上例 mode 0 / rate 0.85 / type 2 来自 ~5 的真实旧草稿迁移逻辑：当 video/audio 片段的 `intensifies_audio` 为 true，会查找绑定的 `materials.realtime_denoises`；没有材料时创建该形状并将 UUID 加入 `segment.extra_material_refs`。

新材料构造默认值与迁移样例不同：`is_denoise:false`、`denoise_mode:1`、`denoise_rate:1`、`sami_type:0`、`path:""`。不能混淆“构造默认值”和“已有启用样例”。`denoise_rate` 的业务单位、0/1 mode 与 0/2 type 的完整枚举尚未恢复，不应任意扩大值域。

72974 action 的输入使用 camelCase：

```json
{
  "segmentIds": ["真实音频片段 ID"],
  "isDenoise": true,
  "path": "待验证的非空本机模型路径",
  "denoiseMode": 1,
  "denoiseRate": 1,
  "samiName": "denoise_v2",
  "samiVersion": "1.0",
  "samiType": 0
}
```

发布 JS 的音频 wrapper 在 `audio.denoiseOn` 方法内补 `isDenoise:true`，`audio.denoiseOff` 补 false。**这不等于原生 C++ 传输服务也会按 operation 名补值。** 主线程后续真实实验确认，直接发 edit 协议信封时必须显式传入 `isDenoise:true`，仅用 denoiseOn 操作名会保存为 false。action 的 check 会验证片段存在、是 audio 类型，并在开启且 path 为空时报 `path empty`。action 的 do 创建 RealtimeDenoiseDelta，将以上参数写入音频片段的 realtimeDenoise 属性。

### 模型路径：静态来源与后续实测

本机存在：

- `Resources/audiosami/unet_denoise_44k_music_model_v1.0.model`（264172 字节）
- `Resources/rnnoise/rnnoise_v2.0.model`（124648 字节）
- `Resources/models/noise_reduction/nn_denoise.bytenn`

VECreator.dll 文件偏移 `0xA11A71B` 含 `/audiosami/unet_denoise_44k_music_model_v1.0.model` 字符串，是优先实验该完整文件路径的依据；不能单凭字符串确定 path 接受文件还是目录。主线程后续 8 秒原生出片已验证该完整本机 model 文件路径可用。Web 草稿修复逻辑对空路径使用 `/__opfs_system_root/integration/audio`，这是 Web 文件系统路径，不能直接搬到 Windows。

## 响度材料

~8 的 88091 模块 `AudioBalance`：

```json
{
  "id": "UUID",
  "type": "audio_balance",
  "enable_balance": false,
  "peak_loudness": 0,
  "average_loudness": 0,
  "target_loudness": 0
}
```

字段属于 `materials.audio_balances` 的材料类型。序列化及默认值明确，但第一阶段没有恢复材料字段与正式控制接口的绑定。后续已确认正式 CLI 使用 LUFS 目标及 SDK dB-family 检测值，详见“第二轮”；这些材料的实际写入仍须正式命令后的 draft diff 验证，也未找到这一版本公开行为服务的 audioBalance setter。

90673 模块 `Loudness` 的字段为 `id/enable/file_id/target_loudness`，可选对象 `time_range` 和 `loudness_param`。39975 模块明确 `loudness_param` 仅为 `avg_loudness/peak_loudness`。同样没有确认其渲染依赖或单位。

## EQ、压缩与限制器

`audioeffect.dll` 的静态字符串和导出名候选包括：

- `AECompressor`、`compressor_ratio`、`compressor_threshold`、`compressor_kneeWidth`、`attack_time_ms`、`release_time_ms`。
- `Limiter`、`climiter`、`enable_limiter`、`limiter_mode`。
- `parametric_eq`、`EqualizerParametric error: bad parameters`、`Equalizer@mammon` 及 `eqGetBandCount/eqGetBandFre/updateCustomizedSetting` 等导出名。

它们证明相关代码/符号存在于发布物，不能证明可经当前草稿控制，也不能证明参数单位和值域。`audio_effects.adjust_params` 的 scene/tone 资源实现是另一条路径；未找到上述 DSP 的可信现成资源映射前，不应将其等同专业 EQ/压缩。

## 安全的独立 session 调用方向

现有 `engine/windows_native_preview.py` 的 NativeClient 通过独立官方服务做：

1. `player.create`，参数 `kind:"draft", serviceGeneration:1`，取得真实 `sessionId`。
2. `player.load`，`targetId` 为该 session，参数由 `player_load_params` 产生：`draftJson` 为紧凑 JSON、`workspacePath` 为任务目录、`timelineId` 为试样时间线 ID。
3. 新增窄范围音频编辑客户端后，发送 `domain:"edit", operation:"audio.denoiseOn", targetId:<该session>, params:<上述输入>`。
4. 检查 authoritative `draftSnapshot` 与 diff，不把 accepted 当保存成功；在自有草稿保存、导出、测量噪声/声音变化，再在 GUI 原生模型中回读并修改参数后二次渲染。
5. `player.destroy` 仅销毁该 session；独立服务按其生命周期结束，不对 GUI 主进程强制结束。

本机 app-server 的 `openAgentDraftSessionNow` 和 `handleBehavior` 正是先 create/load，再向该 targetId 发 edit 请求，并将返回的 `draftSnapshot` 按 session/revision 提交保存；`mirrorActiveDraft:false` 用于独立会话。这个协议说明避免误操作当前 R4 的边界，而不是允许绕过身份和保存检查。

`engine/windows_preview_client.mjs` 当前只允许 system/player 预览相关操作，不允许 edit。应新增审计明确的音频能力，不静默放宽预览允许列表。

`engine/official_features.py::call_agent` 仅接收 fetch-feishu-doc/query-content/plan-patch/validate-patch/apply-patch，且要求现有官方 RuntimeToken；它不是通用音频 edit 入口。`headless_pipeline.py` 只是 ASR/Blueprint/模板/渲染编排，不提供独立音频 DSP。

## 第一阶段待验收项（后续进展见下文）

- 降噪：正确模型路径、原生实际噪声衰减、对白失真、参数修改后的第二次导出均未实测。
- 响度：字段单位、原生增益/响度输出、目标值修改后保存与再导出均未实测。
- EQ/压缩：尚缺可信的材料绑定与正式参数入口，不能声明已实现。
- 原生 GUI 可编辑性：旧静态 qmeta `SoundEditSettingHandler` 有 denoiseSwitch、onDenoiseSwitchClick(bool)、loudnessViewModel，表明后续可通过现有原生桥验证；本次未操作它。

以上未知项需由主线程的独立试样、实际出片和原生编辑回读补齐。

## 后续：原生可调音效入口与缓存查证

**后续纠正：以下示例属于 Web JavaScript DTO，结构与数值枚举需按 Windows native addon 核对。** DLL 的真实传输字段与扁平调参结构已恢复，见 [原生传输 DTO 静态研究](native-transport-dto-20261028.md)。创建原生字段为 `audio_adjust_params`，其元素为 `default_value/min_value/max_value`（addon 可自动补 camelCase 别名）；调参使用顶层 `effect_adjust_value`，不会展平 `audioAdjustParam` 子对象。错误字符串 enum 会中断后续字段解析，不能把这种结果解释为数组字段不支持。

~2 的 83913 模块实现 `audio.setVoiceEffect`，参数为：

```json
{
  "segmentId": "真实视频或音频片段 ID",
  "name": "真实资源名",
  "resourceId": "真实资源 ID",
  "resourcePath": "合法原生音效资源目录",
  "categoryId": "真实分类 ID",
  "categoryName": "真实分类名",
  "audioAdjustParams": [
    {
      "name": "资源定义的参数名",
      "value": 0,
      "defaultValue": 0,
      "parameterIndex": 0,
      "portIndex": 0,
      "minValue": 0,
      "maxValue": 1
    }
  ],
  "productionPath": "",
  "audioEffectType": 0,
  "speakerId": "",
  "sourcePlatform": 0,
  "thirdResourceId": "",
  "isVcCloneTone": false
}
```

示例中的数值只是字段形状，真实枚举和参数值必须来自合法资源，不能直接用此占位调用。action 将该形状保存到片段 `voiceChange` 材料，原生持久化对应 `audio_effects`，并设置 VoiceChangeFlag。

52092 模块的 `audio.setVoiceEffectParams` 接受 `segmentId/resourceId/audioAdjustParam/isKeyframe`，检查目标已有音效的 resourceId 匹配；以 parameterIndex 与 portIndex 共同匹配后更新 value。`isKeyframe:true` 时参数 index 0/1/2 分别可映射 EffectAdjustParam1/2/3 关键帧。对 EQ/压缩而言，这是可复用的原生可调参数通道；但目前仍缺一份真实 EQ/压缩资源包及其参数索引定义，不能用任意 parameterIndex 猜测。

只读缓存检索范围：

- `User Data/Cache/effect` 与 `User Data/Cache/AudioFunction`：1741 个不超过 1 MiB 的 JSON/config/Lua/JS/XML/TXT，合计 6855767 字节。对 compressor/parametric_eq/equalizer/climiter/drc_param/enable_limiter/audio_effect/sami/voice_effect 无匹配。
- `User Data/EMaterial`、`User Data/Cache/onlineMaterial`、`User Data/Download`：按 config/effect/feature/content/meta/manifest JSON 与 Lua 文件名筛选，未发现候选文件。
- 这些是具体本机资源缓存范围内的负结果，不代表剪映线上不存在音频资源。没有读取账号存储、凭据、聊天或无关音频。

补充 DSP 字符串：`SAMICoreEffectSetProperty` 邻近存在 `target_lufs/source_lufs/source_peak/enable_limiter/gain_db`；独立 DRC wrapper 含 `type:"Normal"/"SideChain"`、expander 和 compressor ratio/threshold/kneeWidth、make_up_gain、attack_time_ms、release_time_ms。它们仍只是底层 DSP 线索，尚未与上述资源化音效通道可靠关联。

对应证据：`voice-effect-action-83913.js.txt`、`voice-effect-action-52092.js.txt`、`audio-cache-resource-search.json`、`audio-more-cache-resource-search.json`、`drc-parser-nearby-strings.json`。本轮未执行上述音效调用或改变任何导出门禁。

对 `videoeditor.dll` 导出符号 `NewVEWrapper::createAudioEffectFilter`（RVA `0x15d2990`）做了只读、限地址 LLVM 静态反汇编，证据为 `create-audio-effect-filter.txt`：第二个字符串参数为空会走日志 `preprocess audio effect resource failed, resourcePath is empty`，非空后进入间接资源预处理 factory，并把参数 vector 传给原生 AudioPreprocessFilter。间接 factory 的完整配置结构未恢复，因此不能从 `compressor_ratio` 等字符串跳过资源层自行猜造合法效果包。未调用这些本机函数，未改变 DLL 或 ABI。

发布 JS 的权益枚举中存在 `VipFeatureAudioDenoise=26` / `VipFeatureVolumeBalance=27`。这仅证明有对应功能标识，不证明当前账号的可用性或收费状态。本轮不读取账号数据，不改变权益检查；具体可用性应由正式原生服务实际返回判定。

## 第二轮：官方响度命令与输入单位

本机 `engine/lyra_commands.json` 发现两个正式命令：

```text
draft algo loudness-normalize --ref <ref> --seg-id <id>
  --target-loudness <number>
  --average-loudness <number> --peak-loudness <number>
  --true-peak-ceiling <number> --enable true|false

media loudness --input <local-file> --start <time> --end <time>|--duration <time>
```

`lyra-cli.exe` SHA256：`8cb55d0e520a11bb98d2e165a7b918ae67a030fed268dcd537861848a413c1af`。直接读取其内嵌官方帮助（非执行命令）取得：

- target-loudness：目标 integrated loudness，单位 **LUFS**，默认 **-14**，合法范围 **[-70,0]**。
- average-loudness：预先测得的 integrated loudness，单位 LUFS；必须与 peak-loudness 同时传入。
- peak-loudness：官方描述为 **SDK loudness-detector peak**；CLI 示例使用 `-1.2`，不能将其当 0..1 线性音量。
- true-peak-ceiling：单位 **dBTP**，范围 **[-70,0]**。通过测量源音频 true peak 并降低 effective target 执行，并非证明压缩器或峰值限制器已经运行。
- enable：默认 true；ceiling 要求 enable=true。
- 无显式 average/peak 时，命令检测选中片段的 **source time range**；指定显式测量值时可复用测量，但 ceiling 模式仍会额外测 true peak。

检测响应的可见 key 包括 `avg_loudness`、`peak_loudness`、`detect_result`，还会返回 `avg_loudness_unit:"dB (LUFS-like)"`、`peak_loudness_unit:"dB peak"`。因此 FFmpeg EBU R128 结果适合作为独立参照，但没有实验前不能声称其与 SDK 的 LUFS-like 算法逐数相等。

证据：`research-native-audio/lyra-loudness-static-candidates.json`。本轮进一步完成下述 REA/Ghidra 静态恢复；尚未调用这些响度命令或验证其渲染结果。

### 原生 CLI 处理链与测量返回值

对上述 SHA256 的本机 `lyra-cli.exe` 进行静态分析，未启动程序、未连接活跃剪映：

- `0x1407c3e60` 先限制为恰好一个 audio 或 video 片段，再构造响度处理计划。默认目标常量为 IEEE754 `0xc02c000000000000`，即 -14.0。
- 参数验证函数 `0x1407c4a50` 接受 `enable/target_loudness/average_loudness/peak_loudness/true_peak_ceiling`，并接受 `avg_loudness` 作为 average 的别名；校验上述范围、平均值与峰值必须成对、ceiling 要求 enable=true。
- 计划的 `action_name` 精确为 `LOUDNESS_NORMALIZE_ACTION`，步骤精确为以下 JSON。这里是正式 CLI 产生的内部计划形状，**不等于已证明存在同名原生 edit operation**。

```json
{
  "name": "loudness_normalize",
  "params": {
    "segment_id": "真实片段 ID",
    "segment_type": "audio 或 video",
    "enable": true,
    "target_loudness": -14,
    "average_loudness": -20.3,
    "peak_loudness": -1.2,
    "true_peak_ceiling": -1
  }
}
```

反编译明确的是 vector 内的 `name/params` 与外层 `action_name`，没有恢复调用者对 vector 的最终 JSON 字段名。不得将这个展示样例当作通用 transport 请求。可选的 average、peak、ceiling 示例值来自内嵌帮助，不代表本地音频的实际测量。

正式且无需猜测的最小实验入口应为：

```text
draft algo loudness-normalize --ref <独立试样ref> --seg-id <真实片段id> --target-loudness -14
media loudness --input <本机试样音频> --start 0s --duration 8s
```

在项目已有独立草稿入口调用，先取 SDK 测量结果，再核对原生保存后的 material diff 与二次导出。不能将以上计划直接发给 GUI 主会话。CLI 计划 handler 本身没有直接读写 `audio_balances/loudnesses` 的材料实现，本轮未从它恢复底层材料绑定。

`media loudness` 的主 handler `0x1405fb9a0` 将 CLI 时间字面量解析为微秒，向 `0x14061f9e0` 传入本机路径、start_us、end_us；未指定范围时从开头到文件结束。SDK 调用方向为：

```text
lyra::DetectAudioLoudnessReqStruct
  service = AudioService
  method = detectAudioLoudness
  entries = [本机路径 + 开始微秒 + 结束微秒]
    ↓
lyra::AudioClient::detectAudioLoudness
```

`entries` 同样是结构说明，不是已恢复的 SDK JSON 字段名。实际函数构造一个包含 path/string 与两个 64 位时间量的向量元素；完整请求字段的正式序列化名尚未恢复，不应臆造 JSON 调用。

响应处理已明确：先检查顶层错误码，检查结果数组非空，再检查第一项结果码为 0；将第一项偏移 +8 的 double **直接**返回为 `avg_loudness`，偏移 +16 的 double **直接**返回为 `peak_loudness`，项状态码返回 `detect_result`。CLI 此处没有做线性音量、log 或 dB 换算。外层补充：

```json
{
  "operator": "loudness",
  "input": "本机路径",
  "start_us": 0,
  "end_us": 8000000,
  "avg_loudness_unit": "dB (LUFS-like)",
  "peak_loudness_unit": "dB peak"
}
```

因此，优先让正式 CLI/SDK 检测同一 source range，而不是将 FFmpeg 的 LUFS、TruePeak 或线性峰值混入其 peak_loudness 字段。SDK 测量算法实现、门限、通道权重，以及它与 EBU R128/BS.1770 的精确差异仍未知。`true_peak_ceiling` 也不能当作已接通动态压缩器或 limiter。

新增 REA Evidence：

- `ev_e701f5ac0b266d3f72a3822c93b83da79a53b79e5ce0bf6ceb16bed566ee1532`：归一化计划 handler。
- `ev_5337fe041833eb8259eb780c4066a30455d84e238c5ed99f2963fa87928ae05c`：SDK 测量请求与返回处理。
- `ev_f7b1979dc057845f4962118ab730799f54ef0739a61db8b3f725f4ec490a4308`：media loudness 时间与输出单位。
- `ev_995f16ab9fbe02d8aae056bd289b2b6ee6ac3b8e54dbeb59ad0b4099122c5179`：完整相关字符串库存搜索。

所有反编译结果是发布物静态推导，不能等同实际出片或 GUI 参数修改验收。降噪后续实测由主线程执行：显式 isDenoise=true 的 8 秒原生导出在静音区下降约 12.9 dB，但存在约 23.23 ms 延迟与对白变化；这项结果不延伸证明响度、EQ 或压缩可用。

### 当前音效资源检索类型

重新读取主线程保存的 `official-material-search-help.json`（mtime_ns `1793121677207304700`），`SUPPORTED SEARCH TYPES` 的最后两行是：

```text
mix_mode, material_lib, style, tone, video_mask,
voice_change
```

因此本机构建帮助中包含 `voice_change`，不是从旧文档推断。音效可优先使用 `material search --type voice_change --prompt "均衡器 EQ" --limit 5` 等意图查询；这只是应由主线程选择的合法搜索形状，本子任务未实际查询网络、未取得资源，也不能保证平台提供相应 EQ/压缩素材。`sound` 是声音素材检索，不能等同可编辑处理器。
