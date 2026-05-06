# Academic Paper AI Analyzer V1/V2 Spec

## 2026-05-04 补充：全文下载流程回归用户手动路径

用户重新描述了日常下载文献的真实流程：收到 WoS Citation Alert 邮件后，不阅读邮件正文，直接点击 `View all citations` 进入 WoS 完整结果页；在 WoS 页面逐篇查看摘要，必要时点 `show more` 展开完整摘要；对摘要感兴趣的论文，点击 `Full text at publisher` 进入期刊页面；在期刊页面点击 `View PDF` 进入浏览器 PDF 预览页；最后在预览页保存 PDF，关闭新窗口后回到 WoS 列表继续下一篇。

后续代码应以这个路径作为默认主流程，而不是把全文获取默认做成复杂的跨平台检索器：

1. 邮件阶段只负责找到 WoS Alert 入口链接，不依赖邮件正文里的不完整论文信息。
2. WoS 浏览器阶段负责收集候选论文标题、摘要、DOI、WoS full record 链接与 `Full text at publisher` 链接。
3. 筛选阶段基于 WoS 完整摘要做相似度判断；未达阈值的论文不进入下载。
4. 下载阶段默认只走“WoS/出版商浏览器链路”：`Full text at publisher -> View PDF -> PDF 预览/下载`。遇到登录、机构认证或人机验证时，不绕过，应允许用户在浏览器中人工完成，或明确记录失败原因。
5. OpenAlex、Unpaywall、Semantic Scholar、arXiv、Crossref TDM、Elsevier API 等开放获取/API 来源只作为显式开启的兜底能力，默认关闭，避免主流程混乱。
6. `download_full_text=True` 时，深度解读必须基于真实 PDF。PDF 下载失败或 PDF 文本提取失败的论文只保留为“候选但未深读”，不得自动退回到摘要轻量解读。
7. 报告中应清晰区分：已下载并深读、候选但全文获取失败、低于阈值、未进入 top-k。
8. WoS 浏览器模式必须支持可见窗口运行。用户需要在 WoS/Clarivate/学校认证/出版商验证页面人工操作时，应能通过 CLI 或前端关闭 headless，并设置人工登录等待时间。
9. 兴趣筛选的摘要优先来自 WoS Alert 完整结果页。浏览器模式应先在结果页点击每条记录的 `show more` 展开完整摘要，再基于完整摘要做兴趣判断；只有结果页无法得到完整摘要时，才进入该篇 Full Record 补摘要。不得为了预处理 DOI 或出版商链接而批量打开所有 Full Record。
10. `Full text at publisher` 下载入口可来自 Full Record 页面。只有论文已经基于摘要通过兴趣筛选并进入下载候选时，才打开 Full Record 查找 `Full text at publisher` 并继续出版商 PDF 下载流程。
11. WoS 浏览器收集阶段必须有可观察进度和短路条件。至少输出当前页、滚动轮次、已收集标题数、已获得摘要数、点击 `show more` 数量；当连续多轮没有新增记录且滚动位置不变化时停止当前页，避免反复处理前几条记录。
12. Full Record 摘要兜底必须有上限。若结果页摘要解析失败导致大量论文都缺摘要，不得自动逐篇打开所有 Full Record；应记录失败分布并提示需要修复结果页摘要解析。
13. WoS 结果页解析不能只依赖固定 class/id。结果卡片可能是 `app-summary-record` 等自定义标签；解析摘要时应同时识别标签名、属性、标题附近父级容器，并在滚动产生重复标题时合并更完整的摘要/链接信息。
14. 出版商 PDF 下载阶段采用“手动验证 + 有限自动化”：使用有头浏览器和持久化 `user_data_dir` 复用登录/验证状态；遇到 Cloudflare、CAPTCHA、机构认证等人机验证时暂停等待用户在浏览器中完成；完成后继续当前论文下载，超时则跳过并记录原因。出版商访问必须节流，默认相邻访问间隔不少于 10 秒，避免因为高频请求再次触发验证。
15. 若 Playwright 自带 Chromium 在 Cloudflare/真人验证中循环失败，出版商下载阶段应优先使用本机真实 Chrome/Edge 通道与独立持久化 profile。`PUBLISHER_BROWSER_PROFILE_DIR` 必须真实生效；可通过 `PUBLISHER_BROWSER_CHANNEL=chrome/msedge/chromium/auto` 控制浏览器通道。即使使用真实浏览器通道，也不得自动破解验证码，验证仍由用户手动完成。
16. 如果用户手动验证后仍反复回到“请验证您是真人”/Cloudflare 验证页，说明站点持续拒绝自动化浏览器。程序应在短时间内识别为验证循环，跳过当前全文下载候选并记录“人工验证循环失败”，不得长时间卡住。此类论文只能通过手动 PDF 目录或站点允许的合法 API 兜底。

## 项目目标

实现一个本地运行的论文分析助手。V1 先完成 CLI 核心流程，确认效果后再实现 Streamlit 前端。

产品最终形态调整为“一键生成文献周报”：

1. 用户下载项目后启动本地前端。
2. 前端引导用户填写运行配置：LLM provider、模型名、API key；邮箱运营商、邮箱地址、邮箱授权码；研究主题和筛选参数。
3. 点击运行后，后台自动完成邮箱抓取、论文解析、相关性初筛、全文获取、全文解析、LLM 深度解读和周报推送。
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
3. 全文获取优先级按真实用户场景排序：
   - 出版商/WoS 链接：优先使用用户当前网络环境访问。如果用户处于校园网或已配置学校 VPN，很多订阅期刊可直接下载。
   - 开放获取接口：Unpaywall / Crossref TDM links / Semantic Scholar openAccessPdf 等。
   - 论文仓库或预印本：arXiv 等公开来源。
   - 用户配置的 Google Scholar 镜像或其他镜像 resolver：默认关闭，用户显式配置后启用，并在界面提示版权、稳定性和安全风险。
   - 用户手动上传 PDF 作为兜底。
4. 项目追踪的是最新文献，默认不依赖用户本地已下载 PDF；本地库匹配只作为可选加速，不作为主路径。
5. 对通过初筛的 top-k 论文尝试下载全文；未进入 top-k 的候选不下载全文。
6. 成功下载的全文保存到本次输出目录的 `papers/` 子目录，供用户直接打开；周报中提供本地文件路径和来源链接。
7. 只有成功获取全文的论文进入深度解读；未获取全文的论文进入“候选但未深读”列表，并给出获取失败原因。
8. 周报中的“深度解读”必须基于全文，邮件摘要仅可作为候选筛选和补充元数据。
9. 非 top-k 候选论文不保存全文；临时下载失败文件和中间缓存默认在本次任务结束后清理。已用于周报的 top-k 全文默认保留，便于用户复查。
10. 支持“只验证抓取与全文下载，不调用 LLM”的调试路径：`--download-full-text --skip-llm` 应对达到阈值且进入 top-k 的候选尝试下载和解析全文，但不得初始化 LLM client 或调用模型 API。前端一键周报也需要提供同等调试开关，开启后不要求填写 API Key。

当前已落地的周报能力：

1. 每次调用统一输出层时，除了 `results.json` 和 `report.md`，额外生成 `weekly_report.md`。
2. `weekly_report.md` 是面向用户阅读的最终文档，包含候选论文数量、深度解读数量、重点推荐、候选论文排序和逐篇深度解读。
3. Streamlit 前端优先展示 `weekly_report.md`。
4. 邮件批量分析完成后，可选择通过飞书自定义机器人 webhook 推送周报文本；支持飞书签名密钥。
   - 飞书推送会自动按 Markdown 章节/长度分多条消息发送，避免长周报被截断。
5. Streamlit 已新增“一键周报”入口，支持在前端填写模型、邮箱和飞书配置后串联抓取、分析、生成周报和可选飞书推送。
6. 前端输入的 API key、邮箱授权码、飞书 webhook 只在当前运行进程中临时使用，不写入代码、`.env` 或提交历史。
7. 邮件批量深度解读会把标题、作者、期刊/会议、DOI、链接和摘要一起提供给 LLM，并在 LLM 返回“未识别”时用邮件元数据回填基础字段。
8. 周报展示会将仍无法确认的字段写为“邮件/摘要中未提供，需打开原文确认”，避免大段机械的“未识别”。
9. 已新增全文获取基础层：`paper_analyzer/fulltext/` 支持 publisher PDF 直链、Unpaywall、Semantic Scholar、arXiv 候选 URL 解析和 PDF 下载。
10. `analyze_papers(download_full_text=True)` 会只对达到阈值且进入 top-k 的论文尝试下载全文；下载成功后用 PDF 全文进入 LLM 深度解读，下载失败则标记“全文获取失败”并跳过深读。
11. Streamlit “一键周报”默认启用“下载全文后再深度解读”；邮件批量页可手动开启。

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
10. 支持 `--ignore-seen` 和前端“重新扫描已处理邮件”，用于重复生成周报或调试同一批 WoS 邮件；开启时不更新 `seen_emails.json`。
11. 邮件 HTML 中直接展示的记录不代表完整 Alert 结果；需要提取 `View all ...` / AlertSummary 链接并尝试进入 WoS 完整结果页扩展候选论文。若 WoS 页面需要登录、校园网认证或前端渲染导致 requests 解析不到记录，则保留邮件记录并在审计中记录扩展结果。
12. 邮箱扫描审计需记录收件箱总邮件数、实际检查邮件数、匹配 WoS/Clarivate header 数、因 seen 跳过数，前端空结果时展示这些统计，辅助判断是扫描窗口、seen 过滤还是邮件模板解析问题。
13. 当普通 requests 无法从 WoS `View all` 页面解析完整结果时，提供可选 Playwright 浏览器模式。浏览器模式使用本机浏览器环境打开 AlertSummary 链接，等待前端渲染后抽取候选论文；若未安装 Playwright 或浏览器驱动，需要在抓取审计中记录明确错误并回退到邮件正文记录。浏览器扩展失败时，审计错误不得为空，至少包含异常类型；若页面打开但未发现 WoS 记录链接，需要记录页面标题与当前 URL，便于判断是否被登录页/机构认证页拦截。Windows/Streamlit 环境下需要在启动 Playwright 前修正 asyncio 事件循环策略，避免浏览器子进程启动时报 `NotImplementedError`。
14. 浏览器模式不应只抽取 WoS 完整页首屏记录；解析前需要尝试滚动加载，并在存在下一页控件时翻页抽取。浏览器最多翻页数需要在前端和 CLI 中可配置，并写入抓取审计。抓取审计需要区分浏览器扩展的总记录数、新增唯一记录数和重复记录数，避免“扩展成功但没有新增候选”被误判。
15. 当用户期望最近 N 封 WoS Alert 对应固定候选总数时，抓取审计需要提供逐封邮件和逐个 Alert 链接的解析明细：邮件主题、邮件正文解析数、AlertSummary 链接数、requests 扩展数、浏览器扩展数、新增唯一数、重复数和错误数。审计不得保存完整带 session 的 WoS URL，只保存域名和路径级摘要。
16. Playwright 浏览器模式需要默认使用项目本地持久 profile，以便复用 WoS/Clarivate/机构认证状态；profile 目录必须加入 `.gitignore`，不得提交 cookie、localStorage 或浏览器缓存。所有浏览器错误写入审计前必须脱敏，只保留 URL 的域名和路径，不保存 query、邮箱、sid、loginId 等参数。
17. 当 Playwright 进入 Clarivate 登录页时，允许使用仅存在于当前进程环境变量中的 `CLARIVATE_EMAIL` 和 `CLARIVATE_PASSWORD` 自动登录。账号密码不得写入文件、日志、审计或提交；若页面要求改密码、验证码或学校统一认证，应停止自动化并提示需要用户人工完成。
18. 邮箱抓取阶段必须区分 WoS Citation Alert 和 Clarivate 账户通知邮件。`password reset`、`password changed` 等账户邮件即使来自 Web of Science/Clarivate，也不能占用 `max_emails` 的 Citation Alert 名额；抓取审计需要记录跳过的非 Alert 邮件数量。
19. WoS 完整 AlertSummary 的真实验证以用户校园网/学校 VPN 环境为准。用户可以手动运行前端或 CLI 测试抓取与全文下载，Agent 后续只读取本地结果文件反馈问题：优先检查 `data/processed/fetch_audit.json`、`data/processed/fetched_papers.json` 和最新 `data/outputs/<timestamp>/results.json` / `weekly_report.md`。调试阶段默认开启“只验证抓取和全文下载，不调用 LLM”，避免不必要的模型 API 调用。
20. 浏览器模式遇到 Clarivate/WoS/机构登录页时，需要支持用户在弹出的 Playwright Chromium 中手动完成登录并等待返回结果页。等待时长应在前端和 CLI 可配置，并写入抓取审计；默认 0 秒以避免无人值守运行被长时间阻塞。WoS gateway 跳转过程中出现短暂 `net::ERR_ABORTED` 或 frame detached 时，不应立即判定失败，应继续等待当前页面并检查是否已进入记录页或登录页。
21. 前端一键周报运行时必须展示阶段性状态，至少包含邮箱抓取、逐封邮件解析、WoS 完整页扩展、候选数量、全文下载/跳过 LLM、输出目录等信息。浏览器模式在同一次抓取任务内应复用同一个 Playwright Chromium 上下文，避免每个 Alert 链接重复弹出和关闭浏览器。
22. WoS 结果页可能使用虚拟列表或懒加载，DOM 中一次只保留少量可见记录。浏览器解析必须在滚动过程中持续收集标题链接，而不是滚动结束后只解析一次；同时需要识别英文/中文/图标式下一页控件，避免只抓取首屏或当前可见批次。
23. WoS summary 页的标题元素不一定是带 `full-record` 链接的 `<a>`。浏览器解析应同时识别 `data-ta`、`id`、`class` 中带 summary/record/title 标记的元素；若找不到附近 Full Record 链接，也应保留 title-only 候选，供后续按标题查找全文或补全元数据。
24. WoS 浏览器宽松解析必须过滤页面筛选项和控件文本，尤其是 `arrow_drop_down`、`javascript:void(0)`、期刊筛选下拉项等，避免把 venue/facet 项当作论文候选。
25. 当 WoS 下一页按钮无法通过 DOM 识别时，浏览器模式应支持 summary URL 页码兜底翻页：例如 `/wos/woscc/summary/<id>/relevance/1` 推进到 `/relevance/2`，直到没有新增记录或达到 `browser_max_pages`。
26. 全文下载必须有明确、可配置且偏短的超时，避免某个出版商、arXiv、Unpaywall 或 Semantic Scholar 请求长时间阻塞前端。一键周报前端需要提供“全文下载超时秒数”，默认 10 秒；CLI/分析函数也需要传递该参数。
27. WoS 分页控件不一定暴露稳定的 Next 文本。浏览器模式应识别当前页码并点击下一数字页码，例如当前页为 1 时点击页码 2；该策略应优先于宽泛的 Next 文本兜底。
28. WoS 官网页面不应作为唯一完整元数据来源。实际抓取中，WoS Alert 邮件和浏览器完整页可能只能稳定提供候选标题、WoS 链接和少量摘要；因此抓取阶段在 `--no-web` 未开启时，应在保留 WoS 候选的基础上，按 DOI 或标题调用公开元数据源补全 DOI、作者、期刊/会议和摘要。默认优先使用无需密钥的 OpenAlex、Crossref、Semantic Scholar；补全失败不得中断整批抓取，仍保留 WoS/邮件原始候选。
29. 公开元数据补全必须避免误匹配：按标题检索时只接受与原始标题高度相似的第一候选；外部返回的空字段不得覆盖邮件/WoS 已有字段；补全数量需要写入抓取审计，便于判断 WoS 抓取不完整时还有多少候选被成功补齐。
30. WoS summary 每页通常只显示固定数量记录（例如 50 条）。当 Alert 总数超过单页上限时，浏览器模式必须在抓取当前页后显式进入下一页；如果普通 Next/数字页码按钮不可识别，应从页面 HTML、锚点 href 或当前 URL 中解析 summary 路径并构造下一页 URL。抓取审计中若某封 71 条 Alert 只扩展出约 50 条以内，应优先判断为翻页失败。
31. WoS 浏览器模式在已收集到部分页面记录后，后续翻页或等待记录失败时不得丢弃已收集候选；应停止继续翻页并返回当前已收集记录，同时在日志/审计中保留错误，避免“第 1/2 页已抓到但最终扩展数为 0”的误判。
32. 对相似度筛选后进入 top-k 的论文，全文下载只走合法可控路径：优先 DOI/标题补全元数据，再尝试 publisher PDF 直链、OpenAlex 开放获取 URL、Unpaywall、Semantic Scholar openAccessPdf、arXiv；若 WoS/出版商链接不是 PDF，可尝试在用户当前校园网/学校 VPN/已登录机构权限下访问页面并识别 PDF 链接。无法通过开放获取或机构订阅访问的付费文献不得绕过付费墙，应标记为需要订阅/付费或手动上传 PDF，并在周报中列为候选但未深读。
33. 全文下载失败原因需要分类，至少区分未找到开放全文、需要订阅/付费、下载超时、下载结果不是 PDF、网络/HTTP 错误和需要手动上传，便于前端和周报给出可执行提示。
34. 支持手动 PDF 兜底目录：用户可将付费/订阅文献 PDF 放入本地目录；对进入 top-k 的论文，程序先按 DOI 和标题在该目录中匹配 PDF，匹配成功后复制到本次输出目录并作为 `manual_upload` 来源进入全文解析和深度解读。匹配不到时再走在线合法下载链路。
35. 全文查找必须有单篇总耗时预算，不能让多个开放获取源、出版商页和候选 PDF 串行放大超时时间导致前端长期卡住。默认单篇总预算应随 `full_text_timeout` 缩放，并限制候选 PDF 下载尝试数量；超出预算时返回明确的“全文下载超时”原因。
36. 无 DOI 时按标题查找全文候选必须进行标题相似度校验，OpenAlex、arXiv 等外部来源返回的第一候选标题不够相似时不得下载，避免误把同名/近似主题论文作为全文。
37. 抓取阶段应先收集并去重 WoS/邮件候选，再对去重后的唯一论文执行网页补全和公开元数据补全；同一次抓取内需要按 DOI/标题缓存补全结果，避免重复候选放大外部 API 请求和延迟。
38. 全文候选下载顺序应按来源优先级选择，而不是简单截断最先发现的 URL。手动 PDF 和直接 PDF 优先；开放获取 API 候选按来源去重并限制每源数量，避免某个来源返回多个坏链接挤掉后续可靠来源。
39. 抓取审计需要记录关键阶段耗时，至少包含邮箱扫描、邮件解析、WoS requests 扩展、WoS 浏览器扩展和元数据补全，便于判断真实运行慢在邮箱、WoS、外部 API 还是本地处理。
40. 去重后的公开元数据补全可使用有限并发以降低抓取延迟；并发数默认保持保守，外部 API 失败不得中断整批，输出顺序和去重行为必须保持稳定。
41. 手动 PDF 兜底目录在同一批分析中应尽量只遍历和采样一次，复用目录索引匹配多篇 top-k 候选，避免每篇论文重复 `rglob` 和重复读取 PDF metadata。
42. 批量分析结果需要对每篇论文记录阶段状态，至少区分已评分、输入缺失、低于阈值、未进入 top-k、全文获取失败、全文文本提取失败、LLM 失败、已完成和用户跳过 LLM。前端和报告应能基于该字段统计成功/失败分布。
43. Streamlit 周报/批量分析完成后需要展示审计摘要：候选数、去重数、元数据补全数、全文下载成功/失败数、LLM 完成/失败数和主要跳过/失败原因，避免用户只能查看原始 JSON 才能定位问题。
44. 高风险外部边界需要有本地回归测试覆盖：邮件无 HTML/异常编码/非 Alert、WoS 登录页/无记录页/翻页等待失败、全文 403/429/非 PDF/超时/文本为空、LLM 异常 JSON/空响应，以及无标题/无摘要等输入缺失场景。测试不得依赖真实邮箱、真实 WoS 页面或真实 LLM。

后续版本暂缓需求：

1. 历史抓取管理：将每次 `fetch-papers` 的结果追加到长期论文库，而不是只覆盖 `fetched_papers.json`。
2. 重扫能力：增加 `--reset-seen` 或类似参数，允许用户清空/忽略 `seen_emails.json` 后重新扫描历史 WoS 邮件。
3. 历史去重：跨运行周期按 DOI 或规范化标题去重，避免长期论文库重复保存同一篇论文。

## 固定开发流程

每次需求发生变化时，先更新本文件，再实现代码。

## 2026-05-04 补充：全文下载必须以 PDF 为成功标准

用户确认当前产品闭环的关键阻塞是 top-k 论文无法稳定下载 PDF。HTML 页面即使包含正文，也不能视为全文获取成功，因为经常缺少图表、实验结果、公式排版和 PDF 原文上下文；验证码页或登录页 HTML 更不能进入深度解读。

后续实现必须遵守：

1. `download_full_text=True` 时，只有真实 PDF 文件或用户手动提供的 PDF 可以标记为 `full_text_status=downloaded` 并进入深度解读。
2. 出版商 HTML、验证码页、登录页、摘要页和非 PDF 响应必须标记为失败原因，不得作为 `publisher_html` 成功结果返回。
3. Elsevier/ScienceDirect 论文优先使用合法 API、Crossref TDM link、开放获取 PDF、机构网络/浏览器 profile 可访问的 PDF 链接；不得绕过验证码、登录或付费墙。
4. 深度解读必须基于 PDF 提取文本；如果 PDF 获取失败，则该论文保留为候选但不进入深度解读，并在报告中给出失败原因。

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
6. 达到阈值且开启 `--download-full-text` 时，对允许深读的候选先尝试下载和解析全文。
7. 达到阈值且未指定 `--skip-llm` 时逐篇调用 LLM。
8. 如果传入 `--top-k`，只有相似度最高的前 N 篇允许触发全文下载或 LLM；其他高于阈值但不在 top-k 的论文标记为“未进入 top-k”。
9. 如果同时传入 `--download-full-text --skip-llm`，只执行候选筛选、全文下载和 PDF 文本提取，不调用 LLM。
10. 调用统一 report writer 输出 JSON 与 Markdown。

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
## 2026-05-06 SPIS 文献求助全文获取

1. `download_full_text=True` 的默认全文获取路径改为：手动 PDF 匹配 -> SPIS 文献求助 -> 等待默认邮箱 PDF 附件。旧的出版商网页自动下载不再默认执行，只能作为显式 fallback。
2. SPIS 默认配置：
   - `FULL_TEXT_SOURCE=spis`
   - `SPIS_BASE_URL=https://spis.hnlat.com/`
   - `SPIS_WAIT_MINUTES=30`
   - `SPIS_POLL_INTERVAL_SECONDS=60`
3. SPIS 查询优先使用 DOI；没有 DOI 时使用标题。唯一命中可直接进入详情页；多命中时按标题相似度选择，阈值默认 0.82。
4. SPIS 提交流程使用有头浏览器表单：进入详情页，填写 `.env` 中默认邮箱，勾选服务条款，点击确认。首版不直接调用内部 API。
5. 邮件收取只匹配提交时间之后的新邮件 PDF 附件。匹配优先级：DOI 命中、标题关键词命中、提交时间之后唯一 PDF 附件兜底。
6. 只有真实 PDF 文件可以标记为 `full_text_status=downloaded` 并进入 PDF 文本提取和深度解读。已提交但未收到、未命中、提交失败等状态必须保留在报告中，不得退回摘要深读。
7. 控制台/前端进度应能看到 SPIS 搜索、进入详情、提交求助、等待邮件、发现候选邮件、保存 PDF、超时等关键阶段。

补充：SPIS 搜索结果卡片若出现“下载”按钮，应优先直接下载 PDF；只有搜索结果无下载入口或直接下载失败时，才进入“文献求助 -> 邮箱收 PDF”流程。SPIS 结果解析不能只依赖详情页链接，必须支持 `article` 卡片中的标题、来源、下载链接和文献求助按钮。

再次补充：SPIS 查询必须支持 DOI 与标题两级回退。DOI 搜不到时不能直接标记 `spis_not_found`，必须再用标题搜索；直接下载跳转期刊官网、触发人机验证、返回非 PDF 或超时时，也不能直接失败，必须继续尝试同一结果卡片的“文献求助”弹窗。

SPIS 直接下载必须有短超时和 `.part` 清理。若下载流长时间没有收到 PDF 字节，不能卡住整批任务；应放弃直接下载、删除临时文件，并进入文献求助回退。
