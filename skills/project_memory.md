# 项目记忆

## 已确认决策

- 项目名：Academic Paper AI Analyzer。
- V1 先做 CLI，跑通后再做 Streamlit 前端。
- `skills/` 是给 AI 看的说明书目录，不放业务代码。
- 业务代码包名：`paper_analyzer`。
- 依赖管理先用 `requirements.txt`。
- 新论文 CLI 阶段一次只分析一个 PDF。
- LLM 输出使用结构化 JSON，再由程序生成 Markdown。
- 默认 LLM provider 是 `deepseek`。
- API key 通过 `.env` 配置，仓库只提供 `.env.example`。
- `.env.example` 只放模板，不放真实 API key。
- 输出使用时间戳目录，避免覆盖历史结果。
- PDF 标题优先 metadata title，失败时用文件名。
- 测试只做轻量单元测试，不做复杂 OCR/LLM 集成测试。

## 默认参数

- Abstract 提取失败时取前 4000 字符。
- similarity threshold 默认 0.5。
- LLM temperature 默认 0.2。
- 推荐 Conda 环境名：`paper-ai`。
- 用户 Anaconda 路径：`D:\software\anaconda`。

## 固定流程

每次需求变化：

1. 先更新 `.claude/spec.md`。
2. 必要时更新 `AGENTS.md` 和本文件。
3. 再实现代码。
4. 做必要轻量验证。
