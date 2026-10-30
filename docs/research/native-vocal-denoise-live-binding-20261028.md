# 当前音频检查器：原生降噪开关、绑定与强度边界

日期：2026-10-28。只读静态研究；未使用computer use，未调用native方法，未修改引擎/桥/DLL/草稿/全局配置。构建与指纹沿用 [音频检查器研究](native-audio-inspector-binding-20261028.md) 及 [降噪模型研究](native-vocal-denoise-models-20261028.md)。

## 结论

当前 `DraftInspectorAudioBaseViewModel → SoundEditSettingHandler` 公开**降噪开关**。Qt方法表、属性表和发布QML三方吻合，未公开rate强度setter或滑块。不能把正式SDK允许设置rate，写成当前GUI已有可调强度控件。

特别注意：该GUI开关会调用正常wrapper重建完整降噪请求，mode固定1，rate从 `global_config.audio_denoise_rate` 读取、默认0.85。它不会承诺保留已校准的mode0/rate0.35。后续实际toggle/undo验收必须读回mode、rate、path、name、type全部字段；不能仅看bool或通过一次toggle就宣布0.35→0.2的GUI编辑成功。

## 一手文件

证据目录：`D:\JianyingHeadless\integrations\native-vocal-denoise-research-20261028`。

- `vocal-denoise-qt-metadata-focused.json`：本机Qt元数据的降噪条目及完整表项数量。
- `denoise-qml-8e6d14d.qml`：安装VECreator.dll未压缩QRC资源，实际AudioBase页。
- `denoise-qml-8e6785a.qml`：安装DLL中qCompress资源，实际SoundEditSettingSubView。
- `denoise-qml-extracted.json`：资源文件偏移、压缩方式、解压长度。
- `VECreator-0x35a4fb0.txt`、`VECreator-0x35a51a0.txt`、`VECreator-0x28cabe0.txt`、`VECreator-0x32b0c10.txt`：构造及正常绑定。
- `VECreator-0x3113d70.txt`、`VECreator-0x3111740.txt`、`VECreator-0x32abf50.txt`、`VECreator-0x32a3c60.txt`、`VECreator-0x32a96a0.txt`、`VECreator-0x32a96f0.txt`、`VECreator-0x3261920.txt`：Qt分派、开关/getter/实际请求。

现有原始完整Qt表：`JOB/research-native-audio/gui-audio-qt-metadata.json`、`current-audio-vm-qmeta.json`。解析仅读取PE静态数据，没有调用 `QMetaObject`。

## 正式Qt条目

| 类型 | primary vtable RVA | meta RVA | static metacall RVA |
| --- | --- | --- | --- |
| QQmlElement&lt;DraftInspectorAudioBaseViewModel&gt; | `0xb4b3d68` | 使用同一native meta | — |
| DraftInspectorAudioBaseViewModel | `0xbfc2300` | `0xbf667f0` | `0x3113d70` |
| SoundEditSettingHandler | `0xbf94378` | `0xbedc6d0` | `0x30b8b60` |

SoundEditSettingHandler secondary vtable：对象 `+0x38 → 0xbf946d0`、`+0x1f8 → 0xbf946f8`。它与音效页的 **AudioEffectSettingHandler** (`0xbf95348`) 不是同一类型。

AudioBaseVM local method0 `handler()` 返回 `SoundEditSettingHandler*`；metacall `0x3113da3` 调 `0xf04870`，getter返回对象 `+0x20`。

SoundEditSettingHandler 完整Qt表为70 methods/36 properties，相关条目：

| 表 | local index | 名称 | 签名/类型 |
| --- | ---: | --- | --- |
| method | 24 | denoiseSwitchChanged | signal void() |
| method | 25 | denoiseSwitchEnabledChanged | signal void() |
| method | 40 | checkReduceNoise | signal void() |
| method | 51 | onDenoiseSwitchClick | void(bool bOpenDenoise) |
| method | 59 | isDenoiseSwitchMixed | bool() |
| property | 5 | denoiseSwitch | bool，read/write，notify24 |
| property | 6 | denoiseSwitchEnabled | bool，read，notify25 |

没有denoiseRate、denoiseLevel、acceptDenoiseRate等强度条目。AudioBaseVM自身只有handler和音量增减方法，无降噪强度入口；Qt父类 `DraftInspectorAudioSubViewModel` 只有 `onReady()`。

方法local51由 `0x30b9d04` 跳表索引51到 `0x30b8e82`，读取bool参数并在 `0x30b8e8c` 调 `0x32abf50`。属性5读取分支 `0x30b9694` 调 `0x32a96a0`；属性6读取分支 `0x30b96a3` 调 `0x32a96f0`。

## 正常owner / selection绑定

绑定沿新模型路线，不能借用旧AudioSettingViewModel的偏移：

```text
DraftInspectorAudioViewModel +0x50/+0x58
  → DraftInspectorAudioModel shared_ptr
  → model +0x50 : selected ID vector
  → model +0xa8/+0xb0 : SoundSegmentActionWrapper shared_ptr

DraftInspectorAudioBaseViewModel +0x10/+0x18
  → 同一 DraftInspectorAudioModel weak_ptr
  → +0x20 : SoundEditSettingHandler*
  → Handler +0x388/+0x390 : 同一 SoundSegmentActionWrapper shared_ptr
  → wrapper +0x08 : 内联 selected ID vector
```

静态依据：

1. AudioBaseVM ctor `0x35a4fb0` 调公共子页ctor `0x3338ee0`，再在 `+0x20` 新建Handler；Handler ctor `0x32a2f70` 的parent传入此AudioBaseVM、两个bool均true。
2. 继承 `onReady()` 的static metacall `0x3111740` 调子页virtual `+0x60`；BaseVM此项为 `0x28cabe0`，再正常调virtual `+0x58 → 0x35a51a0`。
3. `0x35a51a0` 锁定model的weak_ptr，`0x37e3890` 取得 `model+0xa8/+0xb0` 的wrapper，再调Handler virtual `+0x2f8 → 0x32b0c10`。
4. `0x32b0c10` 在 `0x32b0c45 / 0x32b0c53` 存入Handler的 `+0x388/+0x390`，并正常发送UI刷新与绑定后续子模型。

后续binder应校验QObject private q_ptr、primary/secondary vtables、root/child共享同一model、控制块仍有效、model/wrapper selected IDs均仅为目标片段、Handler wrapper与model wrapper相同；实例地址不可跨会话复用。本文没有现场扫描或读回新实例，不用旧fixture地址冒充当前绑定。

## GUI开关读值与正常写入链

`denoiseSwitch` getter `0x32a96a0`：取Handler `+0x388`，调用wrapper virtual `+0x58`；当前SoundSegmentActionWrapper vtable `0xbf8cee8` 此项为 `0x3256290`。wrapper无效时返回false。

`denoiseSwitchEnabled` getter `0x32a96f0`：同一wrapper virtual `+0x68 → 0xb9b560`。这是能力/启用状态，不是rate。

正常开关local51进入 `0x32abf50`，保留现有能力/VIP/确认分支；直接路径回调 `0x32a3c60` 再调同一wrapper virtual `+0x60 → 0x3261920`，参数只有bool。不能为了跳过正常能力逻辑而直接调用wrapper地址或写内存。

`0x3261920` 在每次调用中构造新的RealtimeDenoise参数：

- `0x3261996` 写enable bool；`0x326199d..0x32619a7` 写mode1。
- `0x32619ae..0x32619dc` 读 `global_config.audio_denoise_rate`，默认double常量 `VECreator RVA0xa12a900 = 0.85`，写请求rate。
- `0x3261a2d` 指定已安装Music44k model路径，`0x3261adc` 写type2。
- `0x3261af3` 写 `denoise_v2`，`0x3261b0c` 写version1.0。
- `0x3261b64` action名 `AUDIO_REALTIME_DENOISE`，经正常wrapper提交。

因此一次GUI bool切换可能把mode0/rate0.35变成mode1/global-rate。不能为保留某个试验结果修改全局配置，也不能把它当rate setter。历史撤销应由主线程真实保存diff/undo/readback验证，而不是由静态代码推断已经成功。

## 发布QML的直接证据

AudioBase页实际以 `DraftInspectorAudioBaseViewModel{}` 创建VM，`SoundEditSettingSubView.baseViewModel: viewModel.handler()`。

SubView的 `denoiseSwitchComponent` 是一个 `PanelSettingsGroup`：`useKeyFrame:false`、`useReset:false`、`collapsed:true`、`collapsible:false`，enabled绑定 `baseViewModel.denoiseSwitchEnabled`。唯一实际动作：

```qml
onCheckBtnClicked: {
    if (baseViewModel) {
        baseViewModel.onDenoiseSwitchClick(!checked);
    }
    // 原发布物随后记录VIP功能tracking。
}
```

它没有Slider或rate子项；开关变化连接从 `baseViewModel.denoiseSwitch` 同步checked，混选状态调用 `isDenoiseSwitchMixed()`。该组件定义与Qt表的缺少rate是相互独立的证据。

## 可以据此验收什么

可以用正式agent live走当前选择绑定的bool开关，真实保存后读回，再做undo/redo与原生导出；每步检查mode/rate是否被正常UI默认重写。合法SDK的rate0.35→0.2另有真实独立session证据，但它与当前Qt面板的开关能力应分别报告。

如果目标坚持“GUI直接编辑rate”，当前这条原生面板路线尚不满足；不应伪造一个`denoiseRate`属性、绕过QMetaObject签名、改官方DLL，或把离线覆盖/重开称作当前会话同步。

## 后续实测：一次正常关开关与持久化默认值

主线程已通过正常 `onDenoiseSwitchClick(false)` 提交**一次**，没有重放。以下两份原生保存timeline已由本研究只读读回：

- `JOB/denoise-native-before-toggle-timeline.json`：同一材料ID `B0A578A1-C269-4910-A0E2-32647BE80DBC`，显式 `is_denoise:true / denoise_mode:0.0 / denoise_rate:0.35`，path为该独立草稿内模型副本。
- `JOB/denoise-native-off-observed-timeline.json`：同ID，`is_denoise / denoise_mode` 被省略，rate为0.85，path为安装Music44k model完整路径，type2。

省略字段的正式意义已从第一方parser和serializer闭合，**不是请求mode丢失，也不是启用状态不可知**：

### Persistent parser的默认值与edit DTO默认值不同

`videoeditor.dll!from_json(rapidjson::Value const&, PersistentMaterialRealtimeDenoise&)` 导出 RVA `0xce03b0`：

| 持久化字段 | 对象偏移 | 缺失时的实际默认 | 精确分支 |
| --- | ---: | --- | --- |
| is_denoise | `+0x40` | false | `0xce050a` 写byte0 |
| denoise_mode | `+0x48` | 1.0 | `0xce052d` 构造double1；缺失分支 `0xce0556` 存入 |
| denoise_rate | `+0x50` | 1.0 | 缺失分支 `0xce0597` 存同一double1 |
| sami_name | `+0x78` | denoise_v2 | `0xce066d..0xce067e` |
| sami_version | `+0x98` | 1.0（字符串） | `0xce06e0..0xce06f4` |
| sami_type | `+0xb8` | 0 | `0xce0792..0xce0794` |
| is_from_hd_sounds | `+0xbc` | false | `0xce07e5` |

这与edit请求schema中mode/rate默认0是**不同层的默认值**。不能把edit DTO默认0用于解释省略字段的持久化JSON。原生RuntimeTransfer导出 `0xe7c4f0` 在 `0xe7c5b3..0xe7c5db` 将Persistent的 `+0x40/+0x48/+0x50` 逐项交给runtime setter，所以上述默认值真正参与恢复，不只是存档注释。

### RapidJSON serializer的默认值省略

`videoeditor.dll!to_json(PersistentMaterialRealtimeDenoise const&, Allocator&, bool)` 导出 RVA `0xce0cc0`，在 `0xce0cea` 将bool参数存入sil；当bool为true时执行以下省略逻辑：

- `0xce0f41..0xce0f7b`：is_denoise等于false时，不写该key。
- `0xce0fc1 / 0xce0fc6`：将mode与 `RVA0x2f63858` 的double1.0比较；相等时构造空值，并在 `0xce1002` 跳过key写入直到 `0xce1041`。
- `0xce1046 / 0xce104b`：rate也与1.0比较。0.85不等于1，因此它继续写出。

因此这次off snapshot应解释为 `false / mode1 / rate0.85`，恰好匹配正常Qt开关的已恢复构造逻辑。它不能直接按 `node['is_denoise']` 索引，也不能按 `.get('denoise_mode',0)` 判断未改mode。验证器需按所读数据层的正式默认值归一化，同时保留原始省略字段快照作为证据。

Nlohmann版本 `to_json` 导出 `0xce1540` 不含该bool选项并写全字段；不能用一种序列化输出字段齐全，推断另一种compact输出发生数据丢失。

新增证据：研究目录 `videoeditor-0xce03b0.txt`、`videoeditor-0xce0810.txt`、`videoeditor-0xce0cc0.txt`、`videoeditor-0xce1540.txt`、`videoeditor-0xe14d50.txt`、`videoeditor-0xe7c4f0.txt`，以及 `videoeditor.dll-persistent-realtime-symbols.json` 的真实导出名。此轮没有再次提交开关、没有补写JSON、没有调用目标进程。
