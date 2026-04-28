# Academic Paper AI Analyzer V1/V2 Spec

## 项目目标

实现一个本地运行的论文分析助手。V1 先完成 CLI 核心流程，确认效果后再实现 Streamlit 前端。

产品最终形态调整为“一键生成文献周报”：

1. 用户下载项目后启动本地前端。
2. 前端引导用户填写运行配置：LLM provider、模型名、API key；邮箱运营商、邮箱地址、邮箱授权码；研究主题和筛选参数。
3. 点击运行后，后台自动完成邮箱抓取、论文解析、相关性筛选、top-k 控制和 LLM 深度解读。
4. 邮件/WoS 信息只用于候选筛选；进入 top-k 的候选论文必须优先尝试获取全文，再基于全文做 LLM 深度解读。
5. 最终输出一篇面向用户阅读的文献周报，而不是仅展示中间论文列表。
6. 周报可在前端展示，并可选择推送到飞书自定义机器人 webhook。企业微信和个人微信暂不作为当前版本目标。

V1 支持：

1. 使用一组本地 PDF 构建用户研究兴趣向量。
2. 通过命令行传入一个新 PDF 进行分析。
3. 自动提取 PDF 文本，优先使用 PyMuPDF。
4. 文本过短时尝试 OCR fallback；如果本机缺少 Tesseract 或 Poppler，给出清晰提示。
5. 使用 sentence-transformers 生成 embedding。
6. 使用 cosine similarity 计算新论文与兴趣向量的相关性。
7. 分数超过阈值时调用 LLM 进行结构化分析。
8. 输出 JSON 和 Markdown 报告，并保存到带时间戳的输出目录。

V1 暂不包含：

- 邮箱解析
- 自动下载论文
- Web 爬虫
- 复杂 OCR/LLM 集成测试

V1.1 实现 Streamlit 前端，支持拖拽/选择 PDF、供应商选择、参数配置和结果展示。

V1.2 Streamlit 前端补充邮件抓取结果批量分析入口：

1. 前端提供“单篇 PDF”和“邮件批量”两个入口。
2. “邮件批量”读取 `fetch-papers` 已保存的 `data/processed/fetched_papers.json`。
3. 支持配置 profile、阈值、provider、skip-LLM、LLM 文本长度、研究主题和 top-k。
4. 点击分析后调用现有 `analyze_papers()`，输出 JSON 与 Markdown 报告。
5. 前端暂不直接连接 QQ 邮箱抓取邮件；真实邮箱抓取仍先通过 CLI 完成。

V2.1 前端一键周报目标：

1. 前端提供配置表单：
   - LLM provider、模型名、API key、base URL（可选）
   - 邮箱运营商、邮箱地址、邮箱授权码
   - 抓取时间范围、最大邮件数、是否网页补全、相似度阈值、top-k
   - 周报推送渠道：不推送 / 飞书
2. 配置默认只保存在本地 `.env` 或 Streamlit session 中，不提交真实密钥。
3. 点击“生成周报”后串联 `fetch-papers -> candidate screening -> full-text resolver/downloader -> full-text analyzer -> weekly report writer -> notifier`。
4. 周报输出包括：
   - 本周抓取概览：邮件数、解析论文数、去重数、进入 LLM 深读数量
   - 高相关论文列表：标题、来源、相似度、链接
   - 每篇高相关论文的深度解读
   - 本周趋势/主题归纳
   - 对用户研究方向的启发与建议
5. 推送渠道只实现飞书自定义机器人 webhook。个人微信/微信公众号直推暂缓，原因是授权、审核、消息触达规则和非官方方案稳定性风险较高。

V2.1 暂不包含：

- 云端部署和多人账号系统
- 数据库账号管理
- 非官方个人微信自动化
- 长期保存用户 API key 到远端

V2.2 全文获取与深度解读目标：

1. 邮件/WoS 阶段只做候选筛选，不作为最终深度解读依据。
2. 对 top-k 候选论文按 DOI、标题和链接尝试获取全文。
3. 全文获取优先级：
   - 开放获取接口：Unpaywall / Crossref TDM links / Semantic Scholar openAccessPdf 等。
   - 论文仓库或预印本：arXiv 等公开来源。
   - 出版商页面中明确可访问的 PDF/HTML。
   - 用户手动上传 PDF 或从 Zotero/本地文献库匹配。
4. 不默认使用非官方或版权风险较高的镜像下载；如用户提供镜像，只作为可配置 resolver，并需要明确风险提示。
5. 只有成功获取全文的论文进入深度解读；未获取全文的论文进入“候选但未深读”列表，并给出获取失败原因。
6. 周报中的“深度解读”必须基于全文，邮件摘要仅可作为候选筛选和补充元数据。

当前已落地的周报能力：

1. 每次调用统一输出层时，除了 `results.json` 和 `report.md`，额外生成 `weekly_report.md`。
2. `weekly_report.md` 是面向用户阅读的最终文档，包含候选论文数量、深度解读数量、重点推荐、候选论文排序和逐篇深度解读。
3. Streamlit 前端优先展示 `weekly_report.md`。
4. 邮件批量分析完成后，可选择通过飞书自定义机器人 webhook 推送周报文本；支持飞书签名密钥。
5. Streamlit 已新增“一键周报”入口，支持在前端填写模型、邮箱和飞书配置后串联抓取、分析、生成周报和可选飞书推送。
6. 前端输入的 API key、邮箱授权码、飞书 webhook 只在当前运行进程中临时使用，不写入代码、`.env` 或提交历史。
7. 邮件批量深度解读会把标题、作者、期刊/会议、DOI、链接和摘要一起提供给 LLM，并在 LLM 返回“未识别”时用邮件元数据回填基础字段。
8. 周报展示会将仍无法确认的字段写为“邮件/摘要中未提供，需打开原文确认”，避免大段机械的“未识别”。

V2 最小闭环继续保持 KISS 原则，先实现可测试的 CLI 流程：

1. `fetch-papers` 从 QQ 邮箱读取 WoS Citation Alert 邮件，解析为 `FetchedPaper` 列表。
2. 支持将抓取结果保存到 `data/processed/fetched_papers.json`，供后续批量分析复用。
3. `analyze --source fetch` 读取 `fetched_papers.json`，对论文摘要批量计算 embedding 和相似度。
4. `run` 串联 `fetch-papers` 与批量分析。
5. 邮件模式不自动下载 PDF，只使用邮件/网页中的标题、摘要、链接、作者、期刊等信息。
6. 同一批次内按 DOI 或规范化标题去重。
7. 网络抓取失败时保留邮件内容，不中断整体流程。
8. 批量分析支持 `--top-k`，只对相似度最高的前 N 篇触发 LLM，用于控制成本；未进入 top-k 的论文仍输出分数并标记跳过原因。
9. `fetch-papers` 保存轻量抓取审计文件，记录本次抓取时间、读取邮件数、解析论文数、去重后论文数、去重数量和输出路径，便于真实邮箱联调排查。

后续版本暂缓需求：

1. 历史抓取管理：将每次 `fetch-papers` 的结果追加到长期论文库，而不是只覆盖 `fetched_papers.json`。
2. 重扫能力：增加 `--reset-seen` 或类似参数，允许用户清空/忽略 `seen_emails.json` 后重新扫描历史 WoS 邮件。
3. 历史去重：跨运行周期按 DOI 或规范化标题去重，避免长期论文库重复保存同一篇论文。

## 固定开发流程

每次需求发生变化时，先更新本文件，再实现代码。

执行顺序：

1. 调研当前 spec、代码和用户最新要求。
2. 发现需求变化时，先同步 `.claude/spec.md`。
3. 如变化会影响长期协作规则，同步更新 `AGENTS.md`。
4. 若准备切换 Agent，先更新 `.claude/handoff.md`（当前状态快照）与 `.claude/worklog.md`（追加变更记录）。
5. 再修改代码。
6. 做必要的轻量验证。

## 项目结构

```text
paper_analyzer/
  embedding/
    embedder.py
    similarity.py
  pdf/
    parser.py
    ocr.py
    text_selector.py
  llm/
    analyzer.py
    client.py
    prompt.py
  data/
    schema.py
  report/
    writer.py
  utils/
    config.py
    logger.py
pipeline/
  build_profile.py
  analyze_papers.py
  fetch_papers.py
data/
  profile_pdfs/
  incoming_pdfs/
  processed/
  outputs/
skills/
  project_memory.md
tests/
main.py
app.py
requirements.txt
.env.example
```

说明：

- `paper_analyzer/` 是业务代码包。
- `pipeline/` 放 CLI 启动脚本。
- `skills/` 只放给 AI 查阅的说明书，不放业务代码。
- `data/profile_pdfs/` 放用于构建兴趣向量的论文。
- `data/incoming_pdfs/` 可放待分析论文，但 CLI V1 通过参数传入单个 PDF。
- `data/processed/profile.npy` 保存兴趣向量。
- `data/outputs/<timestamp>/` 保存每次分析结果。

## 技术选型

- Python 3.10+
- sentence-transformers
- PyMuPDF
- pytesseract
- pdf2image
- numpy
- openai 兼容 API 客户端
- python-dotenv

V1.1 前端计划使用 Streamlit。

## 配置

使用 `.env` 保存本地密钥，不提交真实 `.env`。

项目提供 `.env.example`，包含：

```env
LLM_PROVIDER=deepseek
LLM_TEMPERATURE=0.2

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=

SILICONFLOW_API_KEY=
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=

MODELSCOPE_API_KEY=
MODELSCOPE_BASE_URL=
MODELSCOPE_MODEL=
```

默认供应商为 `deepseek`。

本项目建议使用独立 Conda 环境运行：

```bash
conda create -n paper-ai python=3.11
conda activate paper-ai
pip install -r requirements.txt
```

用户本机 Anaconda 路径：`D:\software\anaconda`。

Windows 下已发现 Codex 内部调用 PowerShell 可能出现宿主异常。项目运行时默认不要依赖 PowerShell 包装命令，优先直接调用 Conda 环境中的 Python 可执行文件：

```bash
D:\software\anaconda\envs\paper-ai\python.exe -m pytest -q tests -p no:cacheprovider
D:\software\anaconda\envs\paper-ai\python.exe pipeline\build_profile.py --input data\profile_pdfs
D:\software\anaconda\envs\paper-ai\python.exe pipeline\analyze_papers.py --pdf data\incoming_pdfs\example.pdf --provider deepseek
D:\software\anaconda\envs\paper-ai\python.exe -m streamlit run app.py
```

## 核心流程

## V1.1 Streamlit 前端

启动命令：

```bash
D:\software\anaconda\envs\paper-ai\python.exe -m streamlit run app.py
```

第一版前端支持单篇 PDF 分析：

1. 上传或拖拽一个 PDF。
2. 保存到 `data/incoming_pdfs/`。
3. 选择 profile，默认 `data/processed/profile.npy`。
4. 设置相似度阈值，默认 `0.5`。
5. 选择 LLM provider，默认 `deepseek`。
6. 可选择跳过 LLM，只计算相似度。
7. 点击开始分析。
8. 页面展示相似度、LLM 状态、报告内容和输出目录。

邮件批量分析入口：

1. 读取 `data/processed/fetched_papers.json` 或用户指定路径。
2. 展示待分析论文数量。
3. 可选择只计算相似度。
4. 可设置 `top-k`，限制只有最相关的前 N 篇触发 LLM。
5. 页面展示批量报告内容和输出目录。

第一版前端暂不做：

- 批量上传
- 历史报告管理
- Zotero 文献浏览器
- API key 页面输入
- 前端内直接抓取真实邮箱

### 构建兴趣向量

命令：

```bash
D:\software\anaconda\envs\paper-ai\python.exe pipeline/build_profile.py --input data/profile_pdfs
```

如果输入来自 Zotero storage 这类多层目录，使用：

```bash
D:\software\anaconda\envs\paper-ai\python.exe pipeline/build_profile.py --input D:\software\zetero\storage --recursive --limit 10
```

流程：

1. 读取输入目录下的 PDF；默认只读取第一层，传入 `--recursive` 时递归读取子目录。
2. 逐个提取全文。单个 PDF 提取失败时跳过并打印提示，不中断整体流程。
3. 优先提取 Abstract；找不到则取前 4000 个字符。
4. 对每篇论文生成 embedding。
5. 对所有 embedding 求平均，得到 `interest_vector`。
6. 保存到 `data/processed/profile.npy`。
7. 所有 PDF 均提取失败时报错退出。

`--limit` 用于限制处理 PDF 数量，适合先对 Zotero 文献库做小规模试跑。

### 分析新论文

命令：

```bash
D:\software\anaconda\envs\paper-ai\python.exe pipeline/analyze_papers.py --pdf path/to/paper.pdf --provider deepseek --threshold 0.5
```

流程：

1. 加载 `data/processed/profile.npy`。
2. 提取新 PDF 全文。
3. 优先提取 Abstract；找不到则取前 4000 个字符。
4. 生成 embedding。
5. 计算与兴趣向量的 cosine similarity。
6. 如果分数大于等于阈值，调用 LLM 生成结构化分析。LLM 分析默认使用全文前 12000 字符，以提高作者、DOI、期刊等信息的识别概率。
7. 如果分数低于阈值，跳过 LLM，仅记录跳过原因。
8. 生成 JSON 和 Markdown 报告。

### 获取邮件论文 [V2]

命令：

```bash
D:\software\anaconda\envs\paper-ai\python.exe main.py fetch-papers --max 50
```

流程：

1. 从 `.env` 读取 `QQ_EMAIL` 和 `QQ_EMAIL_AUTH_CODE`。
2. 使用 IMAP 连接 QQ 邮箱，筛选 Web of Science / Clarivate 相关邮件。
3. 跳过 `data/processed/seen_emails.json` 中已处理的 Message-ID。
4. 提取 HTML 正文并调用 WoS 解析器得到 `FetchedPaper`。
5. 默认尝试网页补全摘要；传入 `--no-web` 时只使用邮件内容。
6. 按 DOI 或标题去重。
7. 保存到 `data/processed/fetched_papers.json`。
8. 保存轻量抓取审计到 `data/processed/fetch_audit.json`，用于检查邮件数、解析论文数和去重结果。

### 批量分析邮件论文 [V2]

命令：

```bash
D:\software\anaconda\envs\paper-ai\python.exe main.py analyze --source fetch --skip-llm
D:\software\anaconda\envs\paper-ai\python.exe main.py analyze --source fetch --top-k 5
```

流程：

1. 读取 `data/processed/fetched_papers.json`。
2. 加载 `data/processed/profile.npy`。
3. 对每篇论文优先使用 abstract；abstract 为空时使用标题。
4. 批量生成 embedding 并计算 cosine similarity。
5. 低于阈值的论文标记跳过原因。
6. 达到阈值且未指定 `--skip-llm` 时逐篇调用 LLM。
7. 如果传入 `--top-k`，只有相似度最高的前 N 篇允许触发 LLM；其他高于阈值但不在 top-k 的论文标记为“未进入 top-k”。
8. 调用统一 report writer 输出 JSON 与 Markdown。

### 全流程串联 [V2]

命令：

```bash
D:\software\anaconda\envs\paper-ai\python.exe main.py run --max 50 --skip-llm
```

流程等价于先 `fetch-papers`，再对本次抓取到的论文列表执行批量分析。

## 默认参数

- 文本选择默认长度：4000 字符
- LLM 分析文本默认长度：12000 字符
- 相似度阈值：0.5
- LLM provider：deepseek
- LLM temperature：0.2
- OCR 语言：chi_sim+eng（中英文）
- 研究主题：从 .env 的 `RESEARCH_TOPIC` 读取；未配置时使用内置默认值

## 数据结构

`Paper` 字段：

- `title: str`
- `source_path: str | None`
- `link: str | None`
- `abstract: str`
- `selected_text: str`
- `full_text: str`
- `embedding: list[float]`
- `score: float | None`
- `analysis: PaperAnalysis | None`
- `skipped_reason: str | None`
- `source_email_id: str | None`

`FetchedPaper` 字段：

- `title: str`
- `abstract: str`
- `doi: str | None`
- `link: str | None`
- `authors: str | None`
- `venue: str | None`
- `source_email_id: str | None`
- `fetch_method: str`

`FetchAudit` 字段：

- `fetched_at: str`
- `since_date: str | None`
- `max_emails: int`
- `no_web: bool`
- `email_count: int`
- `parsed_paper_count: int`
- `unique_paper_count: int`
- `duplicate_paper_count: int`
- `output_path: str`

`PaperAnalysis` 字段：

- `first_author: str`
- `first_author_affiliation: str`
- `second_author: str`
- `second_author_affiliation: str`
- `corresponding_author: str`
- `corresponding_author_affiliation: str`
- `publication_year: str`
- `paper_title: str`
- `venue: str`
- `doi: str`
- `core_problem: str`
- `core_hypotheses: list[str]`
- `research_approach: str`
- `key_methods: str`
- `data_source_and_scale: str`
- `core_findings: str`
- `main_conclusions: str`
- `field_contribution: str`
- `relevance_to_my_research: str`
- `highlights: str`
- `limitations: str`

标题提取策略：

1. 优先读取 PDF metadata title。
2. 如果 metadata title 明显是模板标题或工具标题，则认为不可信。
3. metadata 不可信时，从首页较大的文本行中提取论文标题。
4. 仍然失败时使用文件名。

## 输出

每次分析输出到：

```text
data/outputs/<timestamp>/results.json
data/outputs/<timestamp>/report.md
```

JSON 示例：

```json
[
  {
    "title": "example",
    "source_path": "path/to/paper.pdf",
    "score": 0.78,
    "analysis": {
      "core_idea": "...",
      "method": "...",
      "innovation": "...",
      "relevance_reason": "..."
    },
    "skipped_reason": null
  }
]
```

Markdown 示例：

```markdown
# 文献总结（精简版）

## 1. 基本信息

- **第一作者**：姓名 / 院校/研究所
- **第二作者**：姓名 / 院校/研究所
- **通讯作者**：姓名 / 院校/研究所
- **发表年份**：
- **论文标题**：
- **期刊/会议名称**：
- **DOI**：

## 2. 核心问题
本研究要解决的关键科学/技术问题：
>

## 3. 核心假设/理论
作者提出的核心研究假设或理论构想：
1.
2.

## 4. 研究思路
整体研究设计（理论/仿真/实验/案例等）：
>

## 5. 方法与数据
- 关键方法/模型：
- 数据来源与规模：

## 6. 核心发现
最重要、最创新的科学发现：
>

## 7. 主要结论
作者基于证据得出的最终结论：
>

## 8. 领域贡献
对本领域的理论/方法/应用贡献：
>

## 9. 与我的研究关联
和我的研究主题/综述方向的核心交集：
>

## 10. 启发与不足
- 亮点/启发：
- 局限/疑问：
```

## 模块职责

### embedding

- `Embedder.encode(texts)`：支持单条和批量文本，返回 numpy array。
- `Embedder` 优先从本地缓存加载模型；缓存不存在时再联网下载。
- `cosine_similarity(vec1, vec2)`：计算余弦相似度。

### pdf

- `extract_text(pdf_path, ocr_lang="chi_sim+eng")`：提取全文，必要时尝试 OCR。`ocr_lang` 传递给 Tesseract，默认中英文。
- `ocr_pdf(pdf_path, lang="chi_sim+eng")`：使用 pdf2image + pytesseract 识别扫描 PDF。`lang` 参数控制 OCR 语言。
- `select_representative_text(full_text, max_chars=4000)`：提取 Abstract 或前 N 字。

### llm

- `build_prompt(text, research_topic=None)`：构建要求 JSON 输出的分析 prompt。`research_topic` 为 None 时从 .env 读取 `RESEARCH_TOPIC`，仍未配置则使用内置默认值。
- `OpenAICompatibleClient`：统一兼容 DeepSeek、硅基流动、魔塔等 OpenAI 风格 API。
- `Analyzer.analyze(text, research_topic=None)`：返回 `PaperAnalysis`。`research_topic` 透传给 `build_prompt`。

### report

- `write_outputs(papers, output_root)`：生成时间戳目录、JSON 和 Markdown。

## 测试策略

V1 只做轻量测试：

- similarity
- text_selector
- prompt
- schema/report 基本序列化

暂不做需要真实外部服务的集成测试。

## 成功标准

V1 成功标准：

1. 用户把若干 PDF 放入 `data/profile_pdfs/` 后，可以构建 `profile.npy`。
2. 用户通过 CLI 传入一个新 PDF 后，可以得到相关性分数。
3. 如果配置了可用 LLM API key，相关论文可以得到结构化分析。
4. 如果未安装 OCR 依赖，文本型 PDF 仍可运行，扫描型 PDF 给出清晰提示。
5. 输出目录不会覆盖历史结果。
