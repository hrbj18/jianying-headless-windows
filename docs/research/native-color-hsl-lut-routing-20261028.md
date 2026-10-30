# 原生 HSL 与 LUT：材料路由阻碍的只读定位

日期：2026-10-28。范围为本机剪映 `11.4.7.14462` 的发布 PE／JS 静态读取；本轮没有运行 CLI、原生 getter/setter、导入器、导出器，没有编辑工程或 engine，没有 computer use。REA native singleton 由音频研究占用，本轮没有切换其 target。

证据根目录为 `D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence`。本文件只报告静态实现及由此支持的新对照条件；是否真实生效以主线程的原生输出为准。

**LUT 路径说明已修正（2026-10-28 后续真实验收）：本文件原 `config.json;cube` 候选将前后两半用途误读。实际原生日志把 suffix 的 cube 当效果包目录并报 cube/config.json 不存在。正确静态合同为 `cube文件;效果包目录`；本文对应字段已改，下轮是否真正出片仍待主线程验收。完整修正证据见 `LUT/色轮研究第12节`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/docs/research/native-lut-wheels-editable-20261028.md`，未随源码分发）。**

## 最有价值的发现：非空 lumi_hub_path 会改变渲染链

`videoeditor.dll` 的 `lvve::AdjustUtils::segmentUseMergeAdjust`（`0x181012f30`）明确执行：

1. 获取当前 segment 的 `MaterialPictureAdjust`。
2. 读取其中的 `hsl` vector（`MaterialPictureAdjust::get_hsl`，`0x180651100`）。
3. 遍历每个 HSL 材料，调用 `MaterialHsl::get_lumi_hub_path`（`0x18015ba70`）。
4. **任何一条 HSL 的 lumi_hub_path 字符串非空，就立即返回 true，启用合并调色链。**

这不是由 `source_platform` 数字猜测的分支。代码先检查该路径是否非空，便足以改变路由。若使用旧 AMG HSL 包，却把 `lumi_hub_path` 也写成同一旧包目录，材料会走另一条链。应先以 `lumi_hub_path:""` 做严格单变量原生渲染对照，保持 `path` 指向原旧包、八色整数参数与各引用／开关不变。

普通 `MaterialEffect` 也有同类判断：helper `0x181012e10` 调用 `MaterialEffect::get_lumi_hub_path`（`0x1801d9be0`），其长度非零即返回 true。因此 LUT 候选材料同样不应将 compound path 填到 lumi_hub_path。

证据：`native-segment-use-merge-adjust-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-segment-use-merge-adjust-static.txt`，未随源码分发）、`native-ordinary-material-use-merge-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-ordinary-material-use-merge-static.txt`，未随源码分发）、`hsl-lut-native-exports.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-lut-native-exports.json`，未随源码分发）。

## HSL 的 raw 材料格式与渲染内部编号

`PersistentMaterialHsl` 的 RapidJSON `from_json`（`0x180cc1e20`）确实读取以下字段：

```text
id, constant_material_id, hsl_color_type, hue, saturation, lightness,
interacting, version, path, type, lumi_hub_path, custom_color,
resource_id, source_platform
```

其中颜色编号与 hue/saturation/lightness 最终存为 int。这个持久化材料 parser **没有读取 hsl_params**；hsl_params 是动作／参数 DTO 的另一层，不能通过把 raw `materials.hsl` 改名为 hsl_params 修复。`visible` 也未出现在这一持久化 HSL parser 中；Web schema 多出的 visible 不应被当成这里的必需项。

材料层与渲染内部层的编号需要区分：

- `IHslAdjustUtils` 的默认颜色选择逻辑把输入减 1 再检查 0..7，支持 UI 材料侧 1..8。
- `cccreator.dll` 的 `CCColorHslFilter::updateHslParamsStr`（`0x180ab1490`）静态初始化 map 为 **0 红、1 橙、2 黄、3 绿、4 青、5 蓝、6 紫、7 紫红**，并生成 HSLRed 等旧 vec3 事件。
- 尚未完成 `MaterialHsl → HslParam` 的减 1 转换定位。因此这项内部编号发现不能直接证明 raw 材料必须用 0..7，也不能把先前 1..8 的材料判为错误。清空 lumi_hub_path 是证据更直接、变量更少的优先对照。

`updateHslParamsStr` 遍历每个 HslParam 的恰好三个整数，归一化后构成 vec3；该实现未见按 version 生成 `HSLRed_H/_S/_L` 标量事件的分支。这进一步说明“version=1 自动适配 hsl_v1”的猜测不成立。这个渲染类是否就是主线程材料最终采用的类，仍应通过实际输出验证。

证据：`native-persistent-hsl-json-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-persistent-hsl-json-static.txt`，未随源码分发）、`hsl-native-utils-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-native-utils-static.txt`，未随源码分发）、`cccreator-hsl-render-params-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/cccreator-hsl-render-params-static.txt`，未随源码分发）。

## LUT：最小候选字段与真正的运行时 flag

本机 `PersistentMaterialEffect::from_json`（`0x180cada30`）是 LUT 共用的效果材料 parser。它比 Web jF0 类 schema 多读取 visible、report_name、category_key/sub_category 等本机字段。缺省 visible 明确为 true，item_effect_type 缺省为 0，platform 缺省为 all；不能把 Web 类字段表当成本机完整结构。

从当前实现可复原以下**最小实验候选**，尚不能称为已验收最小 schema：

```json
{
  "id": "新的UUID",
  "type": "lut",
  "path": "完整外部测试.cube路径;完整本地LUT效果包目录",
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

它放在权威主时间线的 `materials.effects` 中，片段 `extra_material_refs` 引用其 ID，同时保留 `enable_lut:true` 与 `enable_adjust:true`。这些是持久化引用／开关；不是额外伪造 `materials.lut` 数组。

渲染转换时 LUT 的 `flag=1` 由材料 type==LUT 自动设置，不是要求把 `flag:1` 塞入持久化 MaterialEffect。item_effect_type 是另一字段，不能拿它代替原生 filter flag。value 进入强度参数；`enable_skin_tone_correction` 决定另一个算法开关，关闭它有利于把第一轮 LUT 对照限制为查找表本身。

证据：`native-persistent-effect-json-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-persistent-effect-json-static.txt`，未随源码分发）、`lut-selected-modules.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-selected-modules.json`，未随源码分发）、`static-schema-snippets.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/static-schema-snippets.json`，未随源码分发）。

## LUT compound path 的首段需要什么文件

已定位的原生函数 `0x182b7cb90`，在 type==14（LUT）分支把分号后半作为 FeatureSegment 包路径，前半作为 feature_outer_lut_path；前半另取最后一个 `/` 之前的目录，再读取该目录的 `config.json`。`AdjustUtils::fixLutPath` 对首段做 `_access(path,0)` 存在检查。

因此，首段应选真正的 CUBE 文件，后段选本身含 config.json 的合法 LUT 效果包目录。此前把首段当 config.json、后段当 CUBE 的建议错误，已撤销；不能继续作为后续实现依据。

实验候选为：

```text
D:/.../owned-package/owned-test.cube;D:/.../owned-package
```

分号前后不加空格，路径使用 `/`。这只是静态支持的输入，仍需检查保存后的材料与明显的原生像素变化。LUT 数学效果来自测试 CUBE，不得以 FFmpeg/OCIO 烘焙画面代替原生 LUT 验收。

证据：`native-adjust-from-cover-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-adjust-from-cover-static.txt`，未随源码分发）、`native-fix-lut-path-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-fix-lut-path-static.txt`，未随源码分发）、`fix-lut-path-check-helper-annotated.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/fix-lut-path-check-helper-annotated.txt`，未随源码分发）。

## 官方 CLI 的静态范围

从项目的 `draftediting_worker.mjs` 与安装文件清单核对到真实路径为安装根 `lyra-cli.exe`，另有 `lyra_cli_client.dll`；不是猜定的 canvas_agent/cli 子目录。两者有 draft video adjust／HSL 参数及帮助文本，但本次静态字串没有发现可复用的 LUT、LUTS、enable_lut、lut_path、.cube、.3dl 命令契约。没有运行 CLI，也不能把这个未发现结论扩展成“原生无 LUT 功能”。

官方 Qt 原生 importer 与 ICoverFetcherEditor 确实存在；本次仍以它们的静态实现支持材料实验。不能假称已获得现成 CLI CUBE importer。

证据：`cli-pe-color-strings.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/cli-pe-color-strings.json`，未随源码分发）、`draftediting_worker.mjs`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/engine/draftediting_worker.mjs`，未随源码分发）。
# 最新原生实测修正：HSL 必须采用合并调色资源（主线程，2026-10-28）

此前 `lumi_hub_path` 的静态分流分析只能说明走了哪条渲染链，不能证明清空它就是修复。主线程现已完成决定性对照：SDK 使用正确原生枚举 `69` 创建八个 version 1 HSL 节点；分别使用独立 `hsl`／`hsl_v1` 包、并清空 `lumi_hub_path`，即使日志生成了 `HSLRed_H/S/L` 参数，八色全部 `saturation=-100` 仍未得到去色画面。

将 HSL 的 **`path` 与 `lumi_hub_path` 均绑定本机原始 `Resources/DefaultAdjustBundle/merge_all_adjust_color`** 后，原生 ExportService 实际输出严格灰度。主线程像素证据：`JOB/hsl-native-merge-pixel-proof.json`，`mean_chroma=0`、`gray_fraction=1`；同时已查看实际输出帧。出片位于 `D:/JianyingHeadless/work/avhslm-20261028-v4/render.mp4`。所用原始资源共 348 个文件、约 1.27 MB，树摘要前缀 `d3a4a845`。

因此，当前版本已验证可行的是原生 **merge_all_adjust_color 合并资源链**。不得继续把旧包加空 `lumi_hub_path` 推荐为有效修复；也不能将“编码成功”或“日志有 HSL 标量”当作 HSL 生效。GUI 调色模型的加载及 undo/save 路径是另一项仍需独立验收的能力。

