# 剪映 11.4.7 本机人声降噪模型与原生入口

日期：2026-10-28。范围：本机发布文件、只读静态反汇编与主线程已经产生的原生导出证据。本文作者没有调用 native API、操作 GUI、读取凭据、修改引擎或桥，也没有下载模型或发云请求。以下 RVA 都相对各自 DLL 的映像基址，不是可直接调用的绝对地址。

## 可直接采用的结论

1. 已验证的 `realtime_denoise` 组合是 `denoise_v2 / sami_type=2 / Music44k model`。主线程后续采用真实 clean reference、原始单通道、测得延迟补偿的 v2 对照：mode0/rate0.35 的 speech SI-SNR 比 bypass 提高0.8985dB，静音噪声降低3.4417dB，人声音量变化-0.3082dB。这是现有合法模型的正向样例；不能继续以旧 v1 指标宣称当前组合保真失败，也不能把单个fixture推广成所有人声质量保证。
2. **不能把 `sami_type=1` 当 RNNoise。** 本版实际链路是 `AudioSamiFilter → TEAudioSamiProcessor → identify 0x132 → DenoiseV2 内部 TCN44k`。RNNoise48k 的 SAMICore identify 是 `0x131`，这两个值不是同一入口。
3. 本机确有 `Resources/rnnoise/rnnoise_v2.0.model` 及原生 `RNNoise48k` 实现，正确的旧原生类是 `AudioNoiseFilter / NoiseAudioProcessor`；其 mode/rate 可调。尚未证实当前公开 `audio.denoiseOn`、现代 realtime 材料恢复路径能创建该旧类，因此不能通过猜 `sami_name` 伪装打通。
4. MDSP 的现成节点 `Denoise` 也存在，但其初始化硬编码 Speech44k SAMI task，安装目录没有对应 Speech44k 模型。它不是可以直接装入 RNNoise 文件的通用容器。
5. `Resources/models/noise_reduction/nn_denoise.bytenn` 是 **视频画面去噪** 模型，不是人声候选。

## 一手证据位置与指纹

安装目录：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462`。

研究证据目录：`D:\JianyingHeadless\integrations\native-vocal-denoise-research-20261028`，下文省略此前缀。`complete-model-identities.json` 是完整的这三个模型目录文件清单及 SHA256。

| 发布 DLL | SHA256 |
| --- | --- |
| `audioeffect.dll` | `2a384edf76c59a92cc4a4f9d8504d7f512be6e27ae8e32069f0807a489378116` |
| `videoeditor.dll` | `fa89997a94e96cf97c8ee436a56ab028ea5f87731214696ba43ff74c0fdc0fa0` |
| `cccreator.dll` | `a122d8b4c36f3300c8a32666e87b3b46c5acf61b7b32dc0e132bb8f62e1f39a1` |

证据是对已安装第一方发布物的读取；字节命中、静态可达路径、实际运行结果在下文分开标注。辅助 `PE` 脚本只解析磁盘 PE，不加载 DLL。`.pdata` 中有函数分片，少数 `*-range-*.txt` 使用明确起止 RVA 合并分片，避免把缺少后半段的片段误认为完整函数。

## 本机模型盘点

| `Resources` 相对路径 | 大小 | SHA256 | 确认用途及限制 |
| --- | ---: | --- | --- |
| `audiosami/unet_denoise_44k_music_model_v1.0.model` | 264172 | `a20cbd66d4ae8d483fe0f1759fa76803f4355d96aece3b65902b6cf34ff14c1c` | Music44k；与 type2 原生导出有效组合已由主线程验证 |
| `audiosami/time_align_freq_domain_v2.0.model` | 988 | `0ef4a653b63dae44280509bc06c4b91f80e005738cd3fead9ba36530925ef56d` | 时间对齐，不是降噪权重替代品 |
| `audiosami/time_align_time_domain_v1.0.model` | 364 | `2c7cf7aaf411916400beb2bbb3b322291aa92bf62c170db8de395e8692ec2213` | 时间对齐，不是降噪权重替代品 |
| `rnnoise/rnnoise_v2.0.model` | 124648 | `6c3091b0c641ab36cffb4cde25b795f0cd34dd6526a6bb87da8824acb2f870f0` | 原生 RNNoise48k 的模型名与资源路径吻合；现代材料恢复入口未打通 |
| `models/noise_reduction/nn_denoise.bytenn` | 253294 | `3dfdbefcd5da99fde8b54b01c96ce58625b0feb2e2307b9b7bae71a5817b8a83` | 画面去噪，排除出人声候选 |

`audiosami` 当前只有表中三项。音频 DLL 内虽包含 Speech44k、Speech16k、TCN、Dereverb 等实现和模型 task 名，但这不等于这些权重已在本机安装。三个容器的文件头也不同；本研究不解密、转换或声称相互兼容。

画面模型的定性有直接代码证据：`VECreator.dll` RVA `0x6083890` 同一函数在 `0x6083bb9 / 0x6083be2` 引用源码路径 `Capability/Algorithom/video_algrithom/VideoAlgNoiseReduction.cpp` 和函数名 `VideoAlgNoiseReduction::execute`，在 `0x60843a4` 引用 `models/noise_reduction/nn_denoise.bytenn`，还包含 `-pq / -hlg` 分支。见 `gui-model-literals.json`、`bytenn-noise-model-xrefs.json`、`VECreator-0x6083890.txt`。

## 现代 realtime 材料：确切 schema 与允许范围

`videoeditor.dll` 自带 schema（RVA `0x31e8370` 附近）声明：

```json
{
  "is_denoise": {"type":"bool", "default":false},
  "denoise_mode": {"type":"double", "default":0.0},
  "denoise_rate": {"type":"double", "default":0.0},
  "path": {"type":"std::string", "default":""},
  "sami_name": {"type":"std::string", "default":""},
  "sami_version": {"type":"std::string", "default":""},
  "sami_type": {"type":"int32_t", "default":0}
}
```

`is_denoise / denoise_mode / denoise_rate / sami_*` 的 schema key path 在 `item.*`，`path` 是独立路径字段。`id / type` 仍由材料集合序列化管理，不要把上述片段当完整草稿。**这是edit请求schema默认值，不是持久化JSON parser的默认值。** 后者 `PersistentMaterialRealtimeDenoise` 的is_denoise缺省false、mode缺省1.0、rate缺省1.0；compact保存会省略false/mode1，详见 [持久化分支证据](native-vocal-denoise-live-binding-20261028.md)。

原生 validator RVA `0x209a550` 在 `0x209af7f` 一带检查 mode 非负、rate 在 `[0,1]`，错误字符串 RVA `0x31f1050` 明确表达该限制。**mode 类型为 double，不是已经恢复语义的 speech/music 枚举。** 详见 `videoeditor-0x209a550.txt` 和 [既有音频 schema 研究](native-audio-schema-20261028.md)。

可以作为真实对照基础的完整材料形状：

```json
{
  "id":"<新的材料 UUID>",
  "type":"realtime_denoise",
  "is_denoise":true,
  "denoise_mode":0,
  "denoise_rate":0.35,
  "path":"<安装目录>/Resources/audiosami/unet_denoise_44k_music_model_v1.0.model",
  "sami_name":"denoise_v2",
  "sami_version":"1.0",
  "sami_type":2
}
```

必须通过现有正式编辑接口保存并检查 authoritative snapshot；还需由片段 `extra_material_refs` 真实引用材料。直接 native edit 时显式传 `isDenoise:true`，不能仅凭 operation 名推断开启。现有参数传输的 camelCase 与最终 snake_case 材料不应混淆。

### 材料恢复与 filter 构造

`videoeditor.dll` 的恢复链：

1. 音频恢复函数 `0x1b4f670` 的 realtime 分支在 `0x1b51531` 获取材料。
2. `0x1b80660` 将材料转成内部参数：path `+0`，enable `+0x20`，mode `+0x28`，rate `+0x30`，name `+0x38`，version `+0x58`，type `+0x78`。
3. wrapper `0x29c0990` 非 CC 分支调用 factory `0x2b761c0`，创建 `vesdk::pub::AudioSamiFilter`，构造地址 `0x2d17950`、vtable RVA `0x33022d8`。
4. factory 对材料 `sami_type`：1→native1；3→native3；其余→native2。**0 不代表关闭；5 也不能靠此字段直接穿透到 native5。**
5. 生成 config 的形状是 `{"name":<sami_name>,"version":<sami_version>,"config":{"denoisemode":<mode>,"denoiserate":<rate>}}`，没有转发 `denoisetype`。
6. wrapper 的 CC 分支是 `0x29c8340` → `0x2bb3460`，构造同类 CC Sami filter；`0x2bb34ff..0x2bb3527` 同样仅映射 1/3/其余为 native1/3/2。不能将 CC 与非 CC 构造中的枚举作任意扩充。

对应 `videoeditor-0x1b80660.txt`、`videoeditor-0x29c0990.txt`、`videoeditor-0x29c8340.txt`、`videoeditor-0x2b761c0.txt`、`videoeditor-0x2bb3460.txt`。

## `sami_type=1` 为何不是 RNNoise：已闭合的静态链

`cccreator.dll` 的 `TEAudioSamiFilter` 路径使用 `TEAudioSamiProcessor`；后者 RTTI 名在 RVA `0x52071e8`、vtable `0x48ccf20`，init entry 为 `0xa1b7b0`。它从参数 map 读取 model path、`audio sami type`，在 `0xa1c0e9..0xa1c1a0` 分派：

| 输入 native SamiType | SAMICore identify | `audioeffect.dll` 实际初始化 | 模型 task |
| ---: | ---: | --- | --- |
| 1 | `0x132` | ctor `0x8b920`；`0x8c0b0` 第三参 0 | `tcn_denoise_espresso_44k_model` |
| 2 | `0x134` | 同 ctor；第三参 2 | `unet_denoise_music_espresso_44k_model` |
| 3 | `0x138` | 同 ctor；第三参 6 | `unet_denoise_dereverb_espresso_44k_model` |
| 5 | `0x135` | 同 ctor；第三参 3 | `unet_denoise_speech_espresso_44k_model`；现代 factory 未开放此输入 |

`cccreator` IAT `0x41d2058` 已按 import descriptor 解析为 `audioeffect.dll!SAMICoreCreateHandleByIdentify`，并非凭邻近符号推断。其真实导出 RVA 是 `0x11b000`。

`0x11b000` 中的二级跳表：type1 所用 identify `0x132` 索引2→branch `0x11c9ab`→`0x11c9f4` 调 load `0x8c0b0` 且 `r8d=0`。type2 identify `0x134` 索引4→branch `0x11cae6`→`0x11cb26` 置 `r8d=2`→`0x11cb32` 调同 load。内部 0/2 再由 `0x8c0b0` switch 与 `0x8c580` 对应 TCN44k/Music44k。

**RNNoise48k identify 是 `0x131`**：SAMICore 分支进入 `0xbe840`，在 `0xbece6` 比较 `0x131`，`0xbed05` 调 `0x19ca80` (`EffectCreator::createRNNoise48k`)。现代 TEAudioSamiProcessor switch 没有把上述可用材料类型映射为 `0x131`。

证据：`cccreator-0x9b10d0.txt`、`cccreator-0xa1b7b0.txt`、`audioeffect-0x11b000.txt`、`samicore-identify-branches.json`、`audioeffect-0xbe840.txt`、`audioeffect-0x8c0b0.txt`、`audioeffect-0x8c580.txt`。这些静态分支足以否定“sami_type1=rnnoise48k”，但不等于对该分支执行过模型加载。

## DenoiseV2 内部 mode / rate / model type 的区别

`audioeffect.dll` `DenoiseV2Executor` 的 JSON setter `0x8ea80` 支持私有 `config.denoisetype`，含 0..5 映射：

| 私有 denoisetype | 内部模型 enum | 模型 |
| ---: | ---: | --- |
| 0 | 2 | Music44k |
| 1 | 3 | Speech44k |
| 2 | 4 | Music16k |
| 3 | 5 | Speech16k |
| 4 | 0 | TCN44k |
| 5 | 1 | TCN16k |

然而现代材料 schema 没有此字段，恢复 factory 也没有把它写进 config；而且 setter 在模型已经创建后拒绝更改模型类型。不能把这个内部键塞到正式 DTO 后宣称成功。

同一 JSON setter 将 `denoiserate` 限制到 0..1；`denoisemode` 转 int 并限制为 0/1。scalar setter `0x8f740` 对 mode 以 float epsilon 为阈值转 boolean，对 rate 写 float。**mode 不是选择 Speech/Music 的 denoisetype。** mode0/1 的完整听觉语义尚未恢复，合法 0/1 对照可以试，但不能预先命名成“专业人声模式”。

## 本机 RNNoise48k：实现真实，现代材料入口未证实

`audioeffect.dll`：

- `EffectCreator::createRNNoise48k` 导出 RVA `0x19ca80`。
- RNNoise48k ctor `0x2720f0` 依次注册 `denoisemode`（index0，0..1，default0）和 `denoiserate`（index1，0..1，default约0.85）。
- getter `0x2739f0` 返回 `rnnoise/rnnoise_v2.0.model`；`0x273a30` 返回 `rnnoise48k`。
- block length `0x1e0=480` 与模型名是本实现的直接静态证据，不凭文件名推断采样率约束。

`cccreator.dll` 的正确类是 `NoiseAudioProcessor`，不是 TEAudioSamiProcessor：

- RTTI type descriptor RVA `0x5161480`（名称从 `+16` 起），vtable `0x48cc858`。
- vtable init 通过 vtordisp thunk `0xa1a9bc` 跳 `0xa1a150`。init 读取 `model path` / `denoisemode` 并强制插入 `effect_name:"rnnoise48k"`，调用 AudioSDKProcessor 初始化，再加载模型；有明确 `loadModel failed` 错误分支。
- `TEAudioNoiseFilter` 在 `0x9b9740` 读取 `denoisemode` / `denoiserate` / `model path`，经 factory 创建 processor 并调用 init；日志明确 `NoiseAudioProcessor init failure`。
- DTO `CCAudioNoiseFilter` 的发布导出包含 `setModelPath(std::string)`、`setNoiseMode(double)`、`setDeNoiseRate(double)`、`setOpenNoiseFilter(bool)`、`setEnable(bool)`。

这证明原生旧滤镜链存在、有真实参数，而不是只存在一个无调用的算法符号。**仍未知：现代草稿如何持久化该 filter、当前官方 audio edit API 是否能创建它、GUI 是否仍绑定到同一个 rate、导出是否使用它。** 这些未知项未经过实际保存/原生出片，不能将合法旧 C++ DTO 列表误当已开放的正式编辑接口，更不能修改 DLL/ABI 或离线烘焙来替代验收。

证据：`audioeffect-0x19ca80.txt`、`audioeffect-0x2720f0.txt`、`audioeffect-0x2739f0.txt`、`cccreator-thunk-vtable-refs.json`、`cccreator-0xa1a150.txt`、`cccreator-0x9b9740.txt`、`cccreator-noise-filter-xrefs.json`。

上游 [Xiph RNNoise 官方仓库](https://github.com/xiph/rnnoise) 将其定位为神经网络语音增强，示例采用48kHz单声道PCM，许可证为BSD-3-Clause。上游用途可解释为何调查这个候选；**不能据此宣称剪映的 ByteDance fork、权重格式、模型质量或许可证与上游完全相同**，也不能直接拷上游权重覆盖本机资源。

## MDSP `Denoise`：另一条 Speech44k 链，不是通用 RNNoise 入口

`audioeffect.dll` RTTI `Jukedeck::MusicDSP::Processors::DenoiseProcessor` 位于 `0xcd6b00`，vtable `0xab65a8`，getName `0x38f160` 返回精确 processor name `Denoise`。ctor `0x38e890` 的默认内部采样率为44100。状态序列化 `0x38f1e0` 包含 `model_file_name` / `model_param`。

关键初始化 `0x38f530` 的完整分片在 `audioeffect-range-0x38f530.txt`：

- `0x38f76d..0x38f7a8` 固定构造 `unet_denoise_speech_espresso_44k_model`。
- `0x38f803` 调导出 `SAMIEngineCreateFromBuffer` (`0x492e10`)。
- `0x38f8ab` 调 `SAMIExecutorCreate` (`0x4937c0`)；`0x38f8d6` 调 `SAMIExecutorStart` (`0x493f50`)。
- 音频处理 `0x390150` 调 `SAMIExecutorSetInput / Forward / SAMIGetOutput`。

因此节点名 `Denoise` 可确认，Speech44k task 可确认，但**没有已安装的对应 Speech44k 权重**；现有 RNNoise 文件不是此 engine container。未完成参数登记表、加载路径、GUI控件和真实出片验证，不提供虚构的可用 MDSP JSON 样例。

## 最小真实对照建议与当前失败证据

### 后续 v2 真值对照：现有合法模型已有正向样例

主线程产生的 `JOB/vocal-denoise-fidelity-grid-proof-v2.json` 已读回。方法明确为原生导出的一个原始声道，不做立体声downmix；使用真实clean ground truth、补偿测得延迟，单独报告语音增益：

| 候选（mode0/type2） | speech SI-SNR | 相对bypass改善 | 静音噪声下降 | 人声增益相对变化 | 延迟 |
| --- | ---: | ---: | ---: | ---: | ---: |
| bypass | 15.6429dB | 0 | 0 | 0 | 0ms |
| rate0.1 | 15.5956dB | -0.0473dB | 0.8761dB | -0.0984dB | 23.2292ms |
| rate0.2 | 16.0386dB | +0.3957dB | 1.8284dB | -0.1810dB | 23.2292ms |
| rate0.35 | 16.5414dB | +0.8985dB | 3.4417dB | -0.3082dB | 23.2292ms |

这支持继续使用合法的 Music44k/mode0/rate0.35 完成本次fixture验收，无需为了宣称完成硬换RNNoise或混用不兼容权重。文件自身状态为 `measured-no-automatic-quality-promotion`；相同分数不代替对真实素材尾音、瞬态、立体声和听感的进一步边界验证。四个降噪导出的两声道差值RMS都为0，而bypass有0.0038027差值，需保留该立体声边界，不将单声道语音正向结果自动外推到立体声素材。

### v1 旧误差指标记录（保留，不作为 v2 结论）

现有 `D:\JianyingHeadless\work\native-av-upgrade-20261028-004610-32bec1\audio-speech-fidelity-proof-v1.json`：

| 对照 | 相对 clean reference 的 SNR | 最佳对齐延迟 | 已记录 gain |
| --- | ---: | ---: | ---: |
| 未降噪 baseline | 16.1893dB | 0ms | 0.99374 |
| 已测试降噪 | 15.3852dB | 23.2292ms | 0.89731 |

这份旧记录保留了当时观察到的参考误差回退，但其 reference_snr 与 v2 speech_si_snr 不是同一个指标及计算范围，不可跨表直接作质量比较。原“当前合法组合保真不通过”的概括已由上面的 v2 精确对照撤回，不能只展示旧失败或只展示底噪下降。

无需新模型的最短严格对照是：同一 noisy fixture、相同8秒时间线、音乐与EQ/压缩关闭，保持 type2 / Music44k，仅比较 off，以及 mode0/1 各 rate0.1、0.2、0.35。使用同样官方 session 正式保存→原生导出，记录实际保存材料，避免缓存/旧输出混入。若0.1/0.2已明显不足，别大规模盲试。

每个候选同时测：逐通道时间对齐后的人声参考误差、按最佳标量归一后的SI类指标、固定静音/噪声区间的噪声RMS与频谱、语音区间响度/频带保真、瞬态与尾音损失；去除的噪声与损坏的人声必须分开判断。保存的lag/gain需同表报告，不能通过补偿掩盖副作用。0.85强度可作当前强降噪对照，但不应预设为质量优先值。

如果现有合法组合仍不通过，需要先闭合旧 NoiseFilter 的正式材料/API映射，或者获得**合法来源且与本版task兼容**的Speech44k模型，再做独立原生试样。仅列出文件或导出符号不算通过。最终通过标准仍是：真实底噪降低、人声保真不回退、当前剪映开关/强度可编辑、修改后二次原生导出可重复验证。

## 明确保留的未知

- DenoiseV2 mode0/1 的产品语义以及是否有不同语音区间处理策略。
- RNNoise48k旧 filter 对当前正式 native edit 服务的持久化/恢复绑定。
- 当前 Native CC 开关在实际会话的取值；本研究没有读取进程或调用API以确定该值。
- 本机 RNNoise fork 对当前fixture的声音质量、延迟、立体声处理；尚无运行证据。
- Speech44k权重的合法获取来源及本地是否有其他未纳入清单的合法下载资源；没有发资源/云请求。
- MDSP `Denoise` 的完整参数登记、模型文件定位和GUI恢复规则。

本文只研究结论与实验边界；不修改 `engine/native_audio_processing.py` 当前 type2 白名单，也不建议绕过其校验。

## 补充：上游 renderer 不按 type0 / 空name 切换旧 NoiseFilter

对上游四个实际 transfer 调用点的只读复核：

| 调用上下文 | 材料读取/条件 | transfer | 新建或更新 wrapper |
| --- | --- | --- | --- |
| 音频首次restore `0x1b4f670` | `0x1b51531` 读 `SegmentAudio::get_realtime_denoise` (`0x25e1a0`)，`0x1b51536` 仅检查指针非空 | `0x1b51554 → 0x1b80660` | `0x1b5157b → 0x29c0990` |
| 音频update `0x1b520d0` | `0x1b54601` 判断材料存在；存在后 `0x1b54688` 检查dirty；无材料则删除旧绑定 | `0x1b546c9 → 0x1b80660` | 有filter `0x1b546f4 → 0x29c4510`；无filter `0x1b54719 → 0x29c0990` |
| 视频首次restore `0x288d740` | `0x289162e` 读 `SegmentVideo::get_realtime_denoise` (`0x8b2270`)，检查非空及is_denoise | `0x289166f → 0x1b80660` | `0x2891696 → 0x2c6c170` |
| 视频update `0x2895770` | `0x289c19a` 读材料；检查非空、is_denoise、dirty；不存在时删除绑定 | `0x289c219 → 0x1b80660` | 有filter `0x289c244 → 0x2c9dc00`；无filter `0x289c269 → 0x2c6c170` |

上述条件都没有读取 sami_type 或 sami_name。transfer 无条件复制材料的 name/version/type，空字符串也会复制；其中对象地址相等时跳过字符串自赋值的分支不是“名称为空→legacy”判断。

音频新建wrapper `0x29c0990`、视频新建wrapper `0x2c6c170` 仅由context `+0x23a` 选择CC/非CC；两侧分别进入 `0x2b761c0` 或 `0x2bb3460` Sami factory。音频update `0x29c4510`、视频update `0x2c9dc00` 也只是查现有filter及CC模式，随后重建Sami filter；对应CC方法为 `0x29ca5e0 / 0x2ce5a70`。

因此在这些确认的 `MaterialRealtimeDenoise` 恢复/更新路径中，type0/空name并没有更上游的legacy切换，factory内0→2确实会生效。证据：`realtime-renderer-upstream-callers.json` 与同名四个restore/update `videoeditor-*.txt`、六个wrapper的反汇编。扫描覆盖磁盘.text的直接E8/E9引用，不能用其否定其它不经此材料的所有旧SDK调用方式；进一步旧类追踪已按主线程指令停止。

GUI当前原生控制的准确能力边界另见 [降噪检查器绑定研究](native-vocal-denoise-live-binding-20261028.md)。
