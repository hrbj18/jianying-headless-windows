# 2026-10-30 开发快照与换机交接

用户要求将当前版本上传 GitHub 并制作可继续开发的压缩包。
原仓库对当前登录账号返回 403；用户明确选择上传到 hrbj18 名下的继续开发仓库。
因此使用 <https://github.com/hrbj18/jianying-headless-windows>，原仓库保留为 upstream。

## 本轮交接修复

- 先备份全部已跟踪/未忽略的工作文件、原 HEAD、Git diff 与文件摘要，再处理已有未提交修改。
- 两个 Skill 入口的 11 项源码哈希落后于现有实现；回归检查后同步到当前源码。
  `agent_entry.py` 的 CRLF 规范化为项目声明的 LF；官方 DLL、ABI、桥 DLL 和其摘要未改。
- 源码检查遵守 Git 的跟踪/未忽略边界，避免扫描 `.local` 和被忽略的私有研究媒体。
  保留跟踪文件必须属于已检查清单的限制；增加现有 CSV/TypeScript 文本类型，支持链接行号。
- 补回 OVS 固定提交中已被原版文档引用的 `ecommerce.md`，记录文件摘要，未改原版规则。
- 历史文档中的本机证据链接改为明确的路径说明，用户目录使用占位符；未把外部证据伪装成随包文件。
- 增加 [换机说明](../WINDOWS-DEVELOPMENT-HANDOFF.md)、
  [下一轮研究题目](../DEVELOPMENT-NEXT.md) 和本机 Python 包版本快照。

## 实际验证

- `jianying.ps1 agent --client codex doctor`：ready，精确 11.4.7.14462，
  官方签名、运行时哈希、工具链和自有实时桥通过；未调用云端 ASR。
- `python -m unittest discover -s tests -v`：686 项测试，677 通过，9 跳过，0 失败。
  跳过项保留在测试日志中；未以此宣称干净机器原生编辑/导出已验收。
- `python -m pip check`：No broken requirements found。
- `tools/check_package.py`：语法、源码 pin、已知隐私模式、相对链接和跟踪边界通过。
- 额外凭据模式检查未发现待发布文件中的 API Key、GitHub Token、AWS Key 或私钥。

交接包另记录精确提交、独立 Git 检出验证、逐文件摘要、ZIP CRC 和历史 bundle 校验。
新电脑仍须按换机说明重建本机环境，再执行体检和需要的真实媒体验收。
