# Windows 官方动作批处理

`jianying.ps1 edit-actions --plan <JSON> --out <新ASCII审计目录>` 调用剪映本机官方
Lyra/VMSDK，处理**已保存的磁盘工程**。没有鼠标、键盘或截图驱动步骤。正常入口沿用精确
11.4.7.14462 / 11.5.0.14471 构建、DLL 指纹与官方签名校验。

本机 11.4.7 发现了官方两层协议的实际冲突：XML 片段的 `keyframe x/y` 被转换器要求
`layout="absolute"`，但 Selection/XML 校验器又禁止 `keyframe.layout`。直接用官方
`draft keyframe add --animated-property position-x/position-y` 能成功写入坐标关键帧。
本入口把这种已知命令封装为结构化动作，逐步检查真实草稿读回值。

## 顺序与示例

先通过 `lyra create/resource-import/sync/apply` 完成主副轨结构、文字、基本缩放等，再用
`id_map.json` 的真实 `seg_id` 编写动作。XML 的可读 `xml_id` 不是原生 `seg_id`。
先做变速，再按变速后的有效时长设置关键帧和淡入淡出。

```json
{
  "schema": "jy-windows-edit-actions/v1",
  "draft_dir": "D:\\JianyingHeadless\\work\\my-job\\drafts\\unique-project",
  "actions": [
    {
      "op": "keyframe.add",
      "segment_id": "实际PIP片段UUID",
      "property": "position-x",
      "points": [
        {"time_ms": 0, "value": -0.65},
        {"time_ms": 500, "value": 0.45},
        {"time_ms": 2900, "value": 0.1}
      ]
    },
    {
      "op": "keyframe.curve",
      "segment_id": "实际PIP片段UUID",
      "property": "position-x",
      "time_ms": 0,
      "curve": "ease-out"
    },
    {
      "op": "audio.fade",
      "segment_id": "实际音频片段UUID",
      "in_ms": 500,
      "out_ms": 800
    }
  ]
}
```

```powershell
.\jianying.ps1 edit-actions --plan D:\JianyingHeadless\work\my-job\actions.json `
  --out D:\JianyingHeadless\work\my-job\actions-audit
.\jianying.ps1 export-draft --draft-dir D:\JianyingHeadless\work\my-job\drafts\unique-project `
  --out D:\JianyingHeadless\work\my-job\render
```

可选顶层 `source_timeline_sha256` 精确绑定计划制定时的已保存时间线内容；不匹配时不执行。
`--timeout` 为每个官方命令的秒数，默认 120，范围 1..600。

## 动作契约

所有动作必须提供**一个**存在的 `segment_id`，不支持宽选择器、轨道批选、任意原始命令或
额外字段。时间为整数毫秒；内部 CLI 显式转换为 `ms`，解密读回使用微秒核对。

| op | 字段 | 规则 |
| --- | --- | --- |
| `keyframe.add` | `property`、`points`、可选 `curve` | 2..256 个递增、不重复、有效时长内的 `{time_ms,value}`。坐标/透明度/音量是归一化值；位置 -1..1，透明度 0..1，音量 0..4，缩放 0.01..10，角度 -360..360。 |
| `keyframe.curve` | `property`、`time_ms`、`curve` | 必须已有指定时间点。统一 `scale` 会检查 X/Y 两个缩放通道。 |
| `video.speed` | `speed` | 0.1..10，只接受真实视频；官方可能调整该段时长及后续排布，按读回为准。 |
| `audio.fade` | `in_ms`、`out_ms` | 只接受音频段，均非负，二者之和不能超过有效段长；使用官方默认 fade 类型。 |
| `video.adjust` | `brightness`、`contrast`、`saturation` 至少一个 | -1..1 的无单位数值，**不是 0..100 滑杆百分比**。只开放已确认能落成对应原生类型的三个字段。 |
| `video.background` | `type` 加 `color` 或 `blur` | `color` 为 `#RRGGBB`；`blur` 为 0..1。没有 `type:none`：本机官方 typed handler 会拒绝。 |
| `video.filter.add`、`video.effect.add`、`video.transition.add` | `preset` 及对应强度/时长 | 只接受已审核 catalog 资源，详见 [视觉效果契约](WINDOWS-VFX.md)。 |
| `video.mask.set` | `preset`、可选 `config` | 为目标新增一个已审核蒙版；省略字段使用默认值。 |
| `video.mask.update` | `preset`、`config` | 修改已有蒙版，至少一个显式字段。 |
| `video.mask.keyframe` | `preset`、`property`、`points`、可选 `curve` | 绑定蒙版材质本身；几何四通道及现代包羽化通道，条件见 [视觉效果契约](WINDOWS-VFX.md)。 |

`property` 接受官方帮助中的 `position-x`、`position-y`、`scale`、`scale-x`、`scale-y`、
`rotation`、`opacity`、`volume`。可见属性只作用于视频/文字；音量只作用于视频/音频。
`curve` 接受官方帮助中的 `linear`、`ease-in`、`ease-out`、`ease-in-out`、`free-in`、
`free-out`、`free-in-out`，且必须在原生读回中得到对应曲线类型才报告成功。本机实际调用
与 native `CurveOut` 读回已确认 `ease-out`；其它别名仍需在具体工程中按实际结果验收。

## 蒙版本体动画和兼容转场

视觉动作只针对精确 11.4.7.14462，资源和参数的单一权威范围见
[Windows 视觉效果](WINDOWS-VFX.md)，使用前先读该页并运行 `vfx catalog`。
`transition/dissolve-compat` / `transition/fog-compat` 是单独命名的本地兼容资源，
在剪映原生引擎中执行保留的官方 shader，不能把名称解释为官方 GeneralEffect 原路由已修复。

蒙版静态尺寸、位置用 `config.width`、`height`、`center_x`、`center_y`；动画使用
`video.mask.keyframe` 的 `property: width/height/center-x/center-y`；现代 `mask/circle-soft`
还支持 0..1 的静态 `feather` 与第五个 `property: feather` 动画通道。这些是蒙版本体通道，
不同于上节 `keyframe.add` 的前景片段整体变换。蒙版动画第一点必须为局部时间 0，
仅限已审核的正向 1 倍、源入点 0 和 linear 条件。旧 `mask/circle` 仍只接受羽化 0；
完整值域、资源协议及真实像素验收见视觉效果页。

正常带 `Timelines/project.json` 的工程以声明主时间线直接读回为准。少数历史草稿布局中
根文件与嵌套时间线不一致时，兼容模块只接受经目标、绑定和时间范围核对的官方结果，
把请求的字段或通道协调到选中主时间线；不整份覆盖，也不把旧布局问题概括成所有 CLI
调用都会丢失关键帧。后续预览与导出仍对保存结果作独立画面验收。

## 审计与失败语义

`--out` 必须是新的绝对 ASCII 路径，含独立 `work` 路径段，与草稿目录互不包含。
执行前完整预检计划与所有目标，保存 `before/` 原始工程字节副本和 `before-timeline.json`。
每步保存官方信封 `step-NNN.official.json`、原生时间线 `step-NNN.timeline.json`，并核对
关键帧时间/值/曲线、速度、绑定的 fade/canvas/adjust 材料。下一步前检查工程没有被外部改动。

每步官方命令即时提交，**批次不是原子事务**。一旦命令或读回失败立即停止，
`result.json` 记录已确认完成的数量、错误和恢复位置，不自动回滚或继续后续步骤。
动作间并发变化检查不等于原子锁，执行期间保持 GUI 与其他任务不修改同一工程。
需要恢复时先看证据与 `before/`，明确恢复对象后处理；不覆盖用户同时进行的其它编辑。

成功状态是 `applied-and-read-back`；该状态证明已保存的原生数据符合动作，导出仍需独立运行
`export-draft` 并验收 `encoded-and-decoded`、实际画面及音频。本命令固定记录
`export_status: not-tested-by-this-command`，不把 CLI 成功当成渲染验收。

## 本机验收与限制

11.4.7.14462 的隔离测试工程已真实完成多轨 PIP、缩放/旋转/透明度关键帧、位置 X/Y 关键帧、
`ease-out`、1.5 倍变速、500/800 ms 音频淡入淡出、画布背景和基础调色的命令及原生读回。
上述基础参数隔离测试只用本地合成媒体，不请求网络、读取账号或操作已有用户工程。
视觉动作的资源解析与验收范围另见 [Windows 视觉效果](WINDOWS-VFX.md)。

- 已带位置关键帧的 canonical XML 会由官方读回为 `keyframe layout="absolute"`；这又使
  后续 Blueprint apply 被官方 schema 拒绝。因此结构性 Blueprint 编辑应先完成，之后继续用
  typed 动作更新参数。此入口没有修改官方文件或跳过校验。
- `video.adjust color-temperature` 虽返回成功，本机构建却保存为 `type:none`，因此没有开放。
- `audio.fade` 的编辑契约允许单边为 0；本机 0/800 ms 生成的原生 `fade_type:2` 被导出门禁
  正确拒绝。当前独立原生导出仅验收双边 `fade_type:4`；单边 type 2/3 仍需独立验收，
  不能因为命令返回成功就放开。500/800 ms 双边时长已实测生成 type 4 并出片。
- `video.adjust`、`video.background` 的编辑读回与独立导出范围分开。原生导出守卫可能拒绝
  尚未验收的相关材料，不会为“成功出片”静默删掉调色或背景。
- XML 写入速度时存在被后续时长命令重置为 1 的情况，typed `video.speed` 读回实际 speed=1.5；
  应检查真实时间线，不能只检查转换计划里的 speed 参数。
- 修改草稿比例使用官方 ratio 语义；例如 640×360 的 XML 请求会归一化成 1920×1080 的
  16:9 草稿。精确导出尺寸可用 `export-draft --width/--height`，不写回原工程。

现有官方接口类别还包含媒体裁切/转码/分析、字幕歌词、资源检索、模板、转场滤镜特效、
蒙版跟踪、算法任务、复合片段、多时间线及历史管理。完整历史清单见
[LYRA-CLI-MATRIX.md](LYRA-CLI-MATRIX.md)。命令在帮助中出现只是接口发现；在线资源、会员
能力、算法后端、GUI 未保存状态以及未逐项验证的复杂效果不因本次适配自动成为已验收能力。
