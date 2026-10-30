# 自有 3D CUBE：剪映 11.4.7 原生接入边界与 FFmpeg 参考验证

研究日期：2026-10-28。只读研究安装发布物及上游源码；本轮没有调用剪映原生方法、写目标进程、修改 engine/bridge/DLL、操作窗口或安装软件。FFmpeg 的独立测试只产生本研究目录中的测试表及单帧原始 RGB 数据。

## 结论与最短路径

可以在现有 LUT 材料和资源依赖链中接入用户自己的 `.cube`，保持视频素材不变、LUT 强度留在剪映草稿中。初版宜明确限制为：**单一 3D 表、N=33、默认 DOMAIN 0..1、35937 个 RGB triplet、每个数有限且处于 [0,1]**。这是与已真实成功的原生样本相同的兼容档，不是宣称 `.cube` 规范或剪映只允许这个范围。

严格解析用户原件，保存原件 SHA256；另生成仅含 `LUT_3D_SIZE 33` 与原样数值 triplet 的规范化文本副本（不改数值、不重采样），保存其 SHA256。把该副本放入现有独立、短路径的 LUT 依赖目录，复用已经验证的原生效果包及材料引用。强度继续使用原生 `value`，不在 FFmpeg 中烘焙替换视频。现有 pin 住诊断 LogC 表的 verifier 不能直接当作任意用户表的验证器；需要新增该兼容档的内容检查，同时保留效果包配置本身的指纹检查。

FFmpeg 可独立查格式、顺序和参考颜色，但 **FFmpeg 成功不等于剪映支持全部格式，参考像素也不应未经颜色空间/插值核对就要求逐像素相等**。本机两套 loader 对 DOMAIN 和表值范围的处理已有静态差异。

## 一手来源与可复查证据

本研究所有私有静态输出、原创测试表和 FFmpeg 测试记录在：

`D:\JianyingHeadless\integrations\native-custom-cube-research-20261028`

| 来源 | 固定版本 / 证据 |
|---|---|
| 本机独立 FFmpeg | `N-126495-g3a165c77dc-20260910`，libavfilter 12.4.100；`版本`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/ffmpeg-version.txt`，未随源码分发）、`filter help`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/ffmpeg-lut3d-help.txt`，未随源码分发） |
| 对应上游代码 | [vf_lut3d.c，commit 3a165c77dc](https://github.com/FFmpeg/FFmpeg/blob/3a165c77dc/libavfilter/vf_lut3d.c)、[lut3d.h](https://github.com/FFmpeg/FFmpeg/blob/3a165c77dc/libavfilter/lut3d.h)、[同版本 filters.texi](https://github.com/FFmpeg/FFmpeg/blob/3a165c77dc/doc/filters.texi#L17945)；下载 SHA 见 `source-manifest.json`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/source-manifest.json`，未随源码分发） |
| 官方使用文档 | [FFmpeg lut3d](https://ffmpeg.org/ffmpeg-filters.html#lut3d)；当前官网内容可能随版本更新，细节以本机对应 commit 为准 |
| 剪映本机 loader | `11.4.7.14462\cccreator.dll`，SHA256 `a122d8b4c36f3300c8a32666e87b3b46c5acf61b7b32dc0e132bb8f62e1f39a1`；`定位与字符串`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/cccreator-cube-xrefs.json`，未随源码分发）、`常量与 caller`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/cccreator-cube-constants-callers.json`，未随源码分发） |
| 已成功原生样本的实际形状 | `shipped-cube-shape.json`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/shipped-cube-shape.json`，未随源码分发）：33³、35937 行、无 DOMAIN、输出 min/max 为 0/1，SHA256 `de533d358202c2dddbb7f32c6321d9cd2fcb98a46b9f09429539fcf434ac456c` |
| 现有路由和失败根因 | [native-lut-wheels-editable-20261028.md](native-lut-wheels-editable-20261028.md)，尤其 compound path 与原生 JSON 路径转义记录；[现有依赖校验实现](../../engine/native_lut_dependencies.py) |

`vf_lut3d.c` / `lut3d.h` 文件头为 LGPL-2.1-or-later；本机 FFmpeg 是启用 GPL/version3 的整体构建，两者不能混为同一再分发许可判断。本研究不将剪映闭源代码、官方素材包或诊断 LUT 改称自有资源。原创测试表只是坐标恒等 / R-B 互换 / 常数表。

## FFmpeg 的准确边界

以下均对应本机 commit，而不是凭通用 CUBE 介绍推断。

| 项目 | 对应实现与含义 |
|---|---|
| 入口 | `lut3d_init` 依扩展名选择 `parse_cube`；`.cube` 大小写不敏感，文件内容关键字匹配区分大小写。这里只讨论 `lut3d`，不是另一个 `lut1d` filter。 |
| 尺寸 | `allocate_3dlut` 检查 `2 <= N <= MAX_LEVEL`，该版本 `MAX_LEVEL=256`。这是 FFmpeg 上限，不能移植为剪映上限。 |
| 表顺序 | `parse_cube` 的文件读取顺序为 `k → j → i`，内部写入 `lut[i*N*N+j*N+k]`；结合 RGB 查表索引，**R 最快、G 次之、B 最慢**。每行输出依次为 R、G、B。 |
| 行解析 | 行缓冲 512 字节；略过空行及首个非空白字符为 `#` 的行。表格每行用三次浮点扫描；它未因此保证“只含三 token”“没有尾随第四列”“总行数恰好 N³”“全部有限”。 |
| 纯 3D | `parse_cube` 只建立 `LUT_3D_SIZE` 表，没有在此入口组合执行 CUBE 1D shaper。别处的 CSP prelut 和 `parse_cube_1d` 不证明该组合格式可用。 |
| DOMAIN | 默认 min=0、max=1。只有尺寸行之后、读 triplet 的循环才处理 DOMAIN；尺寸前的 DOMAIN 被外层扫描略过。最后设输入 scale=`clip(1/(max-min),0,1)`，浮点采样乘该 scale，**未减 min**。因此不能把本版本当作任意输入域的完整标准转换器。 |
| 输出范围 | `%f` 解析的表值没有统一约束为 0..1；浮点输出路径直接写插值值，整数输出路径有裁剪/量化。仅看输出 PNG 会掩盖超范围表值。 |
| 插值 | nearest / trilinear / tetrahedral / pyramid / prism，默认 tetrahedral。剪映使用哪种 GPU 插值本轮未完全定位，不能由 FFmpeg 默认值推定。 |

实现位置：[parse_cube 与 allocate_3dlut](https://github.com/FFmpeg/FFmpeg/blob/3a165c77dc/libavfilter/vf_lut3d.c#L605)、[浮点采样路径](https://github.com/FFmpeg/FFmpeg/blob/3a165c77dc/libavfilter/vf_lut3d.c#L420)、[MAX_LEVEL](https://github.com/FFmpeg/FFmpeg/blob/3a165c77dc/libavfilter/lut3d.h#L46)、[入口](https://github.com/FFmpeg/FFmpeg/blob/3a165c77dc/libavfilter/vf_lut3d.c#L1236)。这些事实描述实现，不给畸形文件授予项目支持资格。

### 本机 FFmpeg 独立实测

原创 RGB 测试输入覆盖 33³ 个网格点；R 最快，以 `gbrpf32le` 保存，画幅 1089×33。本研究仅对这些单帧原始数据运行 FFmpeg，没有导出替代视频。完整命令和结果：`ffmpeg-cube-behavior-proof.json`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/ffmpeg-cube-behavior-proof.json`，未随源码分发）。

| 用例 | generic C 路径实测 |
|---|---|
| 33³ identity | 全部 float 与输入一致，最大误差 0 |
| R/B 互换表 | 全网格与独立预期一致，最大误差 0；输入 (.25,.5,.75) 输出 (.75,.5,.25) |
| DOMAIN [.25,1.25] 放 SIZE 前 / 后 | 均接受；输入 (.25,.5,.75) 仍输出 (.25,.5,.75)，印证该实现没有完整 min offset 转换 |
| 固定输出 (1.25,-.25,.5) | 浮点数据保留该超范围值，无自动压到 0..1 |
| 33³ 后多一行 triplet | 返回 0，输出与 identity 一致；FFmpeg 静默忽略尾部，不可替代精确计数校验 |

本机默认 CPU dispatch 对这个 1089 宽浮点测试的非恒等表出现行尾/边界差异（identity 会掩盖它）；使用 `-cpuflags 0` 后上述全部独立预期逐 float 一致。原记录保留了两轮。参考验证应固定 generic C 路径，不把这次 FFmpeg SIMD 问题误判为用户 LUT 或剪映的错误。该证据只针对本机构建与该测试输入，不外推为所有 FFmpeg 版本缺陷。

## 本机剪映 Cube loader：确认项与未知项

这里的证据来自**静态磁盘反汇编**，不是运行 loader 试探，更没有修改程序。PE 优选基址 `0x180000000`，以下均为 RVA；真实日志字符串给出源码路径尾部 `Foundation/src/glutils/TELutTextureManager.cpp`，可避免把安装目录里的 FFmpeg/lcms2 解析器误认成原生纹理 loader。

| 原生位置 | 可证实行为 |
|---|---|
| `validateLutFile` 分支 caller `0xe117a0`，call `0xe118b8` | 按后缀选择 Cube 分支，进入 `validateCubeLUT(0xe0e9b0)`；不是仅发现未引用字符串。 |
| `validateCubeLUT` `0xe0e9b0..0xe0ee7a` | 512 字节缓冲逐行查 `LUT_3D_SIZE`；`0xe0eb2a..3d` 将尺寸转整数并检查正数；按 N³ 计数并要求成功解析 triplet，提前 EOF / parse 错误有明确日志。 |
| 同函数 `0xe0eb8b..0xe0ecdd` | 表格读取期间识别 `DOMAIN_MIN` / `DOMAIN_MAX` / `TITLE`，空白和注释可略过；DOMAIN 默认 0/1。`0xe0ee04..29` 要求三个 max 均严格大于 min，否则 `invalid DOMAIN range`。 |
| `load...` caller `0xe10e10`，call `0xe1114f` | 实际走 `readCubeLUT3DHalfRGBA(0xe0f5c0)`，与校验器是不同函数。 |
| `readCubeLUT3DHalfRGBA` `0xe0f5c0..0xe0fd8a` | 同样查尺寸，建立 N³×4 分量的 half RGBA 存储，RGB 来自 triplet，alpha 为 1。数据循环是第一坐标最内层。 |
| 读取器 `0xe0f915..0xe0f999` | 对每个表值计算 `(v-min)/(max-min)`，再夹在 0/1，之后转 half；这与上述 FFmpeg 输入采样缩放、浮点输出可超范围不等价。 |

完整静态证据：`validateCubeLUT`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/cccreator-validateCubeLUT-full-static.txt`，未随源码分发）、`readCubeLUT3DHalfRGBA`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/cccreator-readCubeLUT3DHalfRGBA-full-static.txt`，未随源码分发）、`validation caller`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/cccreator-cube-caller-0xe117a0.txt`，未随源码分发）、`loading caller`（历史本机证据：`D:/JianyingHeadless/integrations/native-custom-cube-research-20261028/cccreator-cube-caller-0xe10e10.txt`，未随源码分发）。函数跨多个 `.pdata` 片段，本研究保存连续范围，没有只把第一片段当整函数。

**关键保留项：**读取器虽然存在 DOMAIN 解析和归一化计算，但 `0xe0f803..0xe0f90f` 的静态控制流中，DOMAIN / TITLE 分支之后仍可落入整行 triplet 扫描，没有像 validator 那样清楚地略过该行；可能出现 validator 接受而实际 reader 不接受的头部组合。本轮不执行原生试验，不能宣布这些头部在实际渲染中兼容。尺寸前的头部也可能被扫描略过。规范副本只保留尺寸和数字行，能直接复用已成功样本的格式，同时避免依赖这条不确定分支。

没有在这些局部函数看到 17/33/65 固定白名单，也没有找到可作为生产承诺的统一 GPU 尺寸上限；`N>0` 是局部解析检查，**绝不等于任意正 N 可安全加载**。GPU纹理容量、上层资源策略、合并滤镜格式和33以外的实际出片仍待验证。目前只有 33³ 是该链已实际渲染通过的档位。

本机还带 `avfilter-10.dll` 的 LUT 字符串及 lcms2 的 DOMAIN/1D/3D 字符串。仅它们存在，不能证明原生 AmazingFilter LUT 就走这些库；本研究没有借它们扩大支持范围。

## 建议的现有 plan 校验与资源封装

### 输入与兼容档

1. 输入为用户指定的本机普通 `.cube` 文件；跟现有依赖策略一致拒绝 symlink/重解析跳转，并限定合理字节预算（如初版 8 MiB，是项目输入预算，不是原生格式上限）。生成副本前后检查源 hash，避免读入期间被替换。
2. 自己逐行解析全部文件，不能只调用 FFmpeg 后查看退出码。接受 UTF-8/ASCII（可剥输入 BOM）；拒绝 NUL、无法解码、未知控制字节。允许普通注释/空白，但完整扫描尾部。
3. 仅一个十进制 `LUT_3D_SIZE 33`；尺寸只出现一次、位于数值表之前。拒绝 `LUT_1D_SIZE`、`LUT_*_INPUT_RANGE`、其他组合 shaper/视频范围指令及未知头部。可读取 TITLE 为元数据，但不把其内容拼入 shell/filtergraph。
4. DOMAIN 可缺省，或各出现一次且**恰好** min=(0,0,0)、max=(1,1,1)，均须在数据前。非默认域明确报“当前剪映兼容档未验证”，不自动重新解释、扩域、缩域或重采样。
5. 数值表恰好 35937 行，每行仅三个数值 token，全部可解析为有限 float32，且处于 [0,1]；拒绝 NaN/Inf、overflow、缺行、多行、第四列、表中再次出现头部。取证保存实际 min/max、数值行数、尺寸、domain、原始与规范副本 SHA。
6. 副本用 ASCII、LF、无 BOM；仅尺寸行 + 数值行。可以保留已验证数值 token 的文本，避免额外舍入；如果重新格式化，应做 float32 往返相等验证。表格顺序不改，保留 R-fastest 顺序。**不能根据颜色是否单调判断顺序**，艺术 LUT 完全可以非单调；顺序应由格式语义及原创坐标表测试来保证。
7. 17³、65³、1D+3D、扩展/HDR输出与自定义 DOMAIN 暂停在明确验证错误上，保留原件。不要静默降到33或压值后还称“原表已支持”。以后每个新增档位用原创 identity+强变化表，做同样的原生0/.4/1出片、GUI保存/历史验收再扩充。

这套限制保护的是当前已证明正确的 SDR 资源链。自定义 Cube 本身不描述素材应为 Rec.709、LogC、S-Log 或某相机色域；源色彩空间/传递函数应由现有素材信息和用户说明确定。不能仅凭 LUT 文件名猜颜色管理，更不能把诊断 LogC→709 表当所有实拍的通用审美提升。

### 现有材料与依赖链

- 扩展现有 plan 中 LUT 的**资源选择**，让用户 source Cube 与强度一起进入目前材料构建流程。保留现有 profile/效果资源包的 hash 钉住策略；用户数据表则由上面的格式+SHA校验替代写死的诊断 Cube 文件名/hash。
- 将规范副本命名为固定安全 ASCII 名如 `user.cube`，存于短路径、独立、按内容 hash 命名的依赖目录；随草稿复制。原件可保留在项目自己的记忆/资源记录中，不依赖下载目录长久存在。原有 `source_dependencies`/`copy_dependency` 的拷前、拷后 hash 核对值得复用。
- 仍按已经实证的 compound path：`<absolute cube>;<absolute effect package directory>`。两个路径统一 `/`，避免本次已经证实的反斜杠被原生 JSON 拼接器错误解释；不要通过随意改变反斜杠数目赌上层转义。原始来源路径不直接成为 nativecompound path；生成的短路径也避免分号等协议分隔字符。
- `lumi_hub_path` 继续指真实合并效果包；不得用 compound path 替代它。保持 LUT 材料 `type/path/value/refs/enable_lut` 的现有路由；不改 DLL/ABI，不加入猜测开关。
- 先在独立测试草稿验证自定义 identity 和 R/B 互换表，然后才接入真实用户 LUT。导出后仍应是原视频路径 + LUT 材料，而不是把滤镜后的 MP4 回填主轨。

## 可直接复用的 FFmpeg 参考命令

用 argument array 启动现有 exe，在私有临时工作目录放受验证的 ASCII 文件名 `input.cube`。不要把用户完整 Windows 路径直接插进 `-vf`；盘符冒号、反斜杠、引号和 filtergraph 有多层转义。以下命令示意 cwd 中已有该规范副本。

只检查 FFmpeg 能建立并运行滤镜（仍必须先做严格解析）：

```powershell
& $ffmpeg -nostdin -hide_banner -v error -cpuflags 0 `
  -f lavfi -i 'color=c=gray:s=128x128:r=1:d=1' `
  -vf 'format=gbrpf32le,lut3d=file=input.cube:interp=tetrahedral' `
  -frames:v 1 -f null -
```

对明确准备好的同色彩空间 RGB 参考帧输出可检查的单帧；该 PNG **仅参考附件**，不进入草稿替代原素材：

```powershell
& $ffmpeg -nostdin -hide_banner -v error -cpuflags 0 `
  -i source-rgb-reference.png `
  -vf 'format=gbrpf32le,lut3d=file=input.cube:interp=tetrahedral,format=rgb24' `
  -frames:v 1 -y reference-lut.png
```

更适合数值对照的是本研究完整全网格 raw-float 命令，已保存在 proof JSON。它避免 PNG 的8bit裁剪掩盖超范围值。若对真实YUV/带HDR标签素材做参考，应显式记录解码矩阵、range、transfer、gamut、目标格式和同一帧时间；上述 PNG 示例本身不执行 Log→709/HDR tone mapping。

### 原生实际验收的最小集合（交主线程执行，本轮未执行）

- 自有33³ identity，强度0/1，输出应无额外创意色差；自有 R/B 交换，强度1应得到明确通道互换趋势，排除“加载成功但没用上表”。
- 同一真实素材、固定其他调色、同一资源目录，0/.4/1 三档。保存材料并对解码RGB比较，应能证明强度有序影响；不能单靠日志 `lut_intensity` 判断实效。
- 从当前页真实模型改强度，保存、undo/redo、回读、再出片；确认材料路径仍为独立 Cube，主素材未烘焙。与用户真实 LUT 的创造性适配是后续审片项，技术接通不等于画面自动高级。

本轮已完成格式/源码/静态loader/FFmpeg独立验证；剪映新自有表的实际渲染及当前页历史验证由主线程执行，报告不将待验证项写成通过。
