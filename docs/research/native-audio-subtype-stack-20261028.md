# 剪映 11.4.7：拆分音色与音效，保留五项独立 DSP 参数

日期：2026-10-28。范围：只读安装包、已下载普通声音资源、现有模块和开源源码，未运行任何 edit/mutator，未附加或改变活跃剪映会话，未使用 computer use，未修改引擎、DLL 或 ABI。本文的 native 结论来自静态代码；实际保存、GUI 和出片验收由主线程独立完成。

## 结论与最短验证路径

**当前 Windows 原生代码支持同一片段保留 Normal=0 与 SoundEffects=1 两条音频效果；renderer 对二者调用同一 SAMI 创建路径并继续遍历下一条效果。** 因此可优先验证两个原创资源：Normal0 承载 EQ gain/frequency 两项，SoundEffects1 承载 compressor threshold/ratio 与 limiter ceiling 三项。这样每个资源的 GUI 列表序号都在 0..2 范围内，避开现有第四、第五项回落第一槽的问题，保留五个独立物理参数。

这不是已完成的 GUI 叠加验收。静态证据还不能证明双类别在当前选中上下文的五项刷新、GUI accept/undo/save、renderer 实际串联顺序全都正确。需要原生 SDK 建立两效果后回读，再通过现有 live 入口分别切换分类并完成真实参数修改、保存与出片。**不要使用发布 Web JS 的 `setVoiceEffect` 路径做双效果测试：其实现会把数组重置成单项。**

建议最短路径：

1. 使用已有专用 QA 音频和两个全新资源 ID，分别以 `audioChangeVoice` Normal0、SoundEffects1 建立效果。不得重复旧任务或使用 `is_modify` 冒充新增。
2. 原生保存后，核对该片段的 `voice_change` / 保存的 `extra_material_refs` 能关联到两条不同资源；两材料 `sub_type` 分别为 0/1，参数数分别为 2/3，源音频材料 `check_flag` 保留 VoiceChange 位（现有样例为 3）。
3. 做四组原生导出：无效果、仅 EQ、仅 dynamics、两者；比较解码 PCM、频谱和峰值。不能只检查 JSON。双效果的强度/参数各改变一次，排除其中一条被另一条覆盖。
4. 通过当前原生模型的类别选择，分别得到 EQ 两对象、dynamics 三对象；每项列表序号必须从 0 重新计数。各项原生 accept 后核对只改变目标参数，其他四项保持；重新选择后值仍吻合，并核验 undo/redo/save。

计划的两阶段顺序是 **EQ → compressor → limiter**。原先单图若为 compressor → EQ → limiter，本拆分改变了节点次序，不能宣称完全等价。对话音频中该次序可作为原创 DSP 设计选择，仍须实际听感与响度验证。

## 一手目标与证据方法

主目标 `D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462\videoeditor.dll`，70,998,296 字节，SHA-256 `fa89997a94e96cf97c8ee436a56ab028ea5f87731214696ba43ff74c0fdc0fa0`。下文地址均为本 DLL RVA；文件 preferred image base 是 `0x180000000`，不能当进程实际地址使用。

方法：已有 PE export 名称、`.pdata` 函数边界、磁盘原始字节与本机 LLVM 有界反汇编。未新开或替换 REA 的活跃 native target，不把这些结果写成 REA 反编译证据。静态取证脚本与原始输出在 `D:\JianyingHeadless\integrations\audio-localgraph-research-20261028\subtype-split`，所有分析操作只读官方二进制。

MSVC 合并了很多布局相同的 getter/setter。某个 RVA 被数百个不同类导出，**不能只凭地址名称判定当前对象类型**。下述 subtype 判断均沿 `SegmentAudio::get_voice_change` 返回的 `MaterialAudioEffect` 容器证明，而非扫描到任意 `0x15ba70` 调用就认定为音频效果。

## Windows SDK 新增操作保留另一个类别

方法注册构造函数 `0x1b5dc40` 在 `0x1b5eacd` 注册 thunk `0x1b59330`，附近方法字面量是 `audioChangeVoice`（`0x1b5eaf0`）。Thunk 从请求结构获取原生参数，然后调用 `0x1b307d0`。该实现区分修改已有材料和新增：

| 路径 | 静态行为 |
| --- | --- |
| 参数 `+0x178` 为真 | 遍历已有效果，按 `resource_id` 匹配，修改该资源的类别/来源等字段；不是正常新增证明 |
| 参数 `+0x178` 为假，音频 | `0x1b30bc5` 起读取材料 `check_flag`，缺少位 2 时 OR 2；取可写 voice-change NodeArray，调用 `0x1b327e0` 构建并插入新效果 |
| 参数 `+0x178` 为假，视频原声 | 对视频材料另一个既有 check 位进行启用，获取对应容器，再调用同一插入 helper；本轮主验证对象仍应是音频材料，不能把其位值套到视频材料 |

插入 helper `0x1b327e0` 的直接证据：

- `0x1b32972` 取参数 `+0xe0`，`0x1b32984` 调用 `MaterialAudioEffect::set_sub_type`（export RVA `0x260500`）。类别为真正的 native 枚举，不仅是 GUI 标签。
- `0x1b32bf5` 读取该类型；**仅 type 2 或 3** 进入后续删除匹配类型的循环。类型 2 另会移除 type 0。这一规则不能泛化到类型 0/1。
- `0x1b32dba` 后，type0 在容器 begin 插入（`0x1b32dca` → `0x1b32dd7`）；非零类型在 end 追加（`0x1b32e24` → `0x1b32e4d`）。因此 Normal0 与 SoundEffects1 不会被这段代码相互删除；正常新建静态预测得到 `[Normal0, SoundEffects1]`。
- 该 helper 为新材料复制 `path`、`resource_id`、`category_id`、`category_name`、`source_platform`，再复制完整 `audio_adjust_params` vector（`0x1b32bf0` 调 `0x768d70`）。没有把参数裁成三项；三槽限制是 GUI 读取/属性绑定路径。
- helper 前半段会对名称匹配做提前返回判断；测试使用两个不同原创名字与资源 ID，避免把名称重复行为误判为类别冲突。同类别重复添加的全面语义不在本报告范围。

证据：`videoeditor-0x1b5dc40.txt`、`videoeditor-0x1b59330.txt`、`videoeditor-0x1b307d0.txt`、`videoeditor-0x1b327e0.txt`、`insert-helper-setters.json`，均位于上述 `subtype-split` 目录。后续 `0x1b415c0` 还进行片段/引用更新；本轮不调用它，也不把静态 NodeArray 插入冒充最终保存成功。

## Renderer 对 type0 与 type1 使用同一 SAMI 链

音频恢复函数 `0x1b4f670`：

| RVA | 行为 |
| --- | --- |
| `0x1b511bd` | `SegmentAudio::get_voice_change` |
| `0x1b511e5` | vector 元素循环，元素为 16 字节 shared_ptr |
| `0x1b511ed` | `MaterialAudioEffect::get_sub_type` |
| `0x1b511f2` / `0x1b511f5` | `cmp subtype,1; ja skip`，无符号比较，接受 0 与 1 |
| `0x1b5124e` | 对当前材料调用公共创建 helper `0x1b4f1d0` |
| `0x1b51253` | `add iterator,16` 后继续，直到 vector end |

更新/diff 函数 `0x1b520d0` 同样读取 voice-change vector、对 dirty 材料判断 subtype<=1、调用同一个 helper 并继续循环（`0x1b53bf6`、`0x1b53c37`、`0x1b53c93`）。所以 renderer 既不是只取第一项，也没有在这段创建分派中把 Normal0 和 SoundEffects1 分成不同的算法引擎。

公共 helper `0x1b4f1d0` 为每条材料取 path/id 与 `audio_adjust_params`。参数映射的 native key 实际顺序是 **(portIndex, parameterIndex)**：`0x1b4f32a` 读取 portIndex（getter `0x5a2890`），`0x1b4f330` 读取 parameterIndex（getter `0x122cc0`）。然后走现有创建/更新 wrapper：无既有 handle 经 `0x29bedf0`，已有 handle 经 `0x29c29c0`；后续共用 SAMI 创建链。这与 `config.effect.Link.type=SAMIAudioEffect` 资源入口相容。

此处能证明两类型都能到达同一 SAMI 创建链。**是否按 vector 顺序串联、每条出片确实生效、是否发生自动规范化**，仍必须用双效果原生导出证明，不能以函数调用次数替代。

证据：`videoeditor-0x1b4f670.txt`、`videoeditor-0x1b520d0.txt`、`videoeditor-0x1b4f1d0.txt`、`effect-creator-callers.json`、`wrapper-call-tail-refs.json`。

## 五控制的拆分绑定

原始 DSP 的物理参数换算见 [本地原创 DSP 研究](native-audio-localgraph-20261028.md)。各独立 bundle 的 root ports 应按该 bundle 的 `parameter_change` 路由定义重新编号，不能直接沿用单图的原始 root port 1/2。以下是假设 EQ root0、comp root0、limiter root1 的最小绑定设计，并非已经制作的资源：

| 类别 | 本类 GUI list index | 控制 | parameterIndex | portIndex |
| --- | --- | --- | --- | --- |
| Normal0 / EQ | 0 | EQ band1 gain | 4 | 0 |
| Normal0 / EQ | 1 | EQ band1 frequency | 2 | 0 |
| SoundEffects1 / dynamics | 0 | Compressor threshold | 2 | 0 |
| SoundEffects1 / dynamics | 1 | Compressor ratio | 1 | 0 |
| SoundEffects1 / dynamics | 2 | Limiter ceiling | 2 | 1 |

每项 `extra.json.setting.audio_effect_parameters_change` 的 `minValue/maxValue` 仍可用 0/1，DSP normalizedparameter 的物理换算保留。不得把列表 index、DSP parameterIndex、root portIndex 混为一谈。

GUI 的已证实缺陷和动作链见 [普通参数滑块研究](native-audio-gui-sliders-20261028.md)。该 GUI 的效果/category selector（VECreator RVA `0x3253b90`）在空 category 下直接取第一条效果；双效果不能依赖空 category 选第二条，必须确认当前 handler 原生分类状态与当前目标资源。**类别分离本身不能证明五项独立关键帧支持**：现有关键帧属性映射还存在独立的三槽约束，本方案首先验证五项固定参数。

## 发布 Web JS 与开源实现的边界

本机 `canvas_agent` 发布 JS action83913 与 action52092 分别使用 `voiceChange[0]` 并写回单项数组（`voiceChange=[g]` / `[A]`）。所以这些 Web action 的单项行为不能用来否定 Windows native vector 支持，也不能用它们添加第二类别再期待第一类别保留。既有 extract：`D:\JianyingHeadless\work\native-av-upgrade-20261028-004610-32bec1\research-native-audio\voice-effect-action-83913.js.txt` 与 `voice-effect-action-52092.js.txt`。

开源一手佐证：[pyJianYingDraft audio_segment.py，固定提交 1e228479](https://github.com/GuanYixuan/pyJianYingDraft/blob/1e228479dda361e312e85f6037002346cf6dca9a/pyJianYingDraft/audio_segment.py)。其 `AudioSegment.add_effect` 只拒绝相同 category 重复，允许音色与场景音同时追加；`AudioSceneEffectType` 导出 subtype1，`ToneEffectType` 省略 subtype（依赖原生默认0）。这只是格式线索；源码所述音色测试版本是5.9/10.8，不能当作11.4.7 Windows验收。仓库 Apache-2.0，本文没有移植其代码。

## 复合片段备用路线的现状

当前 [engine/native_compound.py](../../engine/native_compound.py) 是 macOS 11.4.2/11.5.0 profile 的离线复合构造工具；其 `require_publishable()` 明确阻止带 `materials.drafts` 的 live registration，原因是已知原生保存丢子草稿目录。验证器使用空 path、`extra_type_option=2` 的 video placeholder，并未建立 Windows 三层纯音频复合片段的 GUI 可编辑保存保证。

[engine/lyra_commands.json](../../engine/lyra_commands.json) 记录了官方 CLI `draft compound-clip create`（含 `--ref --seg-id --seg-type --target-track --seg-index --time-window --name`）和 `break-apart`。这是将来可实验的原生命令入口，不是本报告已调用或已验收的替代方案。当前优先走已找到强静态证据的两类别路径；不应把现有 macOS 构造器宣传为可直接交付的 Windows 音频串联能力。

## 仍须实测或未知

- 当前11.4.7专用草稿中两效果同时 native save 后的精确数组、check flag 与引用保留。
- 双效果原生导出的实际处理顺序、两条 DSP 的相对延迟、峰值与各自的独立影响。
- GUI 原生分栏/category 切换是否可用现有已验证模型命令完成，并分别正确刷新2/3项。
- 五项 normal accept、重新选择、undo/redo/save 与保存后实际出片的完整闭环。
- 五项独立关键帧、同类别多实例、第三类插入、视频原声 check flag 以及音频 compound 的当前 Windows 持久化，不在本报告已证明范围。

没有调用任何候选函数，没有修改官方文件或绕过授权；以上静态地址仅作为当前指纹下的验证线索，不能脱离现有桥 ABI 或指纹门禁直接调用。
