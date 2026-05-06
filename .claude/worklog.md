# Worklog

> 记录规则：按时间倒序追加。每条记录包含「做了什么 / 为什么 / 影响文件 / 验证结果 / 下一步」。

---

## 2026-05-04

### 修复：人工验证循环时快速跳过

### 做了什么
- 用户再次确认：即使改用本机 Chrome 通道，验证框仍反复从“正在验证”回到“请验证您是真人”。
- 准备给出版商下载阶段增加验证循环保护：短时间内一直处于同一类验证页时，不再等待完整人工验证窗口，直接记录失败并跳过当前论文。

### 为什么
- 这种状态说明站点持续拒绝自动化浏览器；继续等待不会提高成功率，只会让下载阶段卡死。

### 影响文件
- `.claude/spec.md`
- `.claude/worklog.md`
- `paper_analyzer/fulltext/resolver.py`
- `tests/test_fulltext_resolver.py`

### 验证结果
- 全文下载相关测试：`tests/test_fulltext_resolver.py tests/test_analyze_fetched_papers.py` 共 `47 passed`。
- 回归测试：`tests/test_wos_browser.py tests/test_fetch_papers.py tests/test_fulltext_resolver.py tests/test_analyze_fetched_papers.py` 共 `90 passed`。

### 修复：出版商验证循环时改用真实浏览器通道

### 做了什么
- 用户反馈手动验证后页面反复回到“请验证您是真人”，判断为 Playwright 自带自动化 Chromium 被站点持续判定不可信。
- 准备让出版商下载阶段优先使用本机 Chrome/Edge 通道，并让 `PUBLISHER_BROWSER_PROFILE_DIR` 真正生效。

### 为什么
- 持久化 `user_data_dir` 只能保存合法验证后的状态；如果浏览器本身被验证系统拒绝，保存上下文也无法解决循环。
- 使用本机真实浏览器通道可以提高人工验证通过后状态可复用的概率，但仍不绕过验证码。

### 影响文件
- `.claude/spec.md`
- `.claude/worklog.md`
- `.env.example`
- `paper_analyzer/fulltext/resolver.py`
- `tests/test_fulltext_resolver.py`

### 验证结果
- 全文下载相关测试：`tests/test_fulltext_resolver.py tests/test_analyze_fetched_papers.py` 共 `45 passed`。
- 回归测试：`tests/test_wos_browser.py tests/test_fetch_papers.py tests/test_fulltext_resolver.py tests/test_analyze_fetched_papers.py` 共 `88 passed`。

### 改进：全文下载阶段采用手动验证 + 有限自动化

### 做了什么
- 根据用户确认的可行方案，补充下载阶段长期规则：有头浏览器、持久化 `user_data_dir`、人工完成一次验证后复用状态、出版商访问节流。

### 为什么
- 项目不能绕过 Cloudflare/CAPTCHA/机构认证，但可以把验证设计成可见、可恢复、可跳过的人工协作点，避免整个流程静默卡死。

### 影响文件
- `.claude/spec.md`
- `.claude/worklog.md`
- `paper_analyzer/fulltext/resolver.py`
- `tests/test_fulltext_resolver.py`

### 验证结果
- 全文下载相关测试：`tests/test_fulltext_resolver.py tests/test_analyze_fetched_papers.py` 共 `42 passed`。
- 回归测试：`tests/test_wos_browser.py tests/test_fetch_papers.py tests/test_fulltext_resolver.py tests/test_analyze_fetched_papers.py` 共 `85 passed`。

### 修复：WoS 结果页滚动有进展但摘要计数为 0

### 做了什么
- 真实可见浏览器运行时确认：第 1 页能滚动收集到 50 篇，第 2 页能收集到 39 篇，说明滚动问题已基本收敛；但每轮“已有摘要”始终为 0。
- 判断问题从“没有滚动/没有展开”转移为“结果页摘要容器解析失败”，后续需要修正解析器并重新跑完整流程。

### 为什么
- 用户的核心流程依赖 WoS 结果页完整摘要做兴趣筛选；如果摘要计数为 0，程序会错误进入 Full Record 兜底，重新变慢、变复杂。

### 影响文件
- `.claude/spec.md`
- `.claude/worklog.md`
- `paper_analyzer/ingestion/wos_browser.py`
- `tests/test_wos_browser.py`

### 验证结果
- 已抓取真实 WoS 页面快照定位问题：标题链接本身带 `summary-record-title-link`，旧逻辑误把标题链接当成整条记录容器。
- 修复后用真实快照验证：当前可见的两条记录分别解析出 1215 字符与 409 字符摘要。
- 回归测试：`tests/test_wos_browser.py tests/test_fetch_papers.py tests/test_fulltext_resolver.py tests/test_analyze_fetched_papers.py` 共 `82 passed`。
- 真实可见浏览器完整跑到抓取阶段结束：1 封邮件，WoS 完整页返回 89 篇，去重后 89 篇，89 篇都有摘要且长度均超过 80；`full_record_enriched_count=0`，没有退化为批量 Full Record 补摘要。
- 用户观察到后续全文下载阶段卡在人机验证，已按用户要求停止运行；下一步应给下载阶段增加更清晰的“等待人工验证/跳过当前下载候选”进度和超时策略。

### 修复：WoS 结果页反复处理前几篇与 Full Record 批量退化

### 做了什么
- 根据用户真实观察，确认 WoS 浏览器阶段存在三个问题：只对前几篇反复点 `show more`、滚动推进不稳定、摘要解析失败后又退化为逐篇打开 Full Record。
- `wos_browser.py` 收集循环新增可观察进度：当前页、滚动轮次、已收集论文数、已有摘要数、本轮点击 `show more` 数和滚动是否成功。
- `show more` 点击逻辑收紧：只点击当前视口内可见且未点击过的按钮，排除 `show less/收起`，避免反复处理同一批按钮。
- 滚动逻辑收紧：只选择足够大的页面/结果列表容器滚动，滚动步长增大，并记录滚动状态；连续多轮无新增且滚动位置不变时停止当前页。
- CLI `fetch-papers` / `run` 现在会把抓取阶段进度实时打印到控制台，长流程不再完全黑盒。
- Full Record 摘要兜底新增上限 `FULL_RECORD_ABSTRACT_FALLBACK_LIMIT=8`；当结果页摘要解析大面积失败时，不再逐篇打开全部 Full Record，而是提示需要修复结果页摘要解析。

### 为什么
- 用户确认真实手动流程是在 WoS Alert 完整结果页展开摘要并筛选；项目不能因为摘要解析失败就回到全量 Full Record 扫描。
- 91 篇论文下，缺少进度和短路条件会让真实运行无法判断是正常慢、页面卡住，还是逻辑在重复处理同一区域。

### 影响文件
- `.claude/spec.md`
- `.claude/worklog.md`
- `main.py`
- `pipeline/fetch_papers.py`
- `paper_analyzer/ingestion/wos_browser.py`
- `tests/test_fetch_papers.py`
- `tests/test_wos_browser.py`

### 验证结果
- 针对性测试：`tests/test_wos_browser.py tests/test_fetch_papers.py` 共 `39 passed`。
- 扩展验证：`tests/test_wos_browser.py tests/test_fetch_papers.py tests/test_fulltext_resolver.py tests/test_analyze_fetched_papers.py` 共 `78 passed`。
- 语法检查：`py_compile main.py pipeline/fetch_papers.py paper_analyzer/ingestion/wos_browser.py tests/test_wos_browser.py tests/test_fetch_papers.py` 通过。
- 已确认没有遗留 `fetch-papers` / `main.py run` / `browser_profiles/wos` 相关进程。

### 下一步
- 再跑一次真实可见浏览器抓取，重点看控制台进度是否显示滚动推进、摘要数量是否增长，以及 Full Record 是否不再全量打开。

---

### 收敛：WoS 摘要优先筛选，Full Record 只作摘要兜底和下载入口

### 做了什么
- 修正 WoS 真实流程理解：兴趣筛选的文本应优先来自 WoS Alert 完整结果页，而不是先批量打开所有 Full Record。
- 浏览器滚动收集 WoS 结果时，会先尝试点击可见的 `show more` / `更多` / `展开` 按钮，再解析列表卡片中的摘要。
- `parse_wos_result_page()` 现在会从 summary record 容器中提取摘要，并保存到 `FetchedPaper.abstract`，供后续相似度筛选使用。
- 移除抓取阶段“为了 DOI / publisher link 批量进入所有 Full Record”的逻辑。
- 仅当 WoS 完整结果页中某篇论文摘要缺失或过短时，才进入该篇 Full Record 补摘要；这个步骤服务于兴趣筛选，不再作为全量元数据预处理。
- 全文下载阶段如果某篇已通过筛选但缺少 publisher link，会进入该篇 Full Record 查找 `Full text at publisher`，再继续 `View PDF` 下载。

### 为什么
- 用户明确指出：WoS Alert 完整结果页本身有每篇文献摘要，只是需要点 `show more` 展开。完整摘要拿到后就可以兴趣筛选。
- Full Record 只有在结果页拿不到完整摘要，或论文已通过兴趣筛选准备下载时才需要打开；否则 91 篇逐篇打开会非常慢，且不符合手动工作流。

### 影响文件
- `.claude/spec.md`
- `.claude/worklog.md`
- `paper_analyzer/ingestion/wos_browser.py`
- `pipeline/fetch_papers.py`
- `paper_analyzer/fulltext/resolver.py`
- `tests/test_wos_browser.py`

### 验证结果
- 针对性测试：`tests/test_wos_browser.py tests/test_fetch_papers.py tests/test_fulltext_resolver.py` 共 `63 passed`。
- 语法检查：`py_compile paper_analyzer/ingestion/wos_browser.py pipeline/fetch_papers.py paper_analyzer/fulltext/resolver.py tests/test_wos_browser.py` 通过。

### 下一步
- 用真实 WoS 可见浏览器再跑一封邮件，重点观察结果页摘要是否能通过 `show more` 批量展开并写入 `fetched_papers.json`。

---

### 改进：WoS 浏览器模式支持可见窗口

### 做了什么
- 根据用户确认，给 WoS 浏览器抓取链路新增可见窗口开关。
- CLI `fetch-papers` 和 `run` 新增 `--browser-visible`；开启后传入 `headless=False`，Playwright 会启动可见 Chromium。
- Streamlit 一键周报新增“显示浏览器窗口”复选框；需要人工完成 WoS/机构登录或人机验证时可开启。
- `fetch_papers()` 新增 `browser_headless` 参数，默认仍保持无头模式，避免无人值守时弹窗。
- 针对性测试覆盖 `browser_headless=False` 会传给 `WosBrowserSession`。

### 为什么
- 用户反馈真实流程需要看到浏览器页面，并可能在 WoS、机构认证或出版商页面手动处理验证。
- 之前 `--use-browser` 只启动 headless Chromium，用户和 Agent 都看不到窗口，不适合复刻真实手动下载流程。

### 影响文件
- `.claude/spec.md`
- `.claude/worklog.md`
- `app.py`
- `main.py`
- `pipeline/fetch_papers.py`
- `tests/test_fetch_papers.py`

### 验证结果
- 针对性测试：`tests/test_fetch_papers.py tests/test_wos_browser.py` 共 `37 passed`。
- 语法检查：`py_compile app.py main.py pipeline/fetch_papers.py paper_analyzer/ingestion/wos_browser.py tests/test_fetch_papers.py` 通过。
- 真实可见浏览器小测已确认启动的是 `chrome.exe` 而非 `chrome-headless-shell`；任务仍未在 3 分钟内完成，说明后续还需要继续优化 WoS 页面等待/人工接管流程。

### 下一步
- 在可见浏览器模式下增加更明确的阶段提示与人工接管点，避免程序长时间无反馈地等待 WoS 页面。

---

### 收敛：全文下载流程回归 WoS/出版商浏览器路径

### 做了什么
- 根据用户重新描述的手动流程更新 `.claude/spec.md`：邮件只作为 WoS Alert 入口，默认路径回到 `View all citations -> WoS 摘要筛选 -> Full text at publisher -> View PDF -> 保存 PDF`。
- 调整 `resolve_full_text()`：默认只走手动 PDF 兜底和 WoS/出版商浏览器链路；OpenAlex、Unpaywall、Semantic Scholar、arXiv、Crossref TDM 等开放获取/API 来源改为显式开启的兜底。
- 新增 CLI/前端开关：`--full-text-api-fallback` 与“启用开放获取/API 兜底”复选框，默认关闭。
- 调整 `analyze_papers(download_full_text=True)`：PDF 下载失败或 PDF 文本提取失败时，论文保留为候选但不进入 LLM 深度解读，也不再退回摘要轻量解读。
- 更新周报展示逻辑，全文失败只标记“全文获取失败”，不再提示“基于摘要的轻量解读”。
- 更新测试，覆盖默认关闭 API 兜底、显式开启 API 兜底、全文失败不初始化 LLM、PDF 文本提取失败不深读等行为。

### 为什么
- 用户确认当前程序把下载流程复杂化，偏离了真实使用路径；项目应优先复刻用户日常浏览器操作，而不是默认使用多来源检索器。
- “没有 PDF 就做摘要轻量解读”会掩盖真正问题：程序并没有完成用户想要的下载文献任务。

### 影响文件
- `.claude/spec.md`
- `.claude/worklog.md`
- `app.py`
- `main.py`
- `pipeline/analyze_papers.py`
- `paper_analyzer/fulltext/resolver.py`
- `paper_analyzer/report/weekly.py`
- `tests/test_analyze_fetched_papers.py`
- `tests/test_fulltext_resolver.py`

### 验证结果
- 针对性测试：`41 passed`。
- 全量测试：`154 passed`。
- 语法检查：`py_compile app.py main.py pipeline/analyze_papers.py paper_analyzer/fulltext/resolver.py paper_analyzer/report/weekly.py tests/test_analyze_fetched_papers.py tests/test_fulltext_resolver.py` 通过。

### 下一步
- 继续把 WoS 页面摘要展开、逐篇摘要筛选、出版商新窗口/PDF 预览新窗口这几个浏览器操作做得更直观，减少隐藏的 requests/API 补全路径。

---

### 修复：top-k 全文获取必须下载真实 PDF

### 做了什么
- 明确更新 `.claude/spec.md`：HTML、验证码页、登录页不再视为全文下载成功，深度解读必须基于 PDF。
- 修改 `paper_analyzer/fulltext/resolver.py`：`publisher_html` 不再返回 `success=True`，即使抓到 HTML 正文也会标记为 PDF 获取失败。
- 新增 Crossref TDM PDF link 候选来源，提高公开/出版社 TDM 链接命中率。
- 新增可选 Elsevier Article Retrieval API PDF 下载路径，读取 `ELSEVIER_API_KEY`、`ELSEVIER_INSTTOKEN`、`ELSEVIER_ACCESS_TOKEN`；未配置时自动跳过。
- 出版商浏览器下载改为复用持久化 profile，默认复用 WoS profile，也可通过 `PUBLISHER_BROWSER_PROFILE_DIR` 指定。
- 修复 `resolver.py` 中因编码损坏导致的异常字符串/f-string 语法问题，并将下载失败原因恢复为正常中文。
- `.env.example` 增加 Elsevier API 和出版商浏览器 profile 配置占位。

### 为什么
- 用户确认产品关键阻塞是 top-k 论文无法下载 PDF，HTML 正文缺图表和实验结果，不能支撑深度解读，也不满足“自动帮用户下载好 PDF”的目标。

### 影响文件
- `.claude/spec.md`
- `.claude/worklog.md`
- `.env.example`
- `paper_analyzer/fulltext/resolver.py`
- `tests/test_fulltext_resolver.py`

### 验证结果
- `py_compile paper_analyzer/fulltext/resolver.py tests/test_fulltext_resolver.py` 通过。
- `tests/test_fulltext_resolver.py`：25 passed。
- `tests/test_analyze_fetched_papers.py tests/test_fetch_papers.py tests/test_wos_browser.py`：52 passed。
- 全量测试：156 passed。

### 下一步
- 在真实机构网络/VPN 环境中重跑一键周报或 `--download-full-text --skip-llm`，重点看 top-k 的 `full_text_status` 是否只在 PDF 成功时为 `downloaded`，以及 Elsevier API/Crossref TDM 是否提升 PDF 命中率。

---

## 2026-05-03

### 代码质量改进：统一超时单位（秒）

### 做了什么
- 统一 wos_browser.py 的超时单位：将 `timeout_ms`（毫秒）改为 `timeout`（秒），与全项目保持一致。
- 修改 `WosBrowserSession.__init__` 参数：`timeout_ms: int = 30000` → `timeout: int = 30`。
- 修改 `fetch_wos_alert_with_browser` 参数：`timeout_ms: int = 30000` → `timeout: int = 30`。
- 内部调用处自动转换：`self.timeout * 1000` 转换为毫秒供 Playwright 使用。
- 保持内部函数参数名不变（`_goto_wos_url` 等仍使用 `timeout_ms`），因为它们是内部实现细节。

### 为什么
- 超时单位不一致（毫秒 vs 秒）容易混淆，增加维护成本。
- 与其他模块（如 fulltext_resolver）保持一致，所有超时参数统一使用秒。
- 用户配置时更容易理解：30 秒比 30000 毫秒更直观。

### 影响文件
- paper_analyzer/ingestion/wos_browser.py

### 验证结果
- 相关测试通过：`test_wos_browser.py: 19 passed`，`test_fetch_papers.py: 14 passed`。

### 下一步
- 提交本次修改。
- 继续处理其他改进项（错误处理细化）。

---

## 2026-05-03

### 代码质量改进：路径一致性 + 异常文件清理

### 做了什么
- 修复前端邮件批量 tab 默认路径：从 `paper_library.json` 改为 `fetched_papers.json`，与 fetch_papers 默认输出路径保持一致。
- 清理异常文件 `=4.12,`（命令行误操作产物）。
- 更新 .gitignore 添加 `=*` 规则，防止类似异常文件被追踪。

### 为什么
- 路径不一致会导致用户使用"邮件批量"功能时找不到抓取结果。
- 异常文件污染项目目录，影响 git 状态。

### 影响文件
- app.py
- .gitignore

### 验证结果
- 无需测试，配置修改。

### 下一步
- 提交本次修改。
- 继续处理其他改进项（超时单位统一、错误处理细化）。

---

## 2026-05-03

### 补充：邮件扫描策略调整（测试阶段 vs 正式版）

### 做了什么
- 明确邮件扫描策略：测试阶段使用 `--ignore-seen` 完全忽略 seen 机制，正式版遇已见 Alert 立即停止。
- 修改 `email_reader.py` 扫描逻辑：遇到已处理邮件时 `break` 而非 `continue`，确保正式版不会继续往前扫描。
- 保持测试阶段灵活性：用户可传 `--ignore-seen` 或前端勾选"重新扫描已处理邮件"来反复测试同一批邮件。
- 无新邮件时的友好提示已通过 `_emit_zero_result_diagnostics()` 实现，包含"请等待 WoS 发送下一轮 Citation Alert"的建议。

### 为什么
- 当前是测试阶段，邮箱已被多次扫描，seen 机制会阻止反复测试。
- 正式版应更智能：遇到已处理邮件立即停止，避免无意义的扫描，并明确告知用户无新邮件。
- 用户明确需求：追踪最新文献，只需最新的 2 封邮件（通过 `--max 2` 配置），历史邮件已看过不需要再分析。

### 影响文件
- paper_analyzer/ingestion/email_reader.py

### 验证结果
- 相关测试通过：`test_email_reader.py: 11 passed`，`test_fetch_papers.py: 14 passed`。

### 下一步
- 提交本次修改到 git。
- 用户在真实邮箱环境验证正式版行为（无 `--ignore-seen` 时遇已见 Alert 停止）。

---

## 2026-05-03

### 补充：智能邮件扫描遇已见 Alert 停止 + top-k 全文失败顺延 + headless 默认 + 无新 Alert 诊断

### 做了什么
- 邮件扫描改为从最新到最旧扫描，遇到已处理过的 Citation Alert 立即停止，不再无休止扩大扫描范围。
- `fetch_wos_emails_with_stats()` 返回值从 2 元组改为 3 元组 `(results, stats, hit_seen_alert)`，供上层判断是否因遇到已见 Alert 而提前停止。
- 无新 Alert 时通过 `_emit_zero_result_diagnostics()` 输出友好诊断，包含逐封邮件明细和可操作建议。
- `analyze_papers()` 的 top-k 控制从静态 `llm_allowed_indexes` 集合改为动态 `llm_remaining` 计数器：全文下载失败时名额不消耗，下一个达到阈值的论文自动递补。
- Playwright 浏览器模式默认 `headless=True`。
- 修复 `_enrich_unique_papers` 中因 in-place mutation 导致的 KeyError 和 `metadata_enriched_count` 始终为 0 的 bug：在并发 enrich 前记录 `paper_keys[i]` 和 `paper_snapshots[i]`，reconcile 时使用原始 key。
- 修复 `test_fetch_papers_expands_alert_summary_pages` 函数头被误删的问题。
- 修正所有 `fetch_wos_emails_with_stats` mock 返回值为正确的 3 元组格式。

### 为什么
- 用户明确反馈"应扫描到最近一封已处理 Alert 时停止，而不是无休止扩大搜索范围"，这才是智能文献追踪的正确行为。
- top-k 静态选取导致全文下载失败时名额浪费，用户上次运行 top-k=1 时第 1 名下载超时 → 0 篇深读。
- 浏览器弹窗干扰用户正常使用。
- `FetchedPaper.__eq__` 按字段值比较，in-place mutation 后 `_paper_key` 变化导致 reconcile 阶段 KeyError。

### 影响文件
- paper_analyzer/ingestion/email_reader.py
- pipeline/fetch_papers.py
- pipeline/analyze_papers.py
- paper_analyzer/ingestion/wos_browser.py
- tests/test_fetch_papers.py
- tests/test_analyze_fetched_papers.py
- .claude/spec.md

### 验证结果
- 全量测试：`118 passed`。
- 语法检查通过。

### 下一步
- 用户在真实邮箱环境运行，验证"遇已见 Alert 停止"和"无新 Alert 友好诊断"的实际效果。
- 后续版本可考虑用 IMAP `SINCE` 日期搜索进一步缩小扫描范围。

---

## 2026-04-29

### 补充：WoS 数字页码分页

### 做了什么
- 读取用户最新测试结果：
  - `unique_paper_count=50`，`browser_expanded_paper_count=48`。
  - `arrow_drop_down=0`，`javascript` 链接为 0，候选质量已正常。
  - 数量仍停留在第一页规模，说明 URL 页码兜底没有让 WoS 进入第二页。
- 新增数字页码分页策略：
  - 在 DOM 中识别当前页码。
  - 当前页码为 1 时优先点击页码 2。
  - 该策略放在宽泛 Next 文本匹配之前，减少误点其它 next 控件。

### 为什么
- WoS 的 Next 按钮和 URL 页码都不稳定时，分页器里的数字页码通常更明确。
- 当前抓取已证明第一页解析可用，剩余目标是进入第二页拿到 71 results 中超过第一页的部分。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- .claude/handoff.md
- paper_analyzer/ingestion/wos_browser.py
- tests/test_wos_browser.py

### 验证结果
- 针对性测试：`38 passed`。
- 语法检查：`py_compile paper_analyzer/ingestion/wos_browser.py pipeline/fetch_papers.py app.py main.py` 通过。

### 下一步
- 用户下一轮测试后，若 `browser_expanded_paper_count` 超过 48 且 `unique_paper_count` 接近 73，则分页修复有效。
- 如果仍停在 50，需要在前端日志或审计中记录分页尝试后的 URL/新增数量，继续定位 WoS 分页机制。

---

## 2026-04-29

### 补充：全文下载超时可配置

### 做了什么
- 读取用户反馈后的本地文件：
  - `fetch_audit.json` 已更新到 12:35，说明邮件抓取和 WoS 扩展已完成。
  - 最新 `data/outputs` 没有生成新结果目录，说明任务卡在抓取后的全文下载/分析阶段。
- 为全文下载链路新增可配置超时：
  - `analyze_papers()` 新增 `full_text_timeout`，默认 10 秒。
  - CLI `analyze` / `run` 新增 `--full-text-timeout`。
  - Streamlit 一键周报和邮件批量页新增“全文下载超时秒数”，默认 10 秒。
  - 前端两个同名控件增加唯一 key，避免 Streamlit widget ID 冲突。
- 新增测试确认 `full_text_timeout` 会传递给 `resolve_full_text()`。

### 为什么
- 全文下载会串行访问 arXiv、Unpaywall、Semantic Scholar 或 PDF URL；默认 30 秒在多个 top-k 候选上会让前端看起来卡死。
- 调试阶段应快速失败并写入“全文获取失败”，而不是让用户长时间停在 spinner。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- .claude/handoff.md
- app.py
- main.py
- pipeline/analyze_papers.py
- tests/test_analyze_fetched_papers.py

### 验证结果
- 针对性测试：`35 passed`。
- 语法检查：`py_compile app.py main.py pipeline/analyze_papers.py pipeline/fetch_papers.py paper_analyzer/fulltext/resolver.py paper_analyzer/fulltext/downloader.py` 通过。

### 下一步
- 用户需要刷新或重启 Streamlit 前端后重试。
- 一键周报测试时建议将“全文下载超时秒数”设为 5-10 秒；若只想继续验证抓取数量，可临时取消“下载全文后再深度解读”。

---

## 2026-04-29

### 补充：WoS summary URL 页码兜底翻页

### 做了什么
- 读取用户最新测试结果：
  - `unique_paper_count=50`，`browser_expanded_paper_count=48`。
  - `arrow_drop_down=0`，`javascript` 链接为 0，说明 facet/dropdown 误抓已修复。
  - Raissi 71 results 邮件扩展 46 条，整体表现符合只抓到 WoS 第一页的情况。
- 新增 WoS summary URL 页码兜底翻页：
  - `/wos/woscc/summary/<id>/relevance/1` 自动推进到 `/relevance/2`。
  - 如果 URL 缺少页码，则尝试追加 `/2`。
  - 翻页后若连续页面没有新增标题，提前停止，避免无效循环。
- 新增测试覆盖已有页码递增和缺页码追加两种 URL。

### 为什么
- DOM 下一页按钮在真实 WoS 页面中仍未稳定识别，导致只抓到第一页约 50 条。
- 真实 URL 已暴露 summary 页码结构，使用 URL 页码作为兜底比继续猜按钮 selector 更稳定。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- .claude/handoff.md
- paper_analyzer/ingestion/wos_browser.py
- tests/test_wos_browser.py

### 验证结果
- 针对性测试：`36 passed`。
- 语法检查：`py_compile paper_analyzer/ingestion/wos_browser.py pipeline/fetch_papers.py app.py main.py` 通过。

### 下一步
- 用户下一轮测试后，如果 URL 兜底有效，`unique_paper_count` 应从 50 增加到接近 73。
- 如果仍停在 50，需要捕获页面最后 URL 或前端日志中翻页行为，判断 WoS 是否不接受直接页码 URL。

---

## 2026-04-29

### 补充：过滤 WoS facet/venue 误抓项

### 做了什么
- 读取用户最新测试结果：
  - `browser_expand_error_count=0`，说明浏览器解析已稳定进入 WoS 页面。
  - `browser_expanded_paper_count=89`，`browser_new_unique_paper_count=83`，最终 `unique_paper_count=90`。
  - 结果中混入了 WoS 筛选项/期刊名，例如 `COMPUTER METHODS IN APPLIED MECHANICS AND ENGINEERING arrow_drop_down`，链接为 `javascript:void(0)`。
- 收紧 WoS 结果页解析：
  - 标题中包含 `arrow_drop_down` 或 `javascript:void` 的文本不再视为论文标题。
  - `javascript:` 和 `#` 链接不再视为 WoS record 链接。
  - title 元素自身是 `<a>` 时，只有 href 是真实 WoS record 才回填链接。
- 新增测试覆盖 facet/dropdown 项过滤，以及真实 title-only 候选保留。

### 为什么
- 宽松 title 元素解析解决了抓不到 summary 页记录的问题，但也把左侧筛选项、期刊下拉项误当作论文。
- 过滤控件文本后，候选数量应从 90 回落到更接近真实论文数，同时避免低质量候选污染相似度排序和周报。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- .claude/handoff.md
- paper_analyzer/ingestion/wos_browser.py
- tests/test_wos_browser.py

### 验证结果
- 针对性测试：`34 passed`。
- 语法检查：`py_compile paper_analyzer/ingestion/wos_browser.py pipeline/fetch_papers.py app.py main.py` 通过。

### 下一步
- 用户下一轮测试后重点看 `unique_paper_count` 是否回落到接近 73，且周报候选排序中不再出现 `arrow_drop_down`。
- 如果过滤后候选只有约 48 篇，说明还需要继续增强 WoS 下一页/虚拟列表滚动；如果在 67-73 左右，则抓取阶段基本可进入全文下载命中率优化。

---

## 2026-04-29

### 补充：WoS summary title 元素解析

### 做了什么
- 读取用户最新测试结果：
  - 第二封 Raissi Alert 已进入 `webofscience.clarivate.cn/wos/woscc/summary/.../relevance/2`。
  - 页面标题显示该 Alert 有 67 条结果，但代码未发现旧版 WoS 记录链接 selector。
  - 最终候选退回到 7 篇，说明问题从登录/跳转进一步缩小到 summary 页 DOM 识别。
- 扩展 WoS 结果页解析：
  - 继续支持带 `full-record` / `WOS:` 的链接。
  - 新增识别 `data-ta`、`id`、`class`、`aria-label` 中带 summary/record/title 标记的标题元素。
  - 标题元素附近找不到 Full Record 链接时，保留 title-only 候选。
  - `wait_for_wos_records` 对已加载的 WoS summary 页不再立即报错，允许进入宽松解析。
- 新增测试覆盖 `data-ta="summary-record-title"` title-only 解析，以及标题容器附近链接回填。

### 为什么
- 真实 WoS summary 页可能不再把标题暴露为简单 `<a href="...full-record...">`，而是由组件和属性标记渲染。
- 对当前项目而言，先拿到标题也有价值：可以进入候选筛选，并通过标题查询开放获取全文。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- .claude/handoff.md
- paper_analyzer/ingestion/wos_browser.py
- tests/test_wos_browser.py

### 验证结果
- 针对性测试：`33 passed`。
- 语法检查：`py_compile paper_analyzer/ingestion/wos_browser.py pipeline/fetch_papers.py app.py main.py` 通过。

### 下一步
- 用户重新测试，重点看第二封 Raissi Alert 的 `browser_expanded_paper_count` 是否从 0/少量增加。
- 如果仍然没有增加，需要保存一份脱敏后的 WoS summary DOM 结构或增加页面内 JS 提取策略，直接从可见文本块中识别论文标题。

---

## 2026-04-29

### 补充：WoS 虚拟列表滚动收集

### 做了什么
- 读取用户最新测试结果：
  - 最近两封目标 Alert 已正确命中。
  - 浏览器扩展无错误，`browser_expanded_paper_count=10`。
  - Raissi 71 篇邮件只新增 5 篇，最终候选 12 篇，仍未抓完整。
  - 全文下载链路已验证可用，Top 1 论文成功从 arXiv 下载 PDF。
- 将 WoS 当前页解析从“滚动结束后解析一次”改为“每滚动一段就解析并累计一次”。
- 增强下一页按钮识别，补充英文小写、中文“下一”、图标文本、`data-ta`/class 里的 next 等情况。
- 新增测试覆盖虚拟列表：同一页滚动过程中 DOM 替换可见记录时，解析器能累计所有出现过的标题链接。

### 为什么
- WoS 页面很可能使用虚拟列表或懒加载，DOM 一次只保留当前可见的少量记录；旧逻辑会漏掉滚动过程中出现过但最终被卸载的记录。
- 用户期望最近两封邮件合计 73 篇，但当前只到 12 篇，说明已经越过登录/浏览器错误阶段，瓶颈变成页面滚动与分页解析。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- .claude/handoff.md
- paper_analyzer/ingestion/wos_browser.py
- tests/test_wos_browser.py

### 验证结果
- 针对性测试：`31 passed`。
- 语法检查：`py_compile app.py main.py pipeline/fetch_papers.py pipeline/analyze_papers.py paper_analyzer/ingestion/wos_browser.py paper_analyzer/data/schema.py` 通过。

### 下一步
- 用户下一轮测试仍只验证抓取和全文下载，不调用 LLM。
- 重点观察 `browser_expanded_paper_count` 是否从 10 明显增加，理想情况下 Raissi 71 results 应接近 71 或至少接近页面当前可展示的 50。
- 如果仍停在 10 左右，需要进一步记录真实 WoS 页面分页/列表控件结构，或改走 WoS 前端接口请求。

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
## 2026-05-06

### 做了什么
- 记录新的全文获取方向：默认使用 SPIS 文献求助，提交后轮询默认邮箱接收 PDF。
- 明确旧出版商网页自动下载链路只保留为显式 fallback，不再作为默认路径。
- 根据用户真实截图和本地探测，确认 SPIS 搜索结果卡片存在“下载”入口；后续实现调整为优先直接下载，失败后才文献求助。

### 为什么
- 真实运行中出版商/Cloudflare 验证循环导致自动下载不可用。
- 用户的可行流程已经切换为 SPIS 文献求助 + 邮箱收 PDF，需要让代码流程回到简单、可观测、可维护。
- 若 SPIS 已提供 PDF 下载链接，继续提交文献求助会更慢且容易误判为失败。

### 影响文件
- .claude/spec.md
- .claude/worklog.md
- paper_analyzer/fulltext/spis.py
- paper_analyzer/fulltext/resolver.py
- paper_analyzer/ingestion/email_reader.py
- paper_analyzer/utils/config.py
- pipeline/analyze_papers.py
- main.py
- app.py
- .env.example
- tests/test_spis_fulltext.py
- tests/test_fulltext_resolver.py

### 验证计划
- 先跑 SPIS resolver 和全文 resolver 相关单元测试。
- 如果单元测试通过，再做一次有限真实提交和邮箱轮询验证；真实等待可能受 SPIS 邮件投递时间影响。

### 验证结果
- 用户实测输出 `data/outputs/20260506_190437` 显示目标论文被标记为 `spis_not_found`，原因是旧解析器只识别详情页链接，没有识别搜索结果卡片。
- 本地探测 SPIS 搜索页确认目标论文卡片存在“下载”按钮，链接指向 arXiv PDF。
- 修复后真实小测：`Hybrid two-stage reconstruction of multiscale subsurface flow with physics-informed residual connected neural operator` 通过 SPIS 直接下载保存为 `data/debug/spis_direct/direct_resolver_fixed.pdf`，大小 4,923,079 字节，文件头为 `%PDF-1.7`。
- 全量测试：`D:\software\anaconda\envs\paper-ai\python.exe -m pytest -q tests -p no:cacheprovider`，结果 `180 passed`。

### 2026-05-06 继续修复
- 用户再次完整运行后，30 篇进入全文下载的论文中只有 1 篇成功，失败集中在 `spis_not_found` 与 `spis_submit_failed`。
- 排查发现：SPIS DOI 查询失败后没有退回标题查询；文献求助仍偏向旧详情页表单，未稳定支持搜索结果卡片中的“文献求助”弹窗。
- 下一步改为：DOI/标题两级搜索；直接下载失败后，点击同一结果卡片的“文献求助”，填写邮箱、勾选服务条款并提交。
- 修复后真实小测 1：`Hybrid two-stage reconstruction...` 仍可通过 SPIS 直接下载真实 PDF，大小 4,923,079 字节，文件头 `%PDF-1.7`。
- 修复后真实小测 2：`Energy loss informed cell-based multilayer perceptron...` 这类无下载按钮的 SPIS 结果卡片可打开“文献求助”弹窗并成功提交，状态 `submitted`。
- 全量测试：`D:\software\anaconda\envs\paper-ai\python.exe -m pytest -q tests -p no:cacheprovider`，结果 `180 passed`。
