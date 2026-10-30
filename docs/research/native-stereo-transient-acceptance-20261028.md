# 原生声音链的立体声与瞬态边界验收设计

日期：2026-10-28。本轮为只读计划审核：读取现有 graph 与真实验收证据，查阅一级计量文档；未调用 native/GUI、未连接编辑 pipe、未改 engine/桥/资源/草稿、未安装包。这里的新增源/导出设计**尚不是已经通过的测量结果**。后续真实导出应另附文件、命令和结果。

## 验收范围与最小调整

主线程拟用直接生成的立体声 L/R tone、短 burst、impulse，经原生 EQ/Compressor/Limiter、clip volume 1、ceiling -3 dB 输出 stereo AAC MP4。这适合补当前尚未覆盖的声音边界，前提是把以下三件事分开：

1. 声道路由：左右信号是否仍然独立可辨，是否交换、折叠或出现新泄漏。
2. 动态/瞬态：limiter 是否真的激活，瞬态、恢复、延迟和编码后峰值是什么。
3. 计量正确性：保持原通道测每通道 sample peak/RMS，另测整片 BS.1770 true peak；不再用隐式 mono downmix 的值验收原声道上限。

**建议该边界 fixture 的 EQ 设为 0 dB、Compressor 设 threshold 0 dB / ratio 1:1，保留真实原生链结构，让 limiter 成为唯一主动动态节点。** 默认 threshold -18 / ratio 3 / 无 makeup 会先把稳态音压到 ceiling -3 以下，使 limiter 不激活；“值已可编辑但此刺激未改变 PCM”不能作为限幅激活证据。已有五项参数编辑/undo/redo/导出实效无需重跑；正常生产压缩设置可单列分析，不与单节点上限识别混为一项。

路由 fixture 不开语音降噪、响度归一、额外增益或 clip fade。真实语音降噪已有专门验证，降噪对纯音/脉冲的自适应反应不适合混入这轮声道路由归因；源信号自身明确记录的 burst 包络另论。

## 现有原生映射，避免把两套 port 混用

已只读检查当前 `engine/native_dsp_graph.py`。正式双资源结构是：

| 资源 | GUI category | 控件 | DSP parameterIndex / 根 portIndex |
|---|---|---|---|
| local-studio-eq-v1 | tone | gain | 4 / 0 |
| 同上 | tone | frequency | 2 / 0 |
| local-studio-dynamics-v1 | sound_effect | threshold | 2 / 0 |
| 同上 | sound_effect | ratio | 1 / 0 |
| 同上 | sound_effect | ceiling | 2 / 1 |

EQ 是单 Equaliser 节点；Dynamics 资源内部为 Compressor → Limiter，外部 sidechain bus 不活动。原单包 `local-studio-dsp-v2` 的 threshold/ratio 是 port1、ceiling 是 port2，**不能用于双资源**。两资源之间的实际处理顺序以本次保存 timeline/runtime 为准，不能仅从 Python nodes 或 material vector 的排列猜全局顺序；本轮建议的透明 EQ/压缩使该顺序不影响 limiter 隔离目的。

建议本 fixture 的物理/normalized 设置：

| 参数 | 物理值 | normalized |
|---|---:|---:|
| EQ gain | 0 dB | .5 |
| EQ frequency | 1000 Hz | .5663233347786729 |
| compressor threshold | 0 dB | 1 |
| compressor ratio | 1 | 0 |
| limiter ceiling | -3 dB | .8369073924629202 |

Limiter preset 的 Input Gain 0、Audition Unity false、Lookahead 7 ms、Release 100 ms；Compressor 的 Auto Makeup false、Output Gain 0、external sidechain false。保存/运行时应核对这些设置以及 volume1、stereo source、两个 effect 各自唯一稳定 `constant_material_id`，保留已有主素材音效激活标志。参数只落盘不等于本次限幅已激活。

## 源信号：少量明确片段即可

直接写两个独立数组的 48 kHz stereo WAV；每通道源 peak/RMS 都从最终写入的 WAV 重新读回，记录 sample format、L/R 顺序、采样率、总 samples 和 SHA256。不要先造 mono 再用 `-ac 2` 冒充独立左右信号。使用当前已支持的 PCM 格式，不新增解码依赖。

下表是需要覆盖的段落，不要求固定成某个总时长。每个稳态段约 0.75–1 s，测量中段至少 0.2 s，避开边缘；burst/impulse 之间留约 0.5 s 恢复期，这是当前 100 ms release 的约5个时间常数，属于试验设计，不能当作已证明完全 reset。

| 段落 | 建议内容 | 主要作用 |
|---|---|---|
| 安静头尾 | 约0.3–0.5 s全零 | 暴露启动/尾部延迟与 AAC padding，不把边缘当稳态 |
| L-only 低电平 | L=1 kHz，peak约 .25；R=0 | 左通道身份、右通道泄漏；电平低于-3 ceiling |
| R-only 低电平 | R=2 kHz，peak约 .25；L=0 | 右通道身份、左通道泄漏 |
| 双独立 tone | L=1 kHz、R=2 kHz，低电平 | 同时存在时仍可分辨，排除简单复制/折叠 |
| 同相/反相 | 相同1 kHz，分别 L=R 与 L=-R，低电平 | 声道极性与显式 mono fold；可各用约0.5–1 s |
| 强度平台/短 burst | 每通道 peak约 .95（-0.446 dBFS），5/20/100 ms等级短 burst，加一段足够长平台 | 输入确实高于-3，观察增益衰减、短瞬态与恢复；记录实际 envelope |
| 左右错开 impulse/marker | 先L后R；同时另留一对相同的低电平同步 marker | 区分路由与延迟；低电平 marker 不应触发限幅 |

1 kHz/2 kHz 便于观察，但2 kHz是1 kHz的二次谐波。**双 tone 时 L 中的2 kHz不能直接全部叫作 R→L 串扰**；非线性动态或编码可能生成谐波。串扰主判应使用低电平 L-only/R-only 段，并与同源原生 bypass 导出比较。若源尚未固定，R=1.7 kHz 可避免这一重合；不必为此重复已经完成的导出。

burst 的边缘包络必须写进 manifest。短硬门控会自己产生宽带分量；温和的极短边沿避免无意点击，但不能把 burst 先平滑成完全不同的刺激。单样本 impulse 是诊断信号，AAC 的滤波/前后扩散会改变它；不能把其任何削峰、前振铃或峰位置变化一律归因原生 limiter。

若要补 sample/true-peak 的重建边界，只需一个相位错开的高频段，例如 fs/4 的两个相位版本。EBU Tech 3341 的 true-peak 测试也使用高频、相位和特殊瞬态；这些是**计量器测试设计**，不是给剪映 limiter 套用其计量容差。参考[当前 EBU Tech 3341（2023），Table1 15–23](https://tech.ebu.ch/files/live/sites/tech/files/shared/tech/tech3341.pdf)。

## 必要对照与量测

最好保留两份同源、同视频、同采样率和同 AAC 编码设置的原生导出：原生 bypass 参考，以及上述 limiter -3 版本。不要用 FFmpeg 处理后的音频替代原生输出。已有原生无效果同源导出可复用；目的仅是拆开 codec 与 DSP，避免新增无意义的渲染矩阵。

解码时不指定 `-ac 1`，也不改变 `-ar` 或加 volume。先 probe 实际通道布局；保留 stereo 浮点 PCM，按真实 channels reshape。

```text
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_fmt,sample_rate,channels,channel_layout,start_time,duration -of json INPUT.mp4
ffmpeg -v error -i INPUT.mp4 -map 0:a:0 -vn -c:a pcm_f32le -f f32le ANALYSIS_ONLY.f32
```

这里 `.f32` 仅是分析副本；不送回剪映、不作为交付媒体。保留命令和 FFmpeg 版本，不能把原来的 `-ac1` 测量修正成“所有结果统一减3 dB”。其明确原因见[限制器报告的测量纠正](native-limiter-ceiling-calibration-20261028.md)。

### 每通道及整片峰值

每个预定段、每个通道分别记录：sample peak、RMS、目标频率的正弦拟合幅度、非目标频率幅度、样本数量和窗口实际起止。全片及每个主要 burst/impulse 窗口另记录 true peak；报告输入/原生 bypass/原生 active 三者，不能只挑全片最大值一句话结论。

整片可用 `loudnorm=print_format=json` 丢弃滤镜输出，仅解释 `input_tp/input_i`，或用纯计量 `ebur128=peak=sample+true` 交叉核对。`loudnorm` 的 `output_tp` 不是原生输出。true-peak 与 sample peak 的区别和过采样计量依据见 [ITU-R BS.1770-5 Annex2](https://www.itu.int/dms_pubrec/itu-r/rec/bs/R-REC-BS.1770-5-202311-I%21%21PDF-E.pdf)；FFmpeg 的实现入口与定义见[同本机 build commit 的滤镜文档](https://github.com/FFmpeg/FFmpeg/blob/3a165c77dc/doc/filters.texi)。

短 burst 的 LUFS/LRA只作附带测量，不是制作响度目标；不足60 s 的 LRA也不能拿来宣称稳定宏观动态范围。此次测试不替用户设定广播、短视频或音乐交付 LUFS。

### 串扰、身份与 mono fold

单侧段定义泄漏比 `20log10(RMS_unintended/RMS_intended)`，同时给出原始 RMS 与目标频率相干分量；零能量用 `-inf` 或明确数值下限表示，不把 epsilon 当真实噪底。

先验证身份：L-only 的1 kHz主分量应留在L，R-only的2 kHz主分量应留在R；双 tone 输出不能变成 L/R 相同的混合副本。泄漏的量化结论以同源 bypass 为基准，明确列新增相干成分和误差，不凭空宣称达到某个专业串扰标准。没有既定项目串扰规格时，给测量值与相对退化，不能事后为“通过”挑一个 dB 阈值。

当一侧强 burst 使另一侧已有 tone 的增益也变化时，须区分 stereo-linked 动态增益与音频漏入。前者可能是正常设计；**增益耦合不等于串扰**，应观察另一侧是否新增了本不存在的相干波形。

mono fold 仅在分析数组中显式计算 `M=(L+R)/2`，并记录定义：

- 同相 L=R=x：M应为x，不能增加3.0103 dB。
- 反相 L=-R：M应接近零；残差与 AAC bypass 的残差比较，而不是强求有损编码后逐样本绝对零。
- 两个独立频率：M各频率幅度各为原通道的一半；不要把整体 RMS与某一个原声道的 peak混比。

### latency、声道偏斜与时间完整性

用独特的非周期 marker/impulse 模式做 bounded cross-correlation，分别估计 source→bypass、source→active、bypass→active 的 L/R lag与置信度。单个连续1 kHz tone每1 ms就有相似峰值，不能独自用来确定绝对延迟。

当前 limiter Lookahead 7 ms 在48 kHz相当于336 samples，这是节点内部时间量，**不能直接要求导出必定晚336 samples**：主机可能补偿延迟，AAC priming/skip_samples也会影响解码边界。应同时保留 stream PTS、时长、packet/frame 的 skip/padding信息，先消除 codec共同偏移，再解释 DSP增量延迟。不要把 AAC前振铃的最大样本位置直接叫作链路延迟。

验收应看到两侧共同且稳定的时序，不出现意外 channel skew、逐段漂移、头尾截断或事件丢失。具体 lag 和估计误差以 samples/ms记录；未实测前不宣称“零延迟”。不同频率经过非平坦 EQ 的相位/群延迟也不能自动判声道不同步，因此本轮用 EQ0 dB与相同同步 marker隔离它。

## 可以据实通过的边界，不能提前通过的保证

以下可作为本次 fixture 的明确功能门禁：文件确为2通道、所有PCM有限；源的左右身份正确保持；两个稳定素材 ID与参数原值没有丢失；强刺激下 active相对bypass出现符合限幅方向的衰减且低电平段不被无故增益补偿；所有既定marker存在，时序与声道映射可解释；真实测量命令没有隐式downmix。

对于 peak 则报告 `最大实测 dBTP - 请求 ceiling` 及其发生窗口，并分别评价编码前（如有）和最终 AAC。若任一原声道/重建 true peak高于请求值，应保留反例并判定“此样例未实现该峰值边界”，而不是改测量路由/补偿数值让它通过。若所有样例都低于请求，则结论限于这组源与编码条件；不承诺 limiter 是所有信号的硬 true-peak保证。没有标准/既定规格支持的容差，不从 EBU计量器容差中借一个数给 DSP免责。

本轮测试的“专业”含义是把声道、相位、峰值、编码和时间响应测清楚；它本身不证明审美、可懂度、听感或最终混音合格。真实语音降噪和五控件编辑/音频变化的已通过证据继续有效，无需用这些纯音重新替代它们。
