# 原生音效激活标记与原创 SAMI DSP graph 参数研究

日期：2026-10-28。目标构建：Windows 剪映 11.4.7.14462。

本轮是受委派的只读研究。没有 computer use，没有调用活跃剪映的编辑方法，没有执行下载包、发布 JS 或 DLL；没有修改 engine、桥接 ABI、凭据、权益或已有资源。新文件仅为研究笔记、只读 PE/LLVM 检查器及静态证据。原生出片实验由主线程执行，下面明确标明。

## 结论与最短路径

1. 原来的 radio 材料“能保存，但导出声音不变”已有明确遗漏：**主音频素材 `materials.audios[].check_flag` 没有从真实 SDK 结果移植**。正式 action 修改的是素材标记，不是 segment 的 `is_tone_modify` / `intensifies_audio`。同一素材 SDK 返回 `check_flag:3`，候选导出 JSON 中该字段缺失。主线程补回该原始标记后已测到音效真实生效。
2. 包内 EQ、Compressor、Limiter 并非只存在名字：已在本机 `audioeffect.dll` 中定位处理器 RTTI、vtable、参数目录构造器与归一化函数，能恢复下面的独立参数索引和数值换算。这是静态证据，尚不等于原创包已被剪映接受或 GUI 已显示多个旋钮。
3. 可以据此设计独立原创的三节点 graph，复用剪映已安装的处理器，不复制 radio 的预设数值或干湿曲线。建议先做一个 EQ 增益旋钮的原创最小包，独立出片并验证频带变化，再增加频率、压缩阈值/比率和限制器上限。原生包配置与 GUI 旋钮是否完整接受仍须实际验证。
4. 当前普通下载的 radio 包只公开一个 `(parameterIndex:0,portIndex:0)` 的干湿 macro。不能把该强度滑杆说成 EQ、压缩或 limiter 的独立控制。

## 一手证据位置与身份

安装根：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462`。

研究目录：`D:\JianyingHeadless\integrations\audio-localgraph-research-20261028`。

`artifact-identities.json` 记录安装 DLL、发布 JS 与四个原始声音包文件的完整路径、大小、SHA256。尤其：

- `audioeffect.dll` 是 SAMI/MusicDSP/Jukedeck 实现来源，包含本报告的参数目录与数学函数。
- `videoeditor.dll` 是素材恢复和音效 wrapper 来源。
- `Resources/canvas_agent/app/static/js/ai-creation~2.2895c133.js`，action 模块 83913，是主素材 `checkFlag` 的直接一手来源。
- `Resources/canvas_agent/app/static/js/ai-creation~5.38151757.js` 内的模型枚举可与既有研究 `research-native-audio/native-model-enums-74893.js.txt` 交叉核验。

任务根 `JOB`：`D:\JianyingHeadless\work\native-av-upgrade-20261028-004610-32bec1`。

只读原始声音包：`JOB/audio-resource-radio/7418519267659747877/752c3df02caa20b12bfa3154ed025bff`。

这是普通下载的官方资源，**不是开源素材，也没有将它改名声称自有**。本报告仅提取格式事实；没有将该预设的完整商业参数设置复制进仓库。新 graph 的配置应独立创作。

## 已证实的遗漏：`check_flag`

action 83913 先读取 `u.material.checkFlag`，若未设置 `VoiceChangeFlag`，创建主音频/视频素材 delta 并 OR 该位；随后才提交 `voiceChange`。这是 **primary material** 的字段，不是 segment 的布尔开关。

音频模型枚举：`BasicFlag = 1 << 0`，`VoiceChangeFlag = 1 << 1`。视频对应音效位是 `AudioVoiceChangeFlag = 1 << 11`，不能将视频值套给音频。原有位必须保留，不能统一覆盖所有素材为 3。

真实文件对照：

| 文件 | 同一主音频素材的 `check_flag` |
|---|---:|
| `JOB/voice-effect-session-native-v3-noenums/voice-effect-response.json` 的 `result.draftSnapshot.materials.audios[0]` | 3 |
| `JOB/audio-radio-half-export-v1/timeline.json` | 缺失 |
| `JOB/audio-radio-quarter-export-v1/timeline.json` | 缺失 |

主线程后续实测证据 `JOB/audio-radio-native-proof-v2.json`：旧的 full/half/quarter/soundhalf 与基准解码 PCM 无差异；补回 `check_flag` 的 flaghalf 相对基准有约 6.98 ms 延迟、约 4.05 dB 拟合增益，多个频带出现不同增益，拟合增益后的残差 RMS 约 0.0819。该结果支持音效链已运行，不能将其简化为仅音量变化。该测试的峰值测量约 +0.70 dBFS，主线程须在正式效果方案中控制输出并复测。

上述是主线程的真实实验结果，本研究没有自行调用导出或修改试样。

## 已有包的资源链与路径规则

包内 `config.json` 的 `effect.Link[0].type` 为 `SAMIAudioEffect`；`preset3.yaml` 声明 `effect: music_dsp_effect`，并通过 `chunk.mdsp_preset` 指向 `mdsp_preset.json`。

`videoeditor.dll` 的 `NewVEWrapper::createAudioSamiProcessorFilter`，RVA `0x15d2da0`，静态可见：

- resource path 为空会提前失败。
- resource path 拼接 `/mdsp_preset.json`。
- 参数索引以 `vector<pair<short,short>>`、数值以 `vector<double>` 交给原生处理器 filter。
- CCModel 对应实现 RVA `0x29c8c10` 同样拼接该文件名。

因此传入应为包含 `mdsp_preset.json` 的包目录，不能把 JSON 文件路径直接当包目录。原始包在主线程补回素材标记后已真实生效，说明该目录规则与本构建相容。相关 LLVM 文件：`renderer/videoeditor-0x15d2da0.txt`、`renderer/videoeditor-0x29c8c10.txt`。

原包 `extra.json.setting.audio_effect_parameters_change` 只有一个元素，0..1 的“强度”；其 graph 的参数输入 port 0 同时接往两个 `ParameterChangeTransform` 节点，各自调节 dry/wet gain。这不是直接映射到压缩器或 EQ 的参数。

## DSP 参数索引：当前安装构建的静态恢复

以下索引是 **processor 内部**的 `parameterIndex`。外层 `portIndex` 由 graph 的 `ports` 映射定义；不能把以下 processor 索引直接用在原 radio macro port 上。

### Equaliser

RTTI：`Jukedeck::MusicDSP::Processors::EqualiserProcessor`。

- vtable RVA `0xab32e8`，构造器 RVA `0x347e40`。
- 参数目录构造器 RVA `0x3a6fd0`。
- 目录按 8 个频段循环，每频段 5 个参数；代码中的参数索引从 0 开始。

对第 n 个频段（n=1..8），令 `b=5*(n-1)`：

| 参数名 | 内部索引 | 数值类型/物理范围 | 映射 |
|---|---:|---|---|
| `Filter n Bypass` | b | bool | 0/1 |
| `Filter n Mode` | b+1 | choice，目录含 10 项 | 完整 choice 次序仍需另外核对 |
| `Filter n Freq` | b+2 | Hz，20..20000 | logarithmic |
| `Filter n Q` | b+3 | 0.1..20 | logarithmic |
| `Filter n Gain dB` | b+4 | -20..20 dB | linear |
| 总体 `Gain dB` | 40 | -20..20 dB | linear |

例如第一频段 frequency=2、gain=4；第三频段 frequency=12、gain=14。`Mode` 只应在离线 `processor_state.parameters` 中使用已观察到的名字（如 Bell）；本轮不猜测它的 normalized choice 索引。

证据：`mdsp/annotated-0x3a6fd0.txt`，特别 RVA `0x3a7139`（Freq）、`0x3a717a`（Q）、`0x3a71bf`（Gain）、`0x3a71ff`（索引每次加 5）、`0x3a7242`（总增益索引 40）。

### Compressor

RTTI：`Jukedeck::MusicDSP::Processors::CompressorProcessor`。

- vtable RVA `0xab2ca8`，构造器 RVA `0x342410`。
- 参数目录构造器 RVA `0x3a1450`。

| 参数名 | 内部索引 | 物理范围 | 映射 |
|---|---:|---|---|
| `Bypass` | 0 | bool | 0/1 |
| `Ratio` | 1 | 1..40 | power，指数 2.5 |
| `Threshold dB` | 2 | -70..0 dB | power，指数 0.5 |
| `Knee dB` | 3 | 0..70 dB | power，指数 2 |
| `Attack` | 4 | 0.005..250 | power，指数 2 |
| `Release` | 5 | 1..2500 | power，指数 3 |
| `Auto Makeup Gain` | 6 | bool | 0/1 |
| `Output Gain dB` | 7 | -35..35 dB | linear |
| `Lookahead` | 8 | 0..10 | linear |
| `Use External Sidechain` | 9 | bool | 0/1 |
| `Sidechain Filter Enabled` | 10 | bool | 0/1 |
| `Sidechain Filter Mode` | 11 | choice，3项 | 次序未恢复 |
| `Sidechain Filter Cutoff Frequency` | 12 | 20..20000 Hz | logarithmic |
| `Sidechain Filter Resonance` | 13 | 0.1..20 | logarithmic |
| `Sidechain Audition` | 14 | bool | 0/1 |

Attack/Release/Lookahead 的参数名字与包内值已观察，**本轮静态目录没有恢复单位元数据**，不单凭一般音频常识承诺 ms；当前目标优先 threshold/ratio。

证据：`mdsp/annotated-0x3a1450.txt`。索引由 bool builder 的 r9d、linear builder 的调用栈索引、power builder 的调用栈索引分别明确设置；没有按 JSON 键顺序猜索引。

### Limiter

RTTI：`Jukedeck::MusicDSP::Processors::LimiterProcessor`。

- vtable RVA `0xab3710`，构造器 RVA `0x350020`。
- 参数目录构造器 RVA `0x3a8cc0`。

| 参数名 | 内部索引 | 物理范围 | 映射 |
|---|---:|---|---|
| `Bypass` | 0 | bool | 0/1 |
| `Input Gain dB` | 1 | 0..24 dB | linear |
| `Ceiling dB` | 2 | -24..0 dB | power，指数 0.75 |
| `Release` | 3 | 1..3000 | power，指数 3 |
| `Lookahead` | 4 | 0..10 | linear |
| `Audition Unity Gain` | 5 | bool | 0/1 |

证据：`mdsp/annotated-0x3a8cc0.txt`；`Ceiling dB` 的索引 2 与指数 0.75 在 RVA `0x3a8da7`、`0x3a8db4` 附近。

## normalized 值与物理值的精确换算

不能把 `-18 dB` 直接作为 `audio_adjust_params.value` 发给 normalized event 通道。离线 `processor_state.parameters` 使用人类可读名字和物理值；运行时参数事件采用 normalized 值，是不同层的约定。

火山引擎官方 [单音效处理器](https://docs.volcengine.com/docs/Audiotechnology/Singlesoundeffectprocessor?lang=zh) 文档（页面更新时间 2023-03-16）解释了离线 JSON state 与实时 ParameterEvent 的区别，实时 plain-value API 也明确存在。**剪映本机当前 wrapper 使用的则是下面经静态恢复的 normalized 通道，不能因 SDK 有 plain API 而混用单位。**

令 `u` 为经过 0..1 clamp 的 normalized 值，`a,b` 为物理最小/最大值：

```text
linear:  v = a + (b-a)*u
         u = (v-a)/(b-a)

log:     v = a*(b/a)^u       （本表的 a,b 均为正）
         u = log(v/a)/log(b/a)

power:   v = a + (b-a)*u^p
         u = ((v-a)/(b-a))^(1/p)
```

本机对应函数链：

- `0x30c350`：linear 参数 builder；`0x30c480`：log 参数 builder；`0x30c5b0`：带映射类型和 power 的参数 builder。
- `0x322c80` 根据映射类型 0/1/2 绑定 linear/log/power 的正反向 callable。
- `0x322010`：normalized→linear plain；`0x321fb0`：normalized→log plain；`0x322060`：normalized→power plain。
- `0x322210`：linear plain→normalized；`0x3220f0`：log plain→normalized；`0x322160`：power plain→normalized。
- thunk `0x9edc77` 的 IAT 确认是 `api-ms-win-crt-math-l1-1-0.dll!powf`；`0x9edbe1` 是 `log10f`。并非凭函数形状猜测指数/对数。

独立数学回算记录 `normalization-oracle.json`：

| 控件目标 | normalized u |
|---|---:|
| EQ gain +3 dB（-20..20） | 0.575 |
| EQ frequency 1000 Hz（20..20000） | 0.5663233347786729 |
| Compressor threshold -18 dB | 0.5518367346938776 |
| Compressor ratio 3:1 | 0.3047797829639662 |
| Limiter ceiling -1 dB | 0.9448338825910867 |

数学 oracle 只执行独立 Python 算式，没有加载 DLL、创建 DSP handle 或调用编辑函数；它验证换算的自洽性，不是音效渲染验收。

本机 `audioeffect.dll` RVA `0xd5a40` 从参数事件读取 portIndex、parameterIndex、normalizedValue 并交给 context。日志字符串和调用寄存器将这三项对应关系直接绑定；证据 `mdsp/parameter-event-0xd5a40.txt`。

## 原创 graph 设计建议与未知边界

已观察到合法包采用下列形状：根 `graph_container_node`，子 `processor_node`，`processor_name`，`processor_audio_buses_configuration`，`processor_state.parameters`，`connections` 和 `ports`。这只是格式事实，不能当作通用插件 SDK 的兼容保证。

建议独立创作的最小处理链：

```text
root audio input → original_eq → original_compressor → original_limiter → root audio output

root parameter input port 0 → original_eq,         internal parameter port 0
root parameter input port 1 → original_compressor, internal parameter port 0
root parameter input port 2 → original_limiter,    internal parameter port 0
```

外层参数 port 使用同一 processor 的内部索引，例如设计值 `(portIndex:1,parameterIndex:2)` 指向压缩阈值。建议先只做 root port 0→EQ，验证 `(0,4)` 确实改变第一频段增益，再测试另两个不同 port。**多 port 的这个分配是设计提案，本轮没有执行创建/运行，不声称它已经实测。**

`extra.json` 可声明多个 `audio_effect_parameters_change` 项，每项有 `parameterIndex/portIndex/sliderName/minValue/defaultValue/maxValue`。现有 radio 只有一项，不足以证明剪映 GUI 能同时展示 5 项或更多。发布 JS 普通调参按 index/port 共同匹配，vector 路径可保留多项；关键帧路径则只枚举 EffectAdjustParam1/2/3。**GUI 是否固定最多3个旋钮，以及第三个以上参数如何显示和保存，须由 UI 元数据/实际原生模型补证。**

不能为追求物理单位显示，直接将 extra 的范围填成 -70..0 并发送负值：现有 wrapper 进入 normalized DSP event。若要显示物理单位，需要先确定 GUI 的格式/转换支持；当前能确定的是 0..1 数据通道与上表换算。

最短可验证顺序：

1. 原 radio 只补 SDK 已存在的主素材标记，strength .5/.25 两次原生出片，确认参数真影响声音（主线程进行）。
2. 原创 EQ 单节点、单 normalized slider；保留合法本地包目录，固定频率/模式，gain 两点原生出片验证。
3. 加入 independent port 的 Compressor/Limiter，各参数单独对照；输出增益保持安全、避免自动补偿掩盖压缩效果。
4. 用正常原生 GUI 模型显示、修改、保存及 undo/redo，保存后从同一草稿再次导出并独立比较。
5. 验收前不能把 schema 接受、字段落盘或出现滑杆当作 DSP 实际已运行。

## 开源资料与覆盖限制

本轮围绕 `SAMIAudioEffect`、`mdsp_preset`、`ParameterChangeTransform`、`graph_container_node`、`sami_core_effect_param.h` 做了公开资料检索，未找到可直接复用且带可靠许可的剪映多旋钮 SAMI graph 作者库。搜索空结果仅是本轮检索范围的负结果，不代表全网绝无项目。

既有 pyJianYingDraft / pyCapCut 的素材框架、参数序列化，可供通用草稿结构参考；它们不是以上 proprietary DSP 参数目录的来源，也不能替代本机 renderer 验证。本轮没有引入新依赖或复制没有明确许可的源码。

还检查了剪映自带 `image_h5_material_publish` 两个 audio-effect 发布 JS；它们实际处理 mp3/wav 声音素材上传，而非 DSP graph 编辑器，对本任务没有可用 schema。REA target-free JS evidence `ev_f3a4871eed804fa50eb4b77f3da3b0eb9a87c2f8138c83d0bdf467faa1dc3166`；只分析两个文件，另外31个文件未选，静态关系覆盖部分且语义节点达上限，未执行任何 bundle。没有抢占 `audio_schema` 持有的原生 REA active target。

本报告的所有 VA/RVA 都仅用于当前 artifact 指纹下的研究定位；没有修改正式桥 ABI，不是允许在其它构建猜地址调用的配置。
