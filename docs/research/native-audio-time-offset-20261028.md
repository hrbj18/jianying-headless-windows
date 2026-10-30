# 原生音频入点、延迟补偿与预滚入口只读研究

日期：2026-10-28。目标构建：Windows 剪映 11.4.7.14462。

本轮读取安装发布物、现有代码与主线程已有实验结论；新增了绑定 PID/birth 的选择性 ReadProcessMemory 观察（IAT、配置根缓存和精确 feature 值）。没有连接编辑 pipe、没有调用编辑器 getter 或 mutator、没有加载目标 DLL、没有修改 engine、bridge、ABI、资源或用户草稿。地址均为固定构建的 RVA，**不是允许调用的裸函数清单**。

## 当前结论

1. `MainTimeLineSegmentAudioViewModel` 与其父 VM 没有直接修改 source start 的 Qt invokable/property。现成 Qt 方法是左右边缘裁剪事务，会改变时间线范围；不能直接当作只移动源入点的入口。
2. 原生 `CommonService.updateSegmentSourceStart` 确实存在，同时支持 `SegmentVideo` 和 `SegmentAudio`，它保留 source duration、只写 source start，并检查素材剩余长度。**真实请求携带的是 `shared_ptr<Segment>`，不是 segment ID**。当前只读调查没有找到其 JSON 请求工厂，也没有找到可供现有 typed bridge 直接调用的 QObject 所有者；不可凭服务名猜造 JSON 请求，更不可将原生 shared_ptr 当 QObject* 传入。
3. `CommonService.commonUpdateTimeRangeSegment` 与 `updateTimeRangeSegment` 有明确的正式 JSON DTO，包含 `record`，但它们表达边缘裁剪 `clip_type/clip_time`，没有分别指定 source/target range 的字段，不能作为纯 slip 或已完成的延迟补偿方案。
4. `audioeffect.dll` 有真正的 SAMI executor 延迟参数：`alg_latency_samples`、`cut_delay_samples`、`enable_pre_delay`、`first_wait_samples`。已经找到解析器、整数校验、setter 和从 executor 查询参数的实际代码；**尚未证明剪映内置实时降噪或当前 music_dsp_effect 使用这一 wrapper/config 入口**。这是后续值得追的原生补偿线索，不能直接塞进草稿或资源并宣称有效。
5. 新一轮已找到真正 host 功能 `ve_enable_latency_compensation`（bool，注册默认 false），并确认 decoder 的处理后丢延迟采样、EOF 静音补尾代码。正常 C++ `VEAdapterConfig` bool map 会下发到同一功能 registry；当前 addon JSON 未开放该 map，MixedService 的同名 AB setter 只改另一张 map。**静态路径已找到，现成入口能否正常启用及真实句首/句尾修复仍未验收。**
6. 主线程 v15 新证据已经推翻“后移 source in-point 即可完成补偿”：主体对齐仍会丢句首启动音频。因此，即使实现正常 source-start GUI 提交，也不应作为最终修复的验收标准。

## 发布物和证据范围

安装根：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462`。

- `VECreator.dll` SHA256：`769c33961ef9d7e471e583f03c975be975b0c35e849a767690d09e9f2fc45111`。
- `videoeditor.dll` SHA256：`fa89997a94e96cf97c8ee436a56ab028ea5f87731214696ba43ff74c0fdc0fa0`。
- `Resources/agent_runtime/runtime/videoeditor_addon.node` SHA256：`d9997bc0421a9da9ecafba4835bb8b4c1363de7a8c50e46be81b081766300be9`。
- `audioeffect.dll`：14,006,808 bytes，SHA256 `2a384edf76c59a92cc4a4f9d8504d7f512be6e27ae8e32069f0807a489378116`。
- `cccreator.dll`：158,351,640 bytes，SHA256 `a122d8b4c36f3300c8a32666e87b3b46c5acf61b7b32dc0e132bb8f62e1f39a1`。
- 独立证据目录：`D:\JianyingHeadless\work\native-av-upgrade-20261028-004610-32bec1\research-native-audio\time-offset`（下文简称 `E`）。

Qt metadata、RTTI、PE 导出表、异常目录函数范围和限定 LLVM 反汇编为一手静态证据。REA/Ghidra 仅分析 addon，没有执行它；新 snapshot 为 `E/rea-addon-time-offset.snapshot.json`，已正常关闭会话。REA 的 `0x180082580` 恢复结果再次确认 params 归一化及 `commit_immediately:true`，这并不证明任意服务方法有 JSON factory 或有 live GUI 历史语义。另查询 `0x180082ac0` 是参数键枚举辅助函数，对本目标没有新增业务结论。

## 正常音频 Qt 裁剪接口

完整原始结构见 `E/audio-base-meta.json`；不是通过方法名字符串猜测的签名。

| QObject 类 | metadata RVA | static_metacall RVA |
|---|---:|---:|
| MainTimeLineSegmentAudioViewModel | 0xa81e400 | 0x20704b0 |
| MainTimeLineSegmentViewModel | 0xa805ea0 | 0x2061360 |
| TimelineSegmentViewModel | 0xa816500 | 0x206bd20 |
| TimelineBaseViewModel | 0xa7f93c0 | 0x2059680 |

Audio primary vtable `0xac5a030`；QQml 派生 primary `0xa83fb18`。既有 `engine/live_editor/profile.py` 的固定指纹/secondary vtable 验证应保留；不要复用上次会话的对象地址。既有 native_client 的 segment→timeline 绑定为 `+0x298`，必须与本次 draft/session/timeline 的准确 segment ID 一致。

Audio 本地方法索引与真实调用链：

| 索引 | 精确 Qt 签名 | metacall 分支 | 发布物中的实现 |
|---:|---|---:|---|
| 54 | `bool cutLeftStarted(QQuickItem* rangeSlider)` | 0x2070868 | vtable+0x1d8 → 0x24bc160 |
| 55 | `void cutLeftPositionChanged(double mouseX)` | 0x207088e | +0x1e8 → 0x24bc120 → base 0x223f310 |
| 56 | `void cutLeftFinished(double mouseX)` | 0x20708a7 | +0x1f0 → 0x24bc040 → base 0x223e3c0 |
| 57 | `bool cutRightStarted(QQuickItem* rangeSlider)` | 0x20708c0 | +0x1f8 → 0x24bc3f0 |
| 58 | `void cutRightPositionChanged(double mouseX)` | 0x20708e6 | +0x208 → 0x24bc3b0 |
| 59 | `void cutRightFinished(double mouseX)` | 0x20708ff | +0x218 → 0x24bc360 |

这里只允许经正常 Qt method dispatch 进入，表内虚函数地址用于解释分派，不能绕过 Qt/桥接调用。证据：`E/audio-trim-metacall-jumps.json`、`audio-vt-*.txt`、`VECreator-0x223f310.txt`、`VECreator-0x223e3c0.txt`。

重要边界：

- `mouseX` 是几何坐标 double，不是 source start 微秒。0x223f310 读取本次裁剪上下限 `+0x3e0/+0x3e8`，读取轨道/画布状态，将位置除以对应 pixel size 后转换为 int64 时间；后续还经过吸附/裁剪状态流程。不能把 `6984` 或 `30204` 直接填入 mouseX。
- Started 依赖**实际 rangeSlider QQuickItem**与初始化的选中/轨道/画布状态。不能伪造 QObject 或用 null 跳过初始化。
- Audio 的 Finished 实现先调用 base finish；base finish 主要提交当前进行中的裁剪状态，不应省略 PositionChanged 后仅调用 Finished。
- 父类另有 `cutRightPositionChanged(int64_t duration)`，这不等于 Audio 类暴露了一个 source-start setter，也不等于该 overload 在当前音频上已经验证。没有绕过事务测试它。
- 静态阅读尚不足以声明样本级精度或负 target start 可用；应另外核对最终保存的整数时间，而非仅看滑块外观。

## 真正的 source-start 服务

### 请求结构和实现

VECreator 的 RTTI：`lyra::UpdateSegmentSourceStartReqStruct`，primary vtable `0xac2d6a0`，构造点在正常素材替换状态机 `MaterialReplacementManagerImpl::HandleExecuteModifySourceTimeAction`（RVA `0x219ee20`）。其真实参数尾部为：

```text
ReqStruct + 0xe0 : std::shared_ptr<lvve::Segment>   // 16 bytes，真实已选片段
ReqStruct + 0xf0 : int64_t                         // source start
```

构造点实际从当前 query utility 获取片段并复制 shared_ptr，绝非只写 ID 字符串。请求 service 为 `CommonService`，method 为 `updateSegmentSourceStart`。证据：`E/time-native-inventory.json`、`E/VECreator-0x219ee20.txt`。

DLL 导出：

```cpp
CommonClient::updateSegmentSourceStart(
  std::shared_ptr<lyra::UpdateSegmentSourceStartReqStruct>, long)
```

导出 RVA `0x16fec70`。服务注册表构造 `0x1c868f0` 在 `0x1c89b1c` 注册该名字，handler 为 `0x1c97cb0`，其调用 `0x1c53a10`：

1. dynamic_cast SegmentVideo；否则 dynamic_cast SegmentAudio。
2. 取得素材 duration 和现有 source TimeRange。
3. 若 `requested_start + current_source_duration > material_duration`，保持不变。
4. 否则调用 TimeRange start setter `0x103cd0`，不重建 target range，也不改现有 source duration。

这里的 TimeRange 是草稿原生微秒单位；本机既有 fixture `source_start_us=6984` 对应 308 samples 的证据来自主线程，不是本轮静态代码独立测量。helper 没有显式拒绝负 start 的分支，**缺少检查不构成合法支持**；调用者/UI、保存、恢复、导出还可能拒绝或裁切负值。安全调用仍应满足 `0 <= start` 且 `start + source_duration <= material_duration`。

证据：`E/videoeditor-0x16fec70.txt`、`videoeditor-0x1c868f0.txt`、`videoeditor-0x1c97cb0.txt`、`videoeditor-0x1c53a10.txt`。handler 的 `0x1c839c0` 是获取 `DraftService.getWorkingDraft`，不能把它误标成 draftRecord/历史事务。

### 不能直接发布的原因

当前 DLL 的 RTTI/factory 定位找到 `UpdateTimeRangeSegmentReqStruct`、`CommonUpdateTimeRangeSegmentReqStruct`、`MultiUpdateTimeRangeSegmentReqStruct` 的 `lyra::reqMakerImpl`，没有找到 `UpdateSegmentSourceStartReqStruct` 的相应 factory。它的 request type 在 VECreator 构造，DLL 只看到相应 response type。这个结论只限当前发布物和搜索，不证明另一个隐藏 transport 永远不存在。

因此本轮没有给出猜造的 `edit/common.updateSegmentSourceStart` JSON，也没有把 shared_ptr 包装成 QObject*。当前 typed bridge 只能传它支持的正常 Qt 参数；不能为这一内部 C++ 请求修改 ABI。

正常素材替换编辑器确实有 sourceStart：

- `MaterialReplacementEditorViewModelNew` meta `0xa803990`，metacall `0x2060b10`，`onReplaceClicked()` 本地索引 24，`updateContentX(double x,bool bSeekStart)` 索引 35。
- 旧 `MaterialReplacementEditorViewModel` meta `0xa814970`，metacall `0x206a380`，`onReplaceClicked()` 索引 22，`updateContentX(double x,double offset)` 索引 33。
- `MaterialReplacementManagerImpl` meta `0xa82b7b0` 只有取消导入、导入完成两个 slots，没有公开 start/modify-source 方法。
- Canvas 的 `replaceSegmentFromMenu()` 本地索引 129 是替换工作流入口，未证明它能无文件选择地开启纯音频 slip 编辑。

这些编辑器依赖正常 manager/editor callback 状态；不能手工实例化/伪造 callback 来调用 onReplaceClicked。还没追到供当前 Audio segment 复用的正常 loader，不宣称 GUI live source-start 修改已经可用。证据 `E/replacement-canvas-meta.json`。

## CommonUpdateTimeRange 的真正 JSON DTO

`lyra::reqMakerImpl<CommonUpdateTimeRangeSegmentReqStruct,...>` vtable `0x31400a8`，makeReq `0x1887da0`；普通 UpdateTimeRange 的 makeReq `0x188cd70`。两者都经 envelope parser `0x186de90` → params parser `0x1879fb0`。

| key | 类型/尾部偏移 | 含义范围 |
|---|---|---|
| seg_id | string，ActionParam+0x18 | 片段 ID |
| clip_type | number/enum，+0x38 | 边缘裁剪类型；不能传字符串假冒 native enum |
| clip_time | int64，+0x40 | 裁剪边缘时间 |
| record | bool，+0x48 | 正式记录标志 |
| is_spread_for_cut | bool，+0x49 | 可牵连其它片段，纯校准不应开启 |
| curve_speed_points | array，+0x50 | 速度曲线数据 |
| auto_adjust_tts | bool，+0x68 | TTS 联动 |
| force_resolve_track_conflicts | bool，+0x69 | 冲突处理 |
| is_handle_end_task | bool，+0x6a，构造默认 true | 结束任务处理 |

并没有 `source_start`、`target_start`、`source_range`、`target_range` 可在这个 DTO 中分别设定。不存在“省略 target 就只改 source”的静态证据。`clip_time` 是项目整数时间单位；发布 Web 调用（`ai-creation~13` 模块边缘处理与 `ai-creation~28` executeTrimPlan）用 `ClipStart/ClipDuration` 和 target start/end 运算，进一步表明这是 trim，而非 slip。Web 枚举值不能直接当本机 native enum 数值。

证据：`E/videoeditor-0x1887da0.txt`、`videoeditor-0x188cd70.txt`、`videoeditor-0x186de90.txt`、`videoeditor-0x1879fb0-annotated.txt`、`E/cliptype-js-excerpts.json`。

尚未恢复足够证据证明此正式边缘裁剪服务允许负 target start 或有样本级输出预滚；不能据 `int64` 有符号就作此保证。它的 `record:true` 也不能证明另一个直接 source-start helper 已经录入 GUI 历史。

## SAMI 的原生延迟补偿线索

`audioeffect.dll` 的真实 common executor 配置解析器 RVA `0xb1a60` 含以下 key（相关类型校验存在于各分支）：

```text
enable_pre_delay          bool
alg_latency_samples       integer
first_wait_samples        integer
cut_delay_samples         integer
need_flush                bool
alg_require_process_samples / alg_max_process_samples
```

setter `setAlgLatencySamples` RVA `0xb54d0` 将非负整数保存至对象 `+0xb8`；`setCutDelaySamples` RVA `0xb5700` 保存至 `+0xd4`。两者对负数返回错误。单位由代码中的 `*_samples` 和整数值表明是采样数，不是微秒或毫秒。

`queryCommonParamFromEngineExecutor` RVA `0xbdaa0` 查询 executor 的 `latency_samples`、`cut_delay_samples`、`first_wait_samples` 等；其正常调用者 `createExecutor` RVA `0xbcf70`。源码路径字符串为：

```text
sami_interface/src/capi/engine_executor/common_executor/sami_core_common_utility.cpp
sami_interface/src/capi/engine_executor/common_executor/sami_core_common_executor_wrapper.cpp
```

直接 caller `0x93770` 是 `sami_core_common_aec_utility.cpp` 的 parseConfigInfoParam，证明至少 AEC 派生 utility 会复用 common parser；这**不能证明**剪映本次 realtime denoise 也走相同派生 utility。

相关已导出能力还有 `mammonengine::AudioEffectNode::getLatency`（`0x13ca10`，转交内部 effect）、`mammon::CascadeEffect::getLatency`（`0x19ea60`，读取其 `+0xd0`），但 `mammon::Effect::getLatency` / NonRealtimeEffect 基类默认实现都返回 0。尚未从本次真实 Limiter processor 一路追到最终 host 是否采用它的报告值；不能只凭 getLatency 符号推断系统已经自动补偿。

证据：`E/audioeffect-0xb1a60-annotated.txt`、`audioeffect-0xb54d0.txt`、`audioeffect-0xb5700.txt`、`audioeffect-0xbdaa0-annotated.txt`、`audioeffect-caller-0xbcf70-annotated.txt`、`audioeffect-caller-0x93770-annotated.txt`、`sami-common-direct-callers.json`。

搜索边界：Resources/audiosami 与 rnnoise 目录内现有 json/yaml/yml/txt/xml 没有上述配置项；未解密、未改写模型。当前原创 music_dsp_effect 使用 `config.json` → `preset3.yaml` → `mdsp_preset.json` 的图入口（`engine/native_dsp_graph.py`），尚未证明它将额外 YAML key 传给这个 common executor。不要猜其注入位置或用 setter 裸地址更改运行内存。

历史 bounded negative（已由下节 cccreator 真实 key/消费者证据部分推翻）：此前 VECreator/videoeditor 的短字符串及导出表中没有找到可绑定到本次音频导出的 preroll/delay-compensation 配置；大多 latency 符号属于播放器帧预取。`cccreator.dll` 同类搜索得到 AudioPreprocessFilter、VEAudioPreprocessorImpl 和 getAudioClockWithoutLatency 等，不足以证明本次 DSP 导出会预滚。完整搜索结果分别为 `E/latency-preroll-inventory.json`、`cccreator.dll.json`。`CCAudioPreprocessFilter` 名字不能当作可编辑的音频预滚效果。

## v15 之后的验收与下一步

主线程最新实测：真实非静音句首输入，加 100ms 无损前后 padding 后，原生 DSP+denoise 仍有 1331/1332 samples 延迟；source start 再加 30204us 只令主体 lag 变为 -1/0 sample，前 10ms 仍全零，前 30ms RMS 约 4.5e-5，对照约 0.05。原始 quote PCM 完整。这些是主线程提供的实际结果，不是本轮新执行的实验。

这与“在处理器启动之前裁 source，再从新的片段起点重启处理”一致；目前仍是由实验推断，未静态证明具体 host 处理顺序。最终修复必须同时验证句首/句尾保存、整体 lag、每声道能量、轨道范围、历史与重新导出的结果。

优先继续追的正常入口：

1. 找到内置 realtime denoise/本地 music_dsp_effect 实际创建的 SAMI context 类型，核实 `cut_delay_samples` 是否由模型/效果 executor 原生声明、是否被 host 采用；有真实消费者证据后才能尝试既有配置入口。
2. 如需要 timeline 预滚，先在独立稿验证从处理后的总时间线中导出一个正起点范围，是否在 export-range 起点前真实执行音频 DSP；仅在文件末尾裁去头部不是输入预滚证据。本轮未定位可保证这个语义的正式 export/player 字段。
3. 当前 `engine/native_compound.py` 仅声明 macOS 11.4.2/11.5.0，且因 native save 丢失 sidecar 禁止 live registration。它不能当作现成 Windows 解法；Windows 子时间线预滚、保存重开与可编辑性均需独立验证。

本报告的未完成项是正常当前 GUI 的 sample-accurate delay compensation/预滚提交路径；已恢复的内部 source setter、trim record 字段和 SAMI 参数不能替代这个验收。


## 新突破：真正的 host latency compensation 功能与消费者

本节是对此前 bounded negative 的实质更新，仍为纯静态证据，未启用功能或执行原生实验。

### 注册、类型、默认值

`cccreator.dll` RVA `0x3b5b0` 注册精确 key **`ve_enable_latency_compensation`**，长度 30；传入 default `r9b=0`。注册 helper `0xd5e1e0` 将 default 保存至 registry record `+0x18`，将类型 word `+0x22` 设为 1。后续所有消费者通过同一 feature ID 及 bool lookup `0xd5e7d0` 读取。因此这是注册为 bool、默认 false 的原生音频补偿功能，并非拿名称相近的播放器延迟开关代替。

证据：`E/cccreator-annotated-0x3b5b0.txt`、`cccreator-annotated-0xd5e1e0.txt`、`sami-latency-feature-xrefs.json`。功能 ID 的全局存储位置仅用于 xref 归因，不能写它来启用功能。

### SAMI host 真正查询了处理延迟

- `TEAudioSAMIProcessorFilter::createSAMIHandle`（所属 init function `0x9a9a80`）在资源 JSON 读取、`SAMICoreCreateHandleByIdentify(0,...)`、property `0x64` prepare 之后，若 bool 功能开启，就调用 `SAMICoreGetPropertyById(...,0x25b,...)`。成功且 data 非空、读取的 int32 >0 时，保存为 int64 到 filter `+0xc0`。失败日志明确为 `failed to get latency property or data is null, ret=%d`。
- `TEAudioSamiProcessor::init`（`0xa1b7b0`）在普通降噪 context 创建之后也受同一 bool gate 控制，查询 property `0x25b`，将 data 内 float 转为 int64，存 processor `+8`。`TEAudioSamiFilter::processAudio`（`0x9b10d0`，精确分支 `0x9b29ec..0x9b2a10`）把该值转存 filter `+0xc0`。
- 不应把上述两种 context 的 property payload 强行统一为 int32 或手工调用 property API。MDSP 的 int32、denoise 的 float 是本机不同 host 代码中的实际读取类型。
- 初始化按源采样率准备。MDSP prepare 的 blocksize 为 `0x400`，支持采样率范围的检查为 16000..96000。补偿计数的后续消费者以 PCM sample-frame 数工作，**不是微秒或毫秒**。

证据：`E/cccreator-annotated-0x9a9a80.txt`、`cccreator-annotated-0xa1b7b0.txt`、`cccreator-annotated-0x9b10d0.txt`。以上证明 host 会问 context 要延迟；尚未新实测本次 denoise+五控件图返回值是否等于测量延迟，不能把主线程的 1331/1332 samples 直接替成配置值。

### decoder 丢的是处理后启动延迟，并正常 flush 尾部

`TEAudioDecodeReaderUnit3` constructor `0x3a7790` 在创建时读取同一 bool，缓存至 reader `+0x93c`。相关代码：

1. `applyAudioEffect`（`0x3ba360`，分支 `0x3bb51c` 后）在补偿启用且尚未捕获延迟时，将输出 int64 指针交给 `processAudioSample(0x886010)`。成功且延迟数 >0 后，将计数写至 reader `+0x940`（待丢输出样本）和 `+0x948`（待补尾样本），设置 `+0x93d` 已捕获标志。
2. `writeProcessedCache`（`0x3b26e0`，关键分支 `0x3b2739..0x3b2840`）计算 `drop=min(output_sample_count,pending_drop)`；整块属于延迟则把样本数设为 0，部分属于延迟则把每个 plane 的后续 PCM 搬至首部并减小样本数，再写处理缓存。它兼容 planar/interleaved、按 format/channels 计算 stride，并递减待丢数。
3. `prepareDecodedCache`（`0x3ae5c0`，关键分支 `0x3ae750..0x3ae86d`）在功能开启、源 EOF 已到达、`+0x948>0` 时，以 `min(pending_flush,block_capacity)` 调 `createSilenceAudioSamples`（`0x85aa00`），成功后递减待补尾数，再进入正常处理/写缓存。该 helper 的日志函数名确为 `createSilenceAudioSamples`；内部创建指定 frameCnt 的音频 block、填静音并设置样本数。

这是正常 **处理输出丢启动延迟 + 源结束后补静音 flush** 的代码，和 v15 中先裁 source in-point 再启动处理的行为不同。它为保全句首、句尾提供了有根据的原生候选，但静态路径存在不等于本次实际导出已经修复。

证据：`E/cccreator-annotated-0x3a7790.txt`、`cccreator-annotated-0x3ba360.txt`、`cccreator-annotated-0x886010.txt`、`cccreator-annotated-0x3b26e0.txt`、`cccreator-annotated-0x3ae5c0.txt`、`cccreator-annotated-0x85aa00.txt`。

### 生效时序

- **decoder 创建前**需正常提供 bool。constructor 将值缓存；未发现常规运行中重新读取该缓存字段的 setter。不能在已创建的当前 decoder 上改全局配置后就断言新行为生效。
- MDSP `initSAMI` 在 handle 已存在时直接返回初始化状态；其延迟 query 因而依赖正常 handle 创建/准备时的配置。denoise processor 也是 init 时查询。应由正常 session/player/export 创建生命周期构造新 decoder/context，不能手工改 handle 或 cache flag。
- `lvve::InitVEAbConfig`（videoeditor `0x1564e10`）自身有进程级 init-once guard；首次调 `InitVEAbConfigInner(0x1564ed0)`。再次调用它并不保证重新应用 map。
- 另一路 `VeWrapper::initVeConfig(0x2c4f690)` 可进入 `VESDKModule::veGlobalConfigInit(0xeab7c0)`；该函数的 static map 初始化 guard 不是整个函数只运行一次的证据。它也受本机 wrapper 正常初始化条件控制，不应裸调绕过。

## 正常配置链：已确认与仍缺的入口

### VEAdapterConfig 的版本绑定结构与正式下发

本版 `videoeditor.dll` 导出表明确存在：

```cpp
lvve::InitVEAbConfig(const lvve::adapter::VEAdapterConfig*);
lyra::wrapper::internal::VESDKModule::veAbConfigInit(const VEAdapterConfig*);
lyra::wrapper::internal::VESDKModule::veGlobalConfigInit(const VEAdapterConfig*);
PlayerClient::setVeAdapterConfig(shared_ptr<lyra::SetVeAdapterConfigReqStruct>, long session);
```

MSVC `make_shared<VEAdapterConfig>` 路径 `0x2bc7a20` 分配 `0xc08` 字节，payload 从 `+0x10` 起，明确 `memset(payload,0,0xbf8)`；结合 RTTI `Ref_count_obj2<VEAdapterConfig>` vtable `0x315e620` 和 copy constructor 路径 `0x1972490`，可确定**本版 payload sizeof 为 `0xbf8`**。不能跨版本照搬布局，更不能用这个大小手工拼对象。

已确认的 map 位置如下；“ab_bool_config”是导出 cache 的确切标识符，原始 `VEAdapterConfig` 成员的 C++ 源码拼写/JSON 字段名仍未找到，表内名字是研究标签。

| VEAdapterConfig 相对位置 | 静态确认内容 |
|---:|---|
| `+0xb70` | MSVC `std::map<std::string,int>` |
| `+0xb80` | MSVC `std::map<std::string,bool>`，本目标需要的 bool map |
| `+0xb90` | MSVC `std::map<std::string,std::string>` |
| `+0xad0` | 包含上述 map 的配置子结构起点；copy helper `0x115abf0`，相对 `+0xa0/+0xb0/+0xc0` 分别复制三张 map |

这些是 tree map，**不是 std::function callback**。`InitVEAbConfigInner(0x1564ed0)` 和 `veAbConfigInit(0xeab290)` 从 tree node `+0x20` 取 string key，从 node `+0x40` 取 bool value，通过 getGlobalConfig 返回接口的 vtable `+0x10` 下发。`veGlobalConfigInit` 先将 map 与 cache 合并，再在 `0xeabff0..0xeac001` 走同一 bool setter；其前面的 getVEUtils 是另一个正常辅助接口，不应把整个函数所有 slot 都归为 GlobalConfig。

`getGlobalConfig` 是 **cccreator 正式导出 C API**（`0x177fd0` → `0x2a1390`）；它创建的 primary vtable `0x484e190` 的 `+0x10` 为 `0x2a15e0`。该 setter 正常按 key 查询 registry，检查 feature ID，再交 bool 配置更新函数。因而能把 `ve_enable_latency_compensation=true` 下发到前节 host 实际读取的同一 registry；这不是同名但不相干的 config 推断。

**这仍是 C++ 容器接口证据，不能直接将上表当 JSON schema，也不授权调用裸虚函数。** 安装发布目录未找到对应 `.h/.hpp` 原始头文件；未恢复完整源成员名。

证据：`E/videoeditor-config-exports.json`、`ve-adapter-rtti.json`、`ve-adapter-owner-xrefs.json`、`videoeditor-annotated-0x2bc7a20.txt`、`videoeditor-annotated-0x1972490.txt`、`videoeditor-annotated-0x115abf0.txt`、`videoeditor-annotated-0x1564ed0.txt`、`videoeditor-annotated-0xeab290.txt`、`videoeditor-annotated-0xeab7c0.txt`、`cccreator-annotated-0x2a1390.txt`、`cccreator-annotated-0x2a15e0.txt`。

### 现有 addon initialize JSON 未开放该 map

发布 `Resources/canvas_agent/runtime/videoeditor-service.mjs` 把外部 config 原样 `JSON.stringify` 交给 addon `initialize`。NAPI 正式注册函数 `0x24eee0` 绑定 callback `0x24c3d0`；后续经 `0x25bfc0` 到 runtime initialize `0x262de0`，其 JSON parser `0x25b660` 本轮逐条检查只解析：

```json
{"editorName":"...","modelsDir":"...","algorithmConfigPath":"..."}
```

parser 随后只补齐资源/缓存路径（`0x23f3c0`）。没有把任意 AB bool object 转为上述 `std::map` 的路径证据。故不能建议在 initialize JSON 里塞 `ab_bool_config`、`abConfig` 或任意自创 key 并声称已经启用。也不能把 algorithmConfigPath 当成 VE AB 配置文件路径。

`PlayerService::setVeAdapterConfig` handler `0x2228f80` 存在，会从请求 `+0x58` 复制完整 VEAdapterConfig 并交本 session VeWrapper::init。它证明正式 C++ 服务刷新路径，但当前限定检索未找到对应 JSON request factory/普通 CLI schema；不能把 request 的内嵌 C++ map 当现成 JSON action。完整 key-search 结果保存在 `E/config-map-field-name-search.json`。

证据：`E/runtime-native-init-snippets.json`、`addon-initialize-name-xrefs.json`、`addon-init-binding-0x24eee0.txt`、`videoeditor_addon-annotated-0x24c3d0.txt`、`videoeditor_addon-annotated-0x262de0.txt`、`videoeditor_addon-annotated-0x25b660.txt`、`videoeditor_addon-annotated-0x23f3c0.txt`、`videoeditor-annotated-0x2228f80.txt`。

### MixedService.setABConfigBool 的直接消费者确实不同

本次进一步追了实际注册与实现，没有依名称认定生效：

- `MixedService` 注册函数 `0x1965aa0` 将 operation `setABConfigBool` 绑定到 `0x1f97650`。
- handler 从 request `+0x58` 取 string，从 `+0x78` 取 bool，调 `0x1f8ec80`。
- `0x1f8ec80..0x1f8ed64` 完整函数仅查找/更新 **videoeditor 自己的另一张 `std::map`**；没有调用 getGlobalConfig 或本节 VE bool setter。`SetABConfigBoolReqStruct` 的 C++ payload 布局也不等于可猜的 JSON `key/value`。
- 另外正式导出 `lvve::SetABConfigBool(0x10cd780)` 修改的又是 LVVE 本地 bool map（并非 Mixed map），完整函数同样只有 map 更新。

所以这些直接 setter **没有直接传播到 cccreator host feature registry**。尚未发现“之后某个正常读取流程自动把 Mixed key 搬入 VEAdapterConfig”的链路；不能把 Mixed setter 返回/读回 true 当成音频补偿已经开启。

注意 PE `.pdata` 将 `0x1f8ec80` 函数分成 prologue/续段；只读 helper 最初的 22-byte 截取不完整。本结论依据完整限定范围 `E/videoeditor-fullrange-0x1f8ec80.txt`，不是依据缺失调用的 prologue 作 negative 判断。

证据：`E/ve-config-op-name-xrefs.json`、`videoeditor-annotated-0x1965aa0.txt`、`videoeditor-annotated-0x1f97650.txt`、`videoeditor-fullrange-0x1f8ec80.txt`、`videoeditor-annotated-0x10cd780.txt`。

## 更新后的可执行边界与验收建议

此时问题已经从“引擎有没有补偿”缩小为 **现成入口能否在新 decoder/context 创建前正常提供 VEAdapterConfig bool map**。当前仍没有已证实、保持 ABI/bridge/vendor pins 不变的 addon JSON/CLI 配置入口，因而本轮不给出伪造的最小 JSON 请求。

后续只能使用已有正常配置生产者/正式服务支持的结构与生命周期，先在独立稿/新导出 worker 验证。若找不到，不写 feature 全局、不改开发信任开关、不改 DLL、不造未知 ABI 容器。

真正验收应保留 source/target ranges、处理图、原始 PCM，并重新量测：

1. source start 不做 v15 的 30204us 平移；主体 lag、首 10/30ms 与句尾对应能量一起检查。
2. 检查 decoder 新建、context query 成功与其报告 latency；分别测 denoise、DSP、组合链，不能假设每个算法都正确报告延迟。
3. 采样单位按当前源/处理采样率核对，不把 sample count 当 us；立体声按每声道量测并测末尾 flush。
4. 在真实项目中另验保存重开、正常 GUI undo/redo、首尾与相邻片段连续性。本轮纯静态调查并未完成这些实际验收。


### 现成环境变量、配置文件和头文件的窄查负结果

按父任务最新要求继续限定范围查证，未重复追 Mixed AB：

- 安装版本目录中没有找到 `.h/.hpp`；不能给出未经来源支持的 VEAdapterConfig map 源成员名。上文本版 `sizeof=0xbf8` 和 `+0xb80` 的依据是 RTTI、构造、复制、真实遍历代码，并非原厂公开头文件。
- 发布 Resources 中 json/ini/yaml/yml/xml/conf/cfg/mjs/js 对三个精确 term `ve_enable_latency_compensation`、`ab_bool_config`、`VEAdapterConfig` 没有匹配文件。因此没有现成文件可直接指定此 key 的证据；未读用户账号设置或凭据。
- 窄查 `cccreator` 的 `TERuntimeConfig` singleton 构造 `0xd5d8e0→0xd5d800`、注册/用户配置入口 `0xd225a0`，未见读取环境变量或配置文件。构造建立按 feature 数量分配的值 vector、mutex，再执行正常注册回调。
- 对本机 cccreator 的 getenv/GetEnvironmentVariable 直接 import 调用进行了静态限定清单：共 44 处 direct FF15/FF25 refs；核心 RVA `<0xe00000` 只有 `0xa42040` 中两处 getenv_s，参数是 **`OFX_PLUGIN_PATH`**，属于插件搜索目录，不能用于 VE AB 补偿；runtime-config 范围 `0xd20000..0xd60000` 没有此类 direct imports。这个结果不排除其他模块/间接回调，故不作“任何环境变量都不存在”的全局断言。
- 发布 `VEConfig.dll` 相关导出/字符串窄查没有 VE AB bool setter 或此 feature key。它的路径/INI/algorithmConfig 名称不能当成音频 feature config 格式。
- 2026-10-28 对精确术语进行了互联网检索：`"VEAdapterConfig" "ab"`、`"ve_enable_latency_compensation"`、`"getGlobalConfig" "cccreator"`、`"InitVEAbConfig"` 均未返回结果。没有可引用的公开一级 SDK 头文件/文档；这不是私有文档不存在的证明。

记录：`E/normal-config-search-boundary.json`、`cccreator-runtime-config-strings.json`、`runtime-config-source-xrefs.json`、`cccreator-annotated-0xd5d8e0.txt`、`cccreator-annotated-0xd5d800.txt`、`cccreator-annotated-0xd225a0.txt`、`cccreator-environment-import-calls.json`、`cccreator-annotated-0xa42040.txt`、`veconfig-published-config-surfaces.json`。

当前精确剩余边界仍是：**host 已有真实补偿实现；本版现成 addon initialize/公开 JSON service 尚未找到正常 VE bool map 入口。** 不建议为了启用它扩展裸 ABI、写 registry 全局或试填未验证环境变量。后续若取得原厂适配配置提供者/正式带此 map 的请求工厂，再做独立 worker 的句首句尾实验。


## 更新：正常 GUI 已有 INI 生产路径，且当前 host 实际为 true

本节进一步缩小了上一节“尚未找到文件入口”的范围：**GUI 正常配置生产者已经找到；现有独立导出适配器没有接入这条生产链。** 没有修改 INI 或启用开关，也不能把现有 true 归因于本轮操作。

### 本版正常 frontend 配置链与精确 INI 格式

VECreator `LvSceneCoreUtils::setVEABTestConfig`（`0x10f9020`）在正常 init-once 内执行 lambda `0x10ee080`：

1. 通过现有 IAT `+0x7f2d118` 调 `VEConfig::path::getConfigPath()`，转 QString→QDir→`filePath("ve_ab_conf.ini")`。
2. 使用 `QSettings(filename,1 /*IniFormat*/,nullptr)`，`beginGroup("configs")`，`allKeys()`，逐项 `value()`。
3. QVariant bool 直接进入 bool map；QString 分支先尝试 `toInt(&ok,10)`，成功进入 int map；失败后只把与 ASCII `true`/`false` 精确相等的文本放入 bool map，其余进入 string map。因此 bool 的最小格式应为下例，**不能使用 `=1` 来充当该 bool**：

```ini
[configs]
ve_enable_latency_compensation=true
```

4. 稍后的 `MixedService.getVEAbMap` 是**读取 VE AB key 类型清单/正常设置补充来源**，和上文已排除的 `setABConfigBool` setter 不同。`0x10ef442..0x10ef477` 在 bool map 已有 key 时跳过补充，不覆盖该本地 INI 值。
5. `setVEABTestConfig` 从缓存 maps 正常复制到 VEAdapterConfig `+0xb80/+0xb70/+0xb90`。`LvSceneCoreUtils::initVEAbConfig(0x10f6930)` 在 `0x10f80ab` 等位置调用这个 producer，再走正式配置初始化。无需写 feature 全局、修改 DLL 或调用裸 vtable 才能提供这张配置表。

Qt 官方文档确认 `IniFormat=1`、指定 filename 的 QSettings 是文件路径、INI 数字会作为字符串读回；此处 bool/int 的进一步判定来自剪映真实分支，不是 Qt 文档凭空推断。[Qt QSettings](https://doc.qt.io/qt-6/qsettings.html#Format-enum)

**生效时序：** producer 自身使用 InitOnceBeginInitialize/InitOnceComplete，不能认为已有进程中新建草稿或改文件就会重读。host decoder/context 还各自缓存/查询配置，因此后续正常配置实验必须明确进程、decoder 和 context 的代际。这里不执行重启或文件修改。

证据：`E/gui-veab-producer-xrefs.json`、`VECreator-annotated-0x10ee080.txt`、`VECreator-annotated-0x10f9020.txt`、`VECreator-annotated-0x10f6930.txt`、`veab-ini-passive-import-resolution-current.json`。

### 路径身份与被动确认

VECreator 的发布 IAT 名称受其打包保护，不能将原始 qword 错当明文 hint/name。父线程以既有只读 IAT 工具确认，子任务也选择性读同一当前进程 slot 并对照静态模块导出：

```text
PID 26548 / birth 134376361343594314
VECreator.dll + 0x7f2d118
 → VEConfig.dll + 0x113a0
 → ?getConfigPath@path@VEConfig@@YA?AV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@XZ
```

其余相关 slot 也逐个对照到正式 Qt 导出：QDir 构造/filePath、QSettings 构造/beginGroup/allKeys/value、QVariant::metaType/toBool、QString::operator==(const char*)、QString::toInt。这没有调用任何 getter 或执行 native API。

`getConfigPath` 的静态函数 `0x113a0` 最终缓存 std::string 于 **VEConfig.dll `+0x4c880`**；被动读取值为：

```text
C:\Users\Administrator\AppData\Local\JianyingPro\User Data\Config
```

所以本机正常文件位置为该目录下 `ve_ab_conf.ini`。证据 `E/VEConfig-annotated-0x113a0.txt`、`veab-ini-passive-import-resolution-current.json`、`veab-ini-passive-config-root-and-feature-state.json`。

### 现有文件没有此 key，当前 true 的来源不能归因

只读该既有文件的 stat 和目标 key（不打印其它配置项）得到：

- 3957 bytes，UTF-8；mtime/birth 为 `2026-10-28T04:42:25.019/018 UTC`（北京时间约 12:42:25）。
- SHA256 `658669bdb64d23e3cf43c25787c321694c472629fed1cbc9543edebc01b685b0`。
- 全文 `ve_enable_latency_compensation` literal 计数 **0**；也没有对应 `%5F` 转义形态。

父线程明确说明本轮没有创建/修改此 INI；子任务同样没有写它。mtime 只能描述现有文件时间，不能恢复创建者/来源。

与此独立的当前进程被动观察：GUI producer 初始化 flag 为 1，bool map 有 203 项，精确 key 已存在且为 **true**；cccreator 同 key 的 feature ID 为 144，已物化 value 对象的直接缓存 flag 为 1、bool 值亦为 **true**。这只说明当前 GUI 进程里 host 已开启；由于文件没有此 key，其值可能由正常 `getVEAbMap`/设置源补充，但本轮未把来源完整追实，不能写成“我们通过 INI 已开启”。

证据：`E/existing-veab-ini-key-and-metadata-readonly.json`、`existing-veab-ini-exact-key-absence.json`、`veab-ini-passive-config-root-and-feature-state.json`。旧 PID 26164 已失效时第一次只读模块枚举正常失败，没有回用其对象；所有成功观察绑定父线程提供的新 PID/birth。

### GUI 与独立导出：现有适配器必须分开验证

实际离线导出适配器 `engine/native_export_windows.cpp` 的当前源码：

```cpp
startup(&server, nullptr);
long sid = open_session(&server, nullptr, &name);
```

它加载 videoeditor.dll，并传 null VEAdapterConfig；没有加载/调用上述 VECreator frontend producer、没有读取 ve_ab_conf.ini、没有调用 InitVEAbConfig。可选 built-in-resource-root 分支只补资源路径。`engine/jypack_render.py` 与 `engine/native_export.py` 编译/运行此独立 helper。

因此 GUI registry=true **不能外推**到独立 ExportService helper 的 registry。当前源码足以确认没有走这条 GUI INI 链，但不能以此冒充一次对 helper 实际 feature 值的观测。父线程将启动的新音频 QA/独立导出若仍存活，可以只读绑定该新 PID/birth，按同一静态消费者布局观察 feature；子任务不启动导出。

发布 addon 的 initialize parser 仍只开放前述三个路径/名称字段。它构造自己的配置并设置 VEAB first-read callback，未恢复调用上述 frontend INI producer 的正常 route。正常 GUI INI 路径可作 frontend 配置接口证据，不能把它误称为现有 addon/独立 helper 的可用配置选项。

目前的 Qt 候选 `AbTestConfigSettings`（meta `0x9c793f8`）只有五个具名只读 bool property 及五个 notify signals，没有通用 key/bool slot；`setABConfigBool` 已证属于另一张 map。因此仍未找到保持当前 bridge/ABI 不变、可对现有独立导出 worker 下发此精确 VE bool 的普通 Qt/JSON/CLI 入口。最窄正式 C++ 类型入口仍是 **导出 `lvve::InitVEAbConfig(const lvve::adapter::VEAdapterConfig*)`**；原厂完整 header/字段名未取得，不能在此基础上造 ABI 对象或用裸 vtable。

证据：`E/abconfig-qtmeta.json`、`abconfig-meta-locations.json`、现有 `engine/native_export_windows.cpp`、`engine/native_export.py`、`engine/jypack_render.py`。GUI 与 helper 后续真实语音首尾效果、context latency 值和新导出结果仍由主线程独立验收。


## 独立客户端可用的最窄正式符号与当前缺口

本节按父线程新要求只审计发布导出/现有代码，没有启动 worker，没有调用配置函数。

### InitVEAbConfig 的精确 ABI 证据

| 项 | 本版真实证据 |
|---|---|
| 所属 | `videoeditor.dll`，11.4.7.14462，前述 SHA256 |
| PE 导出名 | `?InitVEAbConfig@lvve@@YAXPEBUVEAdapterConfig@adapter@1@@Z` |
| 本版 RVA | `0x1564e10`；仅用于定位证据，客户端应按真实导出名解析 |
| 还原签名 | `void __cdecl lvve::InitVEAbConfig(const lvve::adapter::VEAdapterConfig*)` |
| 参数来源 | 导出名 `PEBUVEAdapterConfig@adapter@1@` 明确是 const struct pointer；函数首条业务动作 `mov rbx,rcx`，之后将它传给正常 inner |
| Windows x64 | 单一普通函数参数在 RCX；void 返回，无 C++ this，无 hidden return buffer |
| 作用 | 应用 config 到进程全局 VE registry；const 只约束配置对象，不代表此 API 是只读 |

研究用的最小类型声明只需要前向声明，不涉及原生对象布局：

```cpp
namespace lvve::adapter { struct VEAdapterConfig; }
using InitVEAbConfigFn = void (__cdecl*)(const lvve::adapter::VEAdapterConfig*);
```

这只能表达已有正式函数类型，**并不使调用者具备按 key 填充 config 的能力**。现有 helper 已有真正的 `VeWrapper::getVeAdapterConfig()` shared_ptr，其精确导出为：

```text
?getVeAdapterConfig@VeWrapper@wrapper@lyra@@QEAA?AV?$shared_ptr@UVEAdapterConfig@adapter@lvve@@@std@@XZ
```

它提供原生对象所有权/存活保证，但不是按 key 修改 bool 的正式 setter；对空/default map 调 Init 不会创造目标 bool。

**Init-once 限制比“创建 decoder 前”还早：** `0x1564e59..0x1564e66` 先将进程 guard `videoeditor+0x423e784` xchg 为 1；只有原值为 0 才调用 inner。inner `0x1564ed0` 才检查 null。所以第一次即使传 null 也会消耗此 guard。函数返回 void，没有“应用成功”结果；正常返回不证明配置生效。不能等已有 session 初始化后就假定该函数还能补应用 map。子任务未调用它或改变 guard。

证据：`E/formal-adapter-config-narrow-negative.json`、`videoeditor-annotated-0x1564e10.txt`、`videoeditor-annotated-0x1564ed0.txt`；现有 helper 的 typed getter 代码见 `engine/native_export_windows.cpp`。

### 按 key bool setter 与 JSON factory 的导出审计

对本机实际 PE export tables 做版本绑定审计：videoeditor 32568 项、cccreator 7401 项、addon 2 项、VECreator 1868 项，完整筛选保存在 `E/formal-adapter-config-api-export-audit.json`。

- `VEAdapterConfig` 本体的导出成员（精确类作用域 `@VEAdapterConfig@`）**0 项**；没有找到其普通按 key bool setter 或导出 constructor/factory。
- 含 VEAdapterConfig 并含 JSON 的三个导出都是 ScriptStandaloneMgr 的 **返回内容 JSON** 方法，输入反而要求 `const VEAdapterConfig&`；不能把它们当 JSON-to-config factory。未发现 `from_json/deserialize/parse` 以 VEAdapterConfig 为输出对象的导出。
- 同名 `lvve::SetABConfigBool`、MixedClient setter 的错误 registry 归属已有完整函数证据，不再扩展重复检查。
- cccreator 的 `SwingManager::setParameterBool` / `bef_swing_manager_set_parameter_bool` 属于 effect/Swing 参数；没有证据将它们绑定到本节 VE host registry，不能因其支持 string+bool 就替代 host setter。
- `cccreator getGlobalConfig` 正式 C linkage factory 实际对象 RTTI 为 `vesdk::VEGlobalEnvConfigImpl`，其基类含 `IVEGlobalEnvConfig`、`IVEABConfig` 和 secondary `IVEABConfigCompatible`。按 key bool 的实际实现不在导出表；目前只有接口 slot 与机器码，**未取得原厂接口头文件及方法源名**。不能据 RTTI 自造一个带猜测虚函数次序的 C++ interface，再称为正常调用。

还发现一个必须保留的边界：cccreator 内部 `0x1c1040` 解析 JSON，并在 `0x1c16ce..0x1c16f4` 读取 `value` bool 后调用同一 host 更新函数 `0xd21550`。但其唯一直接 caller `0x1ca6f0` 是转码侧的 `std::function` lambda invoke（保存于 function-object vtable），不是 PE 导出、QObject slot 或已识别的 JSON service。它还强设其它功能值，故即使绕过入口调用也不符合本任务范围。不能写成“没有内部 JSON parser”，也不能把内部 parser 地址写成可用配置 API。

证据：`E/cccreator-host-bool-global-update-direct-callers.json`、`cccreator-json-host-bool-parser-callers.json`、`cccreator-annotated-0x1c1040.txt`、`cccreator-annotated-0x1ca6f0.txt`。本轮没有执行这些内部函数。

### 保持现有 ABI/bridge 的实际边界

已有原生 shared_ptr + 正式 Init 导出，足以安全**描述**一个 normal const-pointer 客户端调用；但当前缺少正常构造/填写 bool map 的接口，以及可靠的 init 前调用时序。缺少原厂头文件时，`sizeof=0xbf8`、map 偏移与局部复制反汇编不能替代完整结构定义。

因此本轮不提供以下伪方案：强转 `adapter+0xb80` 后写 map、复制 GUI config 字节到另一进程、手工构造完整 VEAdapterConfig、调用 vtable slot、给 addon 塞未解析字段、用 Mixed map 读回 true 假装 host 生效。

在取得带完整源类型/配置 producer 的正式入口之前，尚不能把独立 helper 的该配置支持列为已完成能力。后续若使用 Init 导出，验收至少应证明目标 worker 的全局 bool 与新 decoder 缓存均为 true、SAMI latency query 成功，并以完整语音句首/句尾实际出片证明补偿；仅函数正常返回、GUI 为 true 或主体 lag 对齐均不够。
