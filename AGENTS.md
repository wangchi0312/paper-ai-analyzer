# AGENTS.md

> 核心项目上下文已同步到根目录 `CLAUDE.md`，Claude 每次启动自动加载。本文件保留长期协作规则。

## 项目协作规则

- 所有回复使用中文。
- 遵循 KISS 原则，优先实现简单、可运行、可维护的方案。
- 每次需求变化时，先更新 `.claude/spec.md`，再实现代码。
- 每次切换 Agent 前，更新 `.claude/handoff.md` 与 `.claude/worklog.md`。
- 如果需求变化影响长期协作规则，同步更新本文件。
- `skills/` 目录只放给 AI 查阅的说明书，不放业务代码。
- 业务代码放在 `paper_analyzer/`。
- CLI 入口放在 `pipeline/`。
- 不创建无必要文档；只有对长期开发有价值的信息才写入 spec、AGENTS 或 skills。
- 不提交真实 API key，不创建真实 `.env`。
- 用户明确要求或批准时，Agent 可以执行联网操作，包括 GitHub 推送、网页请求、真实邮箱抓取、API 调用、pip 安装、模型下载等；涉及真实 API/邮箱/付费调用时先说明风险并保持操作可控。
- Windows 下如果 Codex 内部 PowerShell 宿主异常，默认不要依赖 PowerShell 命令包装，优先直接调用 `D:\software\anaconda\envs\paper-ai\python.exe`。
- 运行测试、CLI、Streamlit 时优先使用 Conda 环境 Python 绝对路径，而不是 `conda run`。

## 当前 V1 方向

- 先实现 CLI 核心流程。
- 再根据 demo 效果实现 Streamlit 前端。
- 构建兴趣向量：读取 `data/profile_pdfs/`。
- 分析新论文：CLI 参数传入单个 PDF。
- 默认 LLM provider：DeepSeek。
- 默认文本选择：优先 Abstract，找不到取前 4000 字符。
- OCR 依赖缺失时给出清晰提示，由用户手动安装 Tesseract 和 Poppler。
