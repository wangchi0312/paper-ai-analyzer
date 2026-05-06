# CLAUDE.md — 项目上下文（每次启动自动加载）

## 项目概述

本地运行的论文分析助手，基于用户研究兴趣向量对新论文做相关性评分和结构化分析。

- V1（已实现）：本地 PDF → 兴趣向量 + 单篇分析 + Streamlit
- V2（开发中）：QQ 邮箱 WoS Citation Alert → 自动获取论文 → 批量筛选分析

## 开发环境

- Python 3.11，Conda 环境名：`paper-ai`
- Anaconda 路径：`D:\software\anaconda`
- 运行命令前缀：`D:/software/anaconda/envs/paper-ai/python.exe`
- 安装项目：`pip install -e .`

## 协作规则

- 所有回复使用中文。
- 遵循 KISS 原则，优先实现简单、可运行、可维护的方案。
- 每次需求变化时，先更新 `.claude/spec.md`，再实现代码。
- 每次切换 Agent 前，更新 `.claude/handoff.md` 与 `.claude/worklog.md`。
- 如果需求变化影响长期协作规则，同步更新 `AGENTS.md`。
- `skills/` 目录只放给 AI 查阅的说明书，不放业务代码。
- 不创建无必要文档；不提交真实 API key，不创建真实 `.env`。
- 用户明确要求或批准时，Agent 可以执行联网操作，包括 GitHub 推送、网页请求、真实邮箱抓取、API 调用、pip 安装、模型下载等；涉及真实 API/邮箱/付费调用时先说明风险并保持操作可控。

## 项目结构

```
paper_analyzer/       # 业务代码包
  embedding/          # embedder.py, similarity.py
  pdf/                # parser.py, ocr.py, text_selector.py
  llm/                # analyzer.py, client.py, prompt.py
  ingestion/          # [V2] email_reader.py, wos_parser.py, wos_browser.py, metadata_enricher.py
  data/               # schema.py (Paper, PaperAnalysis, FetchedPaper, FetchAudit)
  report/             # writer.py, weekly.py
  fulltext/           # [V2] resolver.py, downloader.py, source.py, manual.py
  notification/       # [V2] feishu.py
  utils/              # config.py, logger.py
pipeline/             # CLI 启动脚本（build_profile, fetch_papers, analyze_papers）
data/
  profile_pdfs/       # 构建兴趣向量的 PDF
  incoming_pdfs/      # 待分析 PDF
  processed/          # profile.npy, profile.json, seen_emails.json, fetched_papers.json, fetch_audit.json
  outputs/            # <timestamp>/results.json + report.md + weekly_report.md
  browser_profiles/   # [V2] Playwright 持久浏览器 profile（已 gitignore）
tests/
skills/               # 给 AI 查阅的说明书
main.py               # 统一 CLI 入口（build-profile / analyze / fetch-papers / run）
app.py                # Streamlit 前端
pyproject.toml
.env.example
```

## 核心流程

1. **构建兴趣向量**：`python main.py build-profile --input data/profile_pdfs`
2. **分析单篇 PDF**：`python main.py analyze --pdf path/to/paper.pdf`
3. **从邮件获取论文 [V2]**：`python main.py fetch-papers`
4. **批量分析邮件论文 [V2]**：`python main.py analyze --source fetch`
5. **全流程串联 [V2]**：`python main.py run`

## 默认参数

| 参数 | 默认值 |
|---|---|
| 文本选择长度 | 4000 字符 |
| LLM 分析文本长度 | 12000 字符 |
| 相似度阈值 | 0.5 |
| LLM provider | deepseek |
| LLM temperature | 0.2 |
| OCR 语言 | chi_sim+eng |
| 动态研究主题 | .env 的 RESEARCH_TOPIC，未配置时使用内置默认值 |

## 关键数据结构

`Paper`: title, source_path(Optional), link(Optional)[V2], abstract, selected_text, full_text, embedding, score, analysis(PaperAnalysis|None), skipped_reason, source_email_id(Optional)[V2], full_text_path(Optional)[V2], full_text_source(Optional)[V2], full_text_status(Optional)[V2], stage_status[V2]

`FetchedPaper`[V2]: title, abstract, doi(Optional), link(Optional), authors(Optional), venue(Optional), source_email_id(Optional), fetch_method("email"/"web"/组合)

`FetchAudit`[V2]: fetched_at, since_date, max_emails, no_web, email_count, parsed_paper_count, unique_paper_count, duplicate_paper_count, output_path, 以及 WoS 扩展、浏览器模式、元数据补全等审计字段

`PaperAnalysis`: first_author/affiliation, second_author/affiliation, corresponding_author/affiliation, publication_year, paper_title, venue, doi, core_problem, core_hypotheses(list), research_approach, key_methods, data_source_and_scale, core_findings, main_conclusions, field_contribution, relevance_to_my_research, highlights, limitations

## 技术选型

sentence-transformers, PyMuPDF, pytesseract, pdf2image, numpy, openai 兼容 API 客户端, python-dotenv, streamlit
# 2026-05-06 当前方向：对话式学术 Agent

项目定位已从“文献追踪/自动下载助手”调整为“本地对话式学术助手”。默认入口是 Streamlit 聊天界面，Agent 先理解用户意图并提出待确认动作，再调用工具执行。自动出版商下载、SPIS 下载和文献求助不再属于默认主流程；旧代码仅作为 legacy/experimental 能力保留。

新核心模块：
- `paper_analyzer/agent/`：AcademicAgent runtime、PendingAction、ToolRegistry、AcademicMemory。
- 默认工具：PDF 解读、WoS Alert 候选筛选、记忆检索、兴趣记忆更新、报告生成。
- 长期记忆：`paper_corpus` 与 `interest_memory` 两层，目标使用 Chroma；未安装时降级到 JSON fallback。
- WoS 工具只做候选提取和兴趣推荐，不下载 PDF。
