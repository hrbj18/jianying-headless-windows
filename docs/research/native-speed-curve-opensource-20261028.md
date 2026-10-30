# Windows 剪映原生曲线变速：开源与一手证据

日期：2026-10-28。研究范围：只读源码与本机已安装脚本，未操作活跃剪映、未运行渲染、未发云请求、未读凭据、未使用 computer use。

## 结论

现成的 pyJianYingDraft / pyCapCut / CapCutAPI 不能直接补齐原生曲线变速。最短可验证路径是复用本项目已有官方 `lyra draft video speed` 入口：它已发现 `--curve-name`、`--curve-resource-id`、`--curve-points`。用隔离试样取得真实原生 `curve_speed`，再验证实际渲染、时间映射、保存及再次修改。不要用分段固定速度或 FFmpeg 预渲染冒充原生曲线。

本机官方安装包的一手 JavaScript 数据模型同时证实曲线点字段与时间映射。这里只得到静态事实，不代表 Windows 11.4.7 的 CLI 应用、原生渲染和可编辑性已经通过。

## 开源项目实际覆盖

| 项目／固定提交 | 观察 | 许可与复用判断 |
|---|---|---|
| [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft/tree/1e228479dda361e312e85f6037002346cf6dca9a) | README 明确暂不支持曲线变速；`Speed.export_json()` 硬写 `curve_speed: null, mode: 0`。 | Apache-2.0。可参考草稿基础结构，不能声称集成它就获得曲线变速。 |
| [pyCapCut](https://github.com/GuanYixuan/pyCapCut/blob/main/english_readme.md) | Source Trimming and Global Speed 段明确曲线变速尚不支持。 | 本次未下载／核验其 LICENSE，不复制实现；没有曲线实现可复用。 |
| [CapCutAPI（现重定向 VectCutAPI）](https://github.com/sun-guannan/VectCutAPI/tree/48f8ff9155f4fae37bc8896c57c580cf91c4132a) | 内嵌 `pyJianYingDraft/segment.py` 的 Speed 仍硬写 `curve_speed: None`，全仓检索未找到可执行曲线构建器。 | Apache-2.0。服务包装不解决曲线模型。 |
| [chukcut](https://github.com/chuk-development/chukcut/tree/2609ea72bff998b079f0f5c2f4dabc75aee00cf1) | 作者直接从实际 CapCut 草稿和 videoeditor.dll 符号整理格式；指出 `lvve::CurveSpeed` 有 name/source_platform/speed_points，但坦言样本未实际使用曲线。 | GPL-3.0。作为字段发现参考；本次未复制其实现，也不能把符号发现当作实际渲染验证。 |

上面三个已下载仓库保存在 `D:\JianyingHeadless\integrations\speed-research-20261028`，均未运行其中的自动导出／UI 代码。

pyJianYingDraft 的一级源码证据：

- [README 的源区间与全局变速](https://github.com/GuanYixuan/pyJianYingDraft/blob/1e228479dda361e312e85f6037002346cf6dca9a/README.md#%E6%BA%90%E7%89%87%E6%AE%B5%E6%88%AA%E5%8F%96%E4%B8%8E%E5%85%A8%E5%B1%80%E5%8F%98%E9%80%9F)，本地 README 第 366 行明确曲线不支持。
- [Speed 原始实现](https://github.com/GuanYixuan/pyJianYingDraft/blob/1e228479dda361e312e85f6037002346cf6dca9a/pyJianYingDraft/segment.py#L79-L98)。
- [VectCutAPI 同类实现](https://github.com/sun-guannan/VectCutAPI/blob/48f8ff9155f4fae37bc8896c57c580cf91c4132a/pyJianYingDraft/segment.py)。
- [chukcut 草稿研究的 speeds 节](https://github.com/chuk-development/chukcut/blob/2609ea72bff998b079f0f5c2f4dabc75aee00cf1/docs/research/draft-format.md#speeds)。它的字段来源范围有明确标注，不宣称曲线样例已验证。

## 本机官方一手静态证据

安装位置：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462\Resources\canvas_agent\app\static\js`。

1. `ai-creation~6.6c54528c.js`，Webpack 模块 22611：CurveSpeed 序列化公共字段为 `id, source_platform, name`，数组字段为 `speed_points`。每个点为 x/y。程序内对应 `id, sourcePlatform, name, speedPoints`。
2. `ai-creation~3.fbc221b2.js`，模块 59631：模板变速命令 `TEMPLATE_CHANGE_VIDEO_SPEED` 的选项包含 `segmentId, mode, normalSpeed, curveSpeedName, curveSpeedResourceId, curveSpeedPoints, draftId`；曲线模式把传入点转为原生 Point 对象，设定曲线 id/name/points；普通模式移除 curveSpeed。它同时更新 speed 和 sourceTimerange，不能只写一个 JSON 数组而忽略时间范围。该模板命令不是已验证的 CLI 通用变速调用，不能混淆路由。
3. `ai-creation~12.a09721b4.js` 模块 15123 的曲线数学类：`setSeqDuration`、`mapSeqDeltaToTrimDelta`、`mapTrimDeltaToSeqDelta`、`_calculateAveCurveSpeedRatio`。
4. `ai-creation~14.7680558e.js`，模块 50859：公开使用上述数学类，提供平均速度、源／目标映射及拆分曲线等操作。
5. `ai-creation~5.38151757.js`，模块 30472 的原生迁移 `curveSpeedResourceIdFix` 名称表：自定义 `6768730851543880206`、蒙太奇 `6768648600848175619`、英雄时刻 `6768650238149267981`、子弹时间 `6768731518358524430`、跳接 `6768731594225095175`、闪进 `6768731653402530307`、闪出 `6768731733484376589`。这是安装包直接证据，不依赖网络摘要。
6. 同文件模块 74893 的枚举：`SpeedModeNormal=0`、`SpeedModeCurve=1`、`EffectPlatformLoki=0`；CurveSpeed 构造器的 `sourcePlatform` 默认就是 EffectPlatformLoki。这些是静态类型与默认值，不代替一次真实 CLI 保存结果。

由这些静态实现可以直接得出：

- x 是相对于目标片段时长的归一化时间，y 为速度值。x 先乘 `seqDuration` 再映射到源时间。不要把 x 当源时间。
- 平均速度：`sum((y[i]+y[i+1])/2 * (x[i+1]-x[i]))`。它是曲线下面积，不是控制点 y 的普通算术平均。
- 两点之间的瞬时速度并非简单一条直线；本机实现将区间分为三段，两个内部边界使用 0.2951、速度差权重使用 0.8。源时间通过分段速度积分得到；逆向映射解二次式。只按线性或平均速度推帧索引会在中间时点出错。
- `ai-creation~14` 提取音频的代码会复制 speed，并保留 `isToneModify` 标记。这只能证明结构可继承，不能证明曲线原声的声调、同步、算法实际渲染质量。

本地字段形状（示意，不是已完成验收的可直接导入工程）：

```json
{
  "type": "speed",
  "id": "<material UUID>",
  "mode": 1,
  "speed": 1.5,
  "curve_speed": {
    "id": "6768730851543880206",
    "source_platform": 0,
    "name": "自定义",
    "speed_points": [{"x": 0, "y": 1}, {"x": 0.5, "y": 2}, {"x": 1, "y": 1}]
  }
}
```

本地只读摘录与精确文件 SHA256 位于 `installed-speed-static-excerpts.json`；这些安装包片段属于运行时研究资料，未放进开源模块或发布包。REA 已以 inert text 分析选定四个文件，未执行 bundle、未附加 UI。

REA retained Evidence：`ev_8a4be715c72bc5ef99f307bdc82f5110c6963b02d1d833a667bcce408123f913`，summary view `ev_0417ec23fa8b3dbdeb1f694e742cece57e6d9213ecba4c1b26b9c24818ccc9e2`。四文件共 803173 字节、4 个 JS 均可解析；其余 65 文件未分析，动态关系和部分语义因上限保留为 unknown，不声称完整应用分析。另对名称／枚举所在 ~5 文件单独取得 Evidence `ev_132e98a64f8b7c8839705e8268c3dd2f3fca941ac0b5e75ea6e50af501da7a58`，解析 288112 字节、1 个 JS，无解析错误。证据导出为同目录 `rea-speed-static-evidence.json`（约 35.6 MB）。

## 本项目当前阻断与最短验证路径

- `engine/lyra_commands.json` 的 `draft video speed` 帮助清单已发现 `--curve-name / --curve-resource-id / --curve-points`，完整 CLI 输入格式仍应读当前真实 `--help`，本研究未启动官方宿主获取帮助。
- `engine/native_export.py:170-171` 明确拒绝任何非空 curve_speed。`windows_vfx.py`、`windows_mask_keyframes.py` 另有 1x／无曲线限定。不要为了通过导出而删曲线或全面取消守卫。
- 优先在独立三秒、带帧号的本地原片上试验 `(0,1),(.5,2),(1,1)`，平均 1.5，目标两秒，30 fps 应为精确 60 帧。先用 source_start=0，普通无特效视频，避免曲线、转场、蒙版、混音同时引入。
- 从官方命令保存结果取得全部真实字段和 source/target range。通过原生预览与实际导出，逐帧检查帧号随时间的非匀速变化；比较仅改变中间控制点的 B 版，防止曲线被当成平均固定倍速。
- 保存、原生打开、回读控制点，再改变一个点、保存、重出片；结果应改变且原件哈希不变。仅有字段留存或命令成功不能算可编辑性成立。
- 初次视频曲线通过后再以标记音／连续音源验证原声时间映射、pitch 标志、切点和声道；切勿由静音视频通过推导原声同步也通过。

## 未证实线索与未知项

搜索索引命中 `mcncarl/jianying-headless/docs/SAVED-DEFAULTS-115.md`，摘要提到 macOS 11.5 自定义曲线身份、mode 1、x 从 0 到 1，以及平均速度保存重算。但是 GitHub 原地址与镜像直接访问均为 404，当前未取得该源码或许可证；该摘要也明确并非公开曲线导出支持。因此该摘要只作为检索线索，不作为复制实现或本机验证的依据。自定义 id 与 mode 已随后由上面的本机安装包独立证实，不需要依赖摘要。

仍待实际验证：CLI 曲线点语法；custom/preset 的实际调用与保存行为；本机 native 渲染与帧数；任意入点、曲线修剪／拆分、非线性变速与其它关键帧的组合；原声保调与光流补帧。最后一项不能由 curve_speed 字段本身获得。
