# Worklog

> 记录规则：按时间倒序追加。每条记录包含「做了什么 / 为什么 / 影响文件 / 验证结果 / 下一步」。

---

## 2026-04-28

### 补充：准备 GitHub 首次上传

### 做了什么
- 根据用户要求初始化本地 Git 仓库并准备上传 GitHub。
- 更新 `.gitignore`，排除真实 `.env`、`.eml`、调试邮件、PDF、processed/output 运行产物、缓存和本地 AI 设置。
- 新增 `README.md`，说明项目功能、安装方式、常用命令和默认输出路径。
- 将联网协作规则更新为：用户明确要求或批准时，Agent 可以执行联网操作；真实 API/邮箱/付费调用仍需保持可控。

### 为什么
- GitHub 仓库应只包含源码、测试、配置模板和必要项目文档，不能上传密钥、个人邮件内容、论文 PDF 或运行结果。

### 影响文件
- .gitignore
- README.md
- AGENTS.md
- CLAUDE.md
- .claude/worklog.md

### 验证结果
- `git status --ignored` 已确认 `.env`、`.eml`、`data/debug_emails/`、PDF、processed/output 数据均被忽略。
- 本地仓库已初始化，待创建首个 commit 并推送远端。

### 下一步
- 创建本地首个 commit。
- 如本机存在 GitHub 凭据，创建/连接远端仓库并推送；若缺少凭据，需要用户提供授权方式或手动创建空仓库。

---

## 2026-04-28

### 补充：V2 抓取审计与网页补全失败回退

### 做了什么
- 为 `fetch-papers` 和 `run` 增加 `--audit-output` 参数，默认保存到 `data/processed/fetch_audit.json`。
- 新增 `FetchAudit` 数据结构，记录抓取时间、since/max/no-web 参数、读取邮件数、解析论文数、去重后论文数、重复数量和论文输出路径。
- 修复网页补全异常会中断整批抓取的问题；现在 `enrich_from_web()` 失败时记录 warning，并保留邮件解析出的论文内容继续处理。
- 更新 V2 spec/todo，并补充单元测试。

### 为什么
- 真实 QQ 邮箱联调时需要快速判断“邮件读到了多少、解析到了多少、去重丢了多少”，否则排查 WoS 邮件格式变化成本高。
- spec 已要求网页抓取失败不应中断整体流程，原实现未满足。

### 影响文件
- .claude/spec.md
- .claude/todo.md
- .claude/worklog.md
- main.py
- pipeline/fetch_papers.py
- paper_analyzer/data/schema.py
- tests/test_fetch_papers.py

### 验证结果
- 本地单元测试：`39 passed`。
- CLI help 检查：`main.py fetch-papers --help` 和 `main.py run --help` 均已包含 `--audit-output`。
- 未执行真实邮箱、网页补全或 API 调用，符合当前联网操作协作规则。

### 下一步
- 由用户在本机真实环境执行：`D:\software\anaconda\envs\paper-ai\python.exe main.py fetch-papers --no-web --max 50`。
- 执行后检查 `data/processed/fetched_papers.json` 与 `data/processed/fetch_audit.json`，再决定是否增强 WoS 解析器或批量分析展示。

---

## 2026-04-27

### 补充：批量 LLM top-k 成本控制

### 做了什么
- 为 `analyze --source fetch` 和 `run` 增加 `--top-k N` 参数。
- 批量分析先计算所有论文相似度，再只允许相似度最高的前 N 篇触发 LLM。
- `--skip-llm` 语义优先于 `--top-k`：只算相似度时不会被 top-k 改写跳过原因。
- 补充 top-k 和 skip-llm 组合单测。

### 为什么
- 真实抓取结果中默认阈值 0.5 以上有 31 篇论文，直接批量 LLM 成本偏高。
- `--top-k` 能保留全量相似度报告，同时把 LLM 调用限制在最相关的少量论文上。

### 影响文件
- .claude/spec.md
- .claude/todo.md
- pipeline/analyze_papers.py
- main.py
- tests/test_analyze_fetched_papers.py
- .claude/worklog.md

### 验证结果
- 本地单元测试：`37 passed`。
- 无联网 CLI 验证：`main.py analyze --source fetch --skip-llm --top-k 5 --output-root data/outputs/fetch_topk_verify`。
- 输出：`data/outputs/fetch_topk_verify/20260427_195335`。
- 统计：总数 103，低于阈值 72，达到阈值且 skip-LLM 31。

### 下一步
- 如需真实 LLM 批量验证，由用户执行：`D:\software\anaconda\envs\paper-ai\python.exe main.py analyze --source fetch --top-k 5 --output-root data/outputs/fetch_llm_top5`。

---

### 补充：联网操作协作规则

### 做了什么
- 将“所有需要联网的操作由用户手动执行并反馈结果”写入长期协作规则。
- 明确联网操作范围：API 调用、真实邮箱抓取、pip 安装、模型下载、网页请求。

### 为什么
- 用户当前网络环境不稳定。
- 为避免 Agent 在不可靠网络下误判结果或产生不必要 API 成本，后续 Agent 只负责本地开发、无网络测试、命令准备和结果解读。

### 影响文件
- AGENTS.md
- CLAUDE.md
- .claude/handoff.md
- .claude/worklog.md

### 验证结果
- 文档更新完成，无业务代码变更。

### 下一步
- 继续做本地功能开发和测试；涉及联网验证时给出命令，由用户执行后反馈。

---

### 补充：后续版本需求记录

### 做了什么
- 将“历史抓取管理 / 重扫能力 / 跨运行周期去重 / 抓取审计”记录为后续版本需求。

### 为什么
- 当前 V2 使用 `seen_emails.json` 避免重复处理邮件，`fetched_papers.json` 保存本次抓取结果。
- 用户确认历史库与重扫能力有价值，但不在当前版本实现。

### 影响文件
- .claude/spec.md
- .claude/todo.md
- .claude/worklog.md

### 验证结果
- 文档更新完成，无业务代码变更。

### 下一步
- 当前版本继续优先做 top-k/limit 控制 LLM 批量分析成本，历史抓取管理留到后续版本。

---

### 补充：LLM API 验证

### 做了什么
- 使用 `.env` 中的 DeepSeek 配置执行真实 LLM 分析。
- 发现非流式 OpenAI SDK 调用会在 DeepSeek 返回 `200 OK` 后出现 `incomplete chunked read` / `Connection error`。
- 将 `OpenAICompatibleClient.complete()` 改为流式读取响应内容。
- 新增 `tests/test_llm_client.py` 覆盖流式读取行为。

### 为什么
- 用户已配置 API key，需要验证真实 LLM 链路。
- DeepSeek 当前响应在本地环境下流式模式稳定，非流式读取不稳定。

### 影响文件
- paper_analyzer/llm/client.py
- tests/test_llm_client.py
- .claude/worklog.md

### 验证结果
- 短文本流式调用返回 `{"ok": true}`。
- 真实 PDF 分析成功，输出 `data/outputs/codex_verify_llm/20260427_191746`，报告包含完整结构化字段，`skipped_reason` 为 null。
- 单元测试：`35 passed`。

### 下一步
- 用真实邮箱运行 `fetch-papers --no-web` 后，再对邮件抓取论文执行一次真实 LLM 或 `--skip-llm` 批量验证。

---

### 做了什么
- 补齐 V2 最小 CLI 闭环：新增 `pipeline/fetch_papers.py`，`main.py` 支持 `fetch-papers`、`analyze --source fetch`、`run`。
- `pipeline/analyze_papers.py` 新增邮件论文批量分析，保留原有单篇 PDF 分析。
- 补充 V2 依赖 `beautifulsoup4`、`requests`，并将 `requirements.txt` 按当前 Conda 环境锁定版本。
- 修复 `email_reader.py` 对 `email.message.Message` 类型注解的导入问题。
- 新增 fetch、email_reader、邮件论文批量分析相关单测。

### 为什么
- 当前长期目标是推进 V2 邮件抓取与批量分析，同时保持 V1/V1.1 可用。
- `CLAUDE.md` 已声明 V2 命令，但 `main.py` 尚未提供对应入口。

### 影响文件
- .claude/spec.md
- .claude/todo.md
- main.py
- pipeline/analyze_papers.py
- pipeline/fetch_papers.py
- paper_analyzer/ingestion/email_reader.py
- tests/test_analyze_fetched_papers.py
- tests/test_email_reader.py
- tests/test_fetch_papers.py
- pyproject.toml
- requirements.txt

### 验证结果
- 单元测试：`D:\software\anaconda\envs\paper-ai\python.exe -m pytest -q tests -p no:cacheprovider`，结果 `34 passed`。
- V1 CLI：`main.py analyze --pdf ... --skip-llm` 通过，输出 `data/outputs/codex_verify/20260427_190724`。
- V2 分析 CLI：`main.py analyze --source fetch --fetched data/outputs/test_tmp/fetched_papers/fetched.json --skip-llm` 通过，输出 `data/outputs/codex_verify/20260427_190631`。
- 最小 profile 构建验证通过，输出 `data/processed/profile_codex_verify.npy`。

### 下一步
- 使用真实 QQ 邮箱授权码运行 `main.py fetch-papers --no-web`，确认 WoS 邮件解析数量与内容质量。
- 清理或规范旧 smoke test 输出目录。

---

## 2026-04-26

### 做了什么
- 建立 Agent 接力机制文档：新增 `.claude/handoff.md`、`.claude/worklog.md`。
- 将“切换 Agent 前更新 handoff/worklog”同步进协作规则与规范文档。

### 为什么
- 项目曾被多个 Agent 分段开发，交接信息不连续导致重复理解成本高。
- 通过固定交接模板降低上下文丢失，缩短新 Agent 冷启动时间。

### 影响文件
- AGENTS.md
- .claude/spec.md
- CLAUDE.md
- .claude/handoff.md（新增）
- .claude/worklog.md（新增）

### 验证结果
- 文档创建与规则同步完成。
- 当前工作区无 git 仓库，暂无法提供变更 diff 追踪。

### 下一步
- 执行一次 `build-profile` + `analyze` 最小链路验证，并把实际结果追加到本日志。

---

## 2026-04-26（补充）

### 做了什么
- 在 `.claude/todo.md` 顶部新增「Agent 切换检查清单（切换前勾选）」。

### 为什么
- 将交接动作改为可勾选清单，减少切换时漏项。

### 影响文件
- .claude/todo.md

### 验证结果
- 清单已置顶，可直接用于切换前执行。

### 下一步
- 后续每次切换前按清单逐项勾选，并在 `.claude/worklog.md` 留痕。
