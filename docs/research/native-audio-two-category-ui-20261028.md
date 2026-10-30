# 原生音频两栏：EQ 2 参数 + Dynamics 3 参数的 GUI 路由

日期：2026-10-28。静态只读研究；未调用目标 getter/mutator、未选择片段、未附加进程或使用 computer use。目标为剪映 11.4.7.14462 `VECreator.dll`，SHA-256 `769c33961ef9d7e471e583f03c975be975b0c35e849a767690d09e9f2fc45111`。地址均为该 PE 的 RVA，不能直接复用旧进程指针。接续 [五滑块/三槽反例报告](native-audio-gui-sliders-20261028.md)。

## 可用结构

官方 GUI 已经有独立音色、音效两栏，**不需要通过一个 Handler 的 int 方法切换 subtype**。`AudioEffectsSettingSubViewModel` 持有两个 `AudioEffectSettingHandler`，每个继承 `SoundEditSettingHandler`，分别拥有自己的 `paramDataList` 和从 0 开始的列表序号。

| 链路（以 AudioSettingViewModel primary 起算） | 类型/意义 |
| --- | --- |
| `AudioSettingViewModel +0x40` | `AudioEffectsSettingSubViewModel*` |
| `SubVM +0x68` | `timbreSettingHandler: AudioEffectSettingHandler*` |
| `SubVM +0x70` | `soundSettingHandler: AudioEffectSettingHandler*` |
| `Handler +0x380` | 本地 kind：0 音色、1 音效、2 声音成曲 |
| `Handler +0x2e0/+0x2e8/+0x2f0` | 独立 `QList<SoundChangeParamData*>` data header / 元素指针 / 数量 |

两个属性的原生 getter 分别只返回 `SubVM+0x68` 与 `SubVM+0x70`，没有懒创建。构造 `0x3332e90` 为 `+0x68` 创建 kind=0 Handler，为 `+0x70` 创建 kind=1 Handler；不依赖先点中其中一栏。Handler 构造 `0x32b4bd0` 把传入 kind 写入 `+0x380`。

其 virtual `+0x348` → `0x32b7410` 根据 kind 返回 category：

```text
0 → tone
1 → sound_effect
2 → speech_to_song
其他 → 基类默认 category
```

所以现有计划的 EQ Normal0 应绑定 `tone`，Dynamics SoundEffects1 应绑定 `sound_effect`。这是基于两个现成 Handler 的正确资源拆分方向；两资源实际叠加出片由主线程验收，本报告不宣称已完成。

证据：`类别 Qt metadata`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-category-model-metadata.json`，未随源码分发）、`getter 布局`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-category-handler-getters.txt`，未随源码分发）、`SubVM 构造`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-category-create-refresh.txt`，未随源码分发）、`Handler kind 构造`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-handler-kind-constructor.txt`，未随源码分发）、`固定 category`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-category-fixed-state.txt`，未随源码分发）。

## onVoiceChangeSelected(int) 不是切栏或换素材

`SoundEditSettingHandler` Qt local method 44，metacall `0x30b8b60` 的分支 `0x30b8dc8` 调用实现 `0x32ac880`。实现**完全不使用 int 参数**，只调用当前 Handler 的 virtual `+0x330` 和 `+0x308`。

对于 `AudioEffectSettingHandler`：

```text
+0x330 → 0x32b0030 → 按当前 Handler 固定 category 刷新参数列表
+0x308 → 0x0df9f40 → 仅空包装/计时生命周期，无素材编辑
```

这是一条“选择已经改变”的通知槽。不能用 `onVoiceChangeSelected(0/1)` 将同一对象从音色切到音效，也不能修改 `+0x380` 冒充正常切栏。若准确选中目标后参数尚待刷新，现有桥可按该通知本义对**各自已定位的 Handler**触发正常刷新；本研究没有执行它。

新建参数工厂 `0x32a6230` 在构造每个参数前取 Handler virtual `+0x348`，把 category 传给 `SoundChangeParamData`。因此两个派生栏的 `item.categoryID (+0x88)` 预期分别为 `tone` / `sound_effect`；这是比空 `materialID` 更有用的校验。每项还应校验 owner、index、parameterIndex、portIndex、name、范围、隐藏状态及原生保存值。

证据：`通知实现`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-onVoiceChangeSelected.txt`，未随源码分发）、`派生 virtual slots`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-category-properties.txt`，未随源码分发）、`参数工厂`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-param-factory.txt`，未随源码分发）。

## 普通 QML 的切栏入口

SubVM 构造中的确切资源路径为 `qrc:/FunctionPanel/audio/effect/SoundAudioEffectsSettingSubView.qml`。相应功能的编译单元中，两栏 `baseViewModel` 分别绑定 `root.baseViewModel.timbreSettingHandler` 与 `root.baseViewModel.soundSettingHandler`。

主音频面板还有正式程序入口：`AudioSettingViewModel` 的 signals：

| Qt local index | 信号 | 主 QML 的行为 |
| --- | --- | --- |
| 3 | `selectVoiceChanger()` | 进入音色对应主 tab；旧布局调用旧子面板 `updateIndex(vcIndex)` |
| 4 | `selectVoiceChangerEffect()` | 按新/旧布局进入音效对应主 tab，再调用子面板 `updateIndex(effectIndex)` 或新布局 `updateIndex(0)` |
| 5 | `selectVoiceChangerToSong()` | 声音成曲入口，本方案不使用 |

主 QML 单元文件偏移 `0xbd2e5b0` 的 functions 43/44/45 正是上述三个 signal 的监听处理。两栏子面板的 `VESettingPanelSubTabControl` 使用 `currentIndex/selectedIndex`；旧布局还使用 `isSwapTimbreAndSound()`、`vcIndex` 与 `effectIndex`，所以不要硬编码一个 tab 序号适配所有布局。

`AudioEffectsSettingSubViewModel.onTabIndexChanged(int)` 是 Qt local 8，实现 `0x3333a20`。它是官方 QML 在 tab 事件后调用的模型通知，并含埋点及当前项处理；仅调用它不等于 QML 选中项已经改变。若需要实际展示对应栏，宜复用上述 `AudioSettingViewModel` signal 及其官方 QML 连接；若只编辑已正确绑定的目标，两 Handler 的独立性并不依赖界面当前显示哪栏。

证据：`主 QML 原始 function/lookup`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-main-qml-decoded.json`，未随源码分发）、`两栏 QML 原始 function/lookup`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-category-qml-decoded.json`，未随源码分发）、`tab 通知实现`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-category-tab-handler.txt`，未随源码分发）。

## 当前选中目标的原生绑定，排除缓存同类实例

不能只凭同类 vtable、五个/两个/三个控件或 category 匹配，就使用一个缓存 QObject。当前 `AudioSettingViewModel` 的 primary 布局是：

| primary 偏移 | 内容 |
| --- | --- |
| `+0x18` / `+0x20` | 当前 settings-data 的 `shared_ptr` 对象 / 控制块 |
| `+0x28` / `+0x30` | `VideoSoundgmentActionWrapper` 的 `shared_ptr` 对象 / 控制块 |
| `+0x38` | 基础 `SoundEditSettingHandler*` |
| `+0x40` | `AudioEffectsSettingSubViewModel*` |

**`+0x30/+0x38` 不是 settings-data shared_ptr。** 这两个位置分别属于 wrapper 控制块和基础 Handler。

构造 `0x341b500` 明确写入 wrapper 到 `+0x28/+0x30`、基础 Handler 到 `+0x38`。secondary 接口在 primary `+0x10`；其 bind 实现 `0x3421a10` 以 secondary this 为基准，将传入 settings-data shared_ptr 复制到 `secondary+0x08`，即 primary `+0x18/+0x20`，然后复制到 wrapper `+0x08/+0x10`。同一绑定流程将 wrapper 传给基础 Handler，并调用 SubVM `0x3336500`，依次把同一 wrapper 传给音色/音效等各 Handler 的 virtual `+0x2f8`。

wrapper virtual `+0x18` → `0x341f8e0` → `0xdc0310` 返回 `settingsData +0x08`。调用方把它作为 `std::vector<std::string>` 的 begin/end/capacity，按 `0x20` 字节 string stride 遍历当前选中片段 ID。这里描述由代码行为确定的 settings-data；尚未恢复它精确 C++ 类型名，不把逻辑名称冒充 RTTI 名称。

因此 live 桥应只读验证完整链：

```text
VM primary/secondary 指纹正确
VM.settingsData == wrapper.settingsData
VM.settingsControlBlock == wrapper.settingsControlBlock
selectedIds == [此次真实目标音频 segmentId]
两 Handler.wrapper == VM.wrapper（对象和控制块均相同）
Handler kind/category 与此次资源类别一致
param.owner == 此 Handler；param.categoryID 与此 category 一致
列表序号、DSP parameterIndex/portIndex 与原生保存节点完全对应
```

这比扫到一个同类实例后尝试 getter 更可靠，也避免将上次草稿或选择缓存对象当当前目标。

证据：`VM 构造与 offsets`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-setting-vm-bind-constructor.txt`，未随源码分发）、`secondary bind`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-setting-data-bind.txt`，未随源码分发）、`子模型传播 wrapper`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-category-bind-wrapper.txt`，未随源码分发）、`wrapper selected IDs`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-selected-data-refs.txt`，未随源码分发）、`按 string stride 使用 selected IDs`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-owner-refresh.txt`，未随源码分发）。

## 指纹和待验收项

| 类型 | primary vtable RVA | secondary |
| --- | --- | --- |
| AudioSettingViewModel | `0xbfa7f80` | 对象 `+0x10` → `0xbfa7fe0` |
| AudioEffectsSettingSubViewModel | `0xbf9bfe0` | 当前仅恢复 primary |
| AudioEffectSettingHandler | `0xbf95348` | `+0x38` → `0xbf956b0`；`+0x1f8` → `0xbf956d8` |
| VideoSoundgmentActionWrapper | `0xbfa8008` | 当前仅恢复 primary |
| SoundChangeParamData | `0xbff3ac0` | 当前仅恢复 primary |

元数据：AudioSettingViewModel static metacall `0x3117550`；AudioEffectsSettingSubViewModel `0x30e49a0`；AudioEffectSettingHandler `0x31087d0`。这些 method index 均为所属类 local index，仍应遵守现有桥的 methodOffset/static-metacall ABI。

证据：`当前类别 vtable RTTI`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-category-vtables.json`，未随源码分发）。

主线程尚需验证：两资源实际叠加出片；选中同一音频后音色2项/音效3项各值正确独立读回；分别 accept 真实值后保存、undo/redo 及重选仍正确；编辑某项不改变另一类效果。原单包 gain 曾经实际 accept/save 成功、第四/第五项被拒绝的记录，不可替代上述两栏验收。
