# Academic Agent

本项目正在从“文献追踪与自动下载工具”重构为“本地对话式学术助手”。用户通过聊天框与 Agent 协作：上传论文 PDF、请求解读、筛选 WoS Alert 候选、检索历史论文与研究兴趣、生成报告。

自动下载 PDF 不再是默认主流程。出版商网页、SPIS、文献求助等旧链路仅作为 legacy/experimental 代码保留，默认 UI 和 Agent 工具不会自动触发下载，也不会绕过人机验证、机构认证或付费墙。

## 当前能力

- 聊天式 Streamlit 本地界面。
- 上传 PDF 后，由 Agent 先提出解读计划，用户确认后再执行。
- WoS Alert 筛选作为 Agent 工具：只读取候选论文、摘要和元数据，输出推荐理由与“建议手动下载 PDF 后上传深读”。
- 两层长期记忆：
  - `paper_corpus`：上传/解读/筛选过的论文知识。
  - `interest_memory`：研究方向、方法偏好、排除方向和用户反馈。
- 记忆层优先使用 Chroma；本地未安装时会降级到 JSON 存储，保证应用可打开。

## 安装

```bash
pip install -r requirements.txt
pip install -e .
```

复制 `.env.example` 为本地 `.env`，填写自己的 LLM 和邮箱配置。不要提交真实 `.env`。

## 启动

```bash
python -m streamlit run app.py
```

推荐在本项目约定的 Conda 环境中运行：

```bash
D:\software\anaconda\envs\paper-ai\python.exe -m streamlit run app.py
```

## 旧 CLI

旧 CLI 仍保留，作为底层工具和回归测试入口：

```bash
python main.py build-profile --input data/profile_pdfs
python main.py analyze --pdf path/to/paper.pdf --skip-llm
python main.py fetch-papers --no-web --max 50
python main.py analyze --source fetch --skip-llm
```

带 `--download-full-text` 的旧命令不再推荐作为默认流程。合法获取的 PDF 请直接上传给 Agent 进行深读。

## 数据目录

- `data/library/`：用户上传或允许保存的论文资料。
- `data/memory/chroma/`：Chroma 本地向量库。
- `data/conversations/`：Agent 工具调用日志和会话产物。
- `data/outputs/`：报告和分析结果。
