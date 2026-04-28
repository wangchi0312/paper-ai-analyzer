# Agent Handoff

更新时间：2026-04-28

## 1) 当前目标
稳定推进 V2（邮件抓取与批量分析）同时保持 V1/V1.1 可用。当前已完成 V2 最小 CLI 闭环、top-k 成本控制、抓取审计、网页补全失败回退、Streamlit 邮件批量分析入口、文献周报输出、飞书 webhook 推送基础能力和 Streamlit 一键周报入口。下一步应做真实端到端联调。

## 2) 已完成（可验证）
- V1 CLI 主流程已实现：构建兴趣向量、单篇分析、JSON/Markdown 输出。
- V1.1 Streamlit 前端已接入基础单篇分析流程。
- V2 基础骨架已落地：邮件读取与 WoS 解析模块存在（`paper_analyzer/ingestion/`）。
- V2 最小 CLI 闭环已落地：`fetch-papers`、`analyze --source fetch`、`run` 命令入口存在。
- 批量分析已支持 `--top-k N`，可限制只有相似度最高的前 N 篇触发 LLM。
- DeepSeek API 已通过真实单篇 PDF 分析验证；client 已改为流式读取以规避非流式 `incomplete chunked read`。
- 邮件抓取结果保存到 `data/processed/fetched_papers.json`，批量分析可从该文件读取。
- 邮件抓取审计保存到 `data/processed/fetch_audit.json`，记录邮件数、解析论文数、去重数等统计。
- 网页补全失败时会保留邮件解析内容，不中断整批抓取。
- Streamlit 前端已新增“邮件批量”tab，可读取 `fetched_papers.json` 并复用 `analyze_papers()` 批量输出报告。
- 统一输出层已新增 `weekly_report.md`，Streamlit 优先展示周报。
- 飞书自定义机器人 webhook 推送已实现基础文本推送，支持可选签名密钥。
- Streamlit “一键周报”tab 可在前端填写 LLM/邮箱/飞书配置，并串联抓取、分析、生成周报和可选飞书推送；敏感配置仅在当前进程临时使用，不写入文件。
- 邮件批量深度解读现在会把标题、作者、期刊/会议、DOI、链接和摘要一起给 LLM，并用邮件元数据回填基础字段，减少周报中的“未识别”。
- `requirements.txt` 已按当前 Conda 环境锁定版本。
- 单元测试已覆盖 fetch 结果读写/去重/审计/网页补全回退、邮件 HTML 正文提取、邮件论文批量分析无 LLM 路径。
- 协作规则已统一：需求变化先更新 spec；切换 Agent 前更新 handoff/worklog。

## 3) 未完成（按优先级）
P0：真实邮箱联调
- 使用真实 QQ 邮箱授权码运行 `fetch-papers --no-web`，确认 WoS Citation Alert 解析结果。
- 再运行 `analyze --source fetch --skip-llm` 检查批量报告内容。

P1：工程质量收口
- `data/outputs/smoke/` 当前未发现对应目录，无需清理
- 重新真实生成一篇周报，检查“逐篇深度解读”是否仍有过多“未识别”

P2：V2 连通性增强
- 真实网络下检查 `enrich_from_web()` 对 WoS 页面补全摘要的稳定性。
- 根据 demo 反馈决定是否继续把 `fetch-papers` 接入 Streamlit。

## 4) 当前阻塞
- 无代码硬阻塞。
- GitHub 初次上传已由用户在 PowerShell 成功完成；当前 Codex 非交互环境仍不能直接 `git push`，需要用户本地终端推送或另行配置凭据。
- 真实邮箱联调需要 `.env` 中配置 `QQ_EMAIL` 和 `QQ_EMAIL_AUTH_CODE`。
- 协作约束：用户明确要求或批准时，Agent 可以执行联网操作；真实 API/邮箱/付费调用仍需先说明风险并保持可控。
- 风险项：OCR 依赖（Tesseract/Poppler）在不同机器上可能缺失，需维持清晰报错提示。

## 5) 最近改动文件
- .claude/spec.md（补充 V2 最小闭环范围）
- .claude/todo.md（更新已完成项）
- .claude/worklog.md（追加 2026-04-27 开发记录）
- .claude/worklog.md（追加 2026-04-28 抓取审计与网页补全回退记录）
- .gitignore、README.md、AGENTS.md、CLAUDE.md（准备 GitHub 首次上传）
- app.py（新增 Streamlit “邮件批量”tab，支持 `top-k`）
- app.py（优先展示 `weekly_report.md`，邮件批量分析后可推送飞书）
- app.py（新增 Streamlit “一键周报”tab）
- .env.example（新增飞书 webhook 占位）
- pipeline/analyze_papers.py（邮件论文 LLM 输入加入元数据，并回填基础字段）
- paper_analyzer/report/weekly.py（缺失字段展示为“需打开原文确认”）
- main.py（新增 V2 命令入口）
- main.py（`fetch-papers` / `run` 新增 `--audit-output`）
- pipeline/analyze_papers.py（新增 FetchedPaper 批量分析）
- pipeline/analyze_papers.py（新增 top-k LLM 成本控制）
- pipeline/fetch_papers.py（新增）
- pipeline/fetch_papers.py（新增抓取审计保存；网页补全失败时保留邮件内容）
- paper_analyzer/data/schema.py（新增 `FetchAudit`）
- paper_analyzer/report/weekly.py（新增周报生成器）
- paper_analyzer/notification/feishu.py（新增飞书 webhook 推送）
- paper_analyzer/ingestion/email_reader.py（修复 email.message 导入）
- tests/test_analyze_fetched_papers.py、tests/test_email_reader.py、tests/test_fetch_papers.py（新增）
- tests/test_fetch_papers.py（补充抓取审计与网页补全回退测试）
- paper_analyzer/llm/client.py（改为流式读取）
- tests/test_llm_client.py（新增）
- pyproject.toml、requirements.txt（新增 V2 依赖，requirements 锁定）

## 6) 运行/测试命令与预期
- 构建兴趣向量：`python main.py build-profile --input data/profile_pdfs`
  - 预期：生成 `data/processed/profile.npy`
- 单篇分析：`python main.py analyze --pdf <path-to-pdf>`
  - 预期：生成 `data/outputs/<timestamp>/results.json` 与 `report.md`
- 邮件抓取：`python main.py fetch-papers --no-web`
  - 预期：生成 `data/processed/fetched_papers.json` 与 `data/processed/fetch_audit.json`
- 邮件批量分析：`python main.py analyze --source fetch --skip-llm`
  - 预期：生成批量 `results.json` 与 `report.md`
- 成本受控批量 LLM：`python main.py analyze --source fetch --top-k 5`
  - 预期：只对相似度最高的 5 篇触发 LLM，其余论文仍输出分数和跳过原因
- 测试：`pytest -q`
  - 预期：当前为 `43 passed`
- 真实 LLM 单篇分析：`python main.py analyze --pdf data/profile_pdfs/AdaptiveAF_Paper.pdf --profile data/processed/profile_codex_verify.npy --output-root data/outputs/codex_verify_llm --llm-max-chars 4000`
  - 已验证输出：`data/outputs/codex_verify_llm/20260427_191746`

## 7) 下一 Agent 第一动作（必须）
1. 先读：`CLAUDE.md`、`.claude/spec.md`、`.claude/todo.md`、`AGENTS.md`、`skills/project_memory.md`。
2. 用户明确要求或批准时可以执行联网命令；真实邮箱/API/付费调用前先说明风险。
3. 根据用户反馈将验证结果写入 `.claude/worklog.md`，再决定是否增强网页补全或 Streamlit 批量入口。
4. 若需要同步 GitHub，而当前 Codex 环境仍无法认证，则让用户在 PowerShell 执行 `git push`。
