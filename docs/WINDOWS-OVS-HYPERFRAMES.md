# OVS 与 HyperFrames 接入现有剪映

这是一条项目内制作链，不新增平台、账号、后台 Agent 或自动任务。

## 已接入范围

- `integrations/orkas-video-studio/` 保存 MIT 上游的原版 EDL 校验器、参考学习和设计审片方法。
  提交与逐文件哈希见 `provenance.json`，不修改上游规则冒充通过。
- `tools/validate_ovs_edl.mjs` 用 Node 24+ 执行原版 `validateEdl`。
- `tools/ovs_jianying_bridge.py` 将已验证的源片段计划与独立布局文件转为既有
  `jy14-headless-plan/v1`，再调用既有媒体/字体/轨道校验器；不改原生 ABI、签名或 DLL 检查。
- HyperFrames 固定 `0.8.34`，生成**无声图形底板**，保留 `DESIGN.md/index.html/assets`。
  OVS 的整套平台与其固定 0.7.60 渲染器未安装；此处独立使用 OVS 的纯校验模块与方法。

## 工作流

1. 正常运行 `jianying.ps1 agent --client codex doctor`、新建独立 workspace。
2. 阅读上游 `video-craft/references/reference-recreation.md`，记录实看证据、未知项、
   preserve/may-change 与源时间锚点。先看源帧再写 `ovs-plan.json`，不用文件名推断动作。
3. 建立 `graphics/DESIGN.md` 后写 HyperFrames 图形。用户实拍继续作为剪映原生片段，
   文案继续使用剪映原生文字轨。原声不烘进底板，避免重复声音。
4. 运行固定版本的 HyperFrames check/render；若已有 Chrome，包装会将其传给支持的
   `HYPERFRAMES_BROWSER_PATH`，避免再次下载浏览器。
5. 编译并使用既有 build、preview、export、agent stage，不走 FFmpeg 整片拼接或截图替代原生验收。

```powershell
.\tools\hyperframes.ps1 -Project D:\JianyingHeadless\work\task\graphics check
.\tools\hyperframes.ps1 -Project D:\JianyingHeadless\work\task\graphics render --output background.mp4 --fps 30 --quality high --workers 2
.\.venv\Scripts\python.exe tools\ovs_jianying_bridge.py --edl D:\JianyingHeadless\work\task\ovs-plan.json --layout D:\JianyingHeadless\work\task\layout.json --out D:\JianyingHeadless\work\task\compiled-v1
.\jianying.ps1 build --plan D:\JianyingHeadless\work\task\compiled-v1\production.plan.json --out D:\JianyingHeadless\work\task\build-v1
.\jianying.ps1 preview --build D:\JianyingHeadless\work\task\build-v1 --out D:\JianyingHeadless\work\task\preview-v1 --at 0 2 8 15 23 29
.\jianying.ps1 export --build D:\JianyingHeadless\work\task\build-v1 --out D:\JianyingHeadless\work\task\export-v1
.\jianying.ps1 agent stage --build D:\JianyingHeadless\work\task\build-v1 --open
```

`stage --open` 仅从已打开的剪映首页进入新工程，不替换其他编辑页。

## 适配边界

目前适配连续、帧对齐、原速的 `primary/edit` 片段；非空 OVS 音乐/旁白/字幕轨、生成式
片段或其他层类型明确拒绝，不能默默丢失。音频和文字放在 layout 的独立原生轨道中。
`layout.placements` 必须逐个覆盖 EDL 片段，不能改写素材身份或时间。
图形作为底板、实拍作为上方原生轨是物理图层安排，不把底板冒充实拍来源。

图形内部节点不能在剪映逐个改动：修改 HTML 后重渲并替换该素材；原生文案、实拍切点、
顺序、位置、大小与音量仍可直接编辑。保留完整资源与字体，不能只交一个 MP4。

审片复用上游 `composition-design-review` 的具体问题分级与完整截图检查方法，
但帧由本项目原生播放器/实际导出产生，不声称运行了 OVS snapshot/check 或完整 OVS 平台。
检查必须区分原版计划校验、渲染结构检查、实际看过的帧、听审与 GUI 打开/保存证据。

用户素材、参考图帧、转写、生成片段和剪辑计划保存在私有任务目录，不写入全局 Codex 记忆。
新增适配边界测试：`python -m unittest discover -s tests -p test_ovs_jianying_bridge.py`。

## 本机试剪验收（2026-10-27）

任务记录：`D:\JianyingHeadless\work\ovs-hf-trial30-20261027-151908-1e5fff\acceptance.json`。
剪映草稿 `Haike_OVS_HF_30s_20261027` 已实际打开，7 段实拍、36 段原生文字、10 条轨道。
完成原生文字修改；撤销返回 SAVE_TIMEOUT 后未重放，通过片段/轨道逐项回读确认恢复，随后保存成功。
保存后的草稿原生导出为 1920×1080、30 fps、30 秒、900 帧，完整解码通过、源草稿未变。
最终查看 57 个导出时点；声音完成信号检查，未做主观全程听审。
交付与已知设计限制见该任务的 `delivery/README.md`。

首次打开后若 `subtitle` 返回 `TEXT_PANEL_NOT_BOUND`，先检查审计和原生片段回读，确认是否已写入。
本例在确认未修改后显示编辑窗口，使文字属性面板完成加载，再以新请求完成编辑。
不要自动重放 `needs-inspection` 请求，也不要修改保存文件来假装原生编辑成功。
