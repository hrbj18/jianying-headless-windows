# 当前音频检查器绑定与跨类别参数错读

日期：2026-10-28。本轮是只读现场研究；没有 computer use、没有连接编辑 pipe、没有调用 getter/slot/原生方法、没有修改 engine/桥/ABI/DLL/素材/草稿。仅用已有 `Reader` 的 `PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION`、模块枚举、限定 vtable 扫描读取原生模型，并静态读取安装 PE。实际切 tab 由主线程通过正式入口执行。

目标构建 11.4.7.14462，`VECreator.dll` SHA256 `769c33961ef9d7e471e583f03c975be975b0c35e849a767690d09e9f2fc45111`；`videoeditor.dll` SHA256 `fa89997a94e96cf97c8ee436a56ab028ea5f87731214696ba43ff74c0fdc0fa0`。

## 结论

当前 `AUDIO_CATEGORY_NOT_BOUND` 首先来自**找错了已加载的模型类型**：现用 `DraftInspectorAudioViewModel`，而旧 binder 仅查 `AudioSettingViewModel`。二者不是可以混用字段偏移的同一个对象。新版音效子页尚未加载时，`AudioEffectSettingHandler` 也完全不在堆上；单纯扩大旧类 vtable 白名单不能解决问题。

主线程通过现有 `PanelSettingCommonViewModel.switchTab` 正常加载 `audio_effects` 后，现场已出现两个独立类别 Handler、2+3 个滑块。此时又证实：**两个音效素材都缺少 `constant_material_id`，导致原生 fixed-value getter 跨类别按相同列表序号取值。** 这是素材身份字段的遗漏，不是需要伪改 VM 或改 kind 的 UI 限制。

精确静态查找过程与实际反例相符：threshold/ratio 的列表索引 0/1 先命中 EQ 的两个值；ceiling 索引 2 因 EQ 不足3项而继续遍历，恰好取到 Dynamics 的第三值。为每个素材保存各自唯一、稳定的 `constant_material_id` 是有原生依据的最小修复方向，仍须主线程在新独立 fixture 中实际验收。

## 现场身份与证据

现场由主线程提供：PID 26164；birth `134375592292885847`；draft `117AA48C-C460-451b-99C9-04210C46AB0F`；session `cab3aff3ca8d1166e115e3e020f96d115f241d49a51ca907ee12c693200d9d01`；当前已原生选中 audio `501B67CC-77A9-4E6C-A4FA-F62B46EC3984`。

研究根：`D:\JianyingHeadless\work\native-av-upgrade-20261028-004610-32bec1\research-native-audio`。

证据：

- `current-audio-vm-rtti-all.json`：匹配 Audio/Sound 与 Setting/Inspector 的本机构建 RTTI 和 primary/secondary vtables。
- `current-audio-vm-live-readonly.json`：加载音效页前的只读扫描。
- `current-audio-vm-qmeta.json`：当前新版主/子模型的 Qt metadata，直接来自安装 PE。
- `current-audio-effect-loaded-readonly.json`：主线程正常切 tab 后的只读扫描。
- `current-audio-effect-binding-deep-readonly.json`：root/model/child/wrapper/Handler/参数的原始字段读回。
- `current-audio-effect-*.txt`、`current-audio-model-wrapper-getter.txt`：子页构造/正常 onReady/模型 wrapper getter 的限定 LLVM 反汇编。
- `current-audio-wrapper-*.txt`、`current-audio-value-lookup-*.txt`、`current-audio-lookup-videoeditor-*.txt`：参数刷新至 fixed-value getter 的限定反汇编及注释版本。

扫描仅以指定类型 vtable 为候选，并校验 QObject private 的 q_ptr；没有保存一般进程内存、其它任务、账号或凭据。下面的实例地址仅用于说明此次快照，不能缓存复用。

## 当前实际模型与正常 loader

加载前，以下两种 `AudioSettingViewModel` 均未实例化：native primary `0xbfa7f80` / secondary `+0x10 → 0xbfa7fe0`，以及 `QQmlElement<AudioSettingViewModel>` primary `0xb4ae960` / secondary `+0x10 → 0xb4ae9c0`。

现场真正 root 是 `QQmlElement<DraftInspectorAudioViewModel>` primary RVA `0xb4b3c90`（实例 `0x66235870`）；native 非 QML 包装版是 `0xbfc2018`。Qt static meta RVA `0xbf62a40`，static metacall `0x3110db0`，其父元数据明确是 `PanelSettingCommonViewModel` (`0xbf5e2b0`)。

父类已有 `switchTab(int)` signal，Qt local index 2；tab 模型与视频检查器使用相同的 CommonModel 结构。主线程已实际读到 tab IDs：

```text
audio_basic, audio_vc, audio_effects, audio_speed, audio_lyrics_adapted
```

应按实际 tab ID 查索引，不能把本次 `audio_effects` 为 index 2 当作永久布局保证。沿现有正常 `switchTab` → QML tab/loader → `onReady` 连接加载子页，不调用构造器、不任意写指针。

主线程正常切到 `audio_effects` 后，新增 `QQmlElement<DraftInspectorAudioEffectViewModel>` primary RVA `0xb4b3dd8`（实例 `0x450e9a90`）。其 native 版 primary `0xbfc23b8`，QObject 大小 `0x28`；metadata RVA `0xbf215e0`，metacall `0x30becc0`。Qt `handler()` 的原生实现 `0xf04870` 直接返回对象 `+0x20`，不需要执行 getter 即可只读核对。

## 新布局精确绑定

| 对象 | 偏移 | 含义 |
|---|---:|---|
| DraftInspectorAudioViewModel | +0x50 / +0x58 | 当前 DraftInspectorAudioModel shared_ptr 对象/控制块 |
| DraftInspectorAudioModel | primary RVA `0xbff38d8` | 此次实际模型类型 |
| DraftInspectorAudioModel | +0x50 | `std::vector<std::string>` 当前 selected IDs |
| DraftInspectorAudioModel | +0xa8 / +0xb0 | 当前 SoundSegmentActionWrapper shared_ptr 对象/控制块 |
| DraftInspectorAudioEffectViewModel | +0x10 / +0x18 | 同一 DraftInspectorAudioModel 的 weak_ptr 对象/控制块 |
| DraftInspectorAudioEffectViewModel | +0x20 | AudioEffectsSettingSubViewModel* |
| AudioEffectsSettingSubViewModel | +0x68 / +0x70 | kind0 tone / kind1 sound_effect 两 Handler |
| AudioEffectSettingHandler | +0x388 / +0x390 | 同一 SoundSegmentActionWrapper shared_ptr |
| SoundSegmentActionWrapper | primary RVA `0xbf8cee8` | 当前新版 wrapper |
| SoundSegmentActionWrapper | +0x08 | **内联** selected IDs vector；不是 settings-data 指针 |

实际深读：root.model 与 child.model 均为 `0x5b974b60`，控制块均为 `0x5b974b50`；model.selected IDs 只含本次 audio ID。model.wrapper 为 `0xd2aee770`、控制块 `0xd2aee760`，两 Handler 的 wrapper shared_ptr 完全相同。

旧报告中 `AudioSettingVM+0x18` settings、`+0x28` wrapper、`+0x40` SubVM 的结构确实属于**旧模型**，不能用于此次新版 `DraftInspectorAudioViewModel`。新版 wrapper 自身存 selected vector，也不能把旧 `VideoSoundgmentActionWrapper+8` 的 settings pointer 校验移植过来。

静态依据：

- 子页构造 `0x35a5330` 先构造 `DraftInspectorAudioSubViewModel` (`0x3338ee0`)，后在 `+0x20` 创建 `AudioEffectsSettingSubViewModel` (`0x3332e90`，传 bool true)。两类别 Handler 的原有布局保持成立。
- 新子页基类 `+0x10/+0x18` 从当前 DraftInspectorAudioModel 的上下文取得弱引用，现场与 root.model 一致。
- 子页 `onReady` virtual `+0x60 → 0x35a5400` 锁 model 弱引用，调用 `0x37e3890` 取 `model+0xa8/+0xb0`，再调用 SubVM virtual `+0x58 → 0x3336500` 将 wrapper 传播给 Handler。
- `SoundSegmentActionWrapper` virtual `+0x18 → 0xdc0310` 返回 `this+8`，而非 `[this+8]`。

最小 binder 修正是增加这条新版 root→model→子页→SubVM 路由，保留全过程 QObject/type/控制块/当前选中ID/handler.owner 校验；不是删掉校验或只按列表长度放行。

## 2+3 参数仍错读的真实反例

两 Handler 都是 `AudioEffectSettingHandler` primary `0xbf95348`，secondary `+0x38 → 0xbf956b0`、`+0x1f8 → 0xbf956d8`；kind 为 0/1。每个参数对象 primary `0xbff3ac0`，owner/category/index/parameterIndex/portIndex 均正确。

| category / 列表 index | DSP index / port | 原始内存 value | 主线程核对的保存值 |
|---|---|---:|---:|
| tone / 0 (gain) | 4 / 0 | .45 | .45 |
| tone / 1 (frequency) | 2 / 0 | .3920304196852271 | .3920304196852271 |
| sound_effect / 0 (threshold) | 2 / 0 | **.45** | **.5518367346938776** |
| sound_effect / 1 (ratio) | 1 / 0 | **.3920304196852271** | **.3047797829639662** |
| sound_effect / 2 (ceiling) | 2 / 1 | .8369073924629202 | .8369073924629202 |

主线程确认当前原生保存导出中的两节点 `constant_material_id` **都缺失**。本报告未修改原始字段或滑块值，错读结果保留为反例。

## constant_material_id 参与 fixed-value getter 的完整链

当前新版 `SoundSegmentActionWrapper` 虚函数链是：

```text
Handler refresh → wrapper +0xf0 = VECreator 0x3258880
  category 选择 voice_change 节点：0x3253b90
  对每个 GUI 列表 index 调 wrapper +0xe0 = 0x3266eb0
    取该节点 constant_material_id
    → wrapper +0xe8 = 0x3267280
       列表 index → 0x3258690 → oldAudioFlagtoKeyframeType
       index 0/1/2 → flags 2/4/8 → KFTypeEffectAdjustParam1/2/3
       → 0x3252d10 → 0x1176d30
       → videoeditor KeyframePropertyHelper::getPropertyValues
          (RVA 0x1337730)
```

注意：正常 UI 类别在前半段**有参与**，并非整个 getter 从来不看 category；碰撞发生在后半段按稳定素材 ID 求值时。

`0x3266f4b` 对匹配素材调用的表项 VECreator `0x7f361a8`，通过只读读取当前解析后的函数指针并核对 `videoeditor.dll` 导出，落在 RVA `0xff190`；该地址因 identical-code folding 有多个 getter 别名，其中此对象上下文对应 `MaterialAudioEffect::get_constant_material_id()`。因此没有凭导出列表的最后一个别名把它误判成 `Transform::get_y`。

`0x1176d30` 构造 `KeyframeTypeKey` 的两个 string：属性类型和 constant material ID。后者在 `+0x20`。音频不走 SegmentText 的专用分支；正常调用 `KeyframePropertyHelper::getPropertyValues(shared_ptr<Segment>, KeyframeTypeKey const&, int64)`。

fixed-value fallback 进一步进入：

```text
videoeditor 0x1337d70 → 0x1337f20 → 0x1338400
  动态识别 SegmentAudio → property_audio.cpp 包装 0x1355160
  → 0x1354d40
    KFTypeEffectAdjustParam1 → 0x132cc70(..., index=0)
    KFTypeEffectAdjustParam2 → 0x132cc70(..., index=1)
    KFTypeEffectAdjustParam3 → 0x132cc70(..., index=2)
```

`0x132cc70` 是决定本次反例的最小函数（仅56行反汇编）：

1. `0x132cc8d` 调 `SegmentAudio::get_voice_change`，遍历各音效 shared_ptr。
2. `0x132cca3` 读每个节点 `constant_material_id`。
3. `0x132ccc3` 比较字符串长度；`0x132cccc` `memcmp` 比较内容。它没有校验 UUID 格式，也不比较 category/sub_type/port。
4. 若 ID 匹配，`0x132ccd8` 调 `MaterialAudioEffect::get_audio_adjust_params`，`0x132ccee` 检查该 vector 是否有本次**列表 index**。
5. 有此项则在 `0x132cd25` 读它的 `value` 返回；否则继续下一个 voice_change 节点。

因此两个空 ID 的行为可逐项预测：index0/1 在第一个 EQ 节点就成功，返回 EQ gain/frequency；index2 在 EQ 越界后继续匹配第二个 Dynamics，返回 ceiling。这与现场五个 raw double 完全吻合，已有比“可能缓存”更明确的因果证据。

同一系统在关键帧数组查找 `0x134bac0` 也将 `KeyframeTypeKey` 的 ID 用于匹配素材；但本次没有建立或编辑关键帧，不能因系统函数名为 Keyframe 就把固定值读回忽略掉。

## 合法字段样例与最小验证

已有正式 SDK 创建的原生音效结果给出真实 UUID 例子：

```text
id                   = 7683E624-BF34-4974-B819-49BCEA997AAF
constant_material_id = EE742F55-709F-4f08-83B0-5C3103D64B73
```

来源：`JOB\voice-effect-session-native-v3-noenums\voice-effect-response.json`；在其 `voice-effect-modified-response.json` 调参后保持同一 constant ID。说明 UUID 是真实被接受的正常形状，而且 constant ID 是稳定素材身份，并不必须等于 `id`。

对原创 fixture，可给每个节点新建各自唯一 UUID，后续保存/调参/undo 均保持；若用既有 node UUID 作为 constant ID，字符串查找本身接受这种形状，但仍应与正常独立 constant UUID 的策略明确选定，不能每次渲染重新生成而使身份漂移。它不是资源下载 ID、授权 ID 或伪造官方材料身份。

主线程后续验收应在**新独立构建**中补字段，保持全部 DSP 参数原值；正式打开后确认：两 Handler 的5项 value 各自匹配保存值；参数对象 `constantMaterialId` 也匹配所属节点；单独修改 threshold/ratio 不改变 EQ；undo/redo、保存、重新选择后仍一致；原生出片改变对应音频而保留其它参数。此次只读报告不代替这些运行时验证，也没有为消除错读而写 VM、删控件、改 category、改变 kind 或绕过正常 loader。
