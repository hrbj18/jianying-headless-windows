# 剪映 11.4.7 原生音效普通参数滑块与编辑动作链

日期：2026-10-28。范围：静态读取安装包、Qt 元数据、内嵌 QML 编译单元和有界反汇编；未操作界面、未调用 getter/setter 或 edit 服务、未附加进程，未修改程序或引擎。本文不把静态可达性当作 GUI 编辑验收。

## 结论

**普通音效参数可创建五个滑块，但当前构建的刷新通道只能正确区分前三个。** 该构建从 `extra.json.setting.audio_effect_parameters_change` 解析整个数组，逐项创建 `SoundChangeParamData`，加入 `SoundEditSettingHandler.paramDataList`。官方 QML 的 `Repeater` 直接使用该列表。主线程随后真实读回五个有效对象，但第四、第五项 value 错误回读成第一项；继续静态追踪定位到按列表 index 的三槽 fallback。**创建五项不等于五项正确独立 GUI 编辑已完成。** 详细反例见文末增补。

**真正编辑入口是每个参数对象的 `acceptVoiceChangeAdjustParams(double, bool)`，不是写其 `value` 属性。** 正常分支进入官方 `AudioService/audioChangeVoiceAdjust` 动作，使用 `AUDIO_CHANGE_VOICE_ADJUST_ACTION` 与组合动作提交。静态代码证明其走官方命令通道；撤销、保存和实际音频效果须各自实测。

**关键帧仍只有三个属性槽。** 普通五滑块可建模不意味着五项独立关键帧成立。当前 DSP 的多个 port 共用 parameterIndex，会映射到相同关键帧属性。

## 目标身份与方法

目标：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462\VECreator.dll`，275,234,072 字节，SHA-256 `769c33961ef9d7e471e583f03c975be975b0c35e849a767690d09e9f2fc45111`。本文地址均为该文件的 RVA，除注明 VA。磁盘首选 image base 为 `0x180000000`，活跃进程必须按实际模块基址重定位。

REA `open_binary` 验证目标身份，run `cca787b8-7a44-4319-8884-d8bf68456b7c`；未启动 Ghidra 全程序分析，REA 无函数分析 Evidence 记录。详细证据来自对同一 SHA 的 PE 原始字节读取及本机 LLVM 有界反汇编，保留在任务证据目录，不冒充 REA 反编译。REA 会话已关闭。

证据目录：`D:\JianyingHeadless\work\native-av-upgrade-20261028-004610-32bec1\research-native-audio`。

## 资源到 QObject 列表

1. `0x32aa290` 读取资源的 `extra.json`，进入 `setting` → `audio_effect_parameters_change`，遍历 JSON 数组。每项读取 `parameterIndex`、`portIndex`、`minValue`、`maxValue`、`sliderName`、`defaultValue`，生成原生参数对象 vector。
2. `0x32b0ff0` 调用上述解析函数，从 vector begin 迭代到 end。对每个非空元素，若现有列表长度不足，调用工厂 `0x32a6230`；并将资源参数复制到对应 QObject。循环终止比较是 `0x32b164b: cmp r14, [rsp+0x50]`，不是与常数 3 比较。
3. 工厂 `0x32a6230` 分配大小 `0x100` 的对象，调用构造函数 `0x37e3c00`，连接通知信号，追加到 handler 的 `QList`（handler `+0x2e0`），并通知列表变化。
4. 已有音效刷新路径 `0x32b0030` 同样按返回参数数量遍历并按需扩展列表，按真实数量而非三项循环（`0x32b0819` 比较计数后跳回）。它从已有音效读取当前值，而不是仅重置资源默认值。

证据：`解析与 accept`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-extra-and-accept.txt`，未随源码分发）、`列表工厂`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-param-factory.txt`，未随源码分发）、`完整列表循环`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-param-list-command.txt`，未随源码分发）。

现有项目资源生成器 [native_dsp_graph.py](../../engine/native_dsp_graph.py) 采用这套 extra 格式；以下是一个条目的最小形状，不调用引擎：

```json
{
  "setting": {
    "audio_effect_parameters_change": [
      {
        "parameterIndex": 4,
        "portIndex": 0,
        "sliderName": "EQ增益（-20至20dB）",
        "minValue": 0,
        "maxValue": 1,
        "defaultValue": 0.5
      }
    ]
  }
}
```

这是 GUI 描述与 DSP parameter port 的绑定，并非仅展示标签。数组位置是 GUI `index/paramIndex`；`parameterIndex` 和 `portIndex` 是资源内 DSP 绑定，三者不可混用。

## 官方 QML 的列表和数值换算

未发现明文 QML；当前 PE 内有 Qt 6.2.2 `qv4cdata` 单元。按 Qt 官方 [编译数据结构](https://raw.githubusercontent.com/qt/qtdeclarative/v6.2.2/src/qml/common/qv4compileddata_p.h) 和 [Moth 指令定义](https://raw.githubusercontent.com/qt/qtdeclarative/v6.2.2/src/qml/compiler/qv4instr_moth_p.h) 解读字符串、函数、lookup 表，保留原始字节。这里只恢复已匹配字段，不推测原 QML 文件名。

| PE 文件偏移 / 函数 | 实际 model lookup |
| --- | --- |
| `0xb536e00` / function 268 | `baseViewModel.paramDataList`，lookup 813→814 |
| `0xb551ac0` / function 55 | `root.viewModel ? root.viewModel.paramDataList : []` |
| `0xb568600` / function 43、79 | `baseViewModel.paramDataList`，后者带空值保护 |
| `0xb578da0` / function 56 | `baseViewModel ? baseViewModel.paramDataList : []` |

这些组件包含 `Repeater`、`modelData`、`ParamSettingSliderView` / `VESpinBoxSlider`、`acceptVoiceChangeAdjustParams`。所列 model 绑定不包含 slice 或常数三项限制。

`0xb536e00` function 284 的 `onAccepted` 绑定创建 function 285；后者读取 `dataRange`、`modelData.minValue`，调用 `modelData.acceptVoiceChangeAdjustParams`，其数值换算为：

```text
native_value = (ui_percent / 100) * (maxValue - minValue) + minValue
```

因此将 `50` 当 native value 传入会被当前 0..1 资源范围拒绝。GUI 标签可以写 dB/Hz，但通道实际值仍是资源定义的归一化值；项目物理值 ↔ 归一化换算已有 `native_dsp_graph.normalize()`。

证据：`QML 原始函数/lookup 表`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-qml-decoded.json`，未随源码分发）、`四单元字符串`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-qml-units.json`，未随源码分发）。

## 当前构建 Qt 类型和内存布局

以下来自当前 PE 的 Qt 元数据、构造函数和 MSVC RTTI CompleteObjectLocator，未扫描活跃进程。

| 类 | primary vtable RVA | secondary 校验 | Qt meta VA / static metacall RVA |
| --- | --- | --- | --- |
| `SoundEditSettingHandler` | `0xbf94378` | 对象 `+0x38` → `0xbf946d0`；`+0x1f8` → `0xbf946f8` | `0x18bedc6d0` / `0x30b8b60` |
| `SoundChangeParamData` | `0xbff3ac0` | 当前 RTTI 仅找到 offset=0 的 vtable | `0x18bf6fa30` / `0x3117ad0` |
| `SoundEditSettingSubViewModel` | `0xbf942e8` | 当前 RTTI 仅找到 offset=0 的 vtable | `0x18bedb340` / `0x30b8920` |
| `VideoSoundgmentActionWrapper` | `0xbfa8008` | `ISoundAction` 当前具体 wrapper | 不作为 QObject 识别 |

`SoundEditSettingSubViewModel.getSoundEditSettingHandler()` 是 Qt local method 0。其当前实现仅返回 subVM `+0x60` 指针；该字段可被既有只读 Reader 校验，不必为查找对象执行 getter。

`SoundEditSettingHandler` 当前关键布局：

| 偏移 | 内容 |
| --- | --- |
| `+0x2e0` / `+0x2e8` / `+0x2f0` | Qt `QList` 的 data header / 元素指针 / 元素数量；元素为 `SoundChangeParamData*` |
| `+0x388` / `+0x390` | 当前 `ISoundAction` wrapper 的 shared_ptr 对象 / 控制块 |

Qt local property 14 为 `paramDataList: QList<SoundChangeParamData*>`，15 为 `soundChangeSize:int`。不要把 property ordinal 当结构偏移；不要把 `soundChangeSize` 与 QList 的存储计数混为同一地址。

每项 `SoundChangeParamData`：

| 偏移 | 字段 |
| --- | --- |
| `+0x10` / `+0x18` / `+0x20` / `+0x28` | double `value` / `defaultValue` / `minValue` / `maxValue` |
| `+0x30` / `+0x48` | QString `sliderName` / `sliderNameStarling` |
| `+0x60` / `+0x64` / `+0x68` | int `parameterIndex` / `portIndex` / 列表 `index` |
| `+0x6c` / `+0x6d` | bool `hide` / `isMix` |
| `+0x70` / `+0x88` / `+0xa0` / `+0xb8` | QString `materialID` / `categoryID` / `propertyType` / `constantMaterialId` |
| `+0xd0` | owner `SoundEditSettingHandler*` |

完整证据：`当前 Qt metadata`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-qt-metadata.json`，未随源码分发）、`当前 RTTI/vtable`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-vtables.json`，未随源码分发）、`SubVM metadata`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-submodels-metadata.json`，未随源码分发）、`只读 getter 结构`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-submodel-handler-getter.txt`，未随源码分发）。

## 普通参数编辑与动作提交

`SoundChangeParamData` 的 Qt local 方法：

| local index | 方法 | 实现 RVA |
| --- | --- | --- |
| 17 | `acceptVoiceChangeAdjustParams(double value, bool isSlider)` | `0x37e4320` |
| 18 | `acceptVoiceChangeAdjustParams(double value)`，官方默认 `isSlider=false` | 同上 |
| 19 | `resetToDefault()` | `0x37e4fe0` |

这些是所属类的 **local** index，不能直接当 `QMetaObject` 的包含基类全局 method index。若走官方 `QMetaObject`，应按当前 meta 的 methodOffset 解析；若走已有静态 metacall 桥，则严格按已验证桥 ABI 使用 local index。

编辑流程：

```text
SoundChangeParamData::acceptVoiceChangeAdjustParams (0x37e4320)
  校验 owner、当前 wrapper、hide=false、min <= value <= max
  更新 VM value 并发通知；再做当前目标/资源检查
  → 正常分支 0x37e5cc0
  → 当前 ISoundAction wrapper vtable +0xd8
  → VideoSoundgmentActionWrapper 0x34210b0
  → 0x301da40
      AudioService / audioChangeVoiceAdjust
      AUDIO_CHANGE_VOICE_ADJUST_ACTION
      AUDIO_CHANGE_VOICE_ADJUST_COMBO_ACTION
  → 0x3316d60(actionName, actionVector, true)
```

`0x37e5cc0` 将当前项的列表 `index`、DSP `parameterIndex`、`portIndex`、double 用户值写入原生参数对象，`is_keyframe=false`；wrapper 为当前选中目标补齐上下文。`0x301da40` 逐目标构建动作，完整复制这些参数和 resource/segment 关联，再提交组合动作。它不是直接改 JSON 草稿。

必须在动作后回读草稿/当前 VM：accept 会先更新 VM 值，后续目标检查或确认路径仍可能失败，故单看控件值不能证明动作成功。另一个分支可能进入官方确认/回调逻辑，不能为通过实验而跳过。`resetToDefault()` 读取 `defaultValue`，在有差异或 mixed 状态下走同一个 accept(value,false)。

更正易混点：`0x37e6370` 包含 `voice_change_`、`click`、`Voice_changer` 等埋点构建，是统计路径，不是编辑提交。DLL 的保护层将部分 IAT 项映射为 `gpShell`；本报告不猜测这些导入项身份。

证据：`accept 与范围检查`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-extra-and-accept.txt`，未随源码分发）、`参数对象及 reset`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-adjust-request-reset.txt`，未随源码分发）、`wrapper`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-owner-action.txt`，未随源码分发）、`服务名与组合动作`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-action-to-service.txt`，未随源码分发）、`最终提交路径`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-keyframe-action-submission.txt`，未随源码分发）。

## 三个关键帧槽的实际边界

`0x32aaef0` 根据 `parameterIndex` 返回 propertyType：

| parameterIndex | propertyType |
| --- | --- |
| 0 | `KFTypeEffectAdjustParam1` |
| 1 | `KFTypeEffectAdjustParam2` |
| 2 | `KFTypeEffectAdjustParam3` |
| 其他 | `KFTypeEffectAdjustParam1` |

该映射不包括 portIndex。当前五项参数的 indices 为 4 / 2 / 2 / 1 / 2，跨 port 的不同控制会碰到相同关键帧属性。**本次只能据此推进五个普通固定参数，不能承诺五项独立自动化。** 证据：`关键帧映射`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-keyframe-action-submission.txt`，未随源码分发）。

## 主线程后续实验边界

建议使用现有专用 8 秒 QA 草稿，按每次读取到的 draft/session/segmentId 选中音频；重新解析 Handler/SubVM，校验 primary、secondary、owner、wrapper 和五个不隐藏参数的资源 ID、name、index、port、range。先做一个原值不同的单项 `acceptVoiceChangeAdjustParams(native_value,false)`，回读原生保存参数，再使用既有 live undo/redo/save 和保存后原生导出验证。普通第五项应单独改一次，以排除界面只载入前三项。此列表是待实验条件，本研究未执行。

仍待实测：该效果的安全/确认分支是否触发；前三项 GUI 值的保存、撤销和实际导出；第四、第五项的正确独立读回与编辑。单项 SDK 原生出片由主线程另有实验记录，不能替代 GUI live 验收。

## 增补：真实五项读回反例与三槽刷新缺陷

主线程在专用 `AV_StudioQA_20261028` 草稿正常选中音频后，仅执行读取，得到五个未隐藏的参数对象；owner 均为当前 handler `0x99a472b0`，vtable、index、parameterIndex、portIndex、name、min/max 均吻合。所有 `materialID` 均为空，故不能把该字段当必有的资源 ID 来匹配目标；目标资源还需从当前选中片段及原生保存节点核对。

| 列表 index | DSP parameterIndex / portIndex | GUI value | 原生保存值 / 结论 |
| --- | --- | --- | --- |
| 0 | 4 / 0，EQ gain | 0.45 | 0.45，吻合 |
| 1 | 2 / 0，EQ frequency | 0.3920304196852271 | 吻合 |
| 2 | 2 / 1，threshold | 0.5518367346938776 | 吻合 |
| 3 | 1 / 1，ratio | **0.45** | **0.3047797829639662**，不吻合 |
| 4 | 2 / 2，limiter ceiling | **0.45** | **0.83690739**，不吻合 |

这些数值来自主线程实际结果：`native-studio-slider-readback.json`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/native-studio-slider-readback.json`，未随源码分发）。原生保存节点的 ratio/ceiling 对照值由主线程报告，本子研究没有运行 setter。不能因 GUI 这两个值错误就改写源草稿或重设默认值来掩盖问题。

### 问题位于刷新，而非 Qt property getter

`SoundChangeParamData` 的 Qt property `value` 在 `0x3117dfc` 仅加载 `[item+0x10]` 并复制到返回位置，没有实时去读关键帧/效果。因此原始内存/Qt property 均读到 0.45，是刷新先写入了错误值。

刷新路径已闭环：

```text
Handler refresh 0x32b0030
  → wrapper vtable +0xf0 = 0x341cb10
  → 0x2ffa650
      逐 audio_adjust_params 数组项复制 descriptor
      将列表序号 0..N-1 交给 0x3024a40 获取当前值
      用当前值覆盖复制 descriptor.value
  → 0x3024a40
      把该列表序号交给 0x2ffb2f0 转成参数属性槽
      对当前 selected segment 的该属性获取数值
  → 0x37e5b70
      写入 SoundChangeParamData.value (+0x10)
      通知 GUI
```

`0x2ffa650` 在 `0x2ffa92f` 传入 `[rbp+0x7f]` 的列表序号，`0x2ffa9d4` 每轮递增；不是 `parameterIndex` 或 `portIndex`。`0x2ffb2f0` 的确切分派为：

```text
list index 0 → imported property slot 1
list index 1 → imported property slot 2
list index 2 → imported property slot 3
all other  → imported property slot 1
```

这些导入全局的精确值未在本研究运行中读取，因此这里不为其擅自命名；同三路结构与原生效果参数属性一致。该分派与实测第四、第五项等于第一项完全吻合，已足以解释错误显示，不需要假设 JSON 数组丢失。

证据：`wrapper 与刷新入口`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-source-value-paths.txt`，未随源码分发）、`逐列表序号求值`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-selected-effect-values.txt`，未随源码分发）、`三槽分派`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-value-three-slot-dispatch.txt`，未随源码分发）、`值写入对象`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-value-refresh-candidates.txt`，未随源码分发）、`Qt 原始属性 getter`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-metacall-extra-xrefs.txt`，未随源码分发）。

### 与 normal accept 的关系及当前完成边界

normal accept 仍分别写入 `paramIndex=list index`、`parameterIndex=DSP parameter`、`portIndex=DSP port` 与用户值（见前文 `0x37e5cc0`）。但 wrapper `0x34210b0` 同时将列表 index 传给 `0x2ffb3b0`，该函数也只区分 0/1/2，其他回落槽 1，并将返回的属性类型放入请求公共字段 `+0x68`。随后 `0x301da40` 执行目标/关键帧检查，再构造 `audioChangeVoiceAdjust` 请求。因此不能仅根据 DTO 带有完整索引就宣称第 4/5 项 live 写入一定独立无误；必须验证写入是否命中本项、其它四项是否保持、undo 是否恢复正确值，且重新选择后 GUI 显示仍有已确认缺陷。

此处应区分两套三槽映射：GUI 列表刷新与 wrapper 使用**列表 index**；`propertyType` 字符串函数 `0x32aaef0` 使用 **parameterIndex**。五参数跨 DSP port 时，这两套路径均可能发生槽碰撞，不能将其中一套误认为正确的通用五参数绑定。

后续方案必须保留诚实边界：前三项先单独做原生 live 编辑、undo/save/出片；第 4/5 项在可靠读回完成前拒绝普通 live 编辑。若采用把五项拆成多个不超过三项的原生效果资源，需另查当前服务能否在同一音频上独立叠加这些资源并在 GUI 切换目标；本次未验证，不能直接当成已可用修复。直接写 VM `value` 仅改变显示，不能修复官方刷新与命令属性绑定。

证据：`wrapper 对 index 的三槽转换`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-value-property-dispatch.txt`，未随源码分发）、`正常 accept 参数构造`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-adjust-request-reset.txt`，未随源码分发）、`真实动作构建`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-action-to-service.txt`，未随源码分发）。

### 可继续验证的资源拆分方向

本机检出的 [pyJianYingDraft 原始实现](https://github.com/GuanYixuan/pyJianYingDraft/blob/1e228479dda361e312e85f6037002346cf6dca9a/pyJianYingDraft/audio_segment.py) 在 `AudioSegment.add_effect()` 允许同片段多个不同 category 的效果，只拒绝同 category 重复；其 `AudioEffect` 区分 `tone`、`sound_effect`、`speech_to_song`。这是一条实现线索，不是剪映 11.4.7 原生叠加验收。

当前 GUI `0x3253b90` 的选择函数，在 category 字符串为空时直接取第一条效果；非空时遍历效果，依当前模式执行匹配。由此可考虑把 EQ 两项和 dynamics 三项分到两个现有不同 category 的本地原生资源，保持每资源不超过三项，然后验证两资源在同一音频上叠加、GUI 切换、实际出片、undo/save。这仍需原生实验，不能通过空 category 或沿用第一条效果冒充定位。不得使用 `speech_to_song` 的名称来暗示本地 DSP 已获得该类的算法能力。

静态证据：`当前效果/category selector`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/research-native-audio/gui-audio-effect-category-selector.txt`，未随源码分发）。
