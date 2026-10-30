# Windows 本机高级调色：原生 schema 与本地资源

日期：2026-10-28。目标版本：已安装剪映 `11.4.7.14462`。本次仅静态读取发布 JS、Lua、GLSL、配置和主线程输出的权威草稿 fixture；未执行编辑、未打开或控制界面、未运行发布 JS、未修改 engine 或安装资源。资源存在与 schema 明确均不能替代实际渲染及可编辑性验收。

## 关键结论

1. **本机有完整 HSL、曲线、色轮、色温的本地资源包**，远端 HSL 资源下载失败不等于本地没有 shader。可优先在独立草稿探测本地资源路径绑定；是否可用仍须原生预览、导出、保存和再修改证据。
2. `color-temperature` 是 CLI 参数名，不是原生材料 type。本机 Persist enum 明确 `temperature`，色调材料 type 为 `tone`，LUT 为 `lut`。CLI 落成 `type:none` 的结果应拒绝，不能当成功；修正字段必须以副本差分验证，不猜 ABI。
3. 色彩曲线的点**不是简单 x/y 数组**：每个点具有锚点和左右 Bézier 控制点。已找到本机的原生 JSON 字段和转成 shader 参数的完整顺序。
4. HSL 旧包与 `hsl_v1` 使用不同事件协议，不可仅改路径混用。原生数值到旧 shader 的实际转换为 `0.005 * value + 0.5`；把 `0.3` 存进原生材料只相当于很小的滑杆量，不应自动理解为“30”。
5. `Resources/lut` 只有配置，没有现成 LUT 数据。已找到 LUT 参数路由，但**未找到可直接复用、并已在本机验证的 CUBE 导入／原生材料样例**，不宣称已经接通。

## 证据身份

本机资源根：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462\Resources`。

发布 JS 通过 reverse-engineer-anything 的只读 `analyze_javascript_application` 分析，未执行 bundle：

- `ai-creation~8.7b43c1ad.js`：REA parent Evidence `ev_4c12a2d28af248d6e8dfc1ecc95bb0b0ce50b201686e1bddc4673334d1832440`。
- `ai-creation~6.6c54528c.js`、`~11.fe7840fa.js`、`~5.38151757.js`：REA parent Evidence `ev_ed385de5e24e6f1b9c9647159c46aa426bd63b1218fdddc6fa631c891f74930b`。
- 分析只选择上述源码；其它来源、动态调用和超出语义保留上限的图关系仍是 unknown。静态图不证明代码在本次运行中被执行。

私有证据目录：`D:\JianyingHeadless\integrations\research-native-color-audio-20261028\local-color-evidence`。

- `resource-manifest.json`：资源所有文件的字节数与 SHA256。
- `source-identity.json`：四个发布 JS 的 SHA256。
- `static-schema-snippets.json`：下文模块的源文件、字符区间及有限摘录。
- `rea-js-schema-summary.json`、`rea-js-converter-summary.json`：REA 返回的 summary，包括覆盖与限制；完整 parent 记录仍由 REA 保留。

## 已有本地资源包

| 相对资源根路径 | 文件数 | tree SHA256 |
|---|---:|---|
| `Curves` | 28 | `b5b5b8825e7d714f589e8ceab25ef7a8d45282998aa277bff3212b5d362b8b7e` |
| `DefaultAdjustBundle/hsl` | 18 | `8e7593de75e66402a48fc48811224058cef8075b4e25bc90b38802ce7c97eca6` |
| `DefaultAdjustBundle/hsl_v1` | 18 | `841ef7738820dbf65ba165406f48c2212d861130e17c3c78ad981a6ae4d5cd8f` |
| `DefaultAdjustBundle/temperature_tone_v3` | 13 | `56021dad0238587f85577f88003d8fe5f54f98a7069d5e845e5cd09b6672e26a` |
| `PrimaryWheel/primary_wheel_v0` | 15 | `23daa33492a87257e1d1e1172494f0e69b52ca7518e473771e8ec271baf9ec51` |
| `PrimaryWheel/primary_wheel_v1` | 15 | `d4d52e6bc046afbf3ed0b21da378d54ae9e6ced4fbf573315619ee764d596649` |
| `LogWheel/log_wheel_v0` | 15 | `cbb03bcbcb6aa9e6991dddccc01f4e4eb961ecbe4c794f24ca1bafa52432033c` |
| `LogWheel/log_wheel_v1` | 15 | `81ea47d64bdeb721f86c15be8c981cf83bf25c3f14515b287b0016b465d5a9ed` |
| `lut` | 2 | `3a72e68c91a63efb30824fe983a8aebcb4e7d67252aedb750804ff744ad3dc91` |

tree hash 算法仅用于本研究标识：相对 POSIX 路径映射到 `{sha256,bytes}`，按键排序，以紧凑 JSON UTF-8 编码后 SHA256。正式接入若使用项目已有 tree manifest 算法，应重新生成，不可把不同算法的摘要混比。

包内配置实际指向 `AmazingFeature` 的 scene、Lua、材质和 shader。`Curves` 的 zorder=5010，PrimaryWheel=5011，LogWheel=5012，HSL=10010，色温 v3=8011，lut=2000。它们是现有正版安装资源；不需要改写安装目录，不由资源存在推导任意再分发许可。

## 原生 type 的明确映射

`ai-creation~5.38151757.js` 的 Persist meta enum 直接给出：

| 语义 | 原生 type 字符串 |
|---|---|
| HSL | `hsl` |
| 曲线 | `color_curves` |
| 主色轮 | `primary_color_wheels` |
| Log 色轮 | `log_color_wheels` |
| 色温 | `temperature` |
| 色调 | `tone` |
| LUT | `lut` |

另一处运行时 enum 使用数字（如 HSL=56、Curves=57）；不能将数字直接替代上述持久化字符串。

已读取主线程 `color-controls-v2-authoritative.json`：brightness、contrast、highlight、shadow 各自落成正确 type，而 color-temperature 对应材料为 `none`。`color-hsl-v2-authoritative.json` 未产生 HSL 材料、片段 enable_hsl 仍为 false，与主线程远端下载失败一致。因此这两个 fixture 没有证明高级调色成功。

## 色彩曲线的真实结构与 shader 参数

`~8` 模块 22044 给出材料共同字段：`id,type,panel,resource_id,source_platform,path,lumi_hub_path`，以及 `luma,red,green,blue` 四个数组。

`~6` 模块 98413、16518 给出点结构：

```json
{
  "sync_direction_control": true,
  "anchor": {"x": 0, "y": 0},
  "left_control": {"x": 0, "y": 0},
  "right_control": {"x": 0.3, "y": 0.3}
}
```

`~11` 模块 43731 的函数 M 把原生点数组展平：首点取 anchor、rightControl；中间点取 leftControl、anchor、rightControl；末点取 leftControl、anchor。空通道会使用恒等控制值 `(0,0),(.3,.3),(.6,.6),(1,1)`。因此两个锚点会产生四个 Vec2，三个锚点会产生七个 Vec2。

本地 `Curves/Curves/lua/SeekModeScript.lua` 接收：

- `yPoints/rPoints/gPoints/bPoints`：相应 Vec2 平铺后的 float 序列。
- `yPointsCount/rPointsCount/gPointsCount/bPointsCount`：Lua 用 `(count+2)/3` 转成锚点数量。
- `intensityY/R/G/B`：四个通道强度。

对应 `Curves/Curves/xshader/curveLut.frag` 以 `controlPoints`、`pointsNums` 求 Bézier 曲线，并按像素 x 反求 t；这为控制点协议提供第二层静态证据。

绑定候选是原生 `materials.color_curves` + 片段对应引用／enable_color_curves，并把 path 指向完整的本地 Curves 根包。是否需要额外资源注册、lumi_hub_path 处理或可见性字段，仍须实际引擎验证；本报告不凭 shader 文件存在擅自放开门禁。

## HSL 的八通道及版本差异

`~8` 模块 32047 明确 HSL 材料字段：`id,constant_material_id,hsl_color_type,hue,saturation,lightness,interacting,version,path,type,lumi_hub_path,custom_color,resource_id,source_platform,visible`。

`~5` 明确颜色通道：1 红、2 橙、3 黄、4 绿、5 青、6 蓝、7 紫、8 紫红，0 为 unknown。

`~11` 模块 43731 的函数 D 将每个原生 hue/saturation/lightness 变为 `0.005*value+0.5`；再以 `HSLRed` 等颜色名形成 vec3。旧本地 `hsl/HSL/lua/SeekModeScript.lua` 正好接收该 vec3，将 `(component*2-1)*100` 写到 `hsl_param_0..7`。

因此该已观察的 Web 渲染路径在原生值约 -100..100 时覆盖 shader 的 -100..100。CLI help 的“unitless scalar”不承诺把 0.5 解释成 50；本机 C++ 路径的确切量纲仍需保存值和大幅度对照共同确认。

`hsl_v1` 使用不同 Lua：事件为 `HSLRed_H`／`_S`／`_L` 等单个标量，而非旧包 vec3；它增加最多 10 个用户自选色。事件值先作 `(v*2-1)*100`；用户自选色的 H/L 又乘 .3。**不能在相同 params 下只替换 hsl 为 hsl_v1 就宣称兼容。** version 字段与实际分发协议必须一起验证。

开源 [duckyman-ai add-color.py](https://github.com/duckyman-ai/agent-skills/blob/main/skills/capcut-editor/scripts/add-color.py) 给出原生 HSL 绑定的可读实现，但引用 Mac CapCut 缓存，不能替代本机版本验证；其 hue 参数注释与本机渲染映射也不能不加区分地混用。

## 色温、色调与两套色轮

本地 `DefaultAdjustBundle/temperature_tone_v3/AmazingFeature/lua/Lscript.lua` 接收 `temperature_intensity` 和 `tone_intensity`：前者 x 对应 `6500 - 1970*x + 876*x² - 2630*x³`，后者乘 100 得到 ColorTones。`~11` 的映射函数 A 对 Temperature/Hue 分别使用这两个事件名。另一个版本函数 y 在空版本或 v1 时回退通用 `intensity`，说明版本也可能影响参数路由；实际 C++ 路径不能仅凭包名 `_v3` 猜定 version 值。

`~8` 模块 61213/6445、`~6` 模块 17067 给出：

- Primary：`lift,gamma,gain,offset,intensity`。
- Log：`shadow,midtone,highlight,offset,intensity`。
- 每个轮对象的原生字段包括 `red,green,blue,luma,saturation`。

`~11` 将 RGB 通道夹在 -1..1，再转为 `LiftR/G/B`、`GammaR/G/B`、`GainR/G/B`、`OffsetR/G/B` 等 Lua 参数；Log 分支使用 `Shadow*`、`Midtone*` 和拼写为 `Hightlights*` 的高光参数。静态字段存在不代表所有通道都被该渲染路径转发，例如这段 Web helper 没有简单透传 luma。应从 RGB 单变量差分开始，保留正确 luma 与强度的后续验证。

## LUT：已知与未知

Persist type 为 `lut`，采用通用效果材料而非 HSL／曲线点数组。`~11` 转换分支设置 LUT flag，并使用 `feature_enable_alg`、`feature_outer_lut_path`；`enable_skin_tone_correction` 会影响前者。函数 P$ 对记录路径取父目录，这提示路径可能指向一个包含 LUT 数据的资源结构，而不是任意把 `path` 写成 CUBE 文件即能加载。

本地 `Resources/lut/config.json` 声明 `AmazingFilter`、`alphaState:2`、`bALG_BACH_CONFIG:true`，还列出 `tt_skin_seg` 模型；algorithmConfig 包含 external texture producer、skin segmentation 和 texture blitter。该目录只有这两个配置，没有 CUBE 或转换后的查找表数据。

本次没有找到被当前引擎真实保存并渲染的本地 CUBE LUT fixture，也没有执行导入。可进一步研究原生导入如何生成 LUT 资源目录、记录路径和模型开关；不能凭 `type:lut` 或通用 OpenColorIO 生成结果就算接通。外部 FFmpeg/OCIO 对照可以验证 LUT 的数学效果，但导入烘焙视频不证明剪映 LUT 参数仍可编辑。

## 建议的独立探测顺序

1. 从原生 type 已明确、无远端资源依赖的色温材料开始，对同一原片做 identity／正／负值三组副本。保留本地包完整字节与 manifest；确认不是 type:none。
2. 使用旧 hsl 包及匹配的八通道协议，先做红色饱和度明显变化的对照；确认原生 HSL 材料、引用和开关都保存，并在剪映再修改后重出片。
3. 按本机 Bézier 点结构建立 identity／非线性曲线。以灰阶测试图检查单调性、端点、是否实际改变像素，再在实拍上评估。
4. 色轮与 LUT 各自单独验收。不能将前三项成功的结论扩展到它们；不能把本地资源包 hash 与其它构建或缓存版本替换后沿用旧验收。

上述为静态证据支持的下一步实验设计，不是本次已执行的操作。

## 补充：独立原生服务的 typed 动作入口

对发布物的进一步只读定位找到 `edit` 域的 **`video.setBasicColor`**，以及 `adjustment.setBasicColor`。`app-server.mjs` 的许可方法表列出它们；`ai-creation~3.fbc221b2.js` 的 video API 和 adjustment API 均构造模块 57104 的同一个 action。未找到独立 `video.setHsl`／`video.setColorCurves` 方法，不能以猜测名称调用。

模块 57104 读取的参数结构为：

```json
{
  "segId": "实际视频段 UUID",
  "materials": [
    {"type": "某种调色材料类型"}
  ],
  "presetResourceId": "",
  "isKeyframe": false
}
```

`materials` 为复数数组；action 为每个材料执行模块 44437 的 SetPictureAdjust 行为。以下是**静态代码明确读取的输入结构**，尚未由本子任务调用运行时或证明出片：

### HSL

```json
{
  "type": "hsl",
  "hslParams": {
    "hslColorType": 1,
    "hue": 30,
    "saturation": -50,
    "lightness": 20,
    "path": "本机完整 HSL 资源包根目录",
    "visible": true
  }
}
```

HSL 的本地路径读取自**内层 `hslParams.path`**。模块 44437 新建原生 HSL 材料，并更新／增加相应颜色通道；其 HSL controller `getVersion()` 固定返回 `String(1)`，因此 action 自动写入版本 `"1"`。这条路径不需要由调用方臆造资源 ID；具体本地包版本与参数协议仍需主线程出片验证。

### 曲线

```json
{
  "type": "color_curves",
  "colorCurvesParams": {
    "panel": "",
    "resourceId": "",
    "path": "本机 Resources/Curves 根目录",
    "luma": [
      {
        "anchor": {"x": 0, "y": 0},
        "leftControl": {"x": 0, "y": 0},
        "rightControl": {"x": 0.3, "y": 0.15}
      },
      {
        "anchor": {"x": 1, "y": 1},
        "leftControl": {"x": 0.6, "y": 0.85},
        "rightControl": {"x": 0, "y": 0}
      }
    ],
    "red": [], "green": [], "blue": []
  }
}
```

输入点使用 **`leftControl`／`rightControl`（camelCase）**；持久化草稿才使用 `left_control`／`right_control`。`~4.b708b52d.js` 的 `create…FromPlain` helper 及 `~13.7a331c10.js` 模块 44437 的转换代码相互吻合。该 action 从内层 `colorCurvesParams.path` 读路径，遍历四个通道，直接构造原生曲线材料并写入 segment delta；所读静态实现未见在线资源解析步骤。

### 色温／色调及普通调节

普通分支使用材料的外层字段：`type`、`value`、`path`、`version`、`sourcePlatform`、`categoryId/categoryName`、`name`、`formulaId`、`enableSkinToneCorrection`。例如色温类型为 `temperature`，色调为 `tone`；本地资源路径放在**外层 `path`**。`setPictureAdjust` 明确将这些字段写入相应材料，而不是将 CLI 参数名作为持久化 type。

注意资源包名称 `_v3` 不足以证明 action 的 version 应写哪一字符串，不能把待验证的版本填写方式当成已知。应优先复用主线程已经运行成功的 service 会话和操作信封，只替换上述明确参数，检查权威嵌套主时间线、实际像素与后续编辑。

该发布 JS 的 `updateColorWheelsParam` 是空实现；这只能说明所读 Web 路径没有完整实现，不能据此判断独立原生 addon 的色轮能力。不要把 HSL／曲线动作的成功推广为色轮已成功。

## HSL 版本分支的复核（避免错误推断）

后续主线程真实对照发现旧 hsl 包配合 `version:"1"` 的像素差异很小，要求复核是否存在“版本 1 发标量，版本 0 发 vec3”的具体分支。本次再次静态搜索整个 `canvas_agent` 发布 JS：

- `hslVer` 只在 `ai-creation~11.fe7840fa.js` 出现一次，位于函数 D 的返回对象。
- 调用者在约字符偏移 138597 处调用 D，但仅取 `hslPath`、`extraParams`、`hslVisible`；没有读取 `hslVer`。
- D 对所有版本始终生成 `HSLRed:[.005*hue+.5,.005*saturation+.5,.005*lightness+.5]` 等旧 vec3 格式。
- 因此，**这份 JS 不能证明 ExportService 内部按 version 选择标量／vec3 协议**。它能证明两套本地 Lua 的事件协议确实不同，不能证明 C++ 导出路径采用哪个分支。

保持其它参数、源区间和开关不变，比较旧 hsl 与 hsl_v1 包、以及版本值的独立变量，才可取得本机运行证据。`version:"1" + hsl_v1` 是由本地包及版本信息支持的实验候选，不能在实际像素对照前宣称修复成功。

另一次对 service JS、typed action 与客户端常用代码的静态查找，没有发现明确的 `setLut`／`importLut`、CUBE path 参数或已实测 `--resource local://cube` 绑定实现。本结论只表示未取得可复用的确证，不表示该功能不存在。

## 原生 Qt HSL 元数据复核

本节为只读静态解析安装包 `VECreator.dll` 的 Qt revision 10 元数据与 LLVM 反汇编，没有加载 DLL、附加进程或调用这些方法。证据保存于 `hsl-qt-decoded-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-qt-decoded-static.json`，未随源码分发） 和 `hsl-qt-handlers-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-qt-handlers-static.json`，未随源码分发）。

真实类型为 `AdjustHSLSettingData` 与 `AdjustSettingHandleViewModel`，没有找到名为 `HSLSettingHandler` 的独立 Qt class。前者 `hslColorType` 为 `int`，其 hue/saturation/lightness 为 `ParamSettingSliderData*`；customColor 为 QString，另外有 constantMaterialId、enableState。后者 hslData property 指向这一模型，提供以下普通 slots：

| 本地索引 | 名称与参数 | Qt dispatch 确认的目标 VA |
|---|---|---|
| 88 | `resetHsl()` | `0x1837a6d10` |
| 89 | `acceptHslColorType(int type, QString color)` | `0x183793770` |
| 90 | `acceptHslSaturation(int value, bool record, bool shift)` | `0x183793c70` |
| 91 | `acceptHslHue(int value, bool record, bool shift)` | `0x183793a70` |
| 92 | `acceptHslLightness(int value, bool record, bool shift)` | `0x183793b70` |
| 93 | `setHslEnabled(bool enable)` | `0x1837ac530` |

元数据本身没有 HSL 颜色枚举；不能从 int property 推导每个颜色的数字。`acceptHslColorType` 的汇编在 `type==9` 时使用埋点 `customize_color`，否则使用 `color`。这与已知 Web `unknown=0, red=1..magenta=8, custom=9` 相容，**没有发现支持“全部颜色编号偏移”的证据**，但也不构成原生八色逐项映射的完整证明。`accept-hsl-type-saturation-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/accept-hsl-type-saturation-static.txt`，未随源码分发）

安装包的 `MaterialHsl::get_hue/get_saturation/get_lightness/get_hsl_color_type` C++ 签名返回 `const int&`；`lvve::preset::HslParamInfo` 构造器也是四个 int 与字符串。实际草稿若用 JSON 浮点数，是否会自动转换还取决于原生 JSON coder；应做整数对照，不能仅凭签名认定浮点数导致失效。

这些 slots 可以作为后续原生行为定位线索；**没有证据证明仅创建同名对象便具备合法当前 segment、undo 和编辑 context**。本次没有尝试调用，不建议把它们当作独立 editor API 直接执行。

只在任务关联的 `live-edit-v01/research`、当前 repo tests 与当前 `native-av-upgrade` 工作根检索明文 JSON。旧研究／tests 未发现 UI 真实产生的非空 HSL 材料样例；当前工作根的命中均为本次生成的对照 timeline/runtime，不应循环用作正确 schema 的独立证据。没有扫描其它用户工程。

## LUT 通用材料、原生导入器与复合路径

`ai-creation~8.7b43c1ad.js` 模块 88087 的 `jF0` 为 LUT 使用的通用效果类，持久化 `materials.effects`，而非单独的 `materials.lut`。其完整 schema：

```text
common:
 id, effect_id, resource_id, third_resource_id, name, type, sub_type,
 path, value, category_id, category_name, platform, apply_target_type,
 source_platform, version, formula_id, enable_skin_tone_correction,
 algorithm_artifact_path, intensity_key, panel_id, request_id,
 multi_language_current, lumi_hub_path, covering_relation_change,
 color_correct_alg_result
bigint: item_effect_type
array: adjust_params, face_adjust_params, exclusion_group
object(nullable): time_range, bloom_params, color_match_info
```

构造默认 `id=uuid, effectId/resourceId/thirdResourceId/name/path/version/formulaId/algorithmArtifactPath/intensityKey/panelId/requestId/lumiHubPath/colorCorrectAlgResult=""`，`type=none, subType=none, value=0, itemEffectType=0, platform=all, applyTargetType=0, sourcePlatform=EffectPlatformLoki(0), enableSkinToneCorrection=false, multiLanguageCurrent=none, coveringRelationChange=Unknow`，三组数组为空。输入 camelCase，原生序列化 snake_case。`~13` 模块 44437 `setPictureAdjust` 直接复制 type/path/value/version 等字段，没有在这段函数里导入 CUBE。`lut-selected-modules.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-selected-modules.json`，未随源码分发）

`~14` 的调色反序列化与写回辅助函数把 `type:lut` 放入 `effects`、把材料 ID 放入 `extra_material_refs`，并复制片段的 `enable_lut`。`~11` 渲染转换分支设置 LUT `flag=1`，将 value 写为 `param.intensity`，写入 `feature_enable_alg=enableSkinToneCorrection` 与 `feature_outer_lut_path=res`。**`P$` 已明确只是正斜杠 dirname：**

```js
function E(e) {
  var t=e.lastIndexOf("/");
  return -1!==t ? e.slice(0,t) : "";
}
```

所以未规范化的 Windows 反斜杠路径在这一 Web helper 中得到空字符串。该 helper 只能证明这里取父目录，不能证明 native ExportService 接受任意 CUBE 文件路径。

本机 `VECreator.dll` 包含真正的 LUT 导入器。原生 UI 文案／过滤器包含 `.cube/.3dl`、`*.cube`；存在 `import::CreateLUTImporterImpl`、`import::ReadImportLUTDataFromFile`、`LutImportCfg.json`，以及 `[ParseToImportResult] lut_adjust.path: %s, %d` 日志。精确 Qt 签名为：

```text
LutCategoryInfoViewModel::importFiles(QQuickItem* dropArea, QList<QUrl> urls)
LutCategoryInfoViewModel::clickedLutImport()
LutImportInfoViewModel::clicked(QQuickItem* sender)
import::LUTImportObserver::sigImportFinished(LUTImportItemResult& results)
```

`importFiles` 是 local method 12，`clickedLutImport` 是 14。后者会进入文件选择流程，不符合本任务无 CU 的直接执行目标；前者是否允许 dropArea=null、是否要求现有视图模型／资源面板 context，仍未知，不能盲调。`lut-qt-decoded-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-qt-decoded-static.json`，未随源码分发）、`native-hsl-lut-strings.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-hsl-lut-strings.json`，未随源码分发）

更关键的是，`videoeditor.dll` 明确导出：

```text
lvve::AdjustUtils::fixLutPath(shared_ptr<MaterialEffect> const&, std::string const&)
VA 0x181011b20
```

该函数读材料路径后查找 `0x3b` 分号；分隔路径并重新组合。可以确定原生路径处理认识分号形式；“效果包路径;LUT 文件路径”仍只是有依据的候选，分号前后含义必须通过 importer 输出或真实草稿核对。不能在没有出片差分前把 path 指向普通 `.cube` 当作接通。`native-fix-lut-path-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-fix-lut-path-static.txt`，未随源码分发）

`VECreator.dll` 的 `import::ParseToImportResult` 静态函数为 `0x1865c1050..0x1865c23f2`，通过实际 SDK 对象的 vtable `+0x60/+0x78` 取得结果路径，并记录 `lut_adjust.path`；本次没有解出可脱离对象生命周期安全调用的 ABI，不做运行时尝试。`lut-native-import-parser-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-native-import-parser-static.txt`，未随源码分发）

这些证据全部来自合法本机发布物静态读取，不是可再分发的开源实现；安装包原生资源不得因为本报告而被视为开源授权。开源代码、标准 CUBE 测试数据和外部 OCIO 可作对照；能否保持剪映原生 LUT 参数可编辑，应以原生材料保存、明显画面差分、重载与再改参数共同验收。

## 当前编辑页的只读 HSL 绑定定位

按主线程指定，在 PID `26164`、birth `134375592292885847` 仅用 `OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_LIMITED_INFORMATION)`、`VirtualQueryEx`、`ReadProcessMemory` 搜索精确 vtable。没有 Frida attach、DLL 注入、运行 Qt getter、setter、点击或编辑。安装的 VECreator SHA256 与正式 profile 一致；本次模块基址 `0x7ffbaa840000`。运行时地址只适用于这个进程代际，不能写入长期 ABI profile。

RTTI 确认 `AdjustSettingHandleViewModel` primary vtable RVA `0xbfef5b0`，`VENotifyListener` 子对象 `+0x10` vtable RVA `0xbfef610`。`AdjustHSLSettingData` 的普通／QQmlElement vtable RVA 为 `0xb4a4178`／`0xb4a7e80`。精确扫描未找到这些活跃对象，也未找到相应 `VideoAdjustSettingViewModel` 外层模型。阳性对照能找到当前 video、video_basic 和 manager，证明搜索正常；因此**当前不能给 HSL slots 绑定一个已验证对象地址**。这也不能被解释成原生 HSL 功能不存在，可能尚未实例化调色面板模型。`hsl-rtti-vtables-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-rtti-vtables-static.json`，未随源码分发）、`hsl-active-readonly-scan.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-active-readonly-scan.json`，未随源码分发）

`AdjustSettingHandleViewModel` 的只读属性布局由 Qt ReadProperty dispatch 确认：`isMultiSelect +0x18`、`adjustEnabled +0x50`、`hslData +0xd8`、`enableHslChroma/Keyframe/Compare +0xe0/e1/e2`、`isAdjustMergeResourceLoaded +0x138`。本次实例缺席，故没有这些属性的运行时读值。

静态调用链确实把视频设置模型的选择绑定给 handler：

1. `VideoAdjustSettingViewModel` 的 `VideoSubSettingViewModel` 子对象偏移 `+0x10`。更新函数 `0x18332f780` 将 settings shared_ptr 放在子对象 `+0x20/+0x28`，即 primary `+0x30/+0x38`；handler 指针为 primary `+0x40`，与 `handleViewModel` Qt getter 相符。
2. 更新函数读取 settings 对象 `+0x8` 的 `std::vector<std::string>`，传入 `AdjustSettingHandleViewModel::updateSegmentData`（`0x1837b2910`）。
3. 后者遍历这些 segment ID，经当前 `IQueryUtils::get_segment` 获取真实 Segment，构造 `SegmentHolder`，保存在 handler `+0x1b8` 的 vector（每项 `0x148` 字节）。IAT 的读取地址已被只读运行时解析为 videoeditor.dll 对应导出，不是仅凭汇编猜函数名。
4. `acceptHslColorType` 等槽通过普通调色组合动作调用 `lyra::Server::draftCombo`。这提供当前选择与原生撤销动作的静态依据，仍需活跃模型、唯一选择和草稿 journal 共同保护实际执行。

`ViewVisiableChanged(bool)` 只写可见性并通知 `adjust_panel_visible_changed`，没有在这个函数中构造 handler。不能把调用可见性通知当成完成初始化。`adjust-update-binding-callers.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-update-binding-callers.txt`，未随源码分发）、`adjust-binding-data-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/adjust-binding-data-static.txt`，未随源码分发）、`runtime-iat-readonly.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/runtime-iat-readonly.json`，未随源码分发）

上述外层布局不能套用到 `VideoBasicSettingViewModel`。对该假设的只读候选检查未通过 vector/UUID 校验，没有得到合法 selected IDs，未继续解释或操作该候选。

## LUT 分号两半的进一步原生定位

进一步静态解析 `ICoverFetcherEditor::create`（videoeditor RVA `0x14b81d0`）得到实例 vtable RVA `0x30e46d8`；其 `+0x60` 和 `+0x78` 实现分别为 `0x1814adb30`／`0x1814b45b0`，共同调用 `0x182b7cb90` 转换调色材料。VECreator 的 LUT importer 正是通过这两个槽建立／更新预览用材料，非任意关联函数。`native-cover-create-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-cover-create-static.txt`，未随源码分发）、`native-cover-ctor-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-cover-ctor-static.txt`，未随源码分发）

`0x182b7cb90` 的 `type==14`（LUT）分支明确拆分分号：

- 分号后半进入最终资源路径，随后经过路径规范化 helper；它是外部 LUT 数据路径的候选。
- 分号前半另外取最后一个 `/` 之前的目录，拼接 `/config.json`，读取效果配置。因此前半应该定位包内某个文件，而不是裸包目录。
- 从这些行为得到的具体测试候选为 `Resources/lut/config.json;完整测试文件.cube`，分号前后不加空格、路径规范为 `/`。这是有直接静态依据的实验输入，仍不是实际渲染通过的报告。

`fixLutPath` 对首段检查的 helper `0x180f68100` 已解析为 `_access(path, 0)` 存在检查，进一步支持首段是本机真实资源定位。`fix-lut-path-check-helper-annotated.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/fix-lut-path-check-helper-annotated.txt`，未随源码分发）、`native-adjust-from-cover-static.txt`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/native-adjust-from-cover-static.txt`，未随源码分发）

仍未执行导入或导出。只有在标准可解析 CUBE 的实际原生差分结果符合预期、草稿保留可改材料后，才可把这条路径升级为已验证能力。
