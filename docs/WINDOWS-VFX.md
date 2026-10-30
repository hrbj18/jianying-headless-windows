# Windows 转场、滤镜、特效与蒙版

视觉能力限于本机正版 **11.4.7.14462** 和已审核的资源字节。先运行 `jianying.ps1 doctor`，
再用 `jianying.ps1 vfx catalog` 查看冻结资源、参数、完整文件树 SHA256 与本机绑定。
本页是视觉动作的范围、坐标和兼容规则的权威说明；命令成功仍需保存读回及实际画面验收。

编辑通过官方 Lyra typed CLI 和已审核的窄范围草稿兼容模块，预览直接使用暂停的原生播放器，
导出通过 ExportService。流程不使用鼠标、键盘或桌面截图。编辑已保存磁盘状态，执行期间
保持 GUI 与其他任务不修改同一工程；先完成结构性 Blueprint 编辑，再执行参数动作。

## 资源与动作

静态圆蒙版现在也可直接写入正常 `jy14-headless-plan/v1` 的视频段，无须先发布工程再修改：

```json
{"mask":{"preset":"mask/circle-soft","config":{"width":0.6,"height":0.285,"center_x":0,"center_y":0,"feather":0.02}}}
```

该入口复用下表同一冻结包、材质契约和参数范围，构建时复制完整资源到工程自身
`Resources/vfx/<SHA前16字符>`，完整 SHA 与逐文件哈希仍用于验包，并拒绝短目录碰撞。
此前 `Resources/headless-native/<完整SHA>` 布局继续按原字节校验。`scale/x/y` 控制前景片段整体变换，蒙版 `config`
控制内部取景。在 912×1920 画布中宽 0.6、高 0.285 可形成近似正圆，再随片段整体缩放。
本轮以真实直播 5163 秒入点验证了画中画圆蒙版与原生预览、120 帧导出；不扩展到其它形状。
旧跨平台 `{shape:...}` 写法不是此 Windows preset 接口。尚未发布时，预检只在内存副本
把未来首页资源路径解析到已验哈希的构建副本；工程保存路径及发布验收保持不变。

动作沿用 `jy-windows-edit-actions/v1.actions`，目标为一个真实 `segment_id`。
`preset` 必须来自 `vfx catalog` 的已绑定资源，效果包逐文件校验后才允许编辑及渲染。

| preset | 动作 | 已验证参数 |
| --- | --- | --- |
| `filter/cyberpunk` | `video.filter.add` | `value` 为 0..1 |
| `filter/blanca` | `video.filter.add` | `value` 为 0..1 |
| `filter/retro-lomo` | `video.filter.add` | `value` 为 0..1，像素验收覆盖 0、0.5、1 |
| `filter/silent-film` | `video.filter.add` | `value` 为 0..1，像素验收覆盖 0、0.5、1 |
| `effect/oobe-glow` | `video.effect.add` | `value` 固定为 1 |
| `effect/mild-shake` | `video.effect.add` | `value` 固定为 1，使用原包默认轻微抖动 |
| `effect/blur` | `video.effect.add` | `value` 固定为 1，使用原包默认模糊 |
| `transition/white-flash` | `video.transition.add` | `duration_ms` 为 400 或 600 |
| `transition/dissolve-compat` | `video.transition.add` | `duration_ms` 为 400、600、800 或 1200 |
| `transition/fog-compat` | `video.transition.add` | `duration_ms` 为 400、600、800 或 1200 |
| `transition/slide-left-compat` | `video.transition.add` | `duration_ms` 为 400、600、800 或 1200 |
| `transition/slide-right-compat` | `video.transition.add` | `duration_ms` 为 400、600、800 或 1200 |
| `mask/circle` | `video.mask.set`、`video.mask.update`、`video.mask.keyframe` | 尺寸、位置及四个几何关键帧通道，羽化固定为 0 |
| `mask/circle-soft` | 同上 | 尺寸、位置、0..1 羽化及五个蒙版本体关键帧通道 |

这些是精确资源与参数的验收范围，不能由此推断同类任意资源、会员云功能或其它构建可用。

```json
{
  "schema": "jy-windows-edit-actions/v1",
  "draft_dir": "D:\\JianyingHeadless\\work\\my-job\\drafts\\unique-project",
  "actions": [
    {"op": "video.filter.add", "segment_id": "真实片段UUID", "preset": "filter/cyberpunk", "value": 0.65},
    {"op": "video.transition.add", "segment_id": "切点左侧真实片段UUID", "preset": "transition/dissolve-compat", "duration_ms": 800},
    {"op": "video.mask.set", "segment_id": "前景真实片段UUID", "preset": "mask/circle",
     "config": {"width": 0.5, "height": 0.7, "center_x": -0.25, "center_y": 0.1}}
  ]
}
```

```powershell
.\jianying.ps1 vfx catalog
.\jianying.ps1 edit-actions --plan D:\JianyingHeadless\work\my-job\vfx-actions.json `
  --out D:\JianyingHeadless\work\my-job\vfx-audit
.\jianying.ps1 vfx freeze-draft --draft-dir D:\JianyingHeadless\work\my-job\drafts\unique-project `
  --out D:\JianyingHeadless\work\my-job\vfx-freeze
.\jianying.ps1 preview --draft-dir D:\JianyingHeadless\work\my-job\drafts\unique-project `
  --out D:\JianyingHeadless\work\my-job\vfx-preview --at 2.5 2.8 3 3.2 3.5
.\jianying.ps1 export-draft --draft-dir D:\JianyingHeadless\work\my-job\drafts\unique-project `
  --out D:\JianyingHeadless\work\my-job\vfx-render
```

预览时点按工程实际切点和关键帧选择。`applied-and-read-back` 证明已保存值及绑定符合动作；
`native-frames-captured` 证明取得了带时间戳的引擎帧；`encoded-and-decoded` 证明成片通过
结构、时长、帧数及完整解码。交付前仍要检查画面和声音，尤其是转场中间帧与蒙版边缘。

## 转场的共同条件

转场挂在切点**左片段**的 `extra_material_refs`，后面必须紧跟真实相邻主视频，末段不能加。
当前范围是普通视频、静音源、正向 1 倍速度、单时间线及 overlap；照片、复合片段、变速曲线
和有声源重叠需要独立验收。独立音乐轨不受源视频静音限制，最终仍需检查混音。

转场以切点为中心，不缩短两段的原有总长。以左右各 3 秒、800ms 转场为例，总长仍为 6 秒，
覆盖切点前后各 400ms。左段源结尾之后、右段源开头之前都必须有相应源余量，不能靠重复末帧
补足；两端转场在同一中间段上的窗口也不能相互重叠。入口按实际源时长与保存时间核对。

### 白光快闪

`transition/white-flash` 对应官方资源 RID `7343136487182963211`。冻结包保留原始
`AmazingFeature/main.scene`，164 个原文件按摘要校验。400/600ms 均通过原生预览及导出
逐帧检查：红、蓝隔离样例在重叠区出现可测的光斑与闪光，原有切点前后仍为对应源镜头。

### 叠化和雾化的本地兼容资源

官方叠化 RID `6724845717472416269` 与雾化 RID `7216171159589491259` 的原包是
`GeneralEffect`。原裸运行时加载这些原包时寻找 `main.scene`，即使能编码，画面也会延迟硬切。
本项目以**单独命名的本地兼容包**接入正常入口，没有声称修好了应用原本的 GeneralEffect 路由。

- `transition/dissolve-compat`：保留官方叠化 fragment 原字节，用已验证的 AmazingFeature
  场景胶水绑定两个原生转场输入纹理和归一化进度。
- `transition/fog-compat`：在同一官方引擎内运行原始 8 遍 Gaussian fragment 和 blend
  fragment，保留 120 张原始雾化遮罩及 `event.lua` 中原有 AE 曲线和更新逻辑。胶水只连接
  场景、纹理、时间及 uniform；不以其它视频合成器或片段关键帧代替效果。

四种时长分别完成原生导出、完整解码和像素验收。叠化 800ms 的 3 秒中心帧红/蓝约为
127/127；四档均出现连续两源混合。雾化用高频网格验证了模糊和非均匀遮罩推进，1200ms
样例的绿通道 Laplacian 方差从切点前 9077 降至重叠区 1471、456，随后进入右源镜头。
资源复制到新路径、官方 CLI 添加并保存、加密草稿恢复后再次原生渲染均已验证。

雾化当前 v3 兼容包复用场景中已有的 8 组相机/renderer 和两个已序列化 RT，关闭会重写
相机/RT 的无关模板脚本，修复暂停播放器的左源黑场。原始 shader、AE 更新逻辑和 120 张
遮罩保持原字节；暂停首帧、重叠区真实模糊与非均匀遮罩、末帧及乱序/重复 seek 均已验证。
正常 `preview` 直接取得 VEF1/PNG，不调用 ExportService 或 FFmpeg 取帧。
历史 v2 草稿仍按完整已审核摘要识别，预览仅在独立副本升级资源并留下 `resource_upgrades`，
原工程不变；新动作默认绑定 v3。具体报告和副本升级规则见
[原生帧预览](WINDOWS-NATIVE-PREVIEW.md)。正式导出使用工程保存的资源版本。

`vfx build-compat` 的参数以该子命令 `--help` 为准。构建器只接受已锁定的官方原包、场景模板
与 Lua 胶水摘要，生成单独的新目录，最终完整树也必须匹配已验收摘要。包内保留
`original-ge/` 与 `COMPATIBILITY-PROVENANCE.json`，记录原文件、shader 字节相等证明和
胶水来源。重建的四套兼容包须逐文件一致；构建本身不下载新资源、不修改应用，也不自动登记陌生摘要。

### 左右推移、复古 LOMO、默片、轻微抖动与模糊

本批新增六项资源，沿用上表的动作入口。左右推移对应官方 RID
`6726711499676455435` / `6726711296063967748`；独立兼容包保留各自原始 fragment，
复用已验收的两输入纹理与归一化进度胶水，原 shader 内的五次缓动与位移方向保持不变。
可用 `vfx build-compat --kind slide-left` 或 `--kind slide-right` 按固定输入、输出摘要重建；
官方资源内部 RightMove/LeftMove 目录名与界面名称方向相反，preset 以界面名称和真实像素运动为准。

复古 LOMO RID `7513594589790375178`、默片 RID `7127655037026848031`、轻微抖动 RID
`7399493554147527951`、模糊 RID `7399495140399746304` 均使用完整官方原包，不改写其 shader
或脚本。滤镜强度由 `value` 控制；两种特效目前只接入默认效果，`value:1` 是绑定值，
不代表可调抖动幅度或模糊半径。资源元数据中的滑杆不等于已经开放参数编辑。

验收使用正常 `edit-actions → vfx freeze-draft → preview / export-draft`；
播放器直接输出 VEF1，独立 ExportService 生成视频并完整解码。同时间点对照按 30fps 帧网格
取样：例如 2.85 秒处于两帧之间，不能直接与 2.866667 秒导出帧比较并将位移差异误判为渲染缺陷。
方向、空间模糊、时变抖动与滤镜强度另做内容检查，编码成功不能代替这些检查。
本批使用静音测试素材；音轨试听和 GUI 冷重开不属于此次验收。
静态网格抖动的 10 个逆序时点均与正序 PNG 字节一致；含六项新资源的组合工程逆序复核
有 15/16 帧字节一致，8.0 秒处的抖动输入半幅出现轻微差异，整帧 RGB 平均误差约
0.62/255，时间戳一致且没有黑场。原因尚未定位，不承诺组合预览逐字节确定；
该现象与本批 120 张帧网格对齐的预览/导出对照分别记录。

## 蒙版尺寸、位置和羽化

`video.mask.set` 新增一个 `mask/circle` 或 `mask/circle-soft`，已有蒙版时使用
`video.mask.update` 并保持原 preset。`mask/circle-soft` 使用已冻结的现代官方 27 文件原包，
完整树 SHA256 为 `755f487494e041e0adceaff3c1a747b1238773c071fe3297d1911112cccd3946`。
`config` 是对象；set 省略的字段采用默认值，update 只修改显式字段且至少提供一个。
宽高各按画布相应轴归一化，因此等宽高值在 16:9 画布上形成椭圆，preset 名称不代表始终正圆。

| config 字段 | 范围 / 默认 | 含义 |
| --- | --- | --- |
| `width` | 0.05..1 / 0.65 | 相对于画布宽度 |
| `height` | 0.05..1 / 0.65 | 相对于画布高度 |
| `center_x` | -1..1 / 0 | 画布半宽坐标，正值向右 |
| `center_y` | -1..1 / 0 | 画布半高坐标，正值向上 |
| `feather` | `mask/circle-soft` 为 0..1 / 0；`mask/circle` 固定 0 | 原生归一化软边控制量，非像素半径 |

```json
{"op": "video.mask.update", "segment_id": "已有软边蒙版的真实片段UUID", "preset": "mask/circle-soft",
 "config": {"width": 0.75, "center_x": 0.3, "center_y": -0.2, "feather": 0.5}}
```

旋转、反转、圆角、扩张、跟踪和人物分割不由此接口自动获得支持。参数属于蒙版本体，
不会通过移动/缩放前景片段伪装成蒙版参数。已有同属性蒙版关键帧时，静态 update 会拒绝该字段，
避免保存的基础值被动画覆盖；应通过 `video.mask.keyframe` 修改对应通道并检查实际帧。

旧 `mask/circle` 的 RGBA 输出编码与新蒙版协议不匹配，非零羽化不能据保存值宣称渲染成功。
可调羽化使用现代原包 `mask/circle-soft`，保留包内原始 shader 和参数，已对
0、0.02、0.1、0.5、1 完成软边像素检查，并通过原生预览及导出；相应边缘随值变化可见。
`mask/circle` 的非零羽化仍会被拒绝，不把新资源的验收套用到旧包。

## 蒙版本体关键帧

动作 `video.mask.keyframe` 通过官方 CLI 按蒙版 `material_id` 绑定通道。调用者提供片段 ID
与 preset，入口解析唯一已绑定蒙版；通道不会落到片段整体变换上。

| property | 原生通道 | 值域 |
| --- | --- | --- |
| `width` | `KFTypeCommonMaskSizeWidth` | 0.05..1 |
| `height` | `KFTypeCommonMaskSizeHeight` | 0.05..1 |
| `center-x` | `KFTypeCommonMaskPositionX` | -1..1 |
| `center-y` | `KFTypeCommonMaskPositionY` | -1..1 |
| `feather` | `KFTypeCommonMaskFeather` | 0..1，仅 `mask/circle-soft` |

前四个几何通道用于两种已审核 circle preset；第五个羽化通道仅用于现代 `mask/circle-soft`。
注意位置关键帧名用连字符 `center-x` / `center-y`，静态 config 用下划线 `center_x` / `center_y`。

```json
{"op": "video.mask.keyframe", "segment_id": "已有软边蒙版的真实片段UUID", "preset": "mask/circle-soft",
 "property": "feather", "curve": "linear",
 "points": [{"time_ms": 0, "value": 0}, {"time_ms": 750, "value": 0.1},
            {"time_ms": 1500, "value": 0.5}, {"time_ms": 2250, "value": 1},
            {"time_ms": 2990, "value": 0}]}
```

每个通道有 2..256 个严格递增、不重复的整数毫秒点，第一点必须是片段局部时间 0，末点不超过
当前段长。当前只验收 linear、正向 1 倍速度、源入点为 0、源段长等于目标段长的普通视频。
不能将裁切入点、变速、倒放、非线性曲线或任意 CommonMask 类型当作已支持。

四个几何通道及现代包羽化通道已有真实保存读回和原生像素证明，羽化的
0→0.1→0.5→1→0 动画完成保存、预览及导出验证。具有 `Timelines/project.json` 的正常工程必须在
声明主时间线直接读回通过。少数历史草稿缺少该声明且根文件与嵌套时间线布局不一致时，
兼容模块只在验证目标、蒙版绑定、源素材和时间范围一致后，将指定官方结果字段或通道
写入选中的主时间线；它不整份覆盖根时间线，也不把历史布局现象概括为官方 CLI 通用缺陷。

## 协议、快照与失败语义

本机官方蒙版 add 使用 Vimo 资源解析，当前不能直接用本地 mask 包完成添加。
入口以 `vimo://7356934080102928946` 添加 circle；现代 preset 使用名称 `REA-circle-soft`，
项目兼容模块随后只把已核对的蒙版资源路径绑定到确切的 27 文件现代原包，并设新协议标记。
保存调用官方 `EncryptUtils`，保留前后密文、字段与完整工程审计；原始 shader 包保持原样。
旧 circle 的必要协议协调同样限于声明主时间线。后续官方保存可省略
默认值 false；显式 true 仍须兼容处理。其它镜像不自动同步，GUI 打开、保存及冷重开另行验收。

原生预览和导出检查完整 **48 文件**内建蒙版运行时，导出将其复制到任务快照并显式传入
原生助手。保持应用文件、运行时指纹和资源摘要校验；未知资源、形状、材质字段或算法依赖
停止并保留证据，不能靠静默删除效果取得成功。Windows 没有额外的网络阻断沙箱。

`edit-actions` 每步即时提交，保留 `before/` 和时间线，逐步记录官方返回与原生读回。
兼容写入同样非原子；失败立即停止，保留已完成步骤、恢复副本及证据，不自动回滚或整批重放。
并发检查不等于原子锁，执行期间 GUI 与其它任务应保持目标工程不变。

需要可编辑完整工程时，编辑后运行 `vfx freeze-draft --draft-dir ... --out ...`，将已审核效果包
复制到工程自身 `Resources/reviewed-vfx/<SHA>`，仅重写声明主时间线的对应路径。成功状态
`frozen-and-read-back`，已自有资源为 `already-draft-owned`；冻结后再预览、导出，并备份含
Resources 的整个工程。工程登记首页与 ZIP 备份的路径语义分开说明，MP4 不能代替工程。

转场/蒙版的官方资源解析可能连接官方服务；本工具沿用已有授权，不登录、提取凭据或购买。
本地兼容转场使用固定本地包。预览、导出复制媒体、字体和效果依赖，结束后核对源数据不变。
