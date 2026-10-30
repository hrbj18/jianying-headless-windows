# 原生 GUI 调色模型的正常延迟初始化入口

日期：2026-10-28；目标为本机剪映 11.4.7.14462。研究只用发布 DLL 的 Qt 元数据／RTTI／LLVM 静态分析，以及明确指定进程的 ReadProcessMemory。没有调用原生 getter、mutator、构造器或标签切换，没有 computer use，没有修改 engine。

## 更正：真正加载入口是 switchTab／onTabIndexChanged

主线程实际调用 `onTabClicked(int 5)` 后，15 秒仍没有创建调色模型。随后从 **同一发布 DLL 的 qCompress 资源直接静态解出官方 QML**，确认了此前仅跟踪 C++ 点击通知的局限：`onTabClicked` 负责点击通知／统计，不负责正常切换标签加载器。不能将无报错认作完成加载，也没有依据归因于窗口最小化。

官方 `PanelSettingCommonView` 的精确流程为：

```text
模型 signal switchTab(int index)
  → Connections.onSwitchTab(index)
  → titleBarTabControl.switchTab(index)
  → titleBarTabControl.currentIndex = index
  → onCurrentIndexChanged → handleCurrentIndexChanged()
  → viewModel.onTabIndexChanged(currentIndex, prevIndex)
```

鼠标 `onClicked` 是另一条独立处理，只调用 `viewModel.onTabClicked(index)`。因此优先复用 **`switchTab(int index)`**，它是原生模型提供给官方 QML 的正常程序切页 signal，Qt 本地 method index 2，activation 实现 `0x18316bc20`。若只需直接调用 native loader，Qt 元数据还有 `onTabIndexChanged(int index,int prevIndex)`（local 5）及其 **官方一参默认参数 overload `onTabIndexChanged(int index)`（local 6）**；metacall 一参分支明确传 `prevIndex=-1`，无需自行猜 prevIndex。

当前 inspector 的 virtual `+0x58` 对应 `DraftInspectorVideoViewModel` 的 `0x18358bee0`；普通分支进入 base `0x183348590`，再进入已绑定 tab control 的 `0x183581430`。后者按实际 model index 找子页 ID，进入 `0x183581200`；此实现对比 control `+0x40` 的当前 QString ID，切换注册的子页并调用其正常启用／加载函数。**这是实际子页加载链；`onTabClicked` 不能代替它。**

新证据：`官方 PanelSettingCommonView QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-qml-8dc8fdb.qml`，未随源码分发）、`静态 QML 提取清单`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-qml-extracted.json`，未随源码分发）、`索引变化分发`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/settings-index-loader-static.txt`，未随源码分发）、`base 索引入口`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/settings-common-indexchange-static.txt`，未随源码分发）、`control 索引入口`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/settings-control-indexchange-static.txt`，未随源码分发）、`control 子页加载`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/settings-control-showid-static.txt`，未随源码分发）。本研究没有执行 signal、切页函数或 setter。

## 原先找到的点击通知（不等于加载）

`DraftInspectorVideoViewModel` 继承 `PanelSettingCommonViewModel`，后者 Qt 元数据中有公开 invokable：

```text
void onTabClicked(int index)
int tabCount() const
int getInitializedTabIndex() const
QAbstractListModel* tabListModel() const
void init(QQuickItem* container, QQuickItem* view)
```

本次需要复用已初始化的当前检查器；不应手动调用 init 或构造一个缺少页面 context 的同名对象。`onTabClicked` 为 PanelSettingCommonViewModel 的本地 method index 8，Qt dispatch 目标为 `0x1833483b0`。使用宿主按 Qt 方法名＋精确 int 参数分发即可；静态 VA 只是证据，不是建议直接硬编码调用地址。

`onTabClicked(index)` 的实现先校验已有 tab control 的 QPointer，然后从其实际 tab model 按 index 取条目，再读取条目 ID，传给已绑定 `DraftInspectorVideoModel` 的点击通知分支。后续解出的官方 QML 证明它不负责切页；实际加载入口见本文开头的更正。未找到 activeAdjustControl 或 showAdjustSettings 方法名。

未找到 `activeAdjustControl`、`showAdjustSettings` 这两个字符串。搜索到的 `showAdjustPanel` 属于 `TextReadingItemInfoViewModel` 的语音参数面板，与视频调色无关，排除。

来源：`adjust-init-qt-decoded-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-init-qt-decoded-static.json`，未随源码分发）、`panel-setting-common-metacall.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/panel-setting-common-metacall.txt`，未随源码分发）、`settings-tab-click-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/settings-tab-click-static.txt`，未随源码分发）。

## 当前进程的真实调色 index：5

本次 Reader-only 扫描条件：

```text
PID: 26164
birth: 134375592292885847
VECreator.dll base: 0x7ffbaa840000
VECreator SHA256:
769c33961ef9d7e471e583f03c975be975b0c35e849a767690d09e9f2fc45111
```

RTTI 的完整继承链确认 QQmlElement<DraftInspectorVideoViewModel> 的 QObject primary 与 PanelSettingCommonViewModel 都处于 offset 0。

```text
QQmlElement<DraftInspectorVideoViewModel>
  primary object: 0x5f88eda0
  vtable RVA: 0xb4b2d58
  primary+0x30: tab-control QPointer header 0x45098a50
  primary+0x38: PanelSettingTabViewControl 0x9e03dc90

PanelSettingTabViewControl
  vtable RVA: 0xbfbe988
  +0x10: model QPointer header 0x45098a10
  +0x18: tab model 0x7478c3d0

tab model
  +0x28/+0x30/+0x38: std::vector<shared_ptr<TabItem>>
  item size: 16 bytes
  item+0x58: QString ID
```

从这一真实 vector 读得：

| 当前索引 | 原生 tab ID |
|---|---|
| 0 | ai_generate |
| 1 | screen |
| 2 | audio |
| 3 | speed |
| 4 | animate |
| **5** | **adjust** |
| 6 | AI工具 |

因此，**只在上述进程代际、这一活跃检查器与现有 tab 列表仍成立时**，`switchTab(int 5)` 才对应这一真实调色标签的正常程序切换入口；原先 `onTabClicked(int 5)` 只是该标签点击通知。不能把 5 写成所有工程／模式通用常量；标签集合可随模型／当前选择变化。

所有运行时地址均来自 ReadProcessMemory 与静态布局的联合验证；没有用历史地址假装当前对象。扫描还找到了当前 video、video_basic、manager 作为阳性对照。`AdjustSettingHandleViewModel`／HSL data 在扫描时仍未活跃，符合调色子页尚未创建的状态。

来源：`hsl-rtti-vtables-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-rtti-vtables-static.json`，未随源码分发）、`hsl-active-readonly-scan.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-active-readonly-scan.json`，未随源码分发）、`adjust-tab-binding-readonly.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-tab-binding-readonly.json`，未随源码分发）、`settings-tab-list-getters-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/settings-tab-list-getters-static.txt`，未随源码分发）、`settings-tab-model-index-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/settings-tab-model-index-static.txt`，未随源码分发）。

## 本轮只读确认：调色页已正常创建并绑定唯一片段

主线程后续执行正常切页后，本子任务重新使用 `ReadProcessMemory` 观察到 control 当前子页 ID 为 `video_adjust`，并发现：

```text
QQmlElement<VideoAdjustSettingViewModel>: 0x744cf080 (VT RVA 0xb4b0500)
AdjustSettingHandleViewModel:            0xba3a4de0 (VT RVA 0xbfef5b0)
AdjustHSLSettingData:                    0xdd5fba00
VideoSettingsData:                       0xc06b65d0
```

同一 PID／birth 下，outer `+0x40` 确实指向该 handler，outer `+0x30` 指向 settings；settings `+8` 的真实 selected ID vector 仅含 `7D0C2327-E45F-420C-84FB-720EB221A592`。handler `+0x1b8` 的 SegmentHolder vector 也恰有一项（0x148 字节）。`isMultiSelect=false`，colorCurvesData 为 4 项、hslCurvesData 为 6 项。`isAdjustMergeResourceLoaded` 此次读取为 false；不能由“模型已创建”推断调色资源已加载或实际修改效果已通过。

证据：`只读绑定核验`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-live-binding-readonly.json`，未随源码分发）、`只读设置模型核验脚本`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/read_adjust_binding_only.py`，未随源码分发）、`更新后的只读扫描`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-active-readonly-scan.json`，未随源码分发）。本研究没有执行切页或修改。运行时地址只对这一对象代际成立。

同时发现仅凭 heap／stack 中出现 vtable 数值会命中副本：本次完整扫描的 `0x33cebb8` 也包含 inspector vtable，但其 `+0x38` 无合法 tab control。必须继续用 QPointer、控制对象类型、模型列表与 settings 绑定验证，不能选第一个 vtable 命中。

## context 绑定的静态实现

页面正常打开后，应再次只读查找 `VideoAdjustSettingViewModel` 与 `AdjustSettingHandleViewModel`；不能把发出标签切换调用当成已完成子页加载。前者有真实 Qt property：

```text
AdjustSettingHandleViewModel* handleViewModel
```

其 getter 静态读取 primary `+0x40`。VideoAdjustSettingViewModel 的 VideoSubSettingViewModel 子对象位于 `+0x10`；原生更新函数将 settings shared_ptr 放在 primary `+0x30/+0x38`，并从 settings 对象 `+0x8` 的 selected segment ID vector 传给 handle 的 updateSegmentData。

handler 再用当前 IQueryUtils.get_segment 获取真实 Segment，并在 `+0x1b8` 缓存 SegmentHolder vector（每项 0x148）。此链验证唯一 ID 与当前目标一致后，才有依据调用普通 HSL／曲线动作。

HSL 可复用的精确签名：

```text
acceptHslColorType(int type, QString color)
acceptHslHue(int value, bool record, bool shift)
acceptHslSaturation(int value, bool record, bool shift)
acceptHslLightness(int value, bool record, bool shift)
setHslEnabled(bool enable)
```

这些动作走原生组合编辑 `lyra::Server::draftCombo`；这提供撤销／保存的实现路径依据。仍需主线程在其自有测试稿中执行并验收 undo、redo、保存回读和再出片。本子任务没有执行这些步骤。

相关早期证据：`adjust-update-binding-callers.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-update-binding-callers.txt`，未随源码分发）、`adjust-outer-qt-decoded-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-outer-qt-decoded-static.json`，未随源码分发）、`hsl-qt-handlers-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-qt-handlers-static.json`，未随源码分发）。

`ViewVisiableChanged(bool)` 仅通知可见性，不能取代这个正常 tab loader 入口；也不应将 VideoAdjustSettingViewModel 的布局套到 VideoBasicSettingViewModel。后者此前候选检查未通过，不具有可复用绑定证据。

## 复用的只读脚本

- `hsl_readonly_active_scan.py`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl_readonly_active_scan.py`，未随源码分发）：精确 vtable 扫描与阳性对照；目前指定 PID 26164。
- `adjust_tab_binding_readonly.py`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust_tab_binding_readonly.py`，未随源码分发）：核对相同 birth、vtable，逐项读取标签 ID。

这些是独立研究探针，不是正式长期 ABI 门禁。若进程代际／DLL／对象或列表发生变化，必须重新发现与验证，不得复用本文的运行时地址。

## HSL 的 record／shift：官方当前控件与原生 wrapper

直接解出的官方 HSL QML（`adjust-qml-8e63365.qml`）用 `ParamSettingSliderViewEx`，分别绑定 `hslData.hslHue`、`hslSaturation`、`hslLightness`。此版本当前控件没有直接调用三个 `acceptHsl...` wrapper，而是统一走 `ParamSettingSliderViewEx` 的 handler：

```text
onValueChanged(value,isSlider,withShift,actionType)
  → onValueChanged(commonSliderInfo,value,withShift,false,actionType)
onAccepted(value,isSlider,withShift,actionType)
  → onValueChanged(commonSliderInfo,value,withShift,true,actionType)
```

因此，`record=false` 对应交互中更新，`record=true` 对应确认提交。单次离散数值编辑应对齐一次 `onAccepted` 的提交行为；是否形成完整 undo／redo 仍应由主线程的自有测试稿实际验证。本轮没有执行编辑，也没有以 QML 调用关系冒充 undo 已验收。

三个 wrapper 的静态实现分别为 Hue `0x183793a70`、Saturation `0x183793c70`、Lightness `0x183793b70`。它们将 int 值与 `record` 布尔传入共同 HSL 编辑 helper `0x1837abe20`，对应属性代码 `0x6f/0x70/0x71`。**三个 wrapper 均未读取第四实参 `shift`（Windows x64 的 r9b）**；Hue 先覆盖 r9 为值指针，Saturation／Lightness 先清空 r9。因此在这一版本的这三个入口中，`shift` 不是影响写入的有效 flag，设为 false 不会遗漏 wrapper 中的特殊分支。

当前通用 slider 接口仍把 `withShift` 往下传给其他类型的编辑分支，不能把 HSL wrapper 的无操作结论推广到所有滑杆。本轮没有证明 Shift 键在通用控件底层的完整交互语义，故不推断为“全关键帧平移”等功能。对于本任务 HSL 的直接离散提交，明确可用的形状为 `acceptHslHue/Saturation/Lightness(int value,bool record,bool shift)`；`record=true,shift=false` 对齐确认提交语义。

颜色类型的官方列表也明确：0=吸管，1=红，2=橙，3=黄，4=绿，5=青，6=蓝，7=紫，8=洋红；`acceptHslColorType(int,QString)` 使用列表中的 `colorType` 与 `colorArgb`。例如红色为 `(1,"#FFE64444")`，不是 legacy renderer 内部的 zero-based 索引。

证据：`官方通用 slider wrapper QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-qml-8e02822.qml`，未随源码分发）、`官方 HSL 控件 QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-qml-8e63365.qml`，未随源码分发）、`HSL hue／saturation wrapper 反汇编`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-load-hsl-edit-static.txt`，未随源码分发）、`lightness wrapper`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-hsl-lightness-wrapper-static.txt`，未随源码分发）、`通用 slider 实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-generic-slider-edit-static.txt`，未随源码分发）。

## merge 资源正常加载：真实状态与可调用入口

当前被动读取：handler `0xba3a4de0` 的 `+0x250` 是真实 `SmartColorAdjustEffectLoader` 对象 `0x32984610`；handler `+0x730` 的 collectionPath 字符串为空，初始化 guard `+0x190=true`，`isAdjustMergeResourceLoaded=false`。因此本机文件夹存在，尚不等于该模型已注册／加载这一集合。

原生 `AdjustSettingHandleViewModel::initAdjustCollectionData`（`0x1837997f0`）会从 effect loader 取得集合数据，复制到 handler `+0x6c0`；它检查 `+0x740` 的 path 长度非零，再通过 QDir 枚举目录，文件数大于 0 才设置 `+0x138` 的 loaded 状态并发信号。不得直接伪造 loaded=true。

官方 HSL、曲线、LUT 页的 `LoadTipPanel.onSignalRetry` 都调用：

```text
loadSmartColorPanelData(int index=0)  // Qt local method 61
```

这是有官方调用证据的精确 Qt API（不是猜方法名），dispatch 到 `0x18379da40`。当前实现未读取 index，统一调用 `0x18379d950`，向 SmartColorAdjustEffectLoader 请求 panel ID `adjust_collection`，其内部异步入口为 `0x18650eed0`，额外 bool 为 false。**这一 API 不接受本地目录，尚未证明请求不会下载；不能标成“纯离线导入 merge 包”。**

SmartColorAdjustEffectLoader 的 Qt 元数据只有三个 signal：`needLoadData(std::string)`、`effectDataloadResultSignal(bool,std::string,LoadExtraInfo)`、`effectDataloadProgressSignal(double,std::string)`。没有发现带 `QString path` 的本地目录加载 invokable。不要自行伪造成功 signal 或调用未恢复 ABI 的私有构造器。

本机确有正式 `material_panel::IDefaultAdjustResource` 实现 `DefaultAdjustBundleResource`（VT RVA `0xb4897a0`）。静态实现恢复出两个原生集合：旧列表（`0x182e6a9a0`）的 basename 为 `merge_all_adjust_color`；新列表（`0x182e6a110`）为 `FC`。两者由原生条件函数选择，不能因都称调色资源就互换。该 provider 是 C++ 接口而非 QObject；本轮没有恢复一个可通过现有 Qt typed 桥把本地目录注册为 collection 的公开方法。主线程已验证旧 merge_all_adjust_color 在离线草稿原生渲染有效，与 GUI loader 是否已注册是两个独立事实。

证据：`只读资源状态`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-resource-state-readonly.json`，未随源码分发）、`状态生成实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-loaded-state-write-static.txt`，未随源码分发）、`官方重试方法`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-load-api-static.txt`，未随源码分发）、`集合请求实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-loader-request-static.txt`，未随源码分发）、`loader Qt metadata`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-effect-loader-qt-decoded-static.json`，未随源码分发）、`原生本地 provider`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-local-default-provider-static.txt`，未随源码分发）、`provider 两个默认列表`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-local-provider-lists-static.txt`，未随源码分发）。
