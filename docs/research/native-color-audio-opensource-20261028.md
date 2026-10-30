# 原生高级调色与专业声音：开源实现核查

日期：2026-10-28。研究范围为现有 Windows 剪映项目，禁止 computer use。本文是只读源码研究，不是本机渲染或剪映参数编辑验收。没有修改 engine、操作活跃剪映、读取凭据或提交算法任务。

## 结论

高级调色可借现有草稿格式与资源结构推进；专业声音不能仅凭场景音／变声枚举宣称已补齐。此次核查的四个草稿开源项目均没有提供已经证实适配本机 11.4.7 的原生 EQ＋压缩＋降噪处理链。FFmpeg、Pedalboard、OpenColorIO 适合产生参考结果、分析或对照，但把处理结果导入为视频／WAV 不会自动把处理参数变成剪映中的可编辑控件。

## 已固定的源码

均检出在 `D:\JianyingHeadless\integrations\research-native-color-audio-20261028`，没有安装到项目运行环境。

| 项目 | 固定提交 | 本次确认的实际作用 |
|---|---|---|
| [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) | `1e228479dda361e312e85f6037002346cf6dca9a` | 原生音效材料、参数序列化与段落绑定；根 LICENSE 为 Apache-2.0 |
| [pyCapCut](https://github.com/GuanYixuan/pyCapCut) | `ec61408d9f039c4045f946370bb35746b89b2479` | 类似结构，目标是国际版 CapCut；当前检出根未发现 LICENSE，不能按 pyJianYingDraft 的许可直接推定 |
| [CapCutAPI](https://github.com/sun-guannan/CapCutAPI) | `48f8ff9155f4fae37bc8896c57c580cf91c4132a` | 包装 pyJianYingDraft 的片段、音效和草稿输出；根 LICENSE 为 Apache-2.0，但 pyproject 分类写 MIT，复用时须保留实际许可文件并核对冲突 |
| [JyDraft](https://github.com/HTWMedia/JyDraft) | `94249b21a71a2526e47e04c90e08d1515bac7c77` | C# 原生草稿结构；音频处理仍主要是音效元数据。根 LICENSE 为 Apache-2.0 |

pyCapCut 和 pyJianYingDraft 的导出 controller 含 `uiautomation`、Click 等 UI 操作，**不用于本任务**。这里只参考原生数据结构，实际导出继续使用现有原生引擎入口。[pyCapCut controller](https://github.com/GuanYixuan/pyCapCut/blob/ec61408d9f039c4045f946370bb35746b89b2479/pycapcut/jianying_controller.py)

## 原生高级调色线索

[chukcut 的格式研究](https://github.com/chuk-development/chukcut/blob/master/docs/research/draft-format.md) 给出 `materials.hsl` 的实际示例，使用 `hsl_color_type`、`custom_color`、`hue`、`saturation`、`lightness`，并绑定 `path` 和 `lumi_hub_path`。对应片段需持有材料 ID，且开启 `enable_hsl`。该研究特别说明其 `color_curves`、色轮等部分仅来自 DLL 符号，**不是已运行的样本**；不能直接把字段列表当成已可用功能。

[duckyman-ai 的 add-color.py](https://github.com/duckyman-ai/agent-skills/blob/main/skills/capcut-editor/scripts/add-color.py) 也提供 HSL 构造代码：材料含独立 `id`、`constant_material_id`，`type:hsl`、`version:1`，与片段 `extra_material_refs`／`enable_hsl` 配合。其示例 hue 为 -180..180、saturation/lightness 为 -100..100；引用本机缓存资源 ID `7501974767453474064` 和包内 `lumi_hub_path`。该脚本针对 Mac CapCut，缓存哈希与 Windows 剪映不保证兼容；不能直接复制路径或用其写首页索引方法替换本项目入口。

主线程已在本机官方 `draft video adjust --help` 发现 HSL 相关字段。本机真实提交、解密回读、资源绑定、像素对照和编辑页保存应作为权威；本研究不代替这些检查。

[OpenColorIO](https://opencolorio.org/) 是色彩管理库，可作为 LUT／色彩变换参考及独立计算基准；[LICENSE](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/main/LICENSE) 为 BSD-3-Clause。其本身不会创建剪映原生 HSL、曲线或 LUT 材料。先验证剪映原生材料和本地资源加载，再决定是否用 OCIO 生成参考 LUT；不以预调色视频导入冒充参数接通。

## 原生音频材料：确实存在，但能力有限

[pyJianYingDraft/audio_segment.py](https://github.com/GuanYixuan/pyJianYingDraft/blob/1e228479dda361e312e85f6037002346cf6dca9a/pyJianYingDraft/audio_segment.py) 的 `AudioEffect` 输出 `type:audio_effect`、`resource_id`、`audio_adjust_params` 等字段，音频段把其 ID 放入 `extra_material_refs`；该材料随后写入 `materials.audio_effects`。它保留了参数化音效的结构，而不是生成一份处理后音频。

[EffectParamInstance](https://github.com/GuanYixuan/pyJianYingDraft/blob/1e228479dda361e312e85f6037002346cf6dca9a/pyJianYingDraft/metadata/effect_meta.py) 输出参数名、当前值、最小／最大值、默认值、`parameterIndex` 与 `portIndex`。API 的 0..100 输入按各参数范围映射到原生值，不应把百分比直接当原生单位。

可用于窄范围原生音效验证的资源例子来自 [audio_scene_effect.py](https://github.com/GuanYixuan/pyJianYingDraft/blob/1e228479dda361e312e85f6037002346cf6dca9a/pyJianYingDraft/metadata/audio_scene_effect.py)：

| 场景音 | 原始元数据 | 可改参数 |
|---|---|---|
| 回音 | resource_id `7018011608408396325`；effect_id `5723901` | `change_voice_param_quantity`、`change_voice_param_strength`，原生范围 0..1 |
| 麦霸 | resource_id `7018012141332468260`；effect_id `2672748` | `空间大小`、`强弱`，原生范围 0..1 |
| 环绕音 | resource_id `7161319847819743780`；effect_id `5723960` | `change_voice_param_center_position`、`change_voice_param_surrounding_frequency` |

这些是场景／空间处理，不能充当专业 EQ、压缩、降噪已经实现的证据。国际版 pyCapCut 同名资源的 ID、参数名也不同；不能跨产品混用枚举。

在 pyJianYingDraft 的 `script_material.py`、pyCapCut 的 `script_file.py`、CapCutAPI 的模板和 JyDraft 的 `ScriptFile.cs` 中，`audio_balances`、`loudnesses`、`realtime_denoises` 通常仅被初始化为空数组，没有对应的完整 EQ／压缩功能实现。空槽位不是功能证据。

### 本机发布物的进一步定位

仅做文件关键字查找，未运行 JS：

`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462\Resources\canvas_agent\app\static\js\ai-creation~8.7b43c1ad.js`

同时包含 `audio_balance`、`realtime_denoise`、`loudness_param`；`~11.fe7840fa.js`、`~5.38151757.js` 也有相关名称。它们可作为后续原生序列化／SDK 调用研究的定位种子，当前未据此推断字段的含义、类型、可执行性或效果。

## 外部 DSP 的正确使用边界

- [Pedalboard](https://github.com/spotify/pedalboard) 有 Windows amd64 wheel、Compressor、Limiter、NoiseGate、滤波和混响等，适合对照信号、分析与 DSP 基准。[API](https://spotify.github.io/pedalboard/reference/pedalboard.html)；[GPLv3 LICENSE](https://github.com/spotify/pedalboard/blob/master/LICENSE)。直接运行后写 WAV 会烘焙效果；剪映中可剪辑这条 WAV，不代表能改压缩阈值或 EQ 频点。
- [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html) 的 `acompressor`、`equalizer`、`afftdn`、`alimiter`、`ebur128` 可产生参考与客观测量。同样不会替代剪映原生音效材料。许可依构建配置为 LGPL／GPL，见[官方许可说明](https://ffmpeg.org/legal.html)。

最稳妥的验收是保留同一源片、相同目标区间和静态素材，改变一个原生参数后再次原生渲染；比较频响、动态、噪声底／峰值，并确认剪映保存后材料与参数仍存在。不能只比较导出命令返回值，也不能把新烘焙的音频差异写成原生参数变化。

## 已知访问限制与未完成项

`mcncarl/jianying-headless` 当前 git clone 返回 Repository not found，所给 `docs/SAVED-DEFAULTS-115.md` raw 链接为 404。本次未取得其高级调色／音频源码，没有重试或从搜索摘要臆造实现。

本报告完成了开源源码和文档筛查；尚未证明任何新增高级调色或专业声音功能在本机剪映可用。实际效果、参数继续编辑及资源归属需由主线程在独立工程逐项验证。
