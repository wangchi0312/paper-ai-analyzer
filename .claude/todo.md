# V1 改进计划

## Agent 切换检查清单（切换前勾选）

- [ ] 需求若变更，先更新 `.claude/spec.md`
- [ ] 同步更新 `.claude/handoff.md`（当前目标/状态/阻塞）
- [ ] 在 `.claude/worklog.md` 追加本次变更记录
- [ ] 检查 `.claude/todo.md` 待办优先级是否最新
- [ ] 确认关键入口命令可用（至少一次最小链路）
- [ ] 记录本地环境前提（Python/依赖/OCR 组件）
- [ ] 列出最近改动文件与下一步第一动作
- [ ] 再执行 Agent 切换

## 已完成

- [x] OCR 添加语言参数（默认 chi_sim+eng）
- [x] build_profile 遇到单个 PDF 失败时跳过而非中断
- [x] 标题提取异常添加 logger.debug
- [x] 研究主题可配置（.env / CLI / Streamlit）

## 待完成

- [x] requirements.txt 版本锁定
- [x] 实际端到端验证（build_profile → analyze_papers 完整流程）
- [x] V2 最小 CLI 闭环（fetch-papers / analyze --source fetch / run 命令入口）
- [x] 批量 LLM 成本控制：`analyze --source fetch --top-k N`
- [x] 抓取审计：`fetch-papers` 输出本次邮件数、解析数、去重数等统计
- [x] 清理旧 smoke test 输出（当前未发现 `data/outputs/smoke/` 目录，无需处理）
- [x] Streamlit 暴露邮件批量分析入口，支持读取 `fetched_papers.json` 和 `top-k`
- [x] 生成 `weekly_report.md` 文献周报，作为前端优先展示结果
- [x] 飞书自定义机器人 webhook 推送基础能力
- [x] Streamlit 一键周报入口：前端填写 LLM/邮箱/飞书配置后串联运行
- [x] 全文获取基础层：publisher PDF 直链、Unpaywall、Semantic Scholar、arXiv 候选和 PDF 下载
- [x] 批量分析支持 `download_full_text=True`，只对 top-k 下载全文并基于全文深读

## 后续版本

- [ ] 历史抓取管理：将 `fetch-papers` 结果追加到长期论文库，而不是只覆盖本次 `fetched_papers.json`
- [ ] 重扫能力：增加 `--reset-seen` 或类似参数，允许重新扫描历史 WoS 邮件
- [ ] 跨运行周期去重：长期论文库按 DOI 或规范化标题去重
- [ ] 真实一键周报联调：使用真实 QQ 邮箱、LLM 和飞书 webhook 生成并推送一篇周报
- [ ] 校园网/学校 VPN 下真实测试出版社 PDF 下载命中率
- [ ] 自定义 Google Scholar 镜像 resolver（默认关闭，用户显式配置后启用）
