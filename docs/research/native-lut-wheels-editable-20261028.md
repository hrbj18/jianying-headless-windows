# 剪映 11.4.7：可编辑 LUT 与 primary/log 色轮的只读定位

日期：2026-10-28。目标安装为 `D:/刘宇钊/软件/剪映/JianyingPro/11.4.7.14462`。本轮只读发布 DLL、JS、QML 与该任务已经使用的本地效果包，没有调用剪映运行时、编辑器 setter、导入器或导出器，没有 computer use，没有修改 engine、DLL 或已有草稿。

## 结论与验证边界

色轮有明确的原生持久化材料、Qt 编辑入口、归一化范围与本地 shader 包；自定义 LUT 有明确的 `effects/type:lut` 材料与复合路径读取逻辑。二者都可以继续走现有剪映链，研究没有支持“必须烘焙成新视频”的结论。但是，本轮**没有实际验证 LUT 或色轮出片、原生 undo/redo 和重新打开后的可编辑性**，下面的最小实验只能作为主线程下一轮条件，不能列入已验收能力。

主线程已有的 HSL 成功不应外推成色轮/LUT 成功：当前已有 HSL 原生修改、undo/redo、save、重新导出验收；旧独立 HSL 包即使日志生成正确标量也曾原生编码成功但画面无效。必须继续以实际像素变化验收新模块。此前真实 HSL 对照见 `HSL/LUT 路由研究`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/docs/research/native-color-hsl-lut-routing-20261028.md`，未随源码分发）。

本轮主要证据目录：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence`。本机第一方发布物是协议证据，不是可自由再分发的开源资源；没有给其 shader/LUT 文件附加开源许可或上传到第三方。

## 1. 本机精确材料类型，勿复制旧 Web 数字

当前 `videoeditor.dll` 原生 `MaterialPrimaryColorWheels` 实构造器 `0x18086f870` 在 `0x18086f979` 写公共材料字段 `+0x38 = 0x4c`，即 **76**；`MaterialLogColorWheels` 实构造器 `0x18080b3e0` 在 `0x18080b4e9` 写同字段 `0x4d`，即 **77**。这是静态读指令，没有执行构造器。

旧 `ai-creation~10.f1164957.js` 将对应 MetaType 写为 63/64；它不是本机当前 DLL 的同一枚举版本。实验优先使用明确的持久化 type 字符串；若经 typed SDK 创建材料，要使用本机证据支持的类型，不能照抄旧 Web 编号。

证据：`Primary 实构造器`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-primary-real-ctor-static.txt`，未随源码分发）、`Log 实构造器`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-log-real-ctor-static.txt`，未随源码分发）、`旧 Web 枚举与类片段`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-js-schema-snippets.json`，未随源码分发）。

## 2. Primary 色轮的持久化 schema

`PersistentMaterialPrimaryColorWheels::to_json` 位于 `videoeditor.dll 0x180cdf460`，对应 nlohmann 读取器位于 `0x180cded00`。材料放在权威主时间线的 `materials.primary_color_wheels`，片段 `extra_material_refs` 引用其 ID。

```json
{
  "id": "新的材料UUID",
  "type": "primary_color_wheels",
  "panel": "",
  "resource_id": "",
  "path": "完整原生调色资源包路径",
  "lift":   {"red": 0.0, "green": 0.0, "blue": 0.0, "luma": 0.0, "saturation": 0.0},
  "gamma":  {"red": 0.0, "green": 0.0, "blue": 0.0, "luma": 0.0, "saturation": 0.0},
  "gain":   {"red": 0.0, "green": 0.0, "blue": 0.0, "luma": 0.0, "saturation": 0.0},
  "offset": {"red": 0.0, "green": 0.0, "blue": 0.0, "luma": 0.0, "saturation": 0.0},
  "intensity": 1.0,
  "lumi_hub_path": "",
  "source_platform": 0
}
```

四个组均为 `PersistentColorWheelsInfo`；其 `from_json 0x180bf4930` / `to_json 0x180bf4c50` 明确读取/写入 `red,green,blue,luma,saturation`，值为 double。组的中性值是 **0**；`intensity` 的原生构造默认是 **1**。不能将 shader 内部 gamma/gain 的中性值 1 直接填进这个归一化材料结构。

该版本上述持久化序列化器未列出 `version`、`constant_material_id` 或 `visible`；本轮不把它们当作必需字段。`panel` 的默认空串和本机资源目录名 `v0/v1` 是不同层；仅凭资源目录名不能断言应填 `panel:"v1"`。

## 3. Log 色轮的持久化 schema

`PersistentMaterialLogColorWheels::to_json` 位于 `0x180ccaa50`，对应 nlohmann 读取器 `0x180cca2f0`。材料桶为 `materials.log_color_wheels`，type 明确为 **`log_color_wheels`**，不是 `log_color_wheel`。

共同字段与 Primary 相同；将四组改成：

```json
{
  "shadow":    {"red": 0.0, "green": 0.0, "blue": 0.0, "luma": 0.0, "saturation": 0.0},
  "midtone":   {"red": 0.0, "green": 0.0, "blue": 0.0, "luma": 0.0, "saturation": 0.0},
  "highlight": {"red": 0.0, "green": 0.0, "blue": 0.0, "luma": 0.0, "saturation": 0.0},
  "offset":    {"red": 0.0, "green": 0.0, "blue": 0.0, "luma": 0.0, "saturation": 0.0}
}
```

`type`、桶与 native color info 字段证据：`原生材料/参数解析`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-native-material-schema-static.txt`，未随源码分发）、`原生持久化序列化器`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-persistent-schema-static.txt`，未随源码分发）、`导出符号映射`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-lut-native-exports.json`，未随源码分发）。

## 4. 正常 Qt 色轮编辑入口与范围

已解码 `VECreator.dll` 自有 Qt 元数据。`AdjustSettingHandleViewModel` 有以下真实 invokable（索引为本类 local index，不是可跨版本硬编码的方法 ID）：

```text
109 resetColorWheelsGroup()
110 setColorWheelsEnable(bool bEnable)
111 setColorWheelsTab(int index)
112 setColorWheelValue(AdjustColorWheelItemData* pItem,
      ColorWheelsParamFlag flag,
      double r, double g, double b, double s, double l,
      bool record, QString action_type)
113 setColorWheelValue(...同前，但省略 action_type)
114 resetColorWheelValue(AdjustColorWheelItemData* pItem)
```

精确 flag：

| Qt enum | 值 |
|---|---:|
| ParamRed | 1 |
| ParamBlue | 2 |
| ParamGreen | 4 |
| ParamSaturation | 8 |
| ParamLuma | 16 |
| **ParamRGB** | **23** |

`ParamRGB` 包含亮度位，**不是 7**；Blue 与 Green 也不能按一般 RGB 位序猜测。QML 对单红值使用 `(item, ParamRed, value,0,0,0,0,accept,actionType)`；单绿、单蓝分别只把对应参数置值。它不会把其它 0 参数都当作本次被修改的字段。

绑定链为当前 `AdjustSettingHandleViewModel.colorWheelData → AdjustColorWheelSettingData`，后者有 `lift/gamma/gain/offset` 与 `shadow/midtone/highlight/logOffset` 的 `AdjustColorWheelItemData*`。不要自行构造这些 item 或复用上一草稿的指针。正式 UI 中 Primary tab=0，Log tab=1。

原生 QML 的 RGB 数字输入范围是 **[-1,1]**、步长 0.01；`ColorWheelComponent` 将 RGB 转为亮度：`l = 0.2126*r + 0.7152*g + 0.0722*b`。Item Qt property 暴露 red/green/blue/saturation，没有独立公开 luma property；亮度 slider 更新后会重算 RGB 并走 `ParamRGB`。所有传入 shader 的 number 事件在 Lua 内另限幅 [-1,1]，不代表任意其它 UI 参数都能不看自身 ParamSettingSliderData 范围而硬设 [-1,1]。

`record` 就是官方 QML 的 `accept`：拖动过程 false，`onValueAccept` 为 true；色轮实际 Qt setter 中的 undo 合并、当前片段选择与保存，仍需主线程验收。色轮组显示受 `isAdjustMergeResourceLoaded` 控制；正常加载/重试入口仍为 `loadSmartColorPanelData(0)`。不应通过改 flag 冒充加载完成。

证据：`handler 元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-qt-decoded-static.json`，未随源码分发）、`enum 与 LUT 元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-base-qt-decoded-static.json`，未随源码分发）、`色轮 data 元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-qt-decoded-static.json`，未随源码分发）、`官方色轮面板 QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-qml-8e643c0.qml`，未随源码分发）、`setter 调用 QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-qml-8e658ff.qml`，未随源码分发）、`输入范围与接受时机 QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-qml-8e5df4c.qml`，未随源码分发）。

## 5. 原生动作 DTO 与持久化材料不是同一 schema

`videoeditor.dll` 的 `MaterialColorWheelsParam` JSON 读取器 `0x1800e1f50` 读取：

```text
modified_type    int
modified_fields  int64 bitmask
red, green, blue, luma, saturation, intensity  double
panel, resource_id, path  string
source_platform int
```

Wire 字段名为 `color_wheels_param`；旧 Web wrapper 为 `colorWheelsParam`。旧 Web `function to()` 默认 `modifiedType=ColorWheelsFieldPrimaryWheelsLift`、`modifiedFields=0n`、值全 0，却缺少当前 native 有的 `luma/source_platform`。这进一步说明旧 Web DTO 只能交叉参照，不能代替当前 native 契约。动作里的 intensity 默认 0 也不能覆盖保存材料默认 1。

当前官方命令目录中没有明确的 `--lut`、`--primary-wheel` 或 `--log-wheel` 参数；`video.setBasicColor` 服务映射只说明通用操作存在，没有给所有参数的已验证输入。`ai-creation~13` 的 Web `updateColorWheelsParam` 还是空实现，不能把它当功能已接通证据。

证据：`本机 native DTO`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-native-material-schema-static.txt`，未随源码分发）、`旧 Web DTO 默认构造`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-action-dto-static.json`，未随源码分发）、`官方服务映射片段`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-app-server-dto-snippets.json`，未随源码分发）、`当前官方命令目录`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/engine/lyra_commands.json`，未随源码分发）。

## 6. 色轮资源与原生启用位

安装自带四个独立包：

```text
Resources/PrimaryWheel/primary_wheel_v0
Resources/PrimaryWheel/primary_wheel_v1
Resources/LogWheel/log_wheel_v0
Resources/LogWheel/log_wheel_v1
```

每个包根自身有 config.json，Link 指向 `Wheel/`，类型 AmazingFeature。Primary zorder=5011、Log=5012。不能把没有 config.json 的上级 `Resources/PrimaryWheel` 当成同一个包根。

Primary v1 的 Lua 接收 `Intensity, LiftY/R/G/B/S, GammaY/R/G/B/S, GainY/R/G/B/S, OffsetR/G/B/S, LumaMix` 等 SetEffectIntensity 事件，并以非线性函数把归一化参数变成实际 shader 参数。例如 Gamma v<0 为 `1-4*v`，v>=0 为 `1/(1+4*v)`；Gain v<0 为 `1+0.999*v`，v>=0 为 `1+4*v*v`。所以持久化中性 0 和实际 Gamma/Gain 中性 1 不能混写。

Log v1 接收 `ShadowR/G/B/S, MidtoneR/G/B/S, HightlightsR/G/B/S, OffsetR/G/B/S, RngDown, RngUp`；`Hightlights` 是资源中真实拼写。旧 Web 另有 `RugDown/RugUP` 拼写，不能据它生成当前 shader payload。

本任务已经由主线程验证的缓存 collection：

```text
resource_id: 7416258989467374091
%USERPROFILE%/AppData/Local/JianyingPro/User Data/Cache/effect/
7416258989467374091/9e1cfdca2b07a183049bfc9b5ed32895
```

该包同时含 `AmazingFeature_primaryWheel`、`AmazingFeature_logWheel`、`AmazingFilter_lut`。其根 `Feature.js` 的 scene enable 初值为 false，并明确接收：

```text
primary_color_wheels_enable
log_color_wheels_enable
lut_enable
```

这些是渲染内的 scene 开关，不是随意新增到保存材料的字段。片段的原生组开关为 `enable_color_wheels`（配合 `enable_adjust`），LUT 为 `enable_lut`（配合 `enable_adjust`）。native merge 转换函数 `0x181659bc0` 自身也有 `lut_enable/lut_intensity/lut_skin_intensity/feature_outer_lut_path` 与 wheels 参数映射证据。优先让原生转换产生 shader payload，避免手拼一套与材料脱节的 effect 参数。

同包已能让 HSL/曲线生效，可以作为色轮对照中优先冻结的资源版本；这不证明色轮已工作。具体 `path/lumi_hub_path` 选择应保存实际回读，且要把**资源树复制到任务自己的固定目录并留摘要**，避免依赖可清理的用户缓存或把分号复合路径填进 lumi_hub_path。

证据：`资源 config、LUT 与 Feature.js 摘要`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-shipped-resources-summary.json`，未随源码分发）、`本地资源目录`（历史本机证据：`D:/刘宇钊/软件/剪映/JianyingPro/11.4.7.14462/Resources`，未随源码分发）、`native merge 渲染绑定`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-native-render-bindings-static.txt`，未随源码分发）、`当前资源 catalog`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/engine/windows-color-resources.json`，未随源码分发）。

## 7. 自定义 CUBE LUT 的持久化材料与路径

LUT 共用 `PersistentMaterialEffect`；保存位置为 `materials.effects`、`type:"lut"`，不是一个假定的 `materials.lut` 数组。当前最小实验候选如下；这是已定位字段的组合，仍不是已验收的最小成功 schema。

```json
{
  "id": "新的材料UUID",
  "type": "lut",
  "path": "完整自有测试.cube;完整LUT效果包目录",
  "value": 1.0,
  "visible": true,
  "platform": "all",
  "source_platform": 0,
  "version": "",
  "lumi_hub_path": "",
  "enable_skin_tone_correction": false,
  "item_effect_type": 0,
  "effect_id": "",
  "resource_id": "",
  "third_resource_id": "",
  "adjust_params": [],
  "face_adjust_params": [],
  "exclusion_group": []
}
```

片段 `extra_material_refs` 引用其 UUID，`enable_lut/enable_adjust=true`。原生 parser 的 visible 默认 true、platform 默认 all、item_effect_type 默认 0。渲染转换中的 LUT flag=1 从 LUT 类型派生，不能把它误当 `item_effect_type=1` 或新增持久化 `flag:1`。

复合路径解析定位于 `videoeditor.dll 0x182b7cb90` 的 type==14 分支：

1. 分号后半放入 stack `+0x270`，经规范化后作为 **FeatureSegment 效果包目录**；
2. 分号前半放入 stack `+0x250`，经 `0x182b906d0 → 0x182b94ea0` 写入 **`feature_outer_lut_path`**；
3. 分号前半还取 dirname，读取 `dirname(first)/config.json`；`AdjustUtils::fixLutPath` 对 first 做存在检查。

因此 first 应为实际 CUBE 文件，second 应为自身含 config.json 的合法 LUT 效果包目录。此前本研究将两半语义误读成 `config.json;cube`，已被主线程真实日志否定，撤销该建议；详见第12节。分号两侧不加空格，使用规范绝对路径。`lumi_hub_path` 若采用 merge 链应是真正的 merge 资源路径，不能填 compound path。

安装目录 `Resources/lut/config.json` 是 AmazingFilter 包，zorder2000、version10.2，依赖 skinseg 配置。本任务 collection 还含一个完整的 `AmazingFilter_lut/config.json`，以及实际 CUBE：

```text
AmazingFilter_lut/Alexa LogC to Rec709.cube
LUT_3D_SIZE 33
SHA256 de533d358202c2dddbb7f32c6321d9cd2fcb98a46b9f09429539fcf434ac456c
```

可先用该包内现成 cube 验证路径能否正常解析，再用自有标准测试 CUBE 做强对照。该现成 LogC 表不代表适合当前普通实拍；这里只把它作为格式与路径样本，不能当成审美建议或通用调色预设。

证据：`Effect parser`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-persistent-effect-json-static.txt`，未随源码分发）、`compound path 渲染分支`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-adjust-from-cover-static.txt`，未随源码分发）、`fixLutPath`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-fix-lut-path-static.txt`，未随源码分发）、`存在检查`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/fix-lut-path-check-helper-annotated.txt`，未随源码分发）、`实存 CUBE 与配置摘要`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-shipped-resources-summary.json`，未随源码分发）。

## 8. LUT 正常导入和参数入口

Qt 元数据确认以下真实接口：

```text
AdjustSettingHandleViewModel.setLutEnabled(bool enable)
AdjustSettingHandleViewModel.setSkinProtectEnabled(bool enable)
AdjustSettingHandleViewModel.resetLutGroup()
LutCategoryInfoViewModel.importFiles(QQuickItem* dropArea, QList<QUrl> urls)
```

`lutData` 为 `AdjustLutSettingData*`，属性包含 `intensity` 与 `skinProtectIntensity` 的 `ParamSettingSliderData*`、enableState、skinProtectEnabled、selectedText、isLutPathMix。强度可走现有 handler 的真实 `onValueChanged(ParamSettingSliderData*,double,bool withShift,bool record[,QString action_type])`，范围应从当前 slider data 实际读取，不能根据示例 value1 假定全部 UI 数值用同一单位。

没有找到可直接复用的公开 `importLut(QString)`。`clickedLutImport()` 会走文件选择器，不符合本轮禁止 CU；`importFiles` 是正常导入入口，但 `dropArea` 是否允许空指针、`QList<QUrl>` 如何在当前桥中准确封送尚未验证。本轮没有替它猜空指针或构造一个无上下文 ViewModel。主线程如要验证，应绑定当前实际 category model，再按精确参数类型走正常 importer。

证据：`LUT 与 importer 元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-base-qt-decoded-static.json`，未随源码分发）、`handler 元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-qt-decoded-static.json`，未随源码分发）。

## 9. 推荐的最小实际实验，按独立变量推进

以下是给主线程的建议，本轮没有执行：

1. **Primary 单独验收**：独立专用草稿与同源 baseline，四组均零、intensity1，对照只改 lift.red=0.25；冻结已验证 collection 副本，明确引用与 enable_color_wheels/enable_adjust；原生导出比较真实 RGB、局部暗部和全帧 MAD。日志接受或编码成功不算通过。
2. **Log 单独验收**：独立对照只改 shadow.red=0.25；不要在同一轮加入 HSL、曲线或 primary，以免别的模块造成的变化掩盖 log 失败。
3. **可编辑性**：从成功材料进入正常当前调色模型，读正确 item，调用一次 record=true 的精确 setter；回读材料，undo/redo，保存，再导出保存版本。检验参数和出片随历史恢复，并确认没有把素材路径换成烘焙成片。
4. **LUT 路径/算法先验收**：合法现成资源包 + 包内33³ CUBE，compound 使用 `cube;包目录`，先确认日志不再把 cube 当目录；再用自有 identity CUBE 与强色彩变化 CUBE 对照，value0/1 分别导出。若 identity 相同而强变化也相同，应判链未生效，而非接受“高级 LUT 效果不明显”。
5. **LUT 编辑性后验收**：在真实 lutData 上读范围并改强度，完成 undo/redo/save/re-export；自定义 cube 路径与材料留在草稿中可读回。若只接通离线构建，应明确报告“离线原生可渲染”，不能提前称“当前页完整可编辑”。

对于轮组默认资源版本、panel 的正式取值、LUT merge/standalone 的最佳资源组合，本轮没有足够实际证据宣布唯一正确条件。应以精确保存回读 + 原生输出决定，而不是继续向 schema 填猜测 flags。

## 10. 版本指纹与复查入口

```text
videoeditor.dll SHA256 fa89997a94e96cf97c8ee436a56ab028ea5f87731214696ba43ff74c0fdc0fa0
VECreator.dll   SHA256 769c33961ef9d7e471e583f03c975be975b0c35e849a767690d09e9f2fc45111
```

所有 VA 都是当前磁盘 PE 静态 preferred VA，不能当当前进程的绝对地址使用。Qt 普通方法通过真实元数据和当前对象绑定；不直接调用这些静态地址。后续版本或 DLL 摘要变化后需重新定位。

QML 解包复查脚本：`extract_adjust_qml_readonly.py`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/extract_adjust_qml_readonly.py`，未随源码分发），只解压 qCompress/raw 资源；native 静态边界/字串工具为 `identity_static_probe.py`（历史本机证据：`D:/JianyingHeadless/work/live-edit-v01/research/identity_static_probe.py`，未随源码分发）。二者不注入运行时。本轮新增的文件只有研究证据与本文。

## 11. GUI 色轮的可调用绑定证据（追加，只读静态）

主线程已在独立同源 4 秒草稿中接入 Primary `lift.red=.25` / Log `shadow.red=.25` 原生出片对照，运行和像素验收由主线程负责。本追加仍没有读取/操作当前 GUI 进程，没有调用 native，也没有改 engine。下列值来自同一指纹 DLL 的 Qt property read 分支、RTTI Complete Object Locator 与 setter 实现，不是运行时地址扫描或猜测对象布局。

### 11.1 Getter 与 vtable 的完整链

静态 preferred base=`0x180000000`；实际进程用 `module_base + RVA` 验证 vtable，不使用下面的 preferred VA 直接调用。

| 对象 | 主 QObject vtable preferred VA | vtable RVA | 备注 |
|---|---|---|---|
| AdjustSettingHandleViewModel | 0x18bfef5b0 | 0xbfef5b0 | 对象首地址 |
| 同 handler 的 VENotifyListener 次对象 | 0x18bfef610 | 0xbfef610 | handler+0x10，不是另一个 owner |
| AdjustColorWheelSettingData | 0x18b4a4298 | 0xb4a4298 | handler.colorWheelData 指向这里 |
| AdjustColorWheelItemData | 0x18b4a4238 | 0xb4a4238 | 所有 8 个 item 相同动态类型 |

`AdjustSettingHandleViewModel` 的 local property29 `colorWheelData`，Qt read dispatch case **`0x1830fabb9`**，指令就是 `mov rax,[rcx+0x128]`。因此：`data = *(handler + 0x128)`。

`AdjustColorWheelSettingData::qt_static_metacall` 位于 `0x1830f8710`；ReadProperty 跳表 `0x1830f8e04` 与元数据 property local index 对照后得到：

| 属性 | data 内 offset | 类型 | Qt read case |
|---|---:|---|---|
| enableState | +0x10 | int CheckBoxState | 0x1830f8aff |
| colorWheelsTab | +0x14 | int | 0x1830f8b0f |
| colorWheelIntensity | +0x18 | ParamSettingSliderData* | 0x1830f8b1f |
| logWheelIntensity | +0x20 | ParamSettingSliderData* | 0x1830f8b31 |
| lift | +0x28 | AdjustColorWheelItemData* | 0x1830f8b43 |
| gamma | +0x30 | AdjustColorWheelItemData* | 0x1830f8b55 |
| gain | +0x38 | AdjustColorWheelItemData* | 0x1830f8b67 |
| offset | +0x40 | AdjustColorWheelItemData* | 0x1830f8b79 |
| shadow | +0x48 | AdjustColorWheelItemData* | 0x1830f8b8b |
| midtone | +0x50 | AdjustColorWheelItemData* | 0x1830f8b9d |
| highlight | +0x58 | AdjustColorWheelItemData* | 0x1830f8baf |
| logOffset | +0x60 | AdjustColorWheelItemData* | 0x1830f8bc1 |

Item 的 Qt ReadProperty 跳表 `0x1830f78f8` 对照：red double+0x10、green double+0x18、blue double+0x20、saturation double+0x28；isRedMix/isGreenMix/isBlueMix/isSaturationMix 分别是 byte+0x30/+0x31/+0x32/+0x33，title 是 QString+0x38。**不存在公开 luma property getter**，仍按第4节的官方 UI 换算与 setter 参数处理。

Item 还有 Qt 未公开的内部字段 discriminator int+0x50。原生正常初始化函数 `0x18379ae30` 取上表的 item，然后调用 `0x183799460`；后者明确写 `item+0x50`。真实映射为：

```text
lift=0, gamma=1, gain=2, offset=3,
shadow=5, midtone=6, highlight=7, logOffset=8
```

这个映射**不是连续 1..8**。它是 setter 最终创建动作 DTO 时使用的 modified_type；不要将本字段直接改写成“修复”方式。

证据：`精确 getter、metadata dispatch 与 RTTI 汇总`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/wheels-binding-exact-static.json`，未随源码分发）、`原始 property 分支`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-qt-properties-static.txt`，未随源码分发）、`正常初始化与 setter 实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/wheels-gui-setter-tab-binding-static.txt`，未随源码分发）、`discriminator 写入器`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/wheels-gui-binding-deps-static.txt`，未随源码分发）。

### 11.2 Item 与 owner、目标片段如何绑定

`AdjustColorWheelSettingData` 正常构造实现 `0x1830716b0` 按上述8个 member 分配 item，向同一 QObject 构造入口传入该 data 为 parent，再保存到各 member；两个 intensity slider 也以该 data 为 parent 创建。本轮不另猜 QObject private parent 的内存 offset。稳定可验证的 owner 关系是：**当前已绑定 handler → handler+0x128 的 data → data 对应 member 的 item**，配合三层 vtable 检查；不能仅凭全进程搜到一个相同 item vtable 就认为它属于当前片段。

`setColorWheelValue` 实体为 `0x1837aa520`，进入时检查 handler 的 ``+0x1b8,+0x1c0)` 非空，并检查 colorWheelData 非空。这个 vector 是该 handler 当前选中片段的 holder 集合；item 自身只是字段种类和当前显示值，不保存目标 segment ID。原生 wrapper 未见验证 pItem 是否确实等于当前 data 的8个 member之一，所以正式桥应自己做这个 membership 核验。

目标应沿已有 `prepare_controls` 的当前 outer/settings 绑定验证：当前 `VideoAdjustSettingViewModel+0x40` 为该 handler，`+0x30` 为 settings；settings 的 selectedSegments 中只能是本次 segment。当前项目已有该验证，不需要新建未绑定 owner。变更会话、片段选择或重新打开后重新取 data/item，不复用旧地址。

setter 将 handler、item、当前 tab 是否0、flag、r/g/b/s/l 捕获进正常 action functor，然后经 `0x1837966d0` 的 **`UPDATE_ADJUST_COMBO_ACTION`** 正常事务派发，record 作为提交/预览标志传入。functor thunk `0x183790e30 → 0x183787e10` 读取 item+0x50 生成动作 DTO，依据捕获 tab 生成材料类型 76 或77，并使用 handler 的正常资源配置；不应绕过该链直接写 item 的显示数值。

这里是静态路径证据，单次 setter 的实时输出、undo/redo、保存验收仍应由主线程实际完成。当前 typed 桥既有 pointeroverride/enumoverride 可用于精确类型封送，本轮没有修改 ABI。

证据：[data/item 正常构造与 DTO 生成`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/wheels-owner-item-constructor-static.txt`，未随源码分发）、`setter 与检查`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/wheels-gui-setter-tab-binding-static.txt`，未随源码分发）、`UPDATE_ADJUST_COMBO_ACTION`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/wheels-gui-binding-deps-static.txt`，未随源码分发）、`action functor`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/wheels-setvalue-functor-apply-static.txt`，未随源码分发）、`现有当前片段绑定实现`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/engine/live_editor/color.py`，未随源码分发）。

### 11.3 exact enum 名与8参数 overload

元数据的参数类型字符串精确为 **`ColorWheelsParamFlag`**，定义在 **`AdjustSettingHandleViewModelBase::ColorWheelsParamFlag`**。QML 使用继承可见的 `AdjustSettingHandleViewModel.ParamRed`。typed 方法匹配应采用声明处的 `ColorWheelsParamFlag`，不要把参数类型字符串随意替换成 int 或只依据完整定义名构造另一个 signature。

可用 overload 的参数类型顺序精确为：

```text
setColorWheelValue(
  AdjustColorWheelItemData*, ColorWheelsParamFlag,
  double, double, double, double, double, bool)
```

local method113 的8参数 dispatch case=`0x1830f9dc2`；它构造默认 action_type 后和9参数版本都调用 `0x1837aa520`。第一个指针是 item，不是 data/handler；五个 double 顺序为 **r,g,b,s,l**；bool 是 record。ParamRed=1、Blue=2、Green=4、Saturation=8、Luma=16、RGB=23 均保持第4节已解码枚举值。

### 11.4 setColorWheelsTab 改什么

Qt 方法 local111 dispatch case `0x1830f9d40` 调用真实实现 `0x1837aa970`。该实现：

1. 将当前 data+0x14 改为 index，发 `colorWheelsTabChanged`；
2. 保存 `color_wheels` 配置分组的 `tab` 值；
3. 若 tab0，聚合刷新 lift/gamma/gain/offset；否则刷新 shadow/midtone/highlight/logOffset。聚合器 `0x1837b31f0` 按 holder 集合与 item discriminator 读取材料数值，更新 item 显示值和 Mix 状态。

**这里没有写材料 panel，也没有提交 UPDATE_ADJUST_COMBO_ACTION。** 因此它是带偏好保存的 UI 类型选择，不是把当前材料改成另一个 panel；但是后续 `setColorWheelValue` 在 `0x1837aa59a` 读取 tab是否0，将其捕获并选择 Primary/Log 材料类型。所以正式修改 Log 之前必须正常切到1，Primary切到0，并从对应 member 重新读取 item；不能只把 shadow item 传入仍在 Primary 的 handler。

可读回 data+0x14 确认tab；不用修改材料 panel 来模拟切换，也不直接写内存。tab 偏好属于 UI状态，不能将其“切换成功”算作色轮图像效果或 undo/save 验收。

证据：`setColorWheelsTab 完整实现与 setter 入口`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/wheels-gui-setter-tab-binding-static.txt`，未随源码分发）、`仅聚合刷新 item 的 helper`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/wheels-gui-binding-deps-static.txt`，未随源码分发）。

## 12. LUT 首轮真实失败与 compound path 修正（追加，只读）

主线程真实首轮为已知原包内 `Alexa LogC to Rec709.cube`，path 采用此前本研究的 `config.json;cube` 候选，lumi 指向同 collection 的 lumi_hub_path；value0/1 两轮均 encoded-and-decoded，但与无调色 baseline 实际像素逐字相同、MAD=0。此结果没有通过验收。

直接原因可在 `full 原生日志`（历史本机证据：`C:/JianyingAVQA/work/avlut-full-out-1028-v1/native.stdout.log:696`，未随源码分发） 第696–704行读到：FeatureSegment 开始加载的 path 是 `.cube`，随后查找 `.cube/config.json`，报告不存在、无效配置和 `Cannot load filter scene`。这不是“LUT 效果不明显”，也不足以说明 LUT 不支持；是效果包路径错误导致未加载。

我重新跟踪 `0x182b7cb90` 中的完整寄存器/stack 数据流：

| 分号部分 | 构建位置 | 最终用途 |
|---|---|---|
| second/suffix | 0x182b7d221..34f → rsp+0x270 | 0x182b7dc96 规范化；交 0x182b8f710，再创建 FeatureSegment |
| first/prefix | 0x182b7d3ce..468 → rsp+0x250 | dirname(first)/config.json 的读取；0x182b7df5d → 0x182b906d0 → 0x182b94ea0，后者明确写 feature_outer_lut_path |

此前研究只看到“prefix 旁边读 config”便误把它当配置文件占位，且误判 suffix 是 outer LUT，属于证据解读错误。已修正第7节的 schema 和路径说明；正确的下一轮静态候选是：

```text
<自有root>/AmazingFilter_lut/Alexa LogC to Rec709.cube;<自有root>/AmazingFilter_lut
```

这样 first 是实存 CUBE，dirname(first) 本身有配置；second 是实存 AmazingFilter 包目录，本身也有配置。它保留现有原包字节，不需要改 `item_effect_type` 或伪造 shader enable。是否与当前 lumi 分支组合后实际生效，仍应由主线程新一轮原生输出验收；本轮没有调用 native。

`segmentUseMergeAdjust 0x181012f30` 在 `0x18101349e` 确实读取 MaterialPictureAdjust 的 lut，再在 `0x1810134d0` 经过正常 `MaterialEffect.lumi_hub_path` 检查。因此不能单凭本次日志宣称“原生 merge 不支持 LUT”。当前已证明的失败是 suffix 被当 feature 根；先修正精确合同再判断其它链路，避免同时改 flags 掩盖原因。

新证据：`首轮实际材料、原生日志摘录与像素结果`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-first-export-readonly-diagnosis.json`，未随源码分发）、`Feature 路径/outer 路径两个 helper`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-feature-vs-outer-path-static.txt`，未随源码分发）、`完整 compound 分支`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-adjust-from-cover-static.txt`，未随源码分发）、`merge 判定`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-segment-use-merge-adjust-static.txt`，未随源码分发）。

## 13. LUT 第二轮：资源加载通过，强度仍未通过；GUI 精确绑定

主线程更新：Primary 与 Log 的离线画面均已实际生效；Primary GUI `.25→.08`、Log GUI `.25→.05` 的正常修改、undo/redo、保存与两状态出片均已通过，Log 两状态实际 MAD=3.4998。这是主线程实际操作结论，不是本研究执行的测试；前文首次研究的“尚未验证”边界已被这些新增证据逐项推进，LUT 不在成功范围内。

LUT 第二轮采用 `cube;包目录` 后，已无 `Cannot load filter scene`。但是 `v2 像素结果`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut-native-pixel-proof-v2.json`，未随源码分发） 显示：value0 与 value1 各自对无 grade baseline 的 MAD 都为2.467444，二者逐字相同、MAD=0。**包加载有影响，不代表 CUBE 与强度控制已生效。** 该轮仍应判失败。

### 13.1 value 的真实字段与强度协议

本机导出符号明确 `MaterialEffect::get_value` 为 `videoeditor.dll 0x180122cd0`；该 leaf 的指令为 `lea rax,[rcx+0x130];ret`，因此运行时材料的 value 是 double+0x130。`RuntimeTransfer::TransferMaterialEffectFromPersistentMaterialEffect`（0x180e73e00）在0x180e740c4..d1从持久化 value 所在 `+0x120` 传入正常 `set_value`。同一个 transfer 还正常转移 intensity_key、source_platform、version、lumi_hub_path，不应假设这些字段只存在 JSON 中而必然没入运行时。

已定位的渲染层有两套真实协议：

| 转换器 | 强度来源 | key/路径逻辑 |
|---|---|---|
| 旧逐项转换 0x182b7cb90 | 输入 AdjustInfo double+0x48 | key 由0x182b8f350(type,version)选择；type14落默认 key；compound suffix作为FeatureSegment包路径，prefix作为outer LUT |
| 合并参数转换 0x182b7e290 | 输入 entry double+0x48 | 0x182b90410调用0x182b8f9d0取得功能名并拼 `_intensity`；LUT 对应 `lut_intensity`，另生成feature_enable_alg、lut_skin_intensity、feature_outer_lut_path |
| 合并资源组装 0x182b800b0 | 接收前级的合并参数 JSON | 以merge组处理资源，生成最终包路径、Lumi和参数 |

旧转换器的type14在0x182b8f359先计算 `14-15`，越界后转默认分支0x182b8f4aa；随后对25..40的版本转换范围也越界，回默认0x182b8f546。这个路径没有依据version `"1"` 切成 `lut_intensity`。默认std::string在磁盘的长度为9；因发布物字符串初始化在运行时处理，本轮未被动读取活跃进程来确认其具体9字节，不把推测文本写成已确认值。`lut_intensity` 是13字符，确实属于另一路键名。

`video_wrapper::addAdjusts` 的0x182c5eb40在entry类型0时调用旧逐项转换0x182b7cb90；另有完整merge路径。当前日志的逐个FeatureSegment加载符合旧路径，但本轮尚未把“当前LUT材料→本轮AdjustInfo→merge选择”全部连接成具有唯一解释的因果链。**仍缺这一上游转换的最终确证，不能宣布加某一个字段就是修复。**

`intensity_key` 确实是 PersistentMaterialEffect parser 支持的字段，当前最小候选中未提供；但上述旧转换器的`+0x50`参数是version，不是intensity_key。没有证据支持直接往材料填 `intensity_key:"lut_intensity"` 就能覆盖此处的键名，因此本轮也不推荐这样猜。

关于两种候选变更：

- **version="1"**：所见LUT type14 key分支没有支持它修复强度；不能将其它调色模块的v1协议移植到LUT。
- **清空lumi_hub_path**：segmentUseMergeAdjust对LUT的正常lumi检查已定位，清空它会改变路由资格；但它不是保证强度生效的证据。
- **改用安装自带Resources/lut包**：该包是独立原生AmazingFilter资源，与collection子包是不同资源身份；可作为将“旧协议+完整独立原包”单独验收的对照条件。当前也没有其成功像素证据，不能替换已验证catalog或放宽所有包的校验来冒充修复。

证据：`真实MaterialEffect getter/transfer导出符号`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-material-export-accessors-static.json`，未随源码分发）、`持久化→运行时转移`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-material-runtime-transfer-static.txt`，未随源码分发）、`旧转换完整实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-adjust-from-cover-static.txt`，未随源码分发）、`旧key选择`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-intensity-key-dispatch-static.txt`，未随源码分发）、`合并转换`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-native-merge-convert-adjust-static.txt`，未随源码分发）、`合并key拼接`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-merged-intensity-key-static.txt`，未随源码分发）、`wrapper逐项入口`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-native-cover-dispatch-static.txt`，未随源码分发）。

### 13.2 当前GUI的lutData和强度slider

按真实Qt property跳表与RTTI重新核对，不扫描当前GUI：

```text
data = *(当前已绑定handler + 0xa0)
data vtable RVA = 0xb4a4058  // AdjustLutSettingData
slider = *(data + 0x10)
slider vtable RVA = 0xb4a3ed8  // ParamSettingSliderData
```

Data的其它可读字段：enableState int+0x18；skinProtectEnabled int+0x1c；skinProtectIntensity pointer+0x20；selectedText QString+0x28；isLutPathMix byte+0x40。所有指针都应从已验证的当前handler链读取；不能将同类任意slider当作LUT强度。

| slider 属性 | offset | 类型 |
|---|---:|---|
| text | +0x10 | QString |
| propertyType | +0x28 | QString |
| constantMaterialId | +0x40 | QString |
| enabled / visible / isMix | +0x58/+0x59/+0x5a | byte |
| curValueUI | +0x60 | double |
| minSliderValueUI / maxSliderValueUI | +0x68/+0x70 | double |
| minEditValueUI / maxEditValueUI | +0x78/+0x80 | double |
| sliderType | +0x88 | int |

正常初始化0x183799580在0x18379961e..627给此slider传入功能类型 **14**，内部保存到slider+0x9c，随后将其默认值slot+0xb0设为1.0。这个slot不是curValueUI，也不是强度范围。真实范围由初始化时的参数描述载入，建议主线程直接读取上表的四个范围和当前值，而不是在尚未读取前声称范围一定为0..100或0..1。

### 13.3 onValueChanged的精确调用语义

真实4参数overload仍是：

```text
onValueChanged(ParamSettingSliderData* commonSliderInfo,
               double UI_value, bool withShift, bool bRecord)
```

local method51的dispatch调用实体 `0x18379f650`。它先更新curValueUI，再比较slider内部数值范围；若UI与内部范围不同，实际按如下线性映射产生native value：

```text
native = nativeMin +
         (UI_value - minEditValueUI) /
         (maxEditValueUI - minEditValueUI) * (nativeMax - nativeMin)
```

这里nativeMin/nativeMax是读取器可观察的double+0xa0/+0xa8（不是公开Qt property名；名称仅描述用途）。随后以功能kind14与归一化后的值调用0x1837a7d10，后者继续0x1837a7d90走正常调色action。record是用户接受本次修改的标志，withShift不是权限开关。正式调用应使用当前slider的UI单位，例如只有读到UI最大100以后才能将40作为40%输入。

最有价值的下一步是让主线程通过正常当前GUI读上述状态、提交一次原生LUT强度，再比较保存前后的完整LUT材料（包括path、lumi、version、intensity_key、source_platform、value）和出片。这样可看到官方正常编辑链是否补齐了离线候选缺少的资源/协议数据，而不是反复手填参数猜测。本轮没有执行该操作。

证据：`getter、vtable和范围字段汇总`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-gui-binding-exact-static.json`，未随源码分发）、`slider Qt元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-slider-qt-decoded-static.json`，未随源码分发）、`LUT正常初始化与onValueChanged`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-gui-slider-initialize-edit-static.txt`，未随源码分发）、`提交wrapper`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-gui-slider-submit-static.txt`，未随源码分发）、`正常action构造`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-gui-slider-action-build-static.txt`，未随源码分发）。


## 14. 原生 LUT 选择模型：材料存在不等于库中有这条 LUT

**主线程本机观察（本研究未调用运行时）**：当前 LUT checkbox enable_state=0，但 selected_text=`无`、intensity.enabled=false；UI 强度100、saved.value=1并不能证明已正确选中。正式 getter 初始化的下拉库实际只有一项“无”/空路径，初始化前后完整时间线 fingerprint 相同。`当前库被动读证据`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/native-lut-library-current-observed.json`，未随源码分发）。因此 §13.3 的后续验证必须先满足真实 LUT 选择状态；本轮**不建议向 disabled slider 提交数值**。

原生 refresh `0x1837b23c0` 的确定逻辑：

1. 从已绑定选中片段集合读取 enable_lut，生成 checkbox 的 On/Off/Mix 状态；它与名称查询是两条独立链。
2. 取得当前材料 path，按分号拆开，前半 cube 路径送入 `import::ImportCenter` 查询 `0x18641eab0`。
3. lookup 先查全局 LUT 记录，再查当前项目的 LUT 记录。没有记录则 selectedText=`none` 的本地化值，intensity.enabled=false；有记录则用记录 title、enabled=true。本轮不把这个逻辑解释为权益开关。

以上静态逻辑完整解释了“checkbox on，但名称无、slider disabled”。`refresh 与 lookup 实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-state-and-native-import-static.txt`，未随源码分发）、`库 lookup/getter`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-manager-lookup-and-import-entry-static.txt`，未随源码分发）。

### 14.1 正常下拉 owner 和选择 API

QML 调色面板第844行使用 `viewModel.getVESpinComboBoxViewModel()`。该公开无参 Qt 方法是 handler local method84；实现 `0x183797990`，正常懒建 `VELutSpinComboBoxViewModel`，缓存到 handler+0x208。不可直接调用构造地址。`面板 QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-qml-8e60aeb.qml`，未随源码分发）、`getter和构造`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-combo-constructor-importheader-static.txt`，未随源码分发）。

| 具体 owner 字段 | 静态绑定 |
|---|---|
| primary vtable RVA | `0xbff1940` |
| QObject 主对象大小 | `0x2a8` |
| names | `+0x210`，QStringList |
| cube paths | `+0x228`，QStringList，与名称列表对应 |
| 反向当前 handler | `+0x268` |
| path→title 映射 | `+0x270` |
| 本机 reader 边界 | Qt6 list 三字段，元素为24-byte QString；只读 bounded decode，不写布局 |

正常构造/刷新 `0x1837bec40` 先放入“无”/空路径，随后从 ImportCenter 的实际记录填列表。多于“无”还需核对真实路径存在。公开继承 Qt 方法是：

```text
VESpinComboBoxViewModel.onClickItem(VESpinComboBoxItemViewModel* itemModel,
                                   bool is_search)
VESpinComboBoxViewModel.onClickItem(VESpinComboBoxItemViewModel* itemModel)
```

后者默认false。普通 dispatch virtual+0x1c8 → LUT override `0x1837be040`，从当前 item 取真实资源 key，接 `0x1837bc540`→当前 handler `0x183793d70` 的正常调色 action。未来调用必须取得该 owner 正常创建且属于其 collection 的真实 item，不能伪造 item 或只根据类名扫描到的任意对象；本轮没有执行选择。`Qt元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-import-selection-qt-decoded-static.json`，未随源码分发）、`具体class和VT`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-combo-item-rtti-vtables-static.json`，未随源码分发）、`selection实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-select-library-import-core-static.txt`，未随源码分发）。

## 15. 正常导入接口与现桥类型边界

两个正式 UI 入口均已从一手 QML/Qt metadata 定位：

- 下拉导入头：`baseViewModel.headerClick(QQuickItem* sender)`；QML使用真实root。LUT override `0x1837bd5a0` 明确打开系统文件选择器，并调用原生 importer；**仅打开选择器不等于完成导入**。
- LUT 分类页拖入：`LutCategoryInfoViewModel.checkSuffix(QList<QUrl> urls)` 后 `importFiles(QQuickItem* dropArea,QList<QUrl> urls)`。QML 134–136行以 drop.urls 调用，`importFiles` local method12，实体 `0x1829a29e0`。它对每条QUrl做toLocalFile，交给正常 `MaterialImportImpl::StartImport`，有100条数量检查。

`分类页QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-qml-89fdb76.qml`，未随源码分发）、`下拉头QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-qml-840c5b5.qml`，未随源码分发）、`导入metadata`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-wheels-base-qt-decoded-static.json`，未随源码分发）、`importFiles真实实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-normal-import-and-combo-getter-static.txt`，未随源码分发）。

当前 typed bridge 不能构造 QList<QUrl>；该层不能冒用 QStringList 签名。下层 `MaterialImportImpl::StartImport` 接受std::vector<std::string>，是C++内部API而非已发现的公开Qt invokable。ImportCenter 的7条Qt metadata全是signals；具体 VELutSpinComboBoxViewModel 的6条新增方法是导入回调/cancel/close。没有找到可直接用当前桥支持的QString/QStringList输入文件路径的LUT专用导入槽；这是所读类的有界结论，不是证明整个应用没有其它入口。`ImportCenter metadata`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-importcenter-qt-decoded-static.json`，未随源码分发）、`具体下拉metadata`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-concrete-combo-qt-decoded-static.json`，未随源码分发）。

通用 CLI/SDK 也另行核对，未把关键词负面搜索当作完整证明：仓库 `blueprint_resource_import` 实际包装 `draft blueprint resource --import local:///... --title ...`，官方lyra-cli内置契约称其为导入本地media并写workspace/resource_map.json，含“unsupported or unreadable media”检查；没有证据证明它注册到ImportCenter的应用LUT库。发布JS的 `lutFileList` 唯一结构经导出名追到 `createLutDeleteParamFromPlain`，用途是删除而非导入。现阶段不能把普通资源导入或创建草稿effect材料等同于原生LUT库注册。未执行任何CLI导入试探。`CLI静态契约`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-cli-import-contract-static.json`，未随源码分发）、`SDK导出追踪`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-sdk-lutfilelist-callers-static.json`，未随源码分发）、`通用SDK导入符号检索边界`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-sdk-generic-import-symbols-static.json`，未随源码分发）。

## 16. 原生库磁盘结构、完整四字段 schema 与正常读盘链

### 16.1 权威根路径

主线程仅被动读取 IAT，确认 VECreator slot RVA `0x7f2d0c0` → VEConfig.dll RVA `0x21800`；该地址的真实导出是 `VEConfig::path::getResourcePath()`。静态代码正常构造父根 + `/Resources`；主线程再被动读其已初始化缓存（VEConfig+0x4d230），得到：

```text
%USERPROFILE%/AppData/Local/JianyingPro/User Data/Resources
```

正常LUT工具函数 `0x1865be8e0` 在此后拼 `/Lut/`，用户库索引路径由 `0x186929090` 再拼 `LutImportCfg.json`。当前该目录存在但索引不存在，与库只有“无”相符。`真实根被动观察`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/native-lut-library-root-observed.json`，未随源码分发）、`VEConfig导出`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-veconfig-root-export-static.json`，未随源码分发）、`根函数实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-veconfig-resource-root-static.txt`，未随源码分发）、`路径常量初始化完整证据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-storage-verified-constant-initializers-static.txt`，未随源码分发）。

项目附带库是另一入口：传入项目root拼 `/materials/Lut/LutDraft.json`，由完全相同reader解析，加入第二套项目LUT记录。不能把安装资源包内config.json写成这两种索引；也不应覆盖用户现有索引。

### 16.2 完整持久化 schema

`import::ReadImportLUTDataFromFile`=`0x1869291c0`（源 `Capability/Material/importer/cache/import_disk_cache.cpp`）按JSON array读条目；完整原生writer `0x18692abe0` 对每个对象只写以下4个字符串：

| 字段 | 原生记录 offset | 用途 |
|---|---:|---|
| title | `+0x8` | 下拉显示标题 |
| path | `+0x28` | 管理后的真实cube路径，库lookup比较此字段 |
| originPath | `+0x48` | 原始导入文件路径 |
| imagePath | `+0x68` | 预览图片路径 |

以下仅展示结构，**不是已创建的配置或已通过验收的导入记录**：

```json
[
  {
    "title": "Owned LUT",
    "originPath": "C:/owned/input.cube",
    "path": "C:/owned/managed/input.cube",
    "imagePath": "C:/owned/preview.jpeg"
  }
]
```

完整writer没有序列化ID、version、checksum或resource_id；不能从effect资源ID7416…推导库记录ID。路径字符串写出时通过Qt路径转换；本研究建议候选记录使用实际存在的绝对路径而不是猜相对路径基准。reader取JSON.path后在 `0x18692962b..639` 立即做存在检查，失败直接丢弃该记录（在任何索引目录前缀拼接之前）。title为空时存在从文件名推导标题的逻辑，但正式候选仍应提供明确非空title。后续reader还处理cube所在目录的scene/config资源，注册记录不是完成渲染的充分条件。

`完整JSON writer`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-library-json-full-schema-static.txt`，未随源码分发）、`完整reader`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-library-load-storage-static.txt`，未随源码分发）、`全局/项目记录getter`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-library-storage-paths-static.txt`，未随源码分发）。

### 16.3 正常加载与保存路径

确定的正常读盘链：

```text
VECoreProject::init 0x184f7e300
  → new ImportMgr 0x1867c4620
    → ImportCenter 0x18641f480
      → ImportRAMCache 0x186868eb0
        → Resources/Lut/LutImportCfg.json
        → ReadImportLUTDataFromFile

正常 load_draft_fun (VECoreProject.cpp) 0x184f67c30
  → ImportCenter 0x18641f440(root)
    → ImportRAMCache 0x186868b50(root)
      → root/materials/Lut/LutDraft.json
      → 同一 ReadImportLUTDataFromFile
```

这支持“正常关闭并重新打开自有QA工程，再重新取得当前handler/下拉”的候选验收路线；不要求直接调用构造函数或私有地址。它不是本轮已经执行的reload。没有定位到可供现桥调用、保证重读磁盘的公开reload槽。`onLutVecChanged`/刷新下拉不能凭名称当作重新读磁盘。

原生导入完成时先执行ParseToImportResult，检查数量等，再将正式记录加到RAM；随后 ImportCenter `0x18641f4c0`→RAM flush `0x186869480`→writer `0x18692ab10`→上述四字段writer，写出全局Cfg。没有证据支持“复制cube到目录，刷新就自动枚举”的机制；当前读取的是JSON索引。

`正常工程init完整实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-library-native-project-init-static.txt`，未随源码分发）、`正常loader调用链`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-library-normal-startup-load-static.txt`，未随源码分发）、`loader上游xref`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-library-center-load-callers-static.json`，未随源码分发）、`ImportRAMCache读取实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-library-source-readers-static.txt`，未随源码分发）、`正式import完成`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-import-finish-register-static.txt`，未随源码分发）、`ParseToImportResult`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-import-parse-to-record-static.txt`，未随源码分发）。

### 16.4 实验建议与未解决项

优先由主线程评估任务自有QA工程内 `materials/Lut/LutDraft.json` 的兼容导入：只放自有、可解析cube；保存该工程全部原有记录，若文件存在先备份；在数量限制内，用真实title/path/originPath/imagePath，正常关闭/打开工程触发官方load。随后必须看到真实列表项、正常onClickItem选择、selectedText正确且intensity.enabled=true，再做原生强度两个状态、undo/redo、save/reopen和逐像素出片差异验证。单纯索引能读、草稿能存或出片无错误都不算完成。

本研究**没有写任何用户库配置、项目库、草稿、engine、ABI或DLL，也未调用任何native方法**。仍待主线程实测的是：候选兼容记录能否被正常加载、是否拥有完整可执行scene bundle、普通选择动作产生的准确material/path/lumi，以及强度差异是否真实影响像素。普通SDK/CLI对应用库注册的完整全链仍未证明；不以不存在某个关键词替代该证明。


### 16.5 官方 reader 的目录完整性与可能迁移

进一步静态核对：reader从cube所在目录构造 `algorithmConfig.json` 与 `config.json`。这两个名称均已从CRT初始化及原始字符串恢复；`0x186929e22..0x186929ee6` 检查两者，任一缺少就设置repair条件。repair分支 `0x18692a0a9` 起，使用 `Resources/Lut/` 和cube文件的名称构造目的目录，交给正常复制工具 `0x1865bc0b0`，成功后重写内存record.path，随后继续原生资源修复。因此“索引放项目内”并不保证加载过程完全不写用户Resources/Lut；该行为必须由实际实验journal记录，不能在交付描述中隐去。尚未把repair生成的全部scene文件内容恢复成独立可复用规范，不能自行写假algorithmConfig或声称完整原包已具备这两文件。

证据：`algorithmConfig常量初始化`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-reader-scene-constant-initializer-static.txt`，未随源码分发）、`config常量初始化片段`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-reader-scene-next-constant-static.txt`，未随源码分发）、`完整reader含存在检查、复制和path改写`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-library-load-storage-static.txt`，未随源码分发）。本研究未触发此迁移。


## 17. 正常下拉条目的完整 owner→group→item 绑定（新增只读证据）

主线程的新独立QA已实际观察到：项目索引被官方reader读取，cube迁移到 `User Data/Resources/Lut/Alexa LogC to Rec709`。旧effect材料仍指D盘cube时，显示“无”/disabled可以继续存在；库record已迁移和草稿材料已选择是两个不同步骤。本轮再次明确：**项目索引可触发官方写入用户Resources目录，不能承诺只改项目文件**。该运行结果由主线程报告，本研究没有执行迁移或选择。

### 17.1 真实条目容器

当前combo必须来自本会话handler的正常getter，且具体class/vtable已验证。以下是针对11.4.7该指纹的只读布局证据，不是可写ABI：

```text
combo + 0x100 : root-model QPointer.control
combo + 0x108 : rootModel*
rootModel primary vtable RVA = 0xd34e990  // VETabEffectGridModel

rootModel + 0x88 : QList<QPointer<QUICollectionItem>>
  +0x90 : entries data*
  +0x98 : count (qsizetype)
  each entry 16 bytes: (control*, object*)

root's group object primary vtable RVA = 0xa57eef0
  class VESpinComboBoxTitleViewModel
  group +0x88 同样为 children list / +0x90 data / +0x98 count

leaf item primary vtable RVA = 0xa581508
  class VESpinComboBoxItemViewModel
```

对QPointer，原生代码先检查control存在且control+4的int非0，再使用对象指针；只读walker应同样校验，计数应有合理上限并防止重复指针。必须从当前combo逐层走到条目，不能把进程中另一个同vtable对象当作本下拉条目。初始rootModel是在正常base构造 `0x1819c0dd0` 由 `VETabEffectGridModel` 构造 `0x1865a0bb0` 创建，然后存到combo+100/+108；不依赖从图形界面中点击才能存在。

证据：`rootModel正常创建和存储`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-combo-root-model-binding-static.txt`，未随源码分发）、`root vtable构造`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-root-vtable-owner-constructor-static.txt`，未随源码分发）、`group RTTI和vtable`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-real-group-vtable-static.json`，未随源码分发）、`list getter、加入和枚举实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-group-items-container-static.txt`，未随源码分发）。

### 17.2 每条LUT的路径、标题、类别和反向owner

| leaf item 字段 | 类型 | 原生来源 |
|---|---|---|
| `+0x200` | MSVC std::string | 实际cube key；onClickItem调用`0x1819f79a0`读取此字段 |
| `+0x3b0` | QString | 公开Qt属性titleName；正常setter`0x181bce660` |
| `+0x1a0` | MSVC std::string | 非空LUT类别为`lutItem`，默认空项为`none` |
| `+0x280 / +0x288` | QPointer(control, owner*) | 反向当前combo；正式addGroup建立 |

正常 `VELutSpinComboBoxViewModel` 构建 `0x1837bd110`：刷新names/paths后创建title group，再按paths逐个分配真正的0x4b8-byte item，传当前combo作context；从path→title映射写titleName，从path写key，加入group。默认空项设置类别none，其余lutItem；最多100个非空LUT。完成后 `addGroup 0x1819bee60` 遍历这个group的实际items，每条经virtual+0x120→`0x1819f83f0` 把当前combo写入item的反向QPointer+280/+288，再把group挂到rootModel。

因此普通选择前可以同时要求：当前handler→combo绑定一致；leaf item在当前rootModel/group集合中；item.owner==当前combo；类别lutItem；key等于目标已存在cube；titleName匹配目标记录。row index可以记录为这次容器遍历位置，不应猜一个额外Qt index属性。现有本机metadata未提供cube路径/index的公开getter；path用上述原生key只读字段，title用真正公开属性。

证据：`完整LUT item构建`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-select-library-import-core-static.txt`，未随源码分发）、`key getter和setter`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-combo-data-getters-item-key-static.txt`，未随源码分发）、`item正常构造、title setter及addGroup`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-combo-item-build-and-owner-static.txt`，未随源码分发）、`反向owner准确写入`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-item-exact-owner-binding-static.txt`，未随源码分发）。

### 17.3 正常初始化与普通选择时机

QML下拉的`onVisibleChanged`使用公开 `baseViewModel.getData()`；baseViewModel变更且可见时使用 `startOpenPopup(true)`。`getData()` local method6的本机真实dispatch直接到`0x1819c7990`→LUT virtual+0x260/268→正常build；`getTabData()`/virtual+0x1b8的wrapper `0x1819c79f0`也接同一函数；这条路径会创建上文真实items。已有items重新刷新受combo+0x240 invalidation guard控制，不应自行写此flag或直接调用构造函数。也不能调用viewDidLoad后就假定已构建；必须实际读root/group/leaf列表。

拿到已验证leaf后，提交的正式API仍是 `combo.onClickItem(VESpinComboBoxItemViewModel* item,false)`。它取item.key走handler正常调色action，可用于让原生材料改为真实已迁移的C盘cube。选择完必须实际观察selectedText和enabled，再做强度/history/save/reexport验证；本研究未执行任何调用。当前仍缺的是主线程这一闭环的真实结果。

`正常QML加载时机`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-qml-840c5b5.qml`，未随源码分发）、`getData dispatch`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-combo-item-build-and-owner-static.txt`，未随源码分发）、`本机Qt API`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-import-selection-qt-decoded-static.json`，未随源码分发）、`FusionUI基类metadata检索边界`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-fusionui-collection-base-qt-decoded-static.json`，未随源码分发）。


## 18. 单次正常选择已提交、popup 生命周期与路径规范化

### 18.1 主线程新增运行观察

新的自有QA中，真实root/group/item与反向owner校验通过，库项是“无”及迁移后的C盘cube。主线程仅一次正常 `onClickItem(item,false)` 后，已观察到旧effect ID被新effect ID替换、undo=true、新材料保存。原先20秒SAVE_TIMEOUT来自验收predicate错误要求material ID不变；**该超时不代表动作未提交，不能重放选择**。

正常选择生成的实际path是：

```text
%USERPROFILE%/Resources/Lut/Alexa LogC to Rec709/Alexa LogC to Rec709.cube;
%USERPROFILE%/Cache/effect/7416258989467374091/9e1cfdca2b07a183049bfc9b5ed32895
```

suffix是collection根，lumi仍为collection/lumi_hub_path，effect_id/resource_id均为该collection资源ID、value=1。本轮不把此前候选 `/AmazingFilter_lut` 子目录当作这一正常链的权威suffix。材料成功提交仍不是最终LUT强度像素闭环通过；主线程报告重新准备controls后selectedText仍“无”、intensity.enabled=false。

这些是主线程独立报告的运行结果；本只读研究没有执行选择或保存。

### 18.2 第二bool及真正commit语义

Qt metadata参数名为 `is_search`。但LUT具体override `0x1837be040` **未使用传入r8 bool**，因此不能把第二bool当成accept/record开关。完整链：

```text
combo.onClickItem(item,false)
  → LUT override1837be040
    → combo.preview_restore_flag(+260)=false
    → 读取真实item.key(+200)
    → 1837bc540(path, true)  // true由click实现固定传入
      → handler183793d70([path], true)
        → 1837966d0(..., record=true, ...)
          → UPDATE_ADJUST_COMBO_ACTION
          → per-segment lambda1837912d0
            → generic adjust1837a7ee0(type14,path,record=true)
```

click并不要求popup先可见，也未发现必须再调用后置accept/end才提交的gate。LUT popup恢复体 `0x1837bfc70` 只有在+260仍true时才会把旧路径以record=false恢复；click已先清false。结合真实新material ID和undo观察，本次不存在“只预览尚未确认”的证据，不能额外补一遍同选择或猜accept方法。

`click/commit dispatch`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-click-commit-dispatch-static.txt`，未随源码分发）、`真正per-segment lambda`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-click-native-action-lambda-static.txt`，未随源码分发）、`generic type14调色action`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-generic-adjust-path-commit-static.txt`，未随源码分发）、`popup恢复体`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-select-library-import-core-static.txt`，未随源码分发）。

### 18.3 lookup与路径转换的精确方向

必须区分两层：

- `ImportCenter.lookup 0x18641eab0` 自身逐条以path长度+memcmp比较，未做路径规范化。
- refresh的上游 `getLutPath 0x186a17b10`→叶子 `0x186a17bb0` 读取native材料path之后，明确调用VECreator slot RVA `0x7f26aa8` 做QString转换。因此不能只读lookup就声称整个refresh链没有标准化。

主线程仅被动读取该slot，定位到Qt6Core.dll RVA `0x2b4f0`；本研究核对该DLL真实导出，确认为 **QDir::fromNativeSeparators(QString const&)**，将Windows反斜杠转换为正斜杠。不是toNativeSeparators。

所以若当前RAM库record.path仍是C:\…，refresh从材料得到C:/…后会与其逐字比较不匹配；这是有静态依据的解释，但仍须读实际库record，而不是仅凭保存JSON与界面文案确定原因。普通popup生命周期没有找到补充路径标准化或后置commit的机制。

`路径getter、normalization slot和popup准备`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-path-leaf-and-popup-lifecycle-static.txt`，未随源码分发）、`Qt6Core真实导出`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-native-path-normalizer-export-static.json`，未随源码分发）、`refresh上游遍历`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-refresh-path-normalization-static.txt`，未随源码分发）、`lookup本体`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-manager-lookup-and-import-entry-static.txt`，未随源码分发）。

### 18.4 不重放选择的正常候选

reader在末尾 `0x18692a936..a93f` 会用完整writer `0x18692abe0` 将记录写回原索引；writer对path/originPath/imagePath也调用已确认的fromNativeSeparators。因此可能出现“迁移后的当前RAM库反斜杠、磁盘索引已被官方写成正斜杠”的暂态。

可先由主线程只读核对当前QA的LutDraft.json是否已写为C:/实际路径、cube目录algorithmConfig/config是否都已存在。若满足，正常关闭并重新打开同一自有QA会重新加载官方写回的索引，是不重复选择的有证据候选。它尚非本研究已执行或已通过的修复；必须以重新读真实库record、selectedText、enabled为准，之后才验证强度和像素。


## 19. v6真实出片仍失败：原生参数JSON被Windows反斜杠破坏

主线程已通过正常重开让selectedText正确、enabled=true；公开强度slider提交UI0后，native省略value，当前控件0与保存0匹配。full/zero自有导出各4秒120帧完整解码，但主线程全帧比较MAD仅约0.00146/255，因此仍未通过LUT像素验收。本研究只读检查了这两份实际导出副本和日志，未再调用任何native、修改engine/ABI或回放旧选择。

### 19.1 value缺省准确为0

两种独立证据一致：

- videoeditor.dll `PersistentMaterialEffect` 的RapidJSON `from_json` 是 `0x180cada30`。读取value时，`0x180caded6` 清零r13；value未找到分支 `0x180cae05a` 把零r13直接存到persist+0x120。
- 实际v6 full材料显式value=1，原生日志生成 `lut_intensity:1.000000`；zero材料省略value，日志生成 `lut_intensity:0.000000`。因此不能把native省略0按应用层默认值1补回。

`原生parser缺省分支`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-persist-material-effect-value-default-static.txt`，未随源码分发）、`v6 full/zero原生参数摘录与解析验证`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-v6-native-param-json-proof.json`，未随源码分发）。

### 19.2 已复现的参数错误

v6 `native.stderr.log` 明确显示合并路由已产生lut_intensity 1/0，但outer CUBE路径被原生代码直接拼入JSON：

```text
"feature_outer_lut_path":"C:\JianyingAVQA\work\...\Alexa LogC to Rec709.cube"
```

这里日志中的单个反斜杠是JSON字符串中的原始内容，未被再次escape。紧接着原生 `VideoDriverImpl::addLutEnableStatus:5675` 报：

```text
addLutEnableStatus parse json error, str:{...}
```

用Python json.loads对两条真实setMergeAdjusts参数重读，full和zero均在position595复现 `Invalid \escape`，位置正是outer path的 `C:\JianyingAVQA`。随后ConvertVideoAdjustsFilter打印的`setDirectMergeAdjusts last param`只余默认功能开关，未保留之前的lut_intensity/outer CUBE参数。不能把“完整编码、bundle存在、没有CannotLoadScene”当成LUT已运行。

`full原生日志`（历史本机证据：`C:/JianyingAVQA/work/avlut-native-full-out-1028-v6/native.stderr.log`，未随源码分发）、`zero原生日志`（历史本机证据：`C:/JianyingAVQA/work/avlut-native-zero-out-1028-v6/native.stderr.log`，未随源码分发）、`独立复现JSON错误`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-v6-native-param-json-proof.json`，未随源码分发）、`两份timeline/log只读汇总`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-v6-native-export-review.json`，未随源码分发）。

### 19.3 有证据的下一候选

GUI官方保存的正常材料path原来使用C:/，导出materialization把compound路径前半改成Path默认的C:\形式。一个应先验证的单变量候选是：仅对任务自有导出副本的LUT compound两半使用正斜杠路径（Path.as_posix），不改变强度、启用位、版本、原包或source draft。让原生converter自行生成合法outer-path JSON，再要求：两份原生param均可解析，addLutEnableStatus不再报该错误，日志保留lut_intensity 1与0，并重新比较全部120帧。此处是在规范化原生资源路径，没有烘焙视频或替换原生参数。

本研究没有执行该候选，JSON错误修复是否足以让LUT产生显著像素差异仍待主线程独立实际出片，失败时不得放宽验收。cube包内algorithmConfig/config已读取留证，本轮不建议为处理该明确JSON错误而改写官方shader或猜更多flag。`v6 cube包配置`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-v6-cube-package-config-static.json`，未随源码分发）、`Feature.js实际输入映射`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-v6-shader-inputs-static.json`，未随源码分发）。


## 20. 自有 33³ SDR CUBE 已产生真实效果，独立参考仍未通过

以下原生出片和像素数字来自主线程真实实验，本研究只读复核媒体标签、timeline、日志和发布 DLL，没有调用 native、修改草稿、engine、ABI 或 shader。Windows 路径按 §19 修正后，自有 `mall-sdr-gentle-v1.cube` 的 native 强度 0/1 对全部 120 帧 MAD=6.714450/255，证明 LUT 确实参与出片；但与“对已解码 native0 再运行 FFmpeg lut3d”的独立标准参考 MAD=3.294258/255，超过原定 2，因此仍是 needs-inspection，不能把前一数字当作数学一致性通过。`主线程逐帧结果`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/custom-cube-native-pixel-proof-v1.json`，未随源码分发）

### 20.1 标签和 CUBE 范围没有发现不一致

实际源 S029、native0 和 native1 都是 1080×1920、H.264、yuv420p、limited/tv、BT.709 matrix/transfer/primaries、left chroma location。timeline color_space=0，原生导出设置日志也 color_space=0。自有 CUBE 的 DOMAIN_MIN=0,0,0、DOMAIN_MAX=1,1,1、LUT_3D_SIZE=33。这里没有“源 601、输出 709”或“源 full、输出 limited”的**标签差异**，更不能以 Alexa LogC 转换解释这份自有 SDR CUBE。标签一致仍不能证明 native 内部矩阵和实际数值转换一致。`源 ffprobe`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-source-ffprobe-v1.json`，未随源码分发）、`两份输出标签、材料和日志`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-color-review-v1.json`，未随源码分发）、`自有 CUBE`（历史本机证据：`C:/JianyingAVQA/work/custom-cube-data-1028-v1/mall-sdr-gentle-v1.cube`，未随源码分发）

主线程另做显式解码矩阵对照，BT.709 为 MAD=2.603625，BT.601 为 2.666723；两者仍超过 2。这里仅报告实际测量，不能据此选取较小值重新定义通过。`矩阵对照`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/custom-cube-reference-matrix-tests-v1.json`，未随源码分发）

### 20.2 真正 3D LUT shader 的静态采样候选

`cccreator.dll` 中导出的 `FeatureSegment::_generateLutFeatureScene` 是 preferred VA `0x1811a4040`，在 `0x1811a46e6` 调用 LUT shader/material builder `0x181aeede0`。后者创建 `LutXShader` / `LutMaterial`，按渲染配置对象的 +0x54/+0x55 分支选择下列三个已发布 shader 之一：

| shader 文本 VA | 静态输入处理 | 共同 LUT 采样 |
| --- | --- | --- |
| 0x1841eec70 | 去预乘，再于末尾预乘 | sampler3D；以 RGB 直接作为坐标 |
| 0x1841ef1b0 | 不做去预乘 | 同上 |
| 0x1841ef6a0 | 由 isInputTexPremul 控制去预乘/预乘 | 同上 |

三者都 clamp RGB；核心表达式为 `texture(inputImageTexture2, textureColor1.rgb)`，shader 中没有 `(N-1)/N` 缩放和 `0.5/N` 半 texel 偏移；后续使用 intensity 和可选 skin mask 混合。它们也没有显式 sRGB/linear 转换。这里已找到**当前原生 LUT scene 的正常 shader 构造链**，比旧 64³ tiled-2D shader 字串更相关；但仍需确认纹理上传的实际尺寸、filter/wrap 状态和 importer 是否预处理数据，不能只凭 shader 就断言 33³ 表被原样上传。`场景构造和 setPath`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-native-cccreator-setpath-static-v1.txt`，未随源码分发）、`调用者`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-lutx-shader-callers-v1.json`，未随源码分发）、`shader 选择分支`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-native-3dsampler-selection-static-v1.txt`，未随源码分发）、`三份原样 shader`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-cccreator-3dshaders-v1.json`，未随源码分发）、`发布库指纹`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-cccreator-fingerprint-v1.json`，未随源码分发）

标准 OpenGL 线性纹理取样在 texel 坐标中使用 `u-1/2`，而 FFmpeg lut3d 的表格插值使用 N−1 网格。因而**若** native 将原始 33³ 表直接上传到 linear/clamp 的 3D texture，raw normalized 坐标相当于 `33*x-0.5`，与标准网格 `32*x` 不同。这个条件化差异足以成为独立 identity/GL sampler 诊断候选，尚不能当作已证实误差原因；更不建议改 CUBE、shader、标准参考或阈值来让验收通过。[Khronos OpenGL 2.0 §3.8.8–9，公式 3.26](https://registry.khronos.org/OpenGL/specs/gl/glspec20.pdf)、[FFmpeg lut3d 源码](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavfilter/vf_lut3d.c)

已定位正常 AmazingEngine `AMGLutImporter.cpp` 路径：`0x18218ceb0` 调用 `LutUtil::loadLut` 对应 `0x182318090`，后者读取 TITLE、DOMAIN_MIN/MAX、LUT size 和 RGB 行。3D 分支调用 `0x1823176b0`，检查 RGB 行数恰为 N³，分配 8×N³ 字节，逐项转为 half-float RGBA（alpha=1），再传入 width=N、height=N 并通过真实导出 `Image::setDepth(N)` (`0x1810d5640`) 保存 depth；该构建阶段没有重采样、扩尺寸或补边。最终 GPU sampler 的 filter/wrap 状态本次尚未证明。`3D 体积构建`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-ae-volume-construction-static-v1.txt`，未随源码分发）、`逐项 half-float 写入和尺寸`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-ae-volume-f16-fill-static-v1.txt`，未随源码分发）、`setDepth 真实导出`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-ae-volume-exports-v1.json`，未随源码分发）。另有独立 `TELutTextureManager.cpp / readCubeLUT3DHalfRGBA`，但不能将两套 importer 混为同一个 active 实现。`AE importer 和 parser`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-ae-importer-parser-static-v1.txt`，未随源码分发）、`另一个 TELut parser`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-native-cubeparser-static-v1.txt`，未随源码分发）

主线程另一份独立诊断在 t=2 秒单帧对照中，标准网格 full-frame MAE=2.430272、flat-region MAE=1.979167；normalized-GL-33 模拟分别为 1.967856、1.410140。这个单帧结果支持采样坐标差异值得继续检查，但不是全 120 帧验收，更不是标准 CUBE 数学已经等价；原定标准参考结果仍保留。`单帧 sampler 诊断`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/custom-cube-native-sampler-reference-v1.json`，未随源码分发）

native 在原始渲染链中套 LUT，与在经过 H.264 / YUV420 输出后的 native0 上套 LUT，输入量化、chroma 抽样和空间重采样顺序也可能不同。这是有限候选而非已证实解释；主线程正在用同源无缩放、高码率和 identity 对照进一步隔离。本研究没有重复渲染这些任务，也没有把不能比较的输入链宣称为一致。

## 21. HSL interacting 的实际流向：不能凭字段名当作纯 UI

主线程正常 GUI 将自有 LUT 强度从 1 改成 0.55 后，除 LUT 字段外，唯一观察到的变化是 `materials.hsl[0].interacting` 从省略/default false 变为 true。真实修改已保存且 undo=true，严格 predicate 因此超时；没有重放原动作。该差异目前应单独留证，不能在缺少依据时广泛忽略。

静态证据显示：

- `RuntimeTransfer::TransferMaterialHslFromPersistentMaterialHsl` (`videoeditor.dll 0x180e788b0`) 在 `0x180e789c1..cb` 读取 persistent+0x50，通过正常 `set_interacting` 传入 runtime 材料。因此它确实进入 runtime，并非 parser 直接丢弃。`transfer 及 accessor`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-interacting-transfer-accessors-static-v1.txt`，未随源码分发）
- render DTO `pub::HslParam` 对应 parser `0x18189a560`、serializer `0x1818a4040` 也明确读写 interacting；serializer 从其对象 +0x28 取该 bool。这与 draft/runtime 的布局是不同结构，不能混用 offset。`DTO serialization`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-interacting-real-converter-static-v1.txt`，未随源码分发）
- 当前 scalar HSL builder `0x182bc0150` 按 stride 0x38 遍历另一种内部条目，读取 enum+0、custom_color string+8、hue/saturation/lightness int +0x28/+0x2c/+0x30，并生成 HSLRed_H/S/L 等键；该 builder 未读 +0x34。VideoCover 路径 `0x1814b0850` 直接调用它。另一组 pipeline 使用 `0x182b85bc0` 同族 builder。此处支持“正常 scalar 参数生成未观察到 interacting 参与数值”的窄结论，尚不证明整个默认色、自选色和预览路径都无画面意义。`scalar builders`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-scalar-param-builders-static-v1.txt`，未随源码分发）、`正常调用链`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-scalar-param-builder-callers-v1.json`，未随源码分发）、`VideoCover owner`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-scalar-builder-owners-static-v1.txt`，未随源码分发）

下一项有界证据应由主线程在任务自有导出副本上，仅对 interacting false/true 做同源原生出片并逐帧比较，保持数值、ID、资源和其他材料相同。只有实验支持零差后，才能把该具体版本、该默认色条目和当前路径的差异记录为非画面变化；无需回放已完成的 GUI 提交。本研究未执行该 native 对照，结论保持待验证。
