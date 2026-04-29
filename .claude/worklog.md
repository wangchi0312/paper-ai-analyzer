# Worklog

> 记录规则：按时间倒序追加。每条记录包含「做了什么 / 为什么 / 影响文件 / 验证结果 / 下一步」。

---

## 2026-04-29

### 补充：前端进度日志与浏览器窗口复用

### 做了什么
- 前端一键周报运行时新增状态日志区，不再只显示一个无限转圈提示。
- 抓取流程新增 `progress_callback`，向前端回报邮箱扫描、逐封邮件解析、WoS 完整页扩展、浏览器扩展结果、抓取审计保存等阶段。
- 批量分析流程新增 `progress_callback`，向前端回报相似度计算、top-k 跳过、全文下载、跳过 LLM、输出目录等阶段。
- 浏览器模式改为同一次 `fetch_papers()` 内复用一个 `WosBrowserSession`，只有在 requests 无法扩展且确实需要浏览器时才启动 Chromium。
- 修复“每个 Alert 链接弹出一个浏览器、随后自动关闭”的体验问题。

### 为什么
- 用户反馈点击生成周报后只能看到“正在抓取邮件、分析论文并生成周报...”转圈，无法判断测试是否卡住或何时结束。
- 用户反馈浏览器不停弹出又自动关闭，根因是旧实现每处理一个 AlertSummary 链接就单独启动并关闭一次 Playwright Chromium。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- app.py
- pipeline/analyze_papers.py
- pipeline/fetch_papers.py
- paper_analyzer/ingestion/wos_browser.py
- tests/test_fetch_papers.py

### 验证结果
- 针对性测试：`30 passed`。
- 语法检查：`py_compile app.py main.py pipeline/fetch_papers.py pipeline/analyze_papers.py paper_analyzer/ingestion/wos_browser.py paper_analyzer/data/schema.py` 通过。

### 下一步
- 用户重新打开/刷新 Streamlit 前端后测试。
- 浏览器模式下若需要手动机构认证，应该只弹出一个 Playwright Chromium 窗口；前端日志会显示当前处于邮件扫描、WoS 扩展、全文下载还是写出结果阶段。

---

## 2026-04-28

### 补充：校园网测试反馈与浏览器登录等待

### 做了什么
- 读取用户校园网手动测试后的 `data/processed/fetch_audit.json` 和 `data/processed/fetched_papers.json`。
- 确认抓取已选中目标两封 WoS Citation Alert：
  - `Web of Science Alert - Jagtap, Ameya D. - 2 results`
  - `Web of Science Alert - Raissi, M. - 71 results`
- 确认当前只得到邮件正文里的 7 篇候选，WoS 完整 AlertSummary 扩展为 0。
- 新增浏览器模式“手动完成 WoS/机构登录等待秒数”配置：
  - 前端一键周报可设置等待秒数。
  - CLI `fetch-papers` / `run` 可传 `--browser-manual-login-wait-seconds`。
  - 抓取审计写入 `browser_manual_login_wait_seconds`。
- 浏览器打开 WoS gateway 链接时，如果遇到短暂 `net::ERR_ABORTED` 或 frame detached，不立即失败，继续等待当前页面并检查是否出现 WoS 记录或登录页。

### 为什么
- 用户测试结果显示问题已经不在“邮件选择”阶段，而在“Playwright 浏览器没有有效机构访问态/AlertSummary 跳转失败”阶段。
- 当前自动环境和项目浏览器 profile 没有陕西师范大学机构访问态；需要支持用户在弹出的 Playwright Chromium 中手动完成学校/机构认证。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- .claude/handoff.md
- app.py
- main.py
- pipeline/fetch_papers.py
- paper_analyzer/data/schema.py
- paper_analyzer/ingestion/wos_browser.py
- tests/test_fetch_papers.py
- tests/test_wos_browser.py

### 验证结果
- 针对性测试：`21 passed`。
- 语法检查：`py_compile app.py main.py pipeline/fetch_papers.py paper_analyzer/ingestion/wos_browser.py paper_analyzer/data/schema.py` 通过。

### 下一步
- 用户下一轮测试时，在前端启用“使用浏览器模式解析 WoS 完整页”，并把“手动完成 WoS/机构登录等待秒数”设置为 180-300 秒。
- 浏览器弹出后，若停在 Clarivate/学校认证/CARSI 页面，用户在该 Chromium 窗口完成机构登录；成功后 profile 会保存在 `data/browser_profiles/wos`，后续测试应复用访问态。
- 测试完成后继续查看 `browser_new_unique_paper_count` 是否接近 66（73 篇总量减去邮件正文 7 篇，扣除重复后可能略有差异）。

---

## 2026-04-28

### 补充：校园网手动测试协作方式

### 做了什么
- 明确 WoS 完整 AlertSummary 的真实验证改为由用户在校园网/学校 VPN 环境下手动运行。
- Agent 后续根据本地结果文件反馈，不再尝试在当前非校园网环境继续处理学校机构认证。
- 将测试反馈入口固定为 `data/processed/fetch_audit.json`、`data/processed/fetched_papers.json` 和最新 `data/outputs/<timestamp>/results.json` / `weekly_report.md`。

### 为什么
- 当前 Codex 浏览器环境通过个人 Clarivate 账号只能进入 Free Web of Science profile，继续自动化机构认证成本高且不稳定。
- 用户本机校园网/学校 VPN 环境更接近真实使用场景，能直接验证 WoS 73 篇候选扩展与全文下载链路。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- .claude/handoff.md

### 验证结果
- 仅更新协作记录，未改业务代码，未运行测试。

### 下一步
- 用户手动运行前端或 CLI，建议勾选“只验证抓取和全文下载，不调用 LLM”。
- 用户测试完成后告知 Agent，Agent 读取本地审计和输出文件，判断候选数量、WoS 浏览器扩展、全文下载命中率和失败原因。

---

## 2026-04-28

### 补充：真实 WoS 登录联调与 Citation Alert 邮件筛选

### 做了什么
- 浏览器模式支持通过进程环境变量 `CLARIVATE_EMAIL` / `CLARIVATE_PASSWORD` 在 Clarivate 登录页自动登录。
- 邮箱抓取阶段增加 Citation Alert 判定，跳过 `password reset`、`password changed`、welcome 等账户通知邮件，避免它们占用 `max_emails` 名额。
- 抓取审计新增 `skipped_non_alert_email_count`。
- 真实联调确认最近两封目标邮件为：
  - `Web of Science Alert - Jagtap, Ameya D. - 2 results`
  - `Web of Science Alert - Raissi, M. - 71 results`
- 真实联调确认 Clarivate 个人账号可登录，但当前环境进入的是 Free Web of Science profile，WoS 页面提示需要通过机构访问，AlertSummary 无法展开完整列表。
- 真实联调中生成的临时 HTML/截图/脚本已删除。

### 为什么
- 用户手动点击邮件可进入 WoS，但自动浏览器最初进入 Clarivate 登录页；需要区分个人账号登录、机构访问态和 Citation Alert 页面解析。
- 真实邮箱中新增的 Clarivate 账户通知邮件会干扰“最近 N 封 Alert”选择，导致 `max_emails=2` 选错邮件。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- paper_analyzer/data/schema.py
- paper_analyzer/ingestion/email_reader.py
- paper_analyzer/ingestion/wos_browser.py
- pipeline/fetch_papers.py
- tests/test_email_reader.py
- tests/test_fetch_papers.py
- tests/test_wos_browser.py

### 验证结果
- 抓取/浏览器针对性测试：`19 passed`。
- 语法检查：`py_compile paper_analyzer/ingestion/email_reader.py paper_analyzer/ingestion/wos_browser.py pipeline/fetch_papers.py paper_analyzer/data/schema.py` 通过。
- 真实抓取不调用 LLM：邮箱登录成功，跳过非 Citation Alert 邮件，选中目标 2 封 Alert；但因缺机构访问态，浏览器停在 Free Profile/机构访问提示，未取得 73 条完整候选。

### 下一步
- 需要用户提供学校/机构访问方式：机构名称、学校统一认证账号密码，或先连接学校 VPN/校园网。
- 如果用户日常浏览器已经具备机构访问态，可实现连接用户已打开 Chrome 调试端口，复用日常浏览器会话。

---

## 2026-04-28

### 补充：浏览器登录态持久化与审计脱敏

### 做了什么
- Playwright WoS 浏览器模式改为默认使用持久 profile：`data/browser_profiles/wos`。
- 将 `data/browser_profiles/*` 加入 `.gitignore`，避免提交 cookie、localStorage 或浏览器缓存。
- 浏览器无法解析 WoS 记录时，错误信息只记录页面标题和 URL 域名+路径，不保存 query 参数。
- `fetch_papers` 写入浏览器错误前会再次脱敏 URL，避免 loginId、sid、session 等参数落盘。
- 已清理当前 `data/processed/fetch_audit.json` 中的完整 Clarivate 登录 URL，仅保留域名+路径。

### 为什么
- 用户手动点击邮件中的 View citations 可以直接进入 WoS，但 Playwright 默认使用全新临时浏览器 profile，可能缺少用户浏览器里的 WoS/Clarivate/机构认证状态。
- 真实测试发现审计错误中包含 Clarivate 登录页完整 URL，其中带有邮箱和 session 查询参数，不应保存。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- .gitignore
- paper_analyzer/ingestion/wos_browser.py
- pipeline/fetch_papers.py
- tests/test_fetch_papers.py
- tests/test_wos_browser.py

### 验证结果
- 抓取/浏览器针对性测试：`13 passed`。
- 语法检查：`py_compile paper_analyzer/ingestion/wos_browser.py pipeline/fetch_papers.py` 通过。
- 当前本地审计文件已脱敏；数据文件未提交。

### 下一步
- 若 Playwright 仍进入 Clarivate 登录页，需要在弹出的 Playwright Chromium 中完成一次 WoS/机构认证，让 `data/browser_profiles/wos` 保存访问态。
- 如果用户希望直接复用日常 Chrome 登录态，需要单独设计“连接用户已打开 Chrome 调试端口”方案，不应直接读取默认 Chrome profile。

---

## 2026-04-28

### 补充：新增逐封邮件抓取审计

### 做了什么
- `fetch_audit.json` 新增 `email_details`。
- 每封邮件记录：message id、subject、邮件正文解析论文数、AlertSummary 链接数、requests 扩展数、浏览器扩展数、新增唯一数、重复数、错误数。
- 每个 Alert 链接记录：链接序号、URL 域名+路径摘要、requests 扩展数、浏览器扩展数、新增唯一数、重复数、错误。
- URL 审计只保存域名和路径，不保存 query/session 参数。

### 为什么
- 用户确认最近两封 WoS 邮件应合计 73 篇，但实际 `max_emails=2` 只得到 9 篇唯一候选。
- 总量审计无法判断是选错了两封邮件、邮件正文本身只包含少量论文，还是 WoS 完整页解析没有到达 50/23 的结果页。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- paper_analyzer/data/schema.py
- pipeline/fetch_papers.py
- tests/test_fetch_papers.py

### 验证结果
- 抓取相关针对性测试：`15 passed`。
- 语法检查：`py_compile pipeline/fetch_papers.py paper_analyzer/data/schema.py paper_analyzer/ingestion/wos_browser.py paper_analyzer/ingestion/wos_parser.py` 通过。
- 未运行全量测试；本次只改抓取审计路径。

### 下一步
- 用户重新运行抓取后，查看 `email_details` 中每封邮件的 subject 和每个 Alert 链接扩展数量。
- 若 subject 不是用户期望的两封 Alert，则需要增加按主题/关键词选择邮件的能力。
- 若 subject 正确但每个链接只扩展少量记录，则继续适配 WoS 50 条列表页的真实 DOM 或接口请求。

---

## 2026-04-28

### 补充：支持只验证抓取和全文下载

### 做了什么
- `analyze_papers(download_full_text=True, skip_llm=True)` 改为仍会下载并解析全文，但不会初始化 Analyzer 或调用 LLM。
- 下载验证模式下仍会尊重阈值和 top-k，只对允许深读的候选下载全文，避免批量下载过多 PDF。
- Streamlit 一键周报新增“只验证抓取和全文下载，不调用 LLM”开关。
- 前端开启该开关后不再强制要求填写 API Key。
- 新增测试确保下载验证模式不初始化 LLM，并且尊重 top-k。

### 为什么
- 用户明确指出当前阶段只需要验证 WoS 抓取和全文下载，不应每次调用 LLM，避免慢且浪费 token/API 额度。
- 原实现中 `--skip-llm` 会在全文下载前短路，无法满足“下载但不深读”的调试工作流。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- app.py
- pipeline/analyze_papers.py
- tests/test_analyze_fetched_papers.py

### 验证结果
- 针对性测试：`21 passed`。
- 语法检查：`py_compile app.py main.py pipeline/analyze_papers.py pipeline/fetch_papers.py paper_analyzer/fulltext/resolver.py` 通过。
- 未运行全量测试；本次改动只涉及抓取/全文下载/跳过 LLM 路径。

### 下一步
- 用户可在前端勾选“只验证抓取和全文下载，不调用 LLM”，先确认候选数量和 PDF 下载命中率。
- 候选抓取与全文下载稳定后，再关闭该开关进入 LLM 深度解读和周报生成。

---

## 2026-04-28

### 补充：浏览器最多翻页数可配置

### 做了什么
- Streamlit 一键周报新增“浏览器最多翻页数”，默认 20，只有启用浏览器模式时可编辑。
- `fetch-papers` 和 `run` 新增 `--browser-max-pages` 参数。
- `fetch_papers()` 新增 `browser_max_pages` 参数，并传给 Playwright WoS 抽取函数。
- 抓取审计新增 `browser_max_pages`，记录本次浏览器扩展配置。
- 测试覆盖 `browser_max_pages` 传递与审计写入。

### 为什么
- 用户真实审计显示浏览器扩展已成功带来新增唯一候选：`browser_new_unique_paper_count=14`。
- 但 WoS Alert 可能有几十到上百篇结果，固定最多 5 页不适合真实使用；需要让用户按邮件规模和耗时调整。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- app.py
- main.py
- pipeline/fetch_papers.py
- paper_analyzer/data/schema.py
- paper_analyzer/ingestion/wos_browser.py
- tests/test_fetch_papers.py

### 验证结果
- 局部测试：`12 passed`。
- 全量测试：`61 passed`。
- 语法检查：`py_compile app.py main.py pipeline/fetch_papers.py paper_analyzer/ingestion/wos_browser.py paper_analyzer/data/schema.py` 通过。

### 下一步
- 用户可将浏览器最多翻页数从 20 逐步提高到 30 或 50，观察 `browser_new_unique_paper_count` 是否继续增长。
- 若增长停滞但 WoS 页面显示仍有更多结果，再分析 WoS 的真实分页控件或接口请求。

---

## 2026-04-28

### 补充：浏览器模式支持滚动和翻页抽取

### 做了什么
- 浏览器模式打开 WoS 完整页后，先滚动页面等待前端懒加载记录，再尝试点击 Next/下一页控件继续抽取。
- 默认最多抽取 5 页，避免无限翻页。
- 抓取审计新增 `browser_new_unique_paper_count` 和 `browser_duplicate_paper_count`，区分浏览器扩展总数、新增唯一候选和重复候选。
- 新增测试覆盖浏览器扩展重复计数。

### 为什么
- 用户真实审计显示 `browser_expanded_paper_count=10`，但 `unique_paper_count` 仍为 21，说明浏览器扩展出的 10 篇都是邮件正文已有论文，没有带来新增候选。
- WoS 完整结果页可能只在首屏/第一页显示少量记录，需要滚动或翻页才能拿到完整候选列表。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- paper_analyzer/data/schema.py
- paper_analyzer/ingestion/wos_browser.py
- pipeline/fetch_papers.py
- tests/test_fetch_papers.py

### 验证结果
- 局部测试：`12 passed`。
- 全量测试：`61 passed`。
- 语法检查：`py_compile paper_analyzer/ingestion/wos_browser.py pipeline/fetch_papers.py paper_analyzer/data/schema.py` 通过。
- 本地 Playwright 翻页验证：从模拟 HTML 的第一页和 Next 后新增内容中成功解析 2 篇论文。

### 下一步
- 用户重新运行一键周报后，重点检查 `browser_new_unique_paper_count` 是否大于 0。
- 如果仍为 0，说明 WoS 页面当前只暴露邮件中已有记录，需要进一步处理 WoS 结果页的真实分页控件或接口数据。

---

## 2026-04-28

### 补充：修复 Clarivate 异常跳转链接导致周报失败

### 做了什么
- 增强 WoS 邮件链接解析，支持从 `www.webofknowledge.comundefinednull...referrer=target=...` 这类异常 Clarivate 跳转链接中提取真实 `alert-execution-summary` URL。
- 允许 `webofscience.clarivate.cn` 作为合法 WoS 域名。
- 对无法还原的异常链接返回 `None`，避免坏链接进入 requests 或 Playwright。
- WoS 完整页 requests 扩展阶段改为捕获所有异常，坏链接不再中断周报流程。
- 新增测试复现用户遇到的异常跳转链接。

### 为什么
- 用户真实运行时周报失败：`Failed to parse: 'www.webofknowledge.comundefinednull...'`。
- 该字符串不是可访问 URL，而是 Clarivate 邮件追踪链接中嵌套目标 URL 时生成的异常跳转内容；正确目标藏在 `referrer/target/destparams` 参数里。

### 影响文件
- .claude/worklog.md
- paper_analyzer/ingestion/wos_parser.py
- pipeline/fetch_papers.py
- tests/test_email_reader.py

### 验证结果
- 局部测试：`14 passed`。
- 全量测试：`60 passed`。
- 语法检查：`py_compile paper_analyzer/ingestion/wos_parser.py pipeline/fetch_papers.py` 通过。

### 下一步
- 用户重新运行一键周报；如果 `browser_expand_last_error` 变为登录页或机构认证页，再处理浏览器登录态。

---

## 2026-04-28

### 补充：修复 Windows/Streamlit 下 Playwright NotImplementedError

### 做了什么
- 浏览器模式启动 Playwright 前，在 Windows 环境下切换到 `WindowsProactorEventLoopPolicy`。
- 对 Playwright 子进程启动阶段的 `NotImplementedError` 转换为更明确的中文运行时错误。
- 使用本地 `data:text/html` 页面真实启动 Chromium 并验证 WoS 记录解析函数可运行。

### 为什么
- 用户真实运行审计显示 `browser_expand_last_error = "NotImplementedError: NotImplementedError()"`。
- 这说明失败发生在浏览器子进程启动阶段，不是 WoS 页面解析阶段；Windows/Streamlit 组合下常见原因是 asyncio 事件循环策略不支持 subprocess。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- paper_analyzer/ingestion/wos_browser.py

### 验证结果
- 本地单元测试：`59 passed`。
- 语法检查：`py_compile paper_analyzer/ingestion/wos_browser.py pipeline/fetch_papers.py app.py main.py` 通过。
- 本地 Playwright 抓取函数验证：从 `data:text/html` 页面成功解析 1 篇论文。

### 下一步
- 用户重新运行前端一键周报；如果仍报 `NotImplementedError`，先重启 Streamlit 前端进程再试。
- 如果浏览器启动成功但候选仍未扩展，查看新的 `browser_expand_last_error` 判断是否进入了 WoS 登录页/机构认证页。

---

## 2026-04-28

### 补充：修复浏览器扩展错误为空

### 做了什么
- 浏览器模式扩展失败时，`browser_expand_last_error` 改为记录异常类型和异常内容。
- 如果 WoS 页面打开后没有发现记录链接，明确抛出包含页面标题和当前 URL 的错误。
- 新增测试覆盖空异常字符串和登录页/空页诊断。

### 为什么
- 用户真实运行时 `browser_expand_error_count=5`，但 `browser_expand_last_error=""`，无法判断失败原因。
- 下一轮真实运行需要能区分缺依赖、浏览器启动失败、WoS 登录页、学校认证页或页面结构变化。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- paper_analyzer/ingestion/wos_browser.py
- pipeline/fetch_papers.py
- tests/test_fetch_papers.py
- tests/test_wos_browser.py

### 验证结果
- 本地单元测试：`59 passed`。
- 语法检查：`py_compile pipeline/fetch_papers.py paper_analyzer/ingestion/wos_browser.py paper_analyzer/data/schema.py` 通过。

### 下一步
- 用户重新运行一键周报后，查看 `browser_expand_last_error` 的具体内容，再决定是否需要持久浏览器登录态或 WoS API。

---

## 2026-04-28

### 补充：增加 WoS 完整页浏览器解析模式

### 做了什么
- `fetch-papers`、`run` 和 Streamlit 一键周报新增可选浏览器模式。
- 当 `View all` / `AlertSummary` 链接通过 requests 解析不到记录时，可用 Playwright 打开 WoS 页面并等待前端渲染后抽取候选论文。
- 抓取审计新增 `browser_expanded_paper_count`、`browser_expand_error_count` 和 `browser_expand_last_error`。
- 新增 `paper_analyzer/ingestion/wos_browser.py` 与对应单元测试。
- 将 Playwright 声明为可选浏览器依赖。

### 为什么
- 用户真实运行审计显示 `alert_summary_link_count > 0` 但 `expanded_paper_count = 0`，说明普通 HTML 请求拿不到 WoS 完整结果页内容。
- WoS 页面可能需要登录态、校园网认证或 JS 渲染，因此需要浏览器自动化作为下一层扩展方式。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- app.py
- main.py
- pipeline/fetch_papers.py
- paper_analyzer/data/schema.py
- paper_analyzer/ingestion/wos_browser.py
- pyproject.toml
- requirements.txt
- tests/test_fetch_papers.py
- tests/test_wos_browser.py

### 验证结果
- 本地单元测试：`57 passed`。
- 语法检查：`py_compile app.py main.py pipeline/fetch_papers.py paper_analyzer/ingestion/wos_browser.py paper_analyzer/ingestion/wos_parser.py` 通过。

### 下一步
- 在用户本机安装 Playwright 和 Chromium 后，勾选“使用浏览器模式解析 WoS 完整页”真实运行。
- 运行后检查 `fetch_audit.json` 中 `browser_expanded_paper_count` 与 `browser_expand_error_count`。
- 如果浏览器模式仍无法扩展候选，下一步需要处理 WoS 登录态/学校 VPN 认证，或改接 WoS API。

---

## 2026-04-28

### 补充：增强空抓取结果诊断

### 做了什么
- 邮件扫描窗口从 `max_emails * 3` 扩大为 `max_emails * 20`，上限 2000，降低 WoS 邮件不在最近邮件中导致漏扫的概率。
- 新增 `fetch_wos_emails_with_stats()`，返回邮件结果和扫描统计。
- 抓取审计新增：收件箱总数、实际检查邮件数、匹配 WoS/Clarivate header 数、因 seen 跳过数。
- 前端一键周报在抓取结果为空时展示 `fetch_audit.json`，并根据统计给出诊断提示。

### 为什么
- 用户已勾选“重新扫描已处理邮件”后仍提示“没有抓取到可分析的论文”，说明需要排查更早的邮箱扫描/筛选阶段。
- 旧提示只给猜测，不足以判断是扫描窗口太小、header 匹配失败、seen 过滤，还是邮件模板解析失败。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- app.py
- pipeline/fetch_papers.py
- paper_analyzer/data/schema.py
- paper_analyzer/ingestion/email_reader.py
- tests/test_fetch_papers.py

### 验证结果
- 本地单元测试：`55 passed`。
- 语法检查：`py_compile app.py pipeline/fetch_papers.py paper_analyzer/ingestion/email_reader.py paper_analyzer/data/schema.py` 通过。

### 下一步
- 用户再次运行一键周报后，查看前端展示的抓取审计，定位具体为空的位置。

---

## 2026-04-28

### 补充：通过 WoS View all 链接扩展候选论文

### 做了什么
- 从 WoS Alert 邮件中提取 `View all ...` / `AlertSummary` 链接。
- `fetch_papers()` 新增 `expand_alert_pages` 参数；开启后会尝试进入 WoS 完整结果页解析更多候选论文。
- CLI 新增 `--expand-alert-pages`。
- Streamlit “一键周报”新增“进入 WoS 完整结果页扩展候选”选项，默认开启。
- 抓取审计新增 `alert_summary_link_count` 和 `expanded_paper_count`。

### 为什么
- 用户指出 WoS 邮件正文受页面展示限制，可能只展示少量文献；实际完整候选列表在 `View all` 链接后的 Web of Science 页面中。
- 原实现只解析邮件 HTML 中直接展示的记录，会漏掉大量候选论文。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- app.py
- main.py
- pipeline/fetch_papers.py
- paper_analyzer/data/schema.py
- paper_analyzer/ingestion/wos_parser.py
- tests/test_email_reader.py
- tests/test_fetch_papers.py

### 验证结果
- 本地单元测试：`55 passed`。
- 语法检查：`py_compile app.py main.py pipeline/fetch_papers.py paper_analyzer/ingestion/wos_parser.py` 通过。
- 真实 WoS 完整结果页尚未验证；如果 WoS 页面需要登录或由前端渲染，requests 可能解析不到完整记录，需要后续升级为浏览器自动化或 WoS API 路径。

### 下一步
- 真实运行一键周报，检查 `fetch_audit.json` 中 `alert_summary_link_count` 与 `expanded_paper_count`。
- 如果 `alert_summary_link_count > 0` 但 `expanded_paper_count = 0`，说明 requests 方式无法直接拿到完整结果，需要实现浏览器自动化/登录态方案。

---

## 2026-04-28

### 补充：飞书长周报分片发送

### 做了什么
- 将飞书推送从“超过长度截断”改为“自动分片发送”。
- 分片优先按 Markdown 二级标题切分，单个大块过长时再按长度切分。
- 多条消息会带上“第 n/m 部分”前缀。

### 为什么
- 用户真实测试发现飞书中周报被截断，只能在本地前端看完整内容。
- 对用户而言飞书是主要交付渠道，必须能看到完整周报。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- paper_analyzer/notification/feishu.py
- tests/test_feishu.py

### 验证结果
- 本地单元测试：`53 passed`。
- 语法检查：`py_compile paper_analyzer/notification/feishu.py` 通过。

### 下一步
- 重新生成并推送一次长周报，检查飞书中是否按多条消息完整展示。

---

## 2026-04-28

### 补充：修复重复测试时没有可分析论文

### 做了什么
- `fetch_wos_emails()` 新增 `ignore_seen` 参数。
- `fetch-papers`、`run`、Streamlit 一键周报新增“重新扫描已处理邮件”能力。
- 开启重扫时不读取也不更新 `seen_emails.json`，适合调试或重复生成同一批周报。
- 一键周报抓取结果为空时，不再直接抛出“没有可分析的论文”，而是在前端提示可能原因和重试方式。

### 为什么
- 用户测试时出现“周报生成失败：没有可分析的论文”。
- 根因大概率是上一轮测试已经把 WoS 邮件写入 `seen_emails.json`，再次运行时所有邮件被跳过。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- app.py
- main.py
- pipeline/fetch_papers.py
- paper_analyzer/ingestion/email_reader.py
- tests/test_fetch_papers.py

### 验证结果
- 本地单元测试：`51 passed`。
- 语法检查：`py_compile app.py main.py pipeline/fetch_papers.py paper_analyzer/ingestion/email_reader.py` 通过。

### 下一步
- 用户可在“一键周报”中勾选“重新扫描已处理邮件”后重试。

---

## 2026-04-28

### 补充：全文获取基础层与 top-k 全文深读

### 做了什么
- 新增 `paper_analyzer/fulltext/`：
  - `source.py`：全文获取结果结构。
  - `downloader.py`：PDF 下载、PDF 内容校验和安全文件名。
  - `resolver.py`：publisher PDF 直链、Unpaywall、Semantic Scholar、arXiv 候选全文 URL 解析。
- `Paper` 增加 `full_text_path`、`full_text_source`、`full_text_status` 字段。
- `analyze_papers()` 新增 `download_full_text` 和 `unpaywall_email` 参数。
- 开启全文下载时，只对达到阈值且进入 top-k 的论文下载全文；下载成功后解析 PDF 全文并基于全文做 LLM 深读；下载失败则记录“全文获取失败”并跳过深读。
- 周报中展示全文文件路径和来源。
- Streamlit “一键周报”默认启用全文下载；邮件批量页可手动开启。

### 为什么
- 用户明确要求最终周报必须基于全文，不应基于 WoS/QQ 邮件摘要做深度解读。
- 用户场景是最新文献追踪，默认不能假设本地已有 PDF，因此必须自动下载 top-k 全文。

### 影响文件
- .claude/spec.md
- .claude/todo.md
- .claude/worklog.md
- app.py
- main.py
- pipeline/analyze_papers.py
- paper_analyzer/data/schema.py
- paper_analyzer/fulltext/__init__.py
- paper_analyzer/fulltext/source.py
- paper_analyzer/fulltext/downloader.py
- paper_analyzer/fulltext/resolver.py
- paper_analyzer/report/weekly.py
- paper_analyzer/report/writer.py
- tests/test_analyze_fetched_papers.py
- tests/test_fulltext_resolver.py
- tests/test_weekly_report.py

### 验证结果
- 本地单元测试：`50 passed`。
- 语法检查：`py_compile app.py main.py pipeline/analyze_papers.py pipeline/fetch_papers.py paper_analyzer/fulltext/resolver.py paper_analyzer/fulltext/downloader.py paper_analyzer/report/weekly.py` 通过。
- 未执行真实出版社/Unpaywall/Semantic Scholar/arXiv 下载。

### 下一步
- 在校园网或学校 VPN 环境下真实跑一键周报，检查 top-k 全文下载命中率和失败原因。
- 如果开放获取和出版社直链命中率不足，再实现用户配置的 Google Scholar 镜像 resolver。

---

## 2026-04-28

### 补充：修正周报架构为“候选筛选后获取全文”

### 做了什么
- 将产品流程修正为：邮件/WoS 只做候选筛选，top-k 候选论文优先获取全文，再基于全文做深度解读和周报。
- 规划 V2.2 全文获取目标：优先出版商/WoS 链接配合校园网或学校 VPN，其次开放获取接口、预印本/公开仓库，再到用户显式配置的 Google Scholar 镜像 resolver，最后手动上传兜底。
- 明确项目默认不依赖用户本地已下载 PDF，因为目标场景是追踪最新文献；本地库匹配只作为可选加速。
- 明确只对初筛后的 top-k 论文尝试下载全文，未进入 top-k 的候选不下载；成功下载并用于周报的全文保留，其余临时文件清理。

### 为什么
- 用户真实测试发现，仅基于 QQ 邮箱/WoS 邮件摘要无法支撑深度解读，周报内容会缺少作者、方法、发现、结论等关键信息。
- 最终周报应基于全文，而不是摘要级信息。
- 用户目标是省掉“逐封邮件点开摘要、筛选、手动下载、阅读全文”的整天工作量；周报应让用户直接判断论文是否值得进一步使用。

### 影响文件
- .claude/spec.md
- .claude/worklog.md

### 验证结果
- 规划更新完成，尚未实现全文下载器。

### 下一步
- 设计 `paper_analyzer/fulltext/`：resolver、downloader、cache、fallback upload，并先实现开放获取来源。

---

## 2026-04-28

### 补充：减少周报深度解读中的“未识别”

### 做了什么
- 修复邮件批量分析时 LLM 输入信息不足的问题：现在深度解读输入包含标题、作者、期刊/会议、DOI、链接和摘要。
- LLM 返回“未识别”时，使用 `FetchedPaper` 中的作者、期刊、DOI、标题回填 `PaperAnalysis` 基础字段。
- 周报展示层不再直接大段展示“未识别”，改为“邮件/摘要中未提供，需打开原文确认”。
- 新增测试覆盖元数据传入 LLM、基础字段回填和周报缺失字段展示。

### 为什么
- 用户实际测试发现周报“逐篇深度解读”中大量作者、期刊、方法、发现、结论为“未识别”。
- 根因是邮件模式只有摘要/标题，且之前没有把邮件解析到的元数据传给 LLM，也没有在分析结果中回填基础元数据。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- pipeline/analyze_papers.py
- paper_analyzer/report/weekly.py
- tests/test_analyze_fetched_papers.py
- tests/test_weekly_report.py

### 验证结果
- 本地单元测试：`45 passed`。
- 语法检查：`py_compile app.py main.py pipeline/analyze_papers.py pipeline/fetch_papers.py paper_analyzer/report/weekly.py paper_analyzer/notification/feishu.py` 通过。

### 下一步
- 重新用真实“一键周报”跑一遍，观察作者、期刊、DOI 和逐篇解读质量是否明显改善。
- 若方法/发现/结论仍偏空，需要进一步改 Prompt：要求模型基于摘要做“摘要级解读”，而不是过度保守填“未识别”。

---

## 2026-04-28

### 补充：Streamlit 一键周报入口

### 做了什么
- 在 Streamlit 新增“一键周报”tab。
- 前端支持填写 LLM provider、模型名、Base URL、API key、QQ 邮箱地址、邮箱授权码、抓取范围、top-k 和飞书 webhook。
- 点击“生成周报”后，后台串联 `fetch_papers()`、`analyze_papers()`、`weekly_report.md` 生成和可选飞书推送。
- 前端输入的 API key、邮箱授权码和飞书 webhook 只在当前进程环境变量中临时使用，运行结束后恢复，不写入 `.env` 或代码。
- `.env.example` 增加飞书 webhook 和签名密钥占位。

### 为什么
- 用户确认最终产品形态应是：下载项目、启动前端、填写配置、后台自动运行，最终得到一篇文献周报，并可推送飞书。
- 用户已确认飞书为唯一外部推送渠道，不再规划企业微信版本。

### 影响文件
- .env.example
- .claude/spec.md
- .claude/todo.md
- .claude/worklog.md
- app.py

### 验证结果
- 本地单元测试：`43 passed`。
- 语法检查：`py_compile app.py main.py pipeline/analyze_papers.py pipeline/fetch_papers.py paper_analyzer/report/weekly.py paper_analyzer/notification/feishu.py` 通过。
- 未使用真实 QQ 邮箱、LLM API 或飞书 webhook 做端到端联调。

### 下一步
- 使用真实配置执行一次“一键周报”端到端验证，确认 WoS 邮件解析、LLM 输出、周报展示和飞书推送均可用。

---

## 2026-04-28

### 补充：文献周报输出与飞书推送

### 做了什么
- 新增 `paper_analyzer/report/weekly.py`，将批量分析结果汇总为面向用户阅读的 `weekly_report.md`。
- `write_outputs()` 现在同时输出 `results.json`、`report.md` 和 `weekly_report.md`。
- 新增 `paper_analyzer/notification/feishu.py`，支持飞书自定义机器人 webhook 文本推送和可选签名密钥。
- Streamlit 前端优先展示 `weekly_report.md`，邮件批量分析完成后可选择推送到飞书。
- 补充周报和飞书推送单元测试。

### 为什么
- 用户确认最终交付物应是一篇文献周报，而不是中间论文列表。
- 用户确认推送渠道只做飞书，企业微信后续版本不再规划。

### 影响文件
- .claude/spec.md
- .claude/todo.md
- .claude/worklog.md
- app.py
- pipeline/analyze_papers.py
- paper_analyzer/report/writer.py
- paper_analyzer/report/weekly.py
- paper_analyzer/notification/__init__.py
- paper_analyzer/notification/feishu.py
- tests/test_report_writer.py
- tests/test_weekly_report.py
- tests/test_feishu.py

### 验证结果
- 本地单元测试：`43 passed`。
- 语法检查：`py_compile app.py main.py pipeline/analyze_papers.py pipeline/fetch_papers.py paper_analyzer/report/weekly.py paper_analyzer/notification/feishu.py` 通过。
- 未执行真实飞书 webhook 推送。

### 下一步
- 将 Streamlit 前端进一步改成“一键运行”：前端填写 LLM/邮箱配置后直接执行抓取、分析、生成周报和飞书推送。

---

## 2026-04-28

### 补充：修正前端产品目标为一键周报

### 做了什么
- 将产品最终形态更新为“一键生成文献周报”：用户在前端填写 LLM、邮箱和推送配置，后台自动抓取最新文献、筛选、深度解读并生成周报。
- 规划 V2.1 前端目标：配置表单、后台串联 `fetch-papers -> analyze_papers -> weekly report writer -> notifier`、周报展示和外部推送。
- 明确推送渠道优先级：飞书自定义机器人优先，企业微信群机器人次之，个人微信/公众号直推暂缓。

### 为什么
- 用户确认当前前端不应只是上传 PDF 或读取已有抓取结果，而应成为普通用户启动项目后的主入口。
- 周报是最终交付物，论文列表、相似度和单篇分析只是中间产物。

### 影响文件
- .claude/spec.md
- .claude/worklog.md

### 验证结果
- 文档规划更新完成，尚未进入代码实现。

### 下一步
- 先实现 V2.1 的“周报生成器”和前端配置表单，再接入飞书 webhook 推送。

---

## 2026-04-28

### 补充：Streamlit 邮件批量分析入口

### 做了什么
- 将 Streamlit 前端拆为“单篇 PDF”和“邮件批量”两个 tab。
- “邮件批量”支持读取 `data/processed/fetched_papers.json`，展示待分析论文数量和前 10 条预览。
- 前端批量分析复用现有 `analyze_papers()`，支持 profile、阈值、provider、skip-LLM、研究主题、文本长度、输出目录和 `top-k`。
- 更新 spec/todo，记录 V1.2 前端范围。

### 为什么
- V2 已具备 CLI 批量分析能力，但 demo 时只能在命令行查看结果；前端入口能更快展示邮件论文筛选效果。
- 暂不在前端直接抓真实邮箱，避免 UI 操作误触发邮箱联网或 API 成本。

### 影响文件
- .claude/spec.md
- .claude/todo.md
- .claude/worklog.md
- app.py

### 验证结果
- 本地单元测试：`39 passed`。
- 语法检查：`py_compile app.py main.py pipeline/analyze_papers.py pipeline/fetch_papers.py` 通过。
- Streamlit 已启动：`http://127.0.0.1:8501`。

### 下一步
- 在浏览器里检查“邮件批量”tab 的交互和报告展示。
- 后续可根据 demo 反馈决定是否把 `fetch-papers` 也接入前端，或继续先保持 CLI 抓取。

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
- 本地仓库已初始化，首个 commit 为 `56dc925 Initial project import`，当前分支 `main`。
- 已设置远端 `origin=https://github.com/wangchi0312/paper-ai-analyzer.git`。
- `git push -u origin main` 失败：当前非交互环境没有可用 HTTPS GitHub 凭据。
- SSH 检查失败：GitHub host key 已接受，但 `git@github.com` 返回 `Permission denied (publickey)`。

### 下一步
- 需要用户提供一个可用授权方式：安装并登录 GitHub CLI、配置 GitHub SSH key，或在 GitHub 手动创建空仓库后从交互终端推送。

### 后续反馈
- 用户已在 PowerShell 中成功执行 `git push -u origin main`，远端 `main` 分支已建立并跟踪 `origin/main`。
- 用户确认已撤销聊天中暴露过的 PAT。
- 当前 Codex 非交互环境再次执行 `git push` 仍无法读取 GitHub 用户名；后续同步 GitHub 暂由用户在本地 PowerShell 执行，或另行配置非交互凭据。

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
