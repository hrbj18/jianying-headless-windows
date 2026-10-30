# 标准 CUBE 采样一致性与隔离资源候选（2026-10-28）

本轮为能力审计与隔离候选准备。**本研究没有调用 native/GUI、computer use、原生导出，没有写进程、engine、bridge、DLL、现有资源或草稿；没有接入正式 catalog。初版 v16 候选包保留 NATIVE_UNVERIFIED 标注和原指纹。** 主线程另建修正版 v19 并完成 identity 实测，见文末；不能把该结果回填为旧 v16 已通过。历史研究见 [LUT/色轮记录](native-lut-wheels-editable-20261028.md)。

## 当前真实限制

原生内置 CUBE 路径已具备真实强度编辑、历史、保存和出片能力，但该内置采样路径的标准 CUBE 数学等价仍失败。主线程 identity33 实验的 120 帧 full/zero MAD=1.911992/255；拟合斜率约 1.03125，偏移约 -4/255，与 `33*x-0.5` 的纹理采样模型相符。normalized-texture 预测 MAD=1.299846，说明该模型更接近实际，仍非唯一完整误差来源。`identity 实测`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/identity-cube-native-sampler-measurement-v2.json`，未随源码分发）、`对应能力审计 v14`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/native-av-milestone-audit-v14.json`，未随源码分发）

独立2D兼容候选修正Lua枚举、改用正常Home资源位置的独立filter后，主线程v27–v32完成了编辑、历史、重开和出片；v34标准144色块对float FFmpeg最大误差小于1。未命名filter曾隐藏人工卡片，v41正常新build补name后卡片、强度与出片已通过。**随后真实应用重启将零HSL的资源迁成另一内置revision，严格guard因此正确阻止预览/导出；重启后的这条交付链尚未通过。** 本研究确认两包确有5项语义差异，不能自动等价。LUT14默认包限制、独立兼容filter、资源revision迁移应分别记录；实拍高频边缘差异也仍未宣称完全等价。

这属于当前原生采样路径的精度缺口，不能概括成“不用 computer use 就无法使用 LUT”。已验证的原生编辑能力应保留，标准一致性独立保持未通过。

## 内置路径能否用参数修正

`cccreator.dll` 的 `FeatureSegment::_generateLutFeatureScene`（0x1811a4040）调用 0x181aeede0 创建 `LutXShader` / `LutMaterial`。实际 shader 来自 DLL 内的字符串和正常构造器，非 CUBE 同目录某个可替换 `.frag` 文件。三种 3D shader 都直接 `texture(inputImageTexture2, textureColor1.rgb)`；它们公开的 shader 输入只有纹理、intensity、skin_intensity、enable_alg、isInputTexPremul 这组功能，未发现可修正 `(N-1)/N` 和 `0.5/N` 的坐标/domain uniform。`构造与选择分支`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-native-3dsampler-selection-static-v1.txt`，未随源码分发）、`原样 shader`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-cccreator-3dshaders-v1.json`，未随源码分发）

AE importer 检查 N³ 个节点，逐项转 half RGBA 并保持 width=height=depth=N，没有补边或重采样。CUBE 的 DOMAIN_MIN/MAX 虽被 parser 读取，但当前 shader 没有相应输入坐标变换入口；不能把修改 domain header 当作已经成立的修复。`原始体积构建`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-ae-volume-f16-fill-static-v1.txt`，未随源码分发）、`原 parser/metadata`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-ae-importer-parser-static-v1.txt`，未随源码分发）

还排除一个容易误判的捷径：格式 classifier 0x1811a92f0 认识 PNG=0、CUBE=1、3DL=2，但当前 `_setLutFromPath` 在 0x1811a77a6..aa 只接受原值 1 或 2。直接将 512² PNG 填入同一个 outer LUT path 会进入 unsupported 分支，不能称为现成可用配置。`classifier`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/standard-lut-classifier-and-lutdata-static-v1.txt`，未随源码分发）、`真实入口检查`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/custom-cube-native-cccreator-setpath-static-v1.txt`，未随源码分发）

## 首选：复用本机通用 applyLut3D，独立 AmazingFeature 资源副本

现有 `AmazingFeature_adjustColor/xshader/colorAdjust.frag:92` 的 `applyLut3D` 已实现正确的 2D LUT 采样：半 texel 偏移、RG 双线性取样、相邻蓝切片插值。它由参数控制网格尺寸，当前原资源调用 `(17,17,17,1)`，使用 289×17 strip。对 33³ 表直接重排为 **1089×33 strip**，调用 `(33,33,33,1)`，可以保留全部 35,937 个节点，不 resample64，也无需另写一个平台或替换 DLL。`原函数及调用`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/standard-lut-native-source-copies/colorAdjust.frag`，未随源码分发）、`原资源指纹清单`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/standard-lut-native-source-copies/source-manifest.json`，未随源码分发）

对色彩 C，设 `b=32*C.b`，先在 blue=floor(b)、ceil(b) 两个切片分别取样。strip 坐标为：

```text
u = (blueIndex*33 + 32*C.r + 0.5) / 1089
v = (32*C.g + 0.5) / 33
look = mix(slice0, slice1, fract(b))
out.rgb = (1-a)*C.rgb + a*look.rgb
out.a = C.a
```

采样坐标与 base mix 分开，a=0 为原色，a=1 为标准 look，任意中间值是两者的线性混合，不会对原色先做错误仿射。

正常 native `AmazingFeature` loader 会读取资源 `main.scene`；原 merge config 已有该类型和其他已验证调色场景，根 `Feature.js` 以目录键分派强度和可见性。当前 shader 的强度输入键为 `lut_intensity`。同版本 WaterMark Lua 明确提供 `assetMgr:SyncLoad(imagePath)` → `material:setTex`。旧 LumiUtils 虽出现 prefixed 枚举写法，但它在当前实际运行时为 nil，已由静态 enum 登记和主线程 v19 日志纠正为 `Amaz.FilterMode.LINEAR`、`Amaz.FilterMipmapMode.NONE`，见文末。资源样例不能单独证明当前枚举 API 有效。`normal scene loader`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/standard-lut-main-scene-precedence-static-v1.txt`，未随源码分发）、`精确函数名`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/standard-lut-main-scene-function-exports-v1.json`，未随源码分发）、`原 merge config`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/standard-lut-native-source-copies/merge-config.json`，未随源码分发）、`同版纹理加载`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/standard-lut-native-source-copies/published-watermark-asset-loader.lua`，未随源码分发）

## CPU 数学证据，严格区分 native 验证

独立 CPU 诊断将 gentle 原表重排，按原函数的 2D 纹理坐标模拟取样，与单独 FFmpeg float `lut3d:interp=trilinear` 比较：10,240 个 RGB 样本含 729 个边界组合，最大差仅 **0.00001975 个 8bit 级**。与另一份 canonical 3D 插值实现最大差 4.55e-15。a=0/.25/.5/.55/1 均保持正确混合；原始 CUBE SHA 前后相同，没有读取或处理原片。`诊断输入和完整数字`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/standard-lut-math-diagnostic-v1/result.json`，未随源码分发）

这是浮点 CPU 算法一致性证据，**没有验证 PNG 加载、GPU 浮点精度、原生滤镜顺序或 GUI 可编辑性**。不得将这个数字替换主线程仍失败的标准 native 实验。

8bit PNG 只在所有节点位于 [0,1]、无额外 gamma/sRGB 转换且理想线性取样时，节点舍入误差上界为 0.5/255，凸组合不放大该界。16bit PNG 的理论节点舍入更小，但本机加载器是否保持 16bit、是否转为 RGB8、是否按 data texture 处理，均待原生实测。这里不支持 HDR、超范围节点或 combined 1D+3D CUBE，也不对透明素材预乘语义作已验证承诺。

## 备选与成熟项目来源

| 路径 | 评价与约束 |
| --- | --- |
| 本机 applyLut3D 33-node strip | 首选，现有 native 采样函数逐字复用；只需要任务自有资源适配。尚未原生验证。 |
| GPUImage 2D LUT shader | 成熟参考：正确半 texel 坐标与 original/look intensity 混合，但原代码硬编码 64³/512²，不能直接当作任意 33³ 精确表示。完整 GPUImage 为 Apple 平台框架，无需给此项目另装一套客户端。 |
| OpenColorIO GPU shader | 成熟标准参考：显式 `(pixel*(N-1)+0.5)/N`；还有手工 tetrahedral。新的 3D shader、纹理绑定和原生资源 metadata 仍需适配，当前不比已有本机 2D 函数省事；并须保持本任务要求的 trilinear，而非偷偷改为 tetrahedral。 |
| 单独输入 RGB 仿射 | 否决，会改变 a=0 和中间值的 base。 |
| 成对预/后仿射加 LUT 输出编码 | 数学可行，需三段正常顺序且没有中间截断/量化，复杂度和验证面大于单 pass 2D，列为次选。 |

OCIO 源码明确修正半 texel，GPUImage 源码也保留原色和强度参数；两项目均为 BSD 三条款，复用其代码需保留对应许可。当前候选核心来自**本机发布资源副本**，不能把这些 native 资源声称为上述开源项目或新授权的开源资产。[OCIO 精确源码](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/src/OpenColorIO/ops/lut3d/Lut3DOpGPU.cpp)、[GPUImage 精确源码](https://github.com/BradLarson/GPUImage/blob/167b0389bc6e9dc4bb0121550f91d8d5d6412c53/framework/Source/GPUImageLookupFilter.m)、[OCIO 许可](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/22dd9c4faa0d1b7cfb3d64d1a6e9cb454acc6cfd/LICENSE)、[GPUImage 许可](https://github.com/BradLarson/GPUImage/blob/167b0389bc6e9dc4bb0121550f91d8d5d6412c53/License.txt)、`一手源码下载指纹`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/standard-lut-primary-sources/source-manifest.json`，未随源码分发）

成对方案的准确形式是：`A(C)=32*C/33+0.5/33`，将 LUT 每个输出节点编码为 `E_i=A(T_i)`。原生 raw sampler 对 `A(C)` 得 `A(T(C))`；内部混合后再用 `A^-1`，利用仿射与混合的可交换性可还原 `(1-a)C+aT(C)`。CPU 诊断支持此式；只有前置 A、缺少输出编码及后置逆变换时，a=0 最大误差已达 3.863636/255。没有 native 三段顺序或精度验证，不建议优先落地。

## 已准备的独立候选和接入边界

根目录：`C:/JianyingAVQA/work/lut33-compat-resource-v16`（历史本机证据：`C:/JianyingAVQA/work/lut33-compat-resource-v16/README.md`，未随源码分发）。独立 key：`AmazingFeature_standardLut33_v16`。六份候选为 identity/gentle/nonlinear × 8/16bit，均标注未原生验证。转换脚本只接受 33³、domain [0,1]、节点 [0,1] 的 SDR 表；只写本 scratch 内全新目录。不会修改原始 CUBE 或已复制的源模板。`转换脚本`（历史本机证据：`C:/JianyingAVQA/work/lut33-compat-resource-v16/build_candidate.py`，未随源码分发）、`六包清单`（历史本机证据：`C:/JianyingAVQA/work/lut33-compat-resource-v16/packages-manifest.json`，未随源码分发）、`源资源 SHA`（历史本机证据：`C:/JianyingAVQA/work/lut33-compat-resource-v16/provenance-originals.json`，未随源码分发）

每包 `main.scene`、material、xshader 二进制及源 metadata 原样复制；修改仅在该独立副本的明文 fragment/Lua 和 LUT 数据 PNG。`applyLut3D` 函数逐字保持、SHA 可核对；fragment 只替换 main 为 33³ look 与原色 mix。主 Root Feature.js 使用正常 `lut_intensity` 参数，Lua 复用既有 entity/uniform/事件，避免新增原生 ABI；Lua 不会每帧用构造默认值覆盖 Root 设置。每包有完整文件 SHA、源→候选 diff、manifest 和 native 未验证状态。`最小接入契约`（历史本机证据：`C:/JianyingAVQA/work/lut33-compat-resource-v16/integration/adapter-contract.json`，未随源码分发）

对现有 full merge 包，只能在一个**新的任务自有副本**中替换 LUT Link 为 `type:AmazingFeature`、path 为独立 key，保留其余调色 Link、次序和旧能力；候选 `Feature.merge-adapter.js` 仅替换原 `AmazingFilter_lut` 目录键，保留原强度/enable 分派。它们只是接入说明，未安装、未写入任何 catalog，也没有捏造新的官方 effect/resource ID。`Link 片段`（历史本机证据：`C:/JianyingAVQA/work/lut33-compat-resource-v16/integration/merge-link-fragment.json`，未随源码分发）、`merge JS 候选 diff`（历史本机证据：`C:/JianyingAVQA/work/lut33-compat-resource-v16/integration/Feature.merge-adapter.diff`，未随源码分发）

后续若获继续执行指令，最小验收是：独立 QA 原生加载无错误；identity/gentle/nonlinear 在同一原始 RGBA 输入上比较 a=0/.5/1；核对纹理朝向、data 色彩空间、8/16bit 实际格式和无 mipmap；再用普通 GUI 强度动作完成编辑/undo/redo/save/reopen，并确认材料资源路径迁移后仍绑定该候选。若普通保存恢复为原官方 CUBE 路径，应如实失败，不以仅 export 副本替换后有效冒充 GUI 已正确渲染。**本研究在候选准备后交接给主线程；以上 native 验收没有在本研究中运行。**

## 后续过滤 API 复核与主线程 v19 实测

本节仍是只读复核；所有 native 实验由主线程串行执行。本研究没有修改 v16 候选、原生快照、实验目录、engine、ABI 或 DLL，也没有调用 native/GUI。

### 问题首先出在候选枚举，不能归咎于采样公式

主线程 v18 将真实 nonlinear native 像素与两种预测比较：标准 trilinear MAD 约 1.18、max 20.48；nearest RG + linear B 预测 MAD 约 0.0907、max 0.561，G 通道误差约 1e-15。这个有针对性的证据说明候选实际 RG 过滤仍表现为 nearest，不能因为 B 在 fragment 中显式 mix 就声称整个三线性已成立。`主线程 v18 像素预测`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-candidate-sampler-measurement-v18.json`，未随源码分发）

我在 v16 Lua 中沿用了旧 LumiUtils 的 `Amaz.FilterMode.FilterMode_LINEAR` 写法；仅凭旧资源样例就采用，未先核对当前实际枚举，是该候选需要纠正的地方。实际发布库的 enum RTTI 值构建函数 `0x181da3eb0` 只登记 **NEAREST=0、LINEAR=1**；mipmap 的 `0x181da3e60` 登记 **NONE=0、NEAREST=1、LINEAR=2**。当前有效短名为 `Amaz.FilterMode.LINEAR`、`Amaz.FilterMipmapMode.NONE`。`FilterMode 实际登记`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-filter-binding-exact-setters-static-v17.txt`，未随源码分发）、`mipmap 实际登记`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-filter-mipmap-enum-names-v17.txt`，未随源码分发）

### 应设置 Texture2D 本身，原 .meta 已是 linear

`filterMin` / `filterMag` 确实是 Texture/Texture2D 的正常反射属性，无需移到 `texture.image` 或 material 上。Texture2D 虚表为 `0x1843254c0`：

| 属性 | normal setter | 对象字段与通知 | getter |
| --- | --- | --- | --- |
| filterMin | slot+0x150 → 0x181a5ff20 | 写 +0xd4，值变化时置 +0xf0 dirty | slot+0x158 → 0x1811638d0 |
| filterMag | slot+0x160 → 0x181a5ff00 | 写 +0xd8，值变化时置 +0xf0 dirty | slot+0x168 → 0x18027aaa0 |
| filterMipmap | slot+0x170 → 0x181a5ff40 | 写 +0xdc，值变化时置 +0xf0 dirty | slot+0x178 → 0x1811638e0 |

这里是静态分析可读的字段和正常 setter 路由，未写进程，也不是建议直接写这些 offset。`SyncLoad` 是 AssetManager 已登记方法；PNG 的正常 texture 绑定与同版 WaterMark `texture.image` 检查、`material:setTex` 用法一致。`反射属性注册`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-filter-enum-and-texture-properties-static-v17.txt`，未随源码分发）、`setter/getter 指令`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-texture2d-min-mag-setters-leaf-v17.txt`，未随源码分发）、`min getter`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-texture2d-min-getter-leaf-v17.txt`，未随源码分发）、`mag getter`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-texture2d-mag-getter-leaf-v17.txt`，未随源码分发）

原 `lightSensation_max.png.meta` SHA 仍是 `7bae80006b76ea192e0f1b51d674de35e85ba338e1c83ee65c993a3b9bdc0c43`。按格式中的字段名/type ASCII DJB2(seed5381) hash 精确匹配，而非猜 offset，可读出：filterMin=1、filterMag=1、filterMipmap=0。其 type hash 也分别匹配 FilterMode=0x98994db0、FilterMipmapMode=0xc2014854；wrap S/T/R 的字段与 type hash 同样吻合。因此原 metadata 已是 linear/no-mipmap，不应为此改写原 .meta。`只读字段解析`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-original-texture-meta-filter-fields-v17.json`，未随源码分发）

### 主线程修正短名后的实际结果

主线程在**新的** v19 identity8 副本加入正常 Lua 读数，日志显示：

```text
LUT33_FILTER_BEFORE  nil  1  1  1
LUT33_FILTER_AFTER   1    1  1089  33
```

前一行的旧 prefixed 名确实为 nil，而短名为 1；修正后 texture min/mag 读回 1，尺寸为 1089×33。主线程报告满强度与旧 zero 的三张 **640×1138 原生 RGBA** 已逐像素相同，MAD/max 均为 0。它证明当前新副本的 identity 过滤修正已真实生效；旧 nil 如何经绑定落到零值没有另行逐指令 runtime 追踪，不能伪称做过该内部追踪。`真实 v19 日志 1062–1063`（历史本机证据：`C:/LUTQA/work/p17i8d191p0/service.stdout.log`，未随源码分发）、`native preview 记录`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-candidate-identity-8-filterdiag-v19-1p0-result-v17.json`，未随源码分发）

该结果也表明这次无需绕过正常纹理生命周期或每帧强制重绑才能使 identity 正确。**它尚不等于任意 nonlinear/gentle 标准一致性、强度中间值或 GUI 保存迁移已通过。** 主线程正在单独测 corrected nonlinear8 full/half 和 nonlinear16。本研究不重复执行。此前 identity8 与 identity16 输出一样，也不能单独证明 native 降为 8bit：最终 RGBA8 量化本来就可能使二者相同，需非线性数据对照才能判断精度。

## 后续 v21–v23：标准采样通过，LUT14 首开迁移仍构成编辑缺口

### 新增实测及其边界

本研究读取主线程的新证据：corrected nonlinear8 对显式 float FFmpeg trilinear 的三帧 MAD 为 **0.28562、0.28631、0.28617**，最大误差分别 0.98949、0.97071、0.96960 个 8bit 级；half 对标准 original/look mix 的 MAD 为 0.25889、0.26208、0.26030。原输入为 native 未编码 RGBA，节点未改。主线程另完成4秒1080×1920原生MP4。因此“兼容采样和中间强度没有原生像素验证”已不再是最新状态；范围仍是 opaque SDR33、default domain、trilinear，不含HDR或combined1D。`三帧完整数据`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-corrected-native-FFmpeg-float-proof-v21.json`，未随源码分发）

但主线程首次正常打开 `AV_StandardLutCompat_v22_20261028` 后，type=`lut` 材料的 compound path 后半被改为安装目录 `Resources/DefaultAdjustBundle/merge_all_adjust_color`；lumi 仍指向任务自有候选。这改变了实际 sampler 绑定，**不能据离线成功声称该标准兼容 LUT 在剪映中继续编辑也已通过**。`首开迁移的真实读回`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-native-migrated-on-open-proof-v22.json`，未随源码分发）、`对应时间线`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-native-before-edit-timeline-v22.json`，未随源码分发）

### 只读定位：迁移来自正常项目恢复的专门 LUT 分支

本轮只读发布物，未调用native、未修改GUI/草稿/资源。VECreator.dll 的 `VECoreProject::fix_adjust_resource` 为 **0x184f73510**，源码路径字符串指向 `BizScene/HomeScene/Draft/Project/VECoreProject.cpp`。唯一直接call候选来自 **0x184f765e0**（调用点0x184f766bc），且正常调用链已由指令边界核对。`直接调用索引`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-gui-migration-pe-index-v23.json`，未随源码分发）、`上层完整静态指令`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-gui-migration-caller-v23.txt`，未随源码分发）、`专用修复完整静态指令`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-gui-resource-migration-core-v23.txt`，未随源码分发）

专用函数先从正常 `IDefaultAdjustResource` provider 按材料type取默认调色资源，然后决定是否使用 local。它并不是只在路径不存在时补路径：

1. `0x184f73945` 起扫描材料path是否包含 `Cache`，并比较资源ID与当前mergeID。普通分支的默认ID字符串为7416258989467374091，另一实验分支为7460040331627598345。
2. 非已匹配缓存分支中，若材料type属于需合并资源的集合（predicate `0x186a18570`，type14在内），正常辅助函数 `0x184f64f40` 尝试从资源管理器找到当前mergeID的已下载记录；满足记录ID、正常状态和type==0x90时，才取得该记录资源path。找不到则 `useLocal=true`。
3. **type14** 在 `0x184f73ccd` 进入特殊拆分：保留CUBE前半，将suffix作为单独目录检查。`0x184f73eb8` 对suffix做正常Qt路径检查；检查失败**或**`useLocal=true`时，`0x184f73ee3..eef` 调用默认资源path getter **0x1828afd00** 覆盖suffix，再重组 `cube;suffix` 写回。
4. 尾部还正常修复effect/resource ID后提交。仅改变lumi并不阻止前面的suffix替换，和主线程实测吻合。

这些分支中没有读取material version/source_platform来提供“自有包免迁移”开关；effect/resource ID只按默认资源身份查询、比对和修复。**不能由此建议猜version值、借用其它官方ID、把目录取名Cache或伪造下载状态来保留包。** 当前证据只能说明LUT14被设计为使用应用默认/已登记merge资源，未找到合法的自有suffix保留选项。`useLocal和资源查询辅助函数`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-gui-migration-validation-helpers-v23.txt`，未随源码分发）

### 自有标准 LUT 兼容滤镜：有现成入口，首开路径保留未通过

**更正先前静态解释**：上层恢复 `0x184f765e0` 的第一项不是目录检查，而是 **QFileInfo::isFile**，第二项为QFileInfo::exists；只有真实文件且存在、并非type14时才直接跳过fix。主线程已被动映射真实Qt IAT，详见下节。因此“普通filter真实目录有效即可跳过restore”这一先前推断撤回，不能再作为推荐依据。普通filter仍有下列现成添加/强度入口，但自有资源目录的GUI首开并未通过。

现有项目已具备普通filter能力，所需最小连接如下：

| 项目 | 现成契约与证据 |
| --- | --- |
| 添加 | `draft video filter add --resource local://<真实资源目录> --intensity <0..1>`，项目已有 `windows_vfx.py` 正式组装；不需构造官方资源ID。 |
| 材料 | `materials.effects` 中 `type:"filter"`，挂视频片段 `extra_material_refs`；既有冻结模板的resource_id为空字符串。不得复用LUT14 schema并只改名字。 |
| 效果事件 | 已审核cyberpunk与retro-lomo的Lua都接收 **`intensity`**，`event.args:get(1)`为强度；retro将其交 `material:setFloat("uniAlpha",intensity)`。当前标准LUT候选的`lut_intensity`属于merge协议，走filter时必须在**新的独立资源副本**连接普通`intensity`事件。 |
| 原生编辑 | 当前片段所绑定的 `VideoBasicSettingViewModel.acceptFilterValue(double value,bool with_shift)`，Qt local method64；现有 `agent live filter-value` 使用UI百分值=`value*100`、with_shift=false，并检查保存value0..1。 |
| 数据默认 | 普通filter的省略value为protobuf默认0，既有校验器已明确处理，不应补成1。 |

源码：`正式filter添加及readback`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/engine/windows_vfx.py:397`，未随源码分发）、`已有原生filter编辑`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/engine/live_editor/v02.py:268`，未随源码分发）、`精确Qt签名`（历史本机证据：`D:/JianyingHeadless/work/live-edit-v01/research/v02-effects/meta-VideoBasicSettingViewModel.json:600`，未随源码分发）、`已审核普通filter事件`（历史本机证据：`D:/JianyingHeadless/resources/windows-11.4.7.14462/retro-lomo/AmazingFeature/lua/SeekModeScript.lua:35`，未随源码分发）、`已有filter能力范围`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/docs/WINDOWS-VFX.md`，未随源码分发）

建议只在主线程新的独立QA与新的资源key中验证，名称明确为**标准LUT兼容滤镜**，保留原生LUT下拉功能与旧catalog pins。最小验收链：正常local添加→原生像素a=0/.5/1→首次打开核对资源path/hash→正常filter-value→undo/redo→保存关闭重开→再出片比较。不得回写活动草稿补路径或改默认bundle。若已存在一个普通filter，现有正式入口仅审核每视频一个filter，不能叠加冒充无冲突；与HSL/曲线等调色链先后顺序也须实际验证。**本研究没有建立此候选、更没有执行该验收链。**

## v25–v26：filter 首开失败与路径清空的进一步定位

### 先更正检查类型，排除没有证据的编码解释

主线程新建 `AV_StandardLutFilter_v24_20261028`，任务自有filter包已离线原生出片，但正常首开后材料仍为type=filter、value=.55、resource_id为空字符串，**path被清空**。因此前节filter方案仍是失败候选，不得标为GUI可编辑通过。`真实首开读回`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-filter-open-timeline-inspect-v25.json`，未随源码分发）

主线程仅被动读取IAT及匹配Qt6Core导出，已经落实：

| VECreator slot RVA | 精确方法 |
| --- | --- |
| 0x7f26110 | QString::fromStdString |
| 0x7f27680 | QFileInfo::isFile |
| 0x7f26a48 | QFileInfo::exists |
| 0x7f26a38 | QFileInfo(QString const&) |
| 0x7f26ee8 | QFile::exists(QString const&) |

所以此前“普通资源目录有效就跳过restore”的解释明确撤回；实际isFile检查对普通目录为false，ASCII目录也不会因此跳过。`QString::fromStdString`按Qt官方契约解析UTF-8，并非按当前Windows ANSI代码页；本机实现RVA0xd670也将原始string数据和长度传给正常转换器，没有自制GBK转换。尚无中文路径故障证据，不能用“换ASCII路径”冒充已定位修复。`主线程精确被动映射`（历史本机证据：`C:/LUTQA/work/native-path-check-IAT-v26.json`，未随源码分发）、`本机fromStdString静态实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-qt-fromStdString-v26.txt`，未随源码分发）、[Qt官方UTF-8契约](https://doc.qt.io/qt-6/qstring.html#fromStdString)

### 不能简单把目录改成 config.json

`cccreator.dll FeatureSegment::loadSegment` 为0x1811ab780。在0x1811abc01起把输入path作为effectRoot保存，0x1811abc53..abca1拼接 **root + '/' + 正常配置文件名**，随后检查实际存在；错误路径有明确 `no config.json` 日志。既有 `_generateFeatureScene` 0x1811a2ea0又正常拼 `root+'/main.scene'`。因此直接将材料path写成config.json/main.scene可能经过isFile，却不符合当前AmazingFeature目录加载协议；不能以“通过文件检查”代替加载成功。当前未找到同一正常FeatureSegment入口接受自有zip/效果文件并自动解包的证据。`完整loadSegment实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-filter-native-loadSegment-v25.txt`，未随源码分发）、`场景加载`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/standard-lut-main-scene-precedence-static-v1.txt`，未随源码分发）、`精确导出名`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-filter-loader-export-symbols-v25.json`，未随源码分发）

### 发现直接清空path的正式加载步骤 correctEffectPath

继续沿一手字符串到真实引用，已找到 `draft_load_helper.cpp` 中匿名 **correctEffectPath**：

- effects版本 **0x1850e0520**：遍历持久化effects，type字符串`lut`明确跳过。filter进入正常路径检查。两处失败日志后，**0x1850e09f9..0a1b** 与 **0x1850e0b55..0b77** 直接将PersistentMaterialEffect.path(+0x100)长度设0、写终止符。它确实能产生本次观察到的空path，不是只有名称相似的函数。
- video_effects版本 **0x1850e0bf0**：同样逻辑，使用其持久化path字段+0xe8。
- 正常调用包装器 **0x1850e3e80** 同时把两组材料传入上述函数（调用点0x1850e4015、0x1850e4029）。

本步骤有两种正式路径策略：`feature_gray_config.draft_check_effect_path`（0x180ea2860）与`feature_gray_config.draft_check_effect_unc_path`（0x180ea29d0）。**这些是诊断所需的策略身份，不能修改/关闭开关来令候选通过。** 当前研究没有调用它们或更改配置。主线程新增被动IAT映射后，根路径和方向现已落实，见下一节；没有证据要求冒用官方资源ID。`清空完整实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-filter-correctEffectPath-core-v25.txt`，未随源码分发）、`正常调用包装器`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-filter-correctEffectPath-caller-v25.txt`，未随源码分发）、`正式策略键构建`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-correctEffectPath-policy-functions-v25.txt`，未随源码分发）

已经追过的VECoreProject修复后辅助函数还有旧makeup、beauty_key、chroma和AI文本模板等类型限定，不能把这些看似“登记资源”的私有函数当作filter通用注册接口；没有调用、没有伪造库项。`类型限定的完整静态实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-filter-restore-fallbacks-v25.txt`，未随源码分发）、`第一组限定修复`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-filter-restore-first-fallbacks-v25.txt`，未随源码分发）

截至本节，**标准33³采样数学及离线实际原生出片成立，自有包GUI路径保留失败**。本研究只读发布物和任务关联证据，没有编辑草稿、资源、engine、ABI、DLL、注册库或运行native/GUI。

### v26：正常允许资源位置、filter13分支及Home只读缓存

主线程用同一被动IAT映射脚本落实以下精确方法，没有通过bridge调用getter：

| VECreator slot RVA | 精确方法 |
| --- | --- |
| 0x7f38ad8 | videoeditor.dll StoreWrapper::getDraftRootPath() |
| 0x7f2d558 | VEConfig::path::getDraftRootDir(std::string const&,long long)；第二参数是0的long long，**不是bool** |
| 0x7f2d0e8 | VEConfig::path::getHomePath() |
| 0x7f2d798 | VEConfig::path::getAppResourcePath() |
| 0x7f26e60 | QDir::absolutePath() |
| 0x7f26aa0 | QDir::toNativeSeparators(QString const&) |
| 0x7f26b48 | QString::startsWith(QString const&,Qt::CaseSensitivity) |

结合完整寄存器数据流，两个策略的准确规则为：

```text
P = toNativeSeparators(QDir(material.path).absolutePath())
R1 = toNativeSeparators(StoreWrapper.getDraftRootPath())
R2 = toNativeSeparators(VEConfig.getDraftRootDir("", 0))
H  = toNativeSeparators(VEConfig.getHomePath())
A  = toNativeSeparators(VEConfig.getAppResourcePath())

若 draft_check_effect_path 开启：
    P 以 R1+separator 或 R2+separator 开头 => 清空 path
若 draft_check_effect_unc_path 开启：
    P 未以 H+separator 或 A+separator 开头 => 清空 path
```

比较参数CaseSensitivity=1，使用正常原生分隔符；不是检查路径是否包含中文。项目内包正好命中禁止的草稿根前缀，解释本次正常打开被清空。任意ASCII外部目录也不自动合法：它可能不在后一个允许根内。合法候选应采用**当前Home下、草稿根之外的独立明确命名资源目录**，例如 `H/Resources/AgentOwnedStandardLut/<资源SHA>`；它不是伪装某官方effectID的缓存目录，也不替换默认bundle。保留候选原包、完整hash和独立资源身份；仍由主线程进行正常首开、history及再出片验收。`主线程使用的被动映射脚本`（历史本机证据：`C:/LUTQA/work/map_native_iat.py`，未随源码分发）、`三个根getter的真实PE导出`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-effect-path-native-roots-symbols-v26.json`，未随源码分发）

**filter进入fix_adjust_resource会不会仍被改写？** 现有发布JS明确MetaTypeFilter=13、MetaTypeLUT=14。`DefaultAdjustBundleResource`虚表0x18b4897a0的slot+8为0x182e6b640，它只按传入type精确查找两张列表（0x182e6a110与0x182e6a9a0），查不到返回空shared_ptr。完整初始化列表包含14和调色类型，不包含13，寄存器输入的两项动态常量分别为15和31，亦非13。因此filter13没有默认调色资源，`fix_adjust_resource`在0x184f735f5直接返回false，未执行覆盖路径；**LUT默认merge迁移不是filter13的第二个阻碍**。这段没有提出注册假ID或写DB；“允许位置下整个GUI链通过”仍需真实首开验证。`虚表和slot`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-resource-vtables-static.json`，未随源码分发）、`精确type查找和空返回`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-local-default-provider-static.txt`，未随源码分发）、`两张完整初始化列表`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/merge-local-provider-lists-static.txt`，未随源码分发）、`当前发布枚举`（历史本机证据：`D:/刘宇钊/软件/剪映/JianyingPro/11.4.7.14462/Resources/canvas_agent/app/static/js/byted-image.c0e0a11b.js`，未随源码分发）

**Home的准确只读位置**：VEConfig.dll `getHomePath`导出RVA **0x179d0**，已初始化std::string缓存为模块base+**0x4c808**，初始化guard为+**0x4c828**。MSVC string长度在+0x10、capacity在+0x18；capacity<16读inline，否则先读首指针。这里只提供有来源的缓存布局，不能调用getter来“读值”，因为其初始化分支可能检查/创建路径。本研究未读活跃进程，因此不把猜测值写成观察。正常初始化helper **0x6700** 明确拼接应用数据父目录与 **`/User Data`**，所以此处Home不是整个Windows账户目录。主线程可被动读取缓存落实本机值；在该值落实前不硬编码C盘账户路径。`缓存读取和初始化分支完整实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-veconfig-home-cache-static-v26.txt`，未随源码分发）、`User Data根构造`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut33-veconfig-home-initializer-static-v26.txt`，未随源码分发）

**主线程随后已被动确认本机缓存值**为 `C:\Users\Administrator\AppData\Local\JianyingPro\User Data`，guard原始4字节为`03000080`；没有调用getter。主线程v27使用正常公共build将精确pinned自有包部署到 `H/AgentResources/standard-lut33/<完整tree SHA>`，同时在项目Resources保留完整副本供打包/源验证；不是官方effectID目录。材料保留允许的Home实际路径，导出从build-owned快照解析，原路径策略不变。**本次新增版本正在由主线程做原生出片及GUI首开/history，尚不在成功范围**；本研究不重复运行该实验、不改该目录，也不再建议变更策略开关或泛试路径。

## v27–v34新增验收：原生编辑闭环已通过，人工卡片缺name尚待修复

以下是主线程真实实验与本研究读取证据的结果，不是本研究执行native：

- v27合法Home目录在正常首次打开后保留；v28原生强度`.55→.6`，undo/redo恢复完整原始时间线fingerprint，4秒1080×1920、120帧MP4完成。v29三张原生raw帧随强度变化，MAD约.33–.34/255。`原生历史与保存出片`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-filter-native-history-proof-v28.json`，未随源码分发）、`实际像素变化`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-filter-native-actual-pixel-proof-v29.json`，未随源码分发）
- v32正常关闭重开后`.6→.58→undo .6`，完整时间线状态恢复，三张RGBA与原状态逐字节一致。`重开、编辑、撤销和像素`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-filter-native-cold-reopen-proof-v32.json`，未随源码分发）
- v34使用144个标准色块检查非线性表，full整帧max=.861885、MAD=.302668；half max=.702148、MAD=.265488。v33实拍对同一float参考仍有高频边缘最大46.53/255差异，尽管整帧MAD约.65；空间处理次序只是可能解释，尚未因果闭合，不能据色块校准声明整片完全等价。`完整色块数据`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-filter-native-uniform-color-proof-v34.json`，未随源码分发）、`实拍残余差异`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-filter-native-FFmpeg-float-proof-v33.json`，未随源码分发）

### 同版本正式QML的人工强度控件条件

从已验11.4.7 VECreator.dll只读提取qCompress资源，保留源DLL摘要、payload偏移、原始QML摘要。实际滤镜卡片为 `VideoFilterGroupView`，父面板为 `VideoBasicSettingView`：

| 层级 | 实际条件/原生property |
| --- | --- |
| 父面板lazy item allowActivate | `!viewModel.isMultiSelect && viewModel.filterName !== ""` |
| 卡片root.visible | 同上；名称空即整张卡片隐藏 |
| 卡片展开内容Column.enabled | `viewModel.filterGroupChecked` |
| 强度slider.visible | `filterName.text != ""`；Text直接绑定viewModel.filterName |
| 强度slider.enabled | `viewModel.filterEnabled`，并继承Column.enabled |
| 正常人工提交 | onAccepted调用`acceptFilterValue(curValue,withShift)` |
| UI范围 | min0、max100、decimals0、Normal slider；双击回100 |
| 显示时机 | 父面板使用viewport lazy load，卡片默认`collapsed:true`；人工滚到并展开卡片后看见强度，属于正常布局行为 |

QML中**没有resource_id非空门槛**；VIP相关值仅用于角标、点击角标统计，没有把强度slider gated为VIP。不能通过调用setter就假定以上visible/enable条件满足。`原卡片QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/filter-ui-qml-8d8dd5d-v34.qml:29`，未随源码分发）、`父面板lazy卡片`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/filter-ui-qml-8d908f0-v34.qml:279`，未随源码分发）、`提取来源与完整摘要`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/filter-ui-qml-extracted-v34.json`，未随源码分发）

精确Qt property及正常ReadProperty路由：

| property | 类型/local index | 正常getter VA |
| --- | --- | --- |
| filterName | QString/4 | 0x1833c7b20 |
| filterValue | double/5 | 0x1833c7c90；正常显示值为材料强度×100 |
| filterEnabled | bool/7 | 0x1833c7a30 |
| isMultiSelect | bool/23 | 0x1833ca6d0 |
| filterGroupChecked | bool/24 | 0x1833c7a80 |
| filterGroupCheckedMix | bool/27 | 0x1833c7ad0 |

这些来自真实meta property表和ReadProperty跳表，不是构造新QObject或猜offset；应通过主线程既有当前会话/选中片段绑定读取。filterName getter从当前业务model取首个selected SegmentVideo的filter，然后经IAT **VECreator+0x7f30750**读取名称；主线程被动映射到videoeditor RVA **0x122c10**，其ICF别名包含精确 `MaterialEffect::get_name`，调用语境一致。这里没有资源ID库lookup或路径basename回退。`property精确dispatch`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/filter-ui-properties-read-map-v34.json`，未随源码分发）、`VM正常getters`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/filter-ui-properties-getters-v34.txt`，未随源码分发）、`selected filter名称业务getter`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/filter-ui-business-model-getters-v34.txt`，未随源码分发）

### 已证实的隐卡片问题，修复须经新build验收

v28真实保存的filter材料没有name字段。本研究只读这一事实后，主线程实际读取四个原生property，结果 **filterName=""**，其余单选、filterEnabled及filterGroupChecked条件均满足；因此 **can_edit_in_native_ui=false**，卡片被隐藏。虽然正常acceptFilterValue已经完成编辑/历史和出片闭环，仍不能算人工原生UI可见控件通过。`当时完整材料`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-filter-after-timeline-v28.json`，未随源码分发）

主线程下一版将在**全新独立build**使用 `native_filter_name="标准 LUT33 兼容滤镜"`，由正常构建元数据设置材料name，shader/目录不变，保留旧未命名构建的兼容性验证；随后重新确认首开、真实property、历史和像素。不写活动GUI属性、不强行打开隐藏控件、不继续猜资源ID或修改保护开关。**本节到此只记录问题与已授权的下一实验，命名版控件可见性尚未宣称通过。**

## v41–v42：真实重启后的内置调色revision差异，不能自动等价

主线程新增实测已推进上一节边界：v41命名版filter的原生卡片可见、`.55→.6`、history、MP4及raw帧均已通过。但完整应用重启（PID44364→26548）后，原生把零HSL的path与lumi从cache741625.../9e1...迁成安装目录 `Resources/DefaultAdjustBundle/merge_all_adjust_color`。全时间线diff仅这两路径；公共preview仍正确拒绝，原因是资源字节不属于旧cache pin。**不能把重启后原生编辑成功写成重启后预览和保存导出已通过**。主线程拟按完整独立manifest登记builtin revision，旧cache记录及全部hash/guard保留，再进行实际像素对照。本研究没有调用native/GUI，也没有修改engine、catalog、安装或cache资源。`命名版卡片真实property`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-named-UI-proof-v41.json`，未随源码分发）、`命名版历史`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-filter-native-history-proof-v42.json`，未随源码分发）、`真实完整应用重启`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-named-normal-restart-proof-v44.json`，未随源码分发）、`仅两路径的完整raw diff`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-named-restart-raw-diff-v44.json`，未随源码分发）

### 完整包对比结果

| 包 | 文件数 | 完整tree SHA256 |
| --- | ---: | --- |
| 原cache revision | 348 | ed4fbac05c370b7a517080b495abf6c80d71f0b52e3f9b26a2501b49d9713249 |
| 当前installed builtin revision | 350 | 302c247fd52bfbe39d8cf5c16f01981a92df5945875575550a1b4531568e831c |

同名文件285个逐字节相同；63个字节不同，其中**58个在仅统一文本换行/可选BOM后完全相同**，另有**5个真实文本或JSON值差异**；cache无独有文件，builtin多2个Smart Color算法文件。即使58项仅换行变化，也必须保留两个完整hash身份，不能因此把底层资源完整性校验改成“忽略换行”。`全部文件清单、逐文件SHA及分类`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/color-builtin-vs-cache-manifest-diff-v42.json`，未随源码分发）、`完整真实源码diff（cache→builtin）`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/color-builtin-vs-cache-source-diff-v42.patch`，未随源码分发）

### 重要shader/Lua/config差异

| 文件/功能 | cache→builtin的真实变化 | 不能自动等价的范围 |
| --- | --- | --- |
| adjustColor/lua/SeekModeScript.lua | getVibranceParam删除正强度先×0.6，改为直接100×intensity | 正vibrance参数映射不同 |
| adjustColor/xshader/colorAdjust.frag | calcDstSaturation的**value≤0**分支从三次多项式改为二次多项式；其adjustSaturation helper从HSV饱和度缩放改为亮度矩阵 | 这是**Vibrance分支**所调用的helper；不是普通Saturation主分支整体换算法。正值sigmoid公式未变；普通u_enableSaturation主分支未变 |
| 根Feature.js | sceneIntensityKeyMap与intensityKeyParamsMap删vibrance_intensity；删除enableSmartColorGlobalLuminanceAdjust的AB读取及该情况下logContrast=3/enableGlobalLuminanceAdjust=1 | root分派不再包含vibrance；Smart Color的全局亮度AB行为不相同，不能假设客户端仍走旧协议 |
| particle/lua/SeekModeScript.lua | grain Intensity从intensity×ratio×min(inputWidth,inputHeight)/720改成intensity×ratio | 相同数值在不同渲染尺寸的颗粒强度可能不同 |
| smartColorAdjustment/featureAlgorithmConfig/algorithmConfig.json | blit_0删除stringParam.alg_tag="unmergeable" | 算法组合/合并资格发生变化，不以“JSON加载成功”判等价 |

builtin还多 `AmazingFeature_smartColorAdjustment/featureAlgorithmConfig/kernel.bin`（538533字节，SHA d9d91ca2ba161ff3a15ee32f3d31ab01484c1f96b477d3ea1942bee33525ec85）与`vhdr.ini`（194045字节，SHA503f9b94e2649f131e372e25d36e141b2b3b0f1eb9e6f6bdc08ef1495777f33b）。后者内容含二进制头及NVVM/PTX文本，不能把`.ini`后缀当作普通可随意编辑配置。本研究未执行、替换或忽略它们。

### LUT采样、HSL、曲线和色轮的精确范围

- **applyLut3D未变**：两包adjustColor.frag中该完整函数经相同换行规范化后均为1878字符、SHA`53084cc3bcb6e2b18664d458b1f7c5e2abdd268bec00b526563bee12419da0d7`。原17³ strip取样、坐标和B切片插值无新增改变；builtin这次差异不是一个新的LUT半texel修复。它也不改变DLL中内置CUBE 3D采样路径的旧限制。
- **HSL/曲线/色轮实际shader、Lua、main.scene、material等未见语义变化**：HSL17文件仅2个换行不同；curves26文件仅2个换行不同；hsl_curves35文件6个换行不同（含Quad.mesh）；primaryWheel/logWheel各13文件仅3个换行不同。所有这些组件的语义差异列表为空，支持主线程对同一HSL参数协议单独验收，而不是要求猜新参数。
- `AmazingFilter_lut`的3个文件均为换行不同，CUBE表文本、config和算法JSON值相同；根config、algorithmConfig、Lumi配置在本对比中也只有换行变化。**配置结构相同仍不等于整包所有功能等价**，因为上述Vibrance/颗粒/Smart Color语义差异真实存在。
- 标准LUT兼容filter是Home下另一个独立自有包，保持自身完整SHA；本次原生迁移的是旁边零HSL所依赖的调色包。不能把两者的资源身份合并，也不能据零HSL的即将完成对照扩展到任意非零Vibrance、grain或Smart Color。

最小现实验收应保持相同源/帧/参数，只比较迁移前cache与新builtin revision在**本次零HSL+命名标准兼容filter**上的实际RGBA、保存及原生出片；扩展非零HSL/曲线/色轮时再使用已有真实参数夹具。即便单项源文件相同，root启用、运行时合并和其它特性仍需保持相同控制。不得用新增revision的身份登记代替这些画面验收，旧cache包也不可被新builtin内容覆盖。`只读比较脚本`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/compare_color_revisions_v42.py`，未随源码分发）

## v46状态更正：本样例的完整重启、编辑及保存出片已通过

主线程新增落盘证据已闭合上一节待验项：正常应用重启后，命名兼容filter卡片满足原生可见条件；`.6→.58→undo .6` 已完成。先前preview确实因正确的资源guard拒绝；新增严格builtin revision后，新输出 `p46reopened` 的三张原生RGBA与此前 `p43after` **逐字节相等，MAD/max=0**。保存草稿的 `C:/LUTQA/work/ef46/render.mp4` 已实际encoded-and-decoded，source unchanged。**因此“重启后这条预览/导出链尚未通过”已被此次实测更新为通过。**

范围严格限于**命名标准LUT兼容filter＋当前零HSL样例**；完整raw时间线fingerprint并未跨重启保持一致，因为两条正常HSL资源路径迁移已明确记录，不抹掉这项事实。此次像素与出片成功也不把两个调色包的所有Vibrance/grain/Smart Color算法宣布等价。本研究只读取新增证据、追加本状态，未重跑任务或调用native/GUI。`最终重启后编辑及原生出片证据`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/lut33-named-filter-final-reopen-render-proof-v46.json`，未随源码分发）
