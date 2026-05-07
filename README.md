# Academic Agent

本项目已重构为本地对话式学术助手。默认界面是 React + FastAPI：用户在聊天框中输入需求或上传 PDF，Agent 负责筛选、解读、记忆和建议。

自动下载 PDF 不再是默认主流程。出版商网页、SPIS、文献求助等旧链路仅作为 legacy/experimental 代码保留，默认 Agent 不会自动下载 PDF，也不会绕过人机验证、机构认证或付费墙。

## 当前能力

- React 聊天式主界面，底部输入框支持文本和 PDF 附件。
- FastAPI 后端封装 Agent、配置、上传、后台任务和 SSE 日志流。
- 左侧配置区支持邮箱、授权码、LLM API、模型、研究主题和 WoS 参数。
- 配置可保存到本地 `.env`；真实 `.env` 已被 Git 忽略。
- WoS 筛选默认尝试“邮箱 + WoS 完整结果页”，输出 DOI、摘要、作者、期刊、链接和手动下载建议。
- 记忆层包含 `paper_corpus` 与 `interest_memory`，优先使用 Chroma，缺失时降级到 JSON。

## 安装

```bash
pip install -r requirements.txt
pip install -e .
```

前端依赖：

```bash
cd frontend
npm install
```

## 启动

### 一键启动

Windows 下推荐直接双击根目录的：

```text
start_academic_agent.bat
```

它会自动：

- 启动 FastAPI 后端
- 启动 React 前端
- 打开浏览器到 `http://127.0.0.1:5173`

如需停止当前项目相关的前后端进程，可双击：

```text
stop_academic_agent.bat
```

### 手动启动

后端：

```bash
D:\software\anaconda\envs\paper-ai\python.exe -m paper_analyzer.server
```

前端：

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

打开：

```text
http://127.0.0.1:5173
```

## Legacy / Debug

Streamlit 入口仍保留用于调试：

```bash
python -m streamlit run app.py
```

旧 CLI 仍可用于底层能力验证：

```bash
python main.py build-profile --input data/profile_pdfs
python main.py analyze --pdf path/to/paper.pdf --skip-llm
python main.py fetch-papers --no-web --max 50
python main.py analyze --source fetch --skip-llm
```

带 `--download-full-text` 的旧命令不再推荐作为默认流程。合法获取的 PDF 请直接上传给 Agent 深读。

## 数据目录

- `data/library/`：用户上传或允许保存的论文资料。
- `data/memory/chroma/`：Chroma 本地向量库。
- `data/conversations/`：Agent 工具调用日志和会话产物。
- `data/outputs/`：报告和分析结果。
