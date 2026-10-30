# 原生 SAMI Limiter 的 Ceiling 参数与稳态峰值校准

日期：2026-10-28。目标构建：Windows 剪映 11.4.7.14462。

本轮为只读后台研究：没有 computer use，没有加载/执行目标 DLL，没有调用活跃剪映、原生 DSP 或编辑方法，没有改 engine、桥、ABI、DLL、资源或用户草稿。主线程的现有真实导出是本报告的实验来源；本文新增内容限研究脚本、静态证据与笔记。

## 追加纠正：立体声原通道测量优先，原“超出 ceiling”判断撤回

**当前权威结论：此前 -12 → -9.599 dBFS 的异常来自分析命令 `-ac 1` 对 float 立体声做了 downmix，不是原生 Limiter 固定抬高约 3 dB。原“超出 ceiling”的判断撤回。** 原始导出和旧测量 JSON 均保留，没有据此给 DSP 加减 3 dB，也没有修改归一化映射或重新烘焙成片。

当前主线程的复测证据是 `JOB\limiter-stereo-true-peak-recheck-proof.json`：保持原立体声，分别测每通道 sample peak/RMS，并对完整原导出测 `loudnorm` 的 **input_tp**。fixture 振幅 .85 平台结果如下；整片 true peak 与该平台是不同时间窗口，不应直接当作同一点比较。

| 原生 ceiling 请求 | 稳态每通道 sample peak dBFS（L/R 几乎相同） | 完整原导出 true peak dBTP |
|---|---:|---:|
| -24 | -27.576491 | -26.16 |
| -18 | -19.699275 | -19.45 |
| -12 | -12.609727 | -12.59 |
| -6 | -6.172828 | -6.13 |
| 0 | -4.437290 | -4.41 |

**这组复测没有发现超过各自 ceiling 的 true peak。** 它支持本刺激样例下原生 limiter 已按目标压低峰值；不能仅凭这一个 1 kHz 阶梯音调承诺所有输入、启动瞬态或编码格式均有同样上限精度。

### 为什么本次分析会多出 3.0103 dB

本机 FFmpeg 是 `N-126495-g3a165c77dc-20260910`。已核对同一 commit 的一级源码：[libswresample/rematrix.c](https://github.com/FFmpeg/FFmpeg/blob/3a165c77dc/libswresample/rematrix.c#L190)。stereo→mono 的 L/R 系数各为 `1/sqrt(2)`；`auto_matrix` 在此 float 输出/内部格式路径没有再将系数和压到 1（同文件 L616–631）。因此两个同相同值通道 `L=R=x` 会变成：

```text
mono = L/sqrt(2) + R/sqrt(2) = sqrt(2)*x
20*log10(sqrt(2)) = 3.0102999566398125 dB
```

这不是“float 格式本身必然提高音量”，也不是立体声的每通道音量；它是该次自动 rematrix 的系数叠加。换成反相通道甚至可能相消，所以不能把“测完统一减 3.0103”作为通用分析修正。应直接保持通道数/布局，或为听辨另做明确命名的 downmix，并记录混音矩阵。`rematrix_volume/rematrix_maxval` 的用途见 [FFmpeg Resampler 文档](https://ffmpeg.org/ffmpeg-resampler.html)；本次没有更改这些选项去处理原生输出。

本轮只读计算交叉核验了新旧 JSON 中全部 5×4=20 个平台：旧 peak/RMS 减去原立体声每通道值，均等于上述 3.0102999566 dB；最大偏离分别仅 `1.71e-6` / `2.33e-6` dB。计算证据 `JOB\research-native-audio\limiter-calibration\downmix-arithmetic-crosscheck.json`；本机 `-version`、`aresample/ebur128/loudnorm` help 已保留到同目录 `ffmpeg-rematrix-and-meter-help.txt`。该核验没有重新执行 DSP 或导出。

### 同步更新真实五参数验收状态

主线程后续已完成原生 GUI 调参、保存、全语义 undo/redo、重新导出与实际音频差分：`JOB\native-five-audio-edit-proof.json`、`JOB\native-ceiling-range-activation-proof.json`、`JOB\native-five-audio-signal-proof.json`。

- gain/frequency/threshold/ratio 各自改变对应原生保存参数，其它四项保持。
- 最初 ceiling -9 dB 虽可编辑，但未触发当前压缩后刺激样例的额外限幅，PCM 与上一档相同。该证据保留，没有把“没触发”说成“已改变声音”。
- ceiling -18 dB 的更强对照真实改变音频，导出测得 `-18.52 dBTP`、`-27.29 LUFS`；undo/redo 恢复完整语义指纹，redo 后 PCM 与该档相同。这证明参数通路和本次限幅激活；**-27.29 LUFS 是测试刺激结果，不是交付响度目标。**

原有的静态 catalog、参数单位、近似数学和动态曲线路径仍作为安装包事实保留。但不能再将初轮错误测量当成这些实现细节造成 ceiling 超限的证据，也不需要为消除该错误继续猜补偿、改指数或更换 limiter。

### 尚有必要的立体声与瞬态边界验证

后续若要对交付峰值作更广保证，应只补当前刺激未覆盖的边界，而不是重复已经通过的5项编辑验收：

1. 保持真实立体声，分别用 L-only、R-only、同相、反相及左右不等电平的短信号，记录各通道输入/输出峰值和声道映射；避免 downmix 掩盖一侧过冲或相消。
2. 独立 fixture 用短 burst/瞬态、启停边界、强弱交替和不同相位的高频音调，检查 lookahead 启动与 release 恢复。包括接近四分之一采样率的相位错开音调，以覆盖 sample peak 看不见的插值峰值。sample peak 与 true peak 的区别及过采样测量依据见 [ITU-R BS.1770-5 Annex 2](https://www.itu.int/dms_pubrec/itu-r/rec/bs/R-REC-BS.1770-5-202311-I%21%21PDF-E.pdf)。这是测量边界建议，不是声称本次已运行这些刺激。
3. 在最终使用的采样率/编码器下测原导出的完整节目 true peak，并保留逐通道 sample peak；如能取得编码前 PCM，同时测编码后，以区分 DSP 与编码重建的峰值变化。
4. 分析命令不加 `-ac 1`、downmix 或后级音量；使用 `loudnorm` 时只解释输入统计，不能把滤镜的 output_tp 当原生输出。也可用纯扫描的 `ebur128=peak=sample+true` 交叉核对；FFmpeg 对 true-peak 扫描的过采样说明见[同 commit 滤镜文档](https://github.com/FFmpeg/FFmpeg/blob/3a165c77dc/doc/filters.texi)。分析结果仍以实际文件、通道布局、格式、采样率和命令记录为准。

## 初轮研究结论（历史记录，峰值异常已由上节纠正）

**已证实当前 `Ceiling dB` 控制不能直接承诺“导出峰值绝不超过目标 dBFS”。精确的稳态偏差机制尚未闭环。** 不应通过统一减 3 dB、改称 RMS 上限或猜一个补偿曲线来掩盖这个差异。

本机实现中的 `Ceiling dB` 确实是索引 2、范围 -24..0 dB、power 映射指数 0.75。当前五档写入草稿的 normalized 数值与此映射一致，未发现简单的计划值漏写。静态处理链把这个值直接传给共享动态增益曲线的门限字段，配合极大比率、固定膝宽、检测窗口和 attack/release 形成 limiter；已检查的输出路径没有最终逐样本硬钳位，也没有看到 oversampling/true-peak 检测。因此参数名字中的 ceiling 不等于已经证明的最终 PCM/编码后 true-peak 上限。

这足以解释为何必须实测上限，却**不足以单独数值解释 -12 → -9.599 dBFS**。下面明确区分已观察事实、静态推导和待验证项。

## 一手证据和复现定位

任务根 `JOB`：`D:\JianyingHeadless\work\native-av-upgrade-20261028-004610-32bec1`。

本轮静态证据：`JOB\research-native-audio\limiter-calibration`，含 33 个限定函数的 LLVM listing、对应注释文件、IAT 表与 REA 身份 evidence。检查器只读取 PE 字节并调用 LLVM 反汇编，不调用目标代码。

目标文件：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462\audioeffect.dll`；大小 14,006,808 字节；SHA256 `2a384edf76c59a92cc4a4f9d8504d7f512be6e27ae8e32069f0807a489378116`。以下均为该指纹下的 RVA，VA = `0x180000000 + RVA`，不用于跨版本直接调用。

主线程真实测量：`JOB\limiter-steady-tone-calibration-proof.json`。五个原生导出的实际 `timeline.json` 和构建时 `mdsp_preset.json` 分别位于：

```text
D:\JianyingHeadless\work\avcal-lim-{m24,m18,m12,m6,z0}-out-1028-v1\timeline.json
D:\JianyingHeadless\work\avcal-lim-{m24,m18,m12,m6,z0}-build-1028-v1\draft\Resources\native-av\dynamics\mdsp_preset.json
```

以上只读检查了现有 fixture，没有再执行旧任务。REA 打开目标后首次 Ghidra 反编译在 450 秒 provider timeout，没有返回可用函数伪代码；该结果不计作证据。已导出 `rea-evidence.json` 并正常 `close_binary`，单例已释放。核心结论来自下面限定范围的原始机器指令。

## 初轮 downmix 测量记录（保留，不作原声道上限判断）

四个连续平台是 1 kHz 音调，输入振幅分别 0.03、0.1、0.3、0.85。以下为主线程已保存的稳态结果；数值为解码后 sample peak / RMS dBFS。

| 目标 ceiling | 输入 .03 | 输入 .1 | 输入 .3 | 输入 .85 |
|---|---:|---:|---:|---:|
| -24 | -30.233 / -33.507 | -24.426 / -27.596 | -23.322 / -26.370 | -24.566 / -27.633 |
| -18 | -30.233 / -33.507 | -19.962 / -23.035 | -16.465 / -19.497 | -16.689 / -19.720 |
| -12 | -30.233 / -33.507 | -19.962 / -23.035 | -10.466 / -13.488 | -9.599 / -12.619 |
| -6 | -30.233 / -33.507 | -19.962 / -23.035 | -10.466 / -13.488 | -3.163 / -6.177 |
| 0 | -30.233 / -33.507 | -19.962 / -23.035 | -10.466 / -13.488 | -1.427 / -4.440 |

高输入档相对目标的偏差依次约 -0.566、+1.311、+2.401、+2.837 dB；不是固定的 +3 dB。相同目标下，输入 .3/.85 的结果也不同。故不能拿某一次近似 3 dB 的 peak/RMS 差说明它是 RMS ceiling。正弦自身 peak-RMS 约 3.01 dB，不能从这个差值推断检测器类型。

零上限参考在输入 .85 时是 -1.427 dBFS，接近原始正弦理论 -1.412 dBFS。编码不构成所有档位同样的 2–3 dB 增益；但当前证据没有编码前 PCM，仍应以同源、同条件、编码前后对照严格排除 AAC/reconstruction 贡献。sample peak 也不等于 true peak。

## 参数目录、归一化与实际落盘

`Jukedeck::MusicDSP::Processors::LimiterProcessor` 的 RTTI、vtable RVA `0xab3710`、构造器 `0x350020` 与目录构造器 `0x3a8cc0` 已相互对应。目录证据沿用 `D:\JianyingHeadless\integrations\audio-localgraph-research-20261028\mdsp\annotated-0x3a8cc0.txt`。

| 参数 | 索引 | 物理范围 | normalized → plain | 原生目录默认 |
|---|---:|---|---|---|
| Bypass | 0 | bool | bool | false |
| Input Gain dB | 1 | 0..24 dB | linear | 0 |
| Ceiling dB | 2 | -24..0 dB | `-24 + 24*u^0.75` | 约 -0.3 |
| Release | 3 | 1..3000 | power，指数 3 | 500 |
| Lookahead | 4 | 0..10 | linear | 0 |
| Audition Unity Gain | 5 | bool | bool | false |

`0x322c80` 将 power mapper 的正向 callable 绑定到 `0x322060`，逆向绑定到 `0x322160`。正向先 clamp u 到 0..1，调用 `powf(u,p)`，再乘范围加最小值；存储的 p 是 0.75，没有先取倒数。对应物理值到 normalized 的逆式是 `u=((dB+24)/24)^(1/0.75)`。

真实五档中 dynamics 素材的参数均为 `(parameterIndex:2,portIndex:1)`：

| 目标物理值 | 实际写入 `audio_adjust_params.value` | 按静态目录回算 |
|---|---:|---:|
| -24 | 0 | -24 |
| -18 | 0.15749013123685915 | -18 |
| -12 | 0.3968502629920499 | -12 |
| -6 | 0.6814202223120523 | -6 |
| 0 | 1 | 0 |

同一 `timeline.json` 还保留压缩 threshold normalized=1（0 dB）、ratio normalized=0（1:1）、EQ gain=.5（0 dB），主音频 `check_flag=3`，音量 1，响度归一关闭。这排除“根本没写参数/误开归一”的简单解释，**没有证明实际运行中的 LimiterProcessor 收到的 plain ceiling 就是表中回算值**；后者还需要独立对照或官方只读状态回读。

实际 graph 的 parameter port 0 绑定 Compressor，port 1 绑定 Limiter；离线 preset 的 Limiter state 为 Input Gain 0、Ceiling -2、Lookahead 7、Release 100、Bypass false、Audition Unity false。preset 仍为 -2 是初始状态，而运行时事件负责覆盖；不能仅因此认定事件没生效，也不能因此忽略实时/离线两条路径的对照。

## 实际 DSP 路径

### Ceiling 进入动态曲线门限，没有发现固定补偿

`0x3a8f10` 按目录索引读取 plain 参数：Input Gain 转为 `10^(dB/20)`；Ceiling 原值存到 processor+0x8c；Release 存 +0x90；Audition Unity false 时额外输出系数为 1，true 时系数为输入增益的倒数；Lookahead 存 +0xb8。

prepare/reset/update (`0x350240 / 0x350b40 / 0x350f00`) 将 ceiling 送给 core setter `0x421bc0`；后者只有 `core+8=plainCeiling` 的写入。没有减 3 dB 或加固定 makeup。构造器把共享 core 的比率设为 1,000,000（`0x421af0`）、膝宽参数设为 0.5（`0x421950`）。`0x41db10` 对检测后的包络、比率、ceiling 和膝宽计算增益衰减，是 compressor 风格的 gain curve。

core+0x1c 的输出 dB 增益初值为 0；constructor `0x41ef40 → 0x41ead0` 的参数重排与常量 `(0,1,0,1)` 可恢复此值。现有被检查的 LimiterProcessor 更新函数不修改它。不能因此扩展为“整个剪映绝不可能有后级补偿”；这里只排除该节点这条静态路径的固定补偿。

### 检测器是 abs/窗口/包络，不能称为 RMS

block `0x3504d0 → 0x3507d0` 经双声道入口 `0x420160` 进入 lookahead 分支 `0x4201c0`（mono 对应 `0x41f880 → 0x41f8d0`）。主要过程：

```text
输入增益 → abs(sample) → 近似幅度dB
  → 滑动最大值窗口 → attack/release envelope
  → ceiling/ratio/knee增益曲线 → 增益窗口处理
延迟后的原始音频 × dB转线性增益 × audition系数 → 输出
```

abs 使用 `0x7fffffff` 掩码。窗口 `0x43d7f0` / 队尾更新 `0x43d510` 对较小历史项出队，保留窗口最大值。没有在这条前级检测路径观察到平方、均值、再开根的 RMS 算法。`0x43e430` 另处理增益的双精度环形窗口/平滑；其完整时间响应尚未独立重建，不能把它轻率等同为 hard maximum hold。

attack/release 系数经 `0x421d40 / 0x421dc0 → 0x41dac0` 使用 `exp(-1000/(sampleRate*time))`；结合 lookahead buffer 的 `time*0.001*sampleRate`，这些时间参数可静态推导为毫秒。Lookahead setter `0x421960` 管理延迟/窗口；attack 设置为 `max(Lookahead*.02,.001)`。时域平滑可影响过冲；但对于此处稳态长音，是否足以产生所测偏差仍待对照，不作根因断言。

这条路径最后是延迟样本与增益相乘，未见最终 `min/max` 将样本绝对值限定在 `10^(Ceiling/20)`。已检查函数也未显示 oversampling 的 true-peak 检测器。上述结论限于这条 LimiterProcessor 路径；同一 DLL 里的 mammon CLimiter、PeakLimiter、其它 YAML effect 是不同实现，不能拿名字相似的参数说明互证。

### 近似 dB 转换：真实存在，但尚不能解释全部误差

幅度转换 `0x41e650` 先取最大正正规 float 下限，再做三次 sqrt、减 1、乘常量 3.474355697631836、乘 20。可从指令推导：

```text
L(a) ≈ 20*C*(max(a,FLT_MIN)^(1/8)-1)
C = 3.474355697631836
```

增益转换 `0x41efc0 → 0x41f3e0` 对 `g/20` clamp，乘 0.2878231406211853，加 1、平方三次：

```text
E(g) ≈ max(0,1 + (g/20)*0.2878231406211853)^8
```

它们不是精确 log10 / pow(10,x)，相减/相加不满足精确 dB 运算的乘法关系。但**不能把“发现近似”当作已经解释实验**。例如输入 .85，若简化假设完全静态门限 -12、忽略所有窗口/包络，`a*E(-12-L(a))` 给出约 -12.916 dBFS，方向和实测 -9.599 都不吻合。这是反例，证明仍需检查事件解释和实际包络状态，不能直接据此改实现。

## 官方原始说明能支持到哪里

火山引擎官方 [单音效处理器](https://docs.volcengine.com/docs/Audiotechnology/Singlesoundeffectprocessor?lang=zh) 描述两种参数入口：prepare 前用 `Processor_SetParametersOffline` 设置物理值 JSON；运行时可用 `ContextEmplaceParameterEventNowWithPlainValue` 传 parameterIndex/plainValue。float 直接填写物理数值，bool 为 0/1，choice 为选项索引；具体目录在随 SDK 的 `sami_core_effect_param.h`。

该页支持“离线物理值与事件通道必须区分”的判断，没有公开本构建 Limiter 的严格峰值误差保证，也没有说明它使用 RMS ceiling、固定 +3 dB 或 soft clipping。此次对 SAMI/Limiter/Jukedeck/mdsp/header 的公开检索未找到可核验的同版开源内核或完整官方 Limiter 参数头；不把其他厂商 limiter 手册或网上 Android 日志当成本机实现依据。

## 初轮提出的诊断步骤（历史，按前述纠正收敛）

优先做一个能区分控制路径与 DSP 的对照，全部使用独立 fixture，不碰当前编辑稿：

1. **离线物理参数 vs normalized event。** 单个 Limiter 节点，preset 直接写 Ceiling -12、Input Gain 0、Audition Unity false、Lookahead 7、Release 100；不暴露/不发送 ceiling 参数事件。与同一节点 preset -2 + `(port0,index2,u=.3968502629920499)` 比较。节点独占 port0，避免多节点 port 分配混淆。若输出不同，先追事件/归一化/初始化覆盖；若相同，再归因 DSP 行为。
2. **隔离整个链与编码。** 同一源分别做 bypass、单 Limiter、当前 EQ→Compressor→Limiter；保留同一采样率与声道。优先取得原生编码前 float PCM，测 sample peak、RMS、重建 true peak，之后与 AAC 解码对照。
3. **时间响应区分。** 上项相同后，仅改变 Lookahead 0/7/10、Release 1/100/500；每档独立重置，长稳态与单脉冲分别测量。峰值平台应在初始与切换过渡之外测量；记录采样位置，避免把启动或跨平台 release 误当稳态。
4. **在合法只读状态接口存在时回读 plain value。** 确认实际 processor 的 ceiling、lookahead、release、inputgain、audition 状态，而非只回读草稿 normalized 值。没有已核实接口时，步骤1已可在无新 ABI 的情况下提供强证据。

在这组对照前，接口宜如实称“原生 Limiter ceiling 参数”，而不称“已校准的最终 dBFS/true-peak 保证”。本轮没有修改参数换算、添加补偿、替换处理器或给正式草稿烘焙 WAV。
