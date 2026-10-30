# Agent 入口

Windows 剪映任务先读 [公共调用说明](docs/AGENT-ENTRY.md)，从 `jianying.ps1 agent doctor` 开始。
Codex、WorkBuddy 使用本目录的同一入口与 `.venv`。当前剪映编辑页的修改走 `agent live`；
离线构建、原生预览和导出走同一入口已有子命令。换目标、会话变化、失败后的处置见调用说明。

改代码前保留已有未提交修改。原生 ABI、DLL 指纹、签名和已验证能力范围均须保留。
