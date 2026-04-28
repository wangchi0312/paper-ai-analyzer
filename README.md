# Academic Paper AI Analyzer

本地运行的文献追踪与论文分析助手。项目通过用户已有论文构建研究兴趣向量，再对新论文或 Web of Science Citation Alert 邮件中的论文做相关性评分和结构化分析。

## 功能

- 从本地 PDF 构建研究兴趣向量。
- 分析单篇 PDF，输出相关性分数、JSON 和 Markdown 报告。
- 从 QQ 邮箱读取 WoS Citation Alert 邮件，解析论文标题、摘要、DOI 和链接。
- 对邮件论文批量计算相似度，并支持 `--top-k` 控制 LLM 调用数量。
- 提供基础 Streamlit 前端用于单篇 PDF 分析。

## 环境

推荐 Python 3.11。

```bash
pip install -r requirements.txt
pip install -e .
```

复制 `.env.example` 为本地 `.env`，再填写自己的 API key 和邮箱授权码。不要提交真实 `.env`。

## 常用命令

构建兴趣向量：

```bash
python main.py build-profile --input data/profile_pdfs
```

分析单篇 PDF：

```bash
python main.py analyze --pdf path/to/paper.pdf --skip-llm
```

从邮件抓取论文：

```bash
python main.py fetch-papers --no-web --max 50
```

批量分析邮件论文：

```bash
python main.py analyze --source fetch --skip-llm
python main.py analyze --source fetch --top-k 5
```

启动 Streamlit：

```bash
python -m streamlit run app.py
```

## 输出

- 兴趣向量：`data/processed/profile.npy`
- 邮件抓取结果：`data/processed/fetched_papers.json`
- 抓取审计：`data/processed/fetch_audit.json`
- 分析报告：`data/outputs/<timestamp>/results.json` 和 `report.md`

这些运行产物默认不提交到 Git。
