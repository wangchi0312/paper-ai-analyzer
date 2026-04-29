from contextlib import contextmanager
import os
from pathlib import Path
import time
import json

import streamlit as st

from pipeline.analyze_papers import analyze_papers, analyze_pdf
from pipeline.fetch_papers import fetch_papers, load_fetched_papers
from paper_analyzer.notification.feishu import send_feishu_text
from paper_analyzer.utils.config import load_research_topic


INCOMING_DIR = Path("data/incoming_pdfs")
DEFAULT_PROFILE = Path("data/processed/profile.npy")
DEFAULT_FETCHED = Path("data/processed/fetched_papers.json")
DEFAULT_AUDIT = Path("data/processed/fetch_audit.json")
PROVIDER_PREFIX = {
    "deepseek": "DEEPSEEK",
    "siliconflow": "SILICONFLOW",
    "modelscope": "MODELSCOPE",
}
DEFAULT_BASE_URL = {
    "deepseek": "https://api.deepseek.com",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "modelscope": "",
}


def main() -> None:
    st.set_page_config(page_title="文献追踪助手", layout="wide")

    st.title("文献追踪助手")

    with st.sidebar:
        st.header("参数")
        profile_path = st.text_input("兴趣向量", value=str(DEFAULT_PROFILE))
        output_root = st.text_input("输出目录", value="data/outputs")
        threshold = st.slider("相关性阈值", min_value=0.0, max_value=1.0, value=0.5, step=0.05)
        provider = st.selectbox("LLM provider", ["deepseek", "siliconflow", "modelscope"], index=0)
        skip_llm = st.checkbox("只计算相似度", value=False)
        research_topic = st.text_input("研究主题", value=load_research_topic())
        max_chars = st.number_input("Embedding 文本长度", min_value=500, max_value=20000, value=4000, step=500)
        llm_max_chars = st.number_input("LLM 文本长度", min_value=1000, max_value=50000, value=12000, step=1000)

    params = {
        "profile_path": profile_path,
        "threshold": threshold,
        "provider": provider,
        "max_chars": int(max_chars),
        "llm_max_chars": int(llm_max_chars),
        "output_root": output_root,
        "skip_llm": skip_llm,
        "research_topic": research_topic or None,
    }

    if not Path(profile_path).exists():
        st.warning("尚未找到兴趣向量，请先运行 build_profile。")

    weekly_tab, pdf_tab, batch_tab = st.tabs(["一键周报", "单篇 PDF", "邮件批量"])
    with weekly_tab:
        _render_weekly_tab(params)
    with pdf_tab:
        _render_pdf_tab(params)
    with batch_tab:
        _render_batch_tab(params)


def _render_weekly_tab(params: dict) -> None:
    st.subheader("一键生成文献周报")

    with st.form("weekly_report_form"):
        st.markdown("**模型配置**")
        provider = st.selectbox("模型提供商", ["deepseek", "siliconflow", "modelscope"], index=0)
        model_name = st.text_input("模型名", value=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
        base_url = st.text_input("Base URL", value=DEFAULT_BASE_URL[provider])
        api_key = st.text_input("API Key", type="password")

        st.markdown("**邮箱配置**")
        email_provider = st.selectbox("邮箱运营商", ["QQ邮箱"], index=0)
        email_address = st.text_input("邮箱地址")
        email_auth_code = st.text_input("邮箱授权码", type="password")

        st.markdown("**抓取与筛选**")
        col1, col2, col3 = st.columns(3)
        with col1:
            since_date = st.text_input("起始日期（可选）", placeholder="YYYY-MM-DD")
        with col2:
            max_emails = st.number_input("最多检查邮件数", min_value=1, max_value=500, value=50, step=1)
        with col3:
            top_k = st.number_input("深度解读 Top K", min_value=1, max_value=50, value=5, step=1)

        no_web = st.checkbox("跳过网页补全，只使用邮件内容", value=True)
        ignore_seen = st.checkbox("重新扫描已处理邮件", value=False, help="调试或重复生成周报时开启。开启后不会更新 seen_emails.json。")
        expand_alert_pages = st.checkbox("进入 WoS 完整结果页扩展候选", value=True, help="尝试打开邮件里的 View all 链接，获取完整 Alert 结果；若 WoS 需要登录会自动回退到邮件内容。")
        use_browser = st.checkbox("使用浏览器模式解析 WoS 完整页", value=False, help="requests 解析不到完整结果页时启用。需要安装 playwright 和 chromium。")
        browser_max_pages = st.number_input("浏览器最多翻页数", min_value=1, max_value=50, value=20, step=1, disabled=not use_browser)
        browser_manual_login_wait_seconds = st.number_input(
            "手动完成 WoS/机构登录等待秒数",
            min_value=0,
            max_value=600,
            value=0,
            step=30,
            disabled=not use_browser,
            help="如果浏览器停在 Clarivate 或学校认证页，可设置 180-300 秒，并在弹出的 Chromium 中手动完成登录。",
        )
        download_full_text = st.checkbox("下载全文后再深度解读", value=True)
        download_only = st.checkbox("只验证抓取和全文下载，不调用 LLM", value=False, help="用于调试候选抓取和 PDF 下载。开启后不需要填写 API Key，也不会调用模型。")
        unpaywall_email = st.text_input("Unpaywall 查询邮箱", value=email_address, help="用于查询开放获取全文，可填常用邮箱。")
        push_to_feishu = st.checkbox("生成后推送到飞书", value=False)
        feishu_webhook = ""
        feishu_secret = ""
        if push_to_feishu:
            feishu_webhook = st.text_input("飞书机器人 Webhook", type="password")
            feishu_secret = st.text_input("飞书签名密钥（可选）", type="password")

        submitted = st.form_submit_button("生成周报", type="primary")

    if not submitted:
        return

    if email_provider != "QQ邮箱":
        st.error("当前版本只支持 QQ 邮箱。")
        return
    if not download_only and (not api_key or not model_name or not base_url):
        st.error("请填写完整的模型配置。")
        return
    if download_only and not download_full_text:
        st.error("只验证抓取和全文下载时，需要勾选“下载全文后再深度解读”。")
        return
    if not email_address or not email_auth_code:
        st.error("请填写邮箱地址和邮箱授权码。")
        return
    if push_to_feishu and not feishu_webhook:
        st.error("请填写飞书机器人 Webhook。")
        return

    status_placeholder = st.empty()
    log_placeholder = st.empty()
    progress_messages: list[str] = []

    def report_progress(message: str) -> None:
        progress_messages.append(f"{time.strftime('%H:%M:%S')}  {message}")
        status_placeholder.info(message)
        log_placeholder.code("\n".join(progress_messages[-80:]))

    with st.spinner("正在抓取邮件、分析论文并生成周报..."):
        try:
            with _temporary_runtime_env(
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                email_address=email_address,
                email_auth_code=email_auth_code,
                research_topic=params["research_topic"],
            ):
                fetched = fetch_papers(
                    since_date=since_date or None,
                    max_emails=int(max_emails),
                    no_web=no_web,
                    output_path=str(DEFAULT_FETCHED),
                    audit_output_path=str(DEFAULT_AUDIT),
                    ignore_seen=ignore_seen,
                    expand_alert_pages=expand_alert_pages,
                    use_browser=use_browser,
                    browser_max_pages=int(browser_max_pages),
                    browser_manual_login_wait_seconds=int(browser_manual_login_wait_seconds),
                    progress_callback=report_progress,
                )
                if not fetched:
                    st.error("没有抓取到可分析的论文。请查看下方抓取审计，判断是没有扫到 WoS 邮件、邮件已处理，还是邮件解析失败。")
                    _show_fetch_audit(DEFAULT_AUDIT)
                    return
                report_progress(f"候选抓取完成，共 {len(fetched)} 篇；开始相似度筛选和全文处理")
                output_dir = analyze_papers(
                    papers=fetched,
                    profile_path=params["profile_path"],
                    threshold=params["threshold"],
                    provider=provider,
                    max_chars=params["max_chars"],
                    llm_max_chars=params["llm_max_chars"],
                    output_root=params["output_root"],
                    skip_llm=download_only,
                    research_topic=params["research_topic"],
                    top_k=int(top_k),
                    download_full_text=download_full_text,
                    unpaywall_email=unpaywall_email or email_address,
                    progress_callback=report_progress,
                )
            if push_to_feishu:
                report_progress("开始推送飞书")
                send_feishu_text(
                    webhook_url=feishu_webhook,
                    text=(output_dir / "weekly_report.md").read_text(encoding="utf-8"),
                    secret=feishu_secret or None,
                )
        except Exception as exc:
            report_progress(f"任务失败：{exc}")
            st.error(f"周报生成失败：{exc}")
            if DEFAULT_AUDIT.exists():
                _show_fetch_audit(DEFAULT_AUDIT)
            return

    report_progress("任务完成")
    st.success(f"周报生成完成：{output_dir}")
    if push_to_feishu:
        st.success("已推送到飞书。")
    _show_fetch_audit(DEFAULT_AUDIT)
    _show_result(output_dir)


def _render_pdf_tab(params: dict) -> None:
    uploaded_file = st.file_uploader("上传 PDF", type=["pdf"])

    if uploaded_file is None:
        return

    saved_pdf = _save_uploaded_pdf(uploaded_file)
    st.info(f"已保存：{saved_pdf}")

    if st.button("开始分析", type="primary"):
        with st.spinner("正在分析 PDF..."):
            try:
                output_dir = analyze_pdf(
                    pdf_path=str(saved_pdf),
                    profile_path=params["profile_path"],
                    threshold=params["threshold"],
                    provider=params["provider"],
                    max_chars=params["max_chars"],
                    llm_max_chars=params["llm_max_chars"],
                    output_root=params["output_root"],
                    skip_llm=params["skip_llm"],
                    research_topic=params["research_topic"],
                )
            except Exception as exc:
                _cleanup_pdf(saved_pdf)
                st.error(f"分析失败：{exc}")
                return

        st.success(f"分析完成：{output_dir}")
        _show_result(output_dir)


def _render_batch_tab(params: dict) -> None:
    fetched_path = st.text_input("抓取结果", value=str(DEFAULT_FETCHED))
    top_k_enabled = st.checkbox("限制 LLM 分析篇数", value=True)
    top_k_value = st.number_input("Top K", min_value=1, max_value=100, value=5, step=1, disabled=not top_k_enabled)
    top_k = int(top_k_value) if top_k_enabled else None
    download_full_text = st.checkbox("下载全文后再深度解读", value=False)
    unpaywall_email = st.text_input("Unpaywall 查询邮箱（可选）")
    push_to_feishu = st.checkbox("生成后推送到飞书", value=False)
    feishu_webhook = ""
    feishu_secret = ""
    if push_to_feishu:
        feishu_webhook = st.text_input("飞书机器人 Webhook", type="password")
        feishu_secret = st.text_input("飞书签名密钥（可选）", type="password")

    try:
        fetched_papers = load_fetched_papers(fetched_path)
    except FileNotFoundError:
        st.warning("尚未找到抓取结果，请先运行 fetch-papers。")
        return
    except Exception as exc:
        st.error(f"读取抓取结果失败：{exc}")
        return

    st.metric("待分析论文", len(fetched_papers))
    preview = [
        {
            "标题": paper.title,
            "期刊": paper.venue or "",
            "DOI": paper.doi or "",
        }
        for paper in fetched_papers[:10]
    ]
    if preview:
        st.dataframe(preview, hide_index=True, use_container_width=True)

    if st.button("开始批量分析", type="primary"):
        with st.spinner("正在批量分析..."):
            try:
                output_dir = analyze_papers(
                    papers=fetched_papers,
                    profile_path=params["profile_path"],
                    threshold=params["threshold"],
                    provider=params["provider"],
                    max_chars=params["max_chars"],
                    llm_max_chars=params["llm_max_chars"],
                    output_root=params["output_root"],
                    skip_llm=params["skip_llm"],
                    research_topic=params["research_topic"],
                    top_k=top_k,
                    download_full_text=download_full_text,
                    unpaywall_email=unpaywall_email or None,
                )
            except Exception as exc:
                st.error(f"批量分析失败：{exc}")
                return

        st.success(f"批量分析完成：{output_dir}")
        if push_to_feishu:
            try:
                weekly_report_path = output_dir / "weekly_report.md"
                send_feishu_text(
                    webhook_url=feishu_webhook,
                    text=weekly_report_path.read_text(encoding="utf-8"),
                    secret=feishu_secret or None,
                )
                st.success("已推送到飞书。")
            except Exception as exc:
                st.error(f"飞书推送失败：{exc}")
        _show_result(output_dir)


def _save_uploaded_pdf(uploaded_file) -> Path:
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_name = Path(uploaded_file.name).name
    target = INCOMING_DIR / f"{timestamp}_{safe_name}"
    target.write_bytes(uploaded_file.getbuffer())
    return target


def _cleanup_pdf(pdf_path: Path) -> None:
    try:
        if pdf_path.exists():
            pdf_path.unlink()
    except OSError:
        pass


def _show_result(output_dir: Path) -> None:
    weekly_report_path = output_dir / "weekly_report.md"
    report_path = output_dir / "report.md"
    results_path = output_dir / "results.json"

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("周报")
        if weekly_report_path.exists():
            st.markdown(weekly_report_path.read_text(encoding="utf-8"))
        elif report_path.exists():
            st.markdown(report_path.read_text(encoding="utf-8"))
        else:
            st.warning("未找到报告文件")

    with col2:
        st.subheader("输出文件")
        st.code(str(output_dir))
        if results_path.exists():
            st.download_button(
                label="下载 results.json",
                data=results_path.read_text(encoding="utf-8"),
                file_name="results.json",
                mime="application/json",
            )
        if report_path.exists():
            st.download_button(
                label="下载 report.md",
                data=report_path.read_text(encoding="utf-8"),
                file_name="report.md",
                mime="text/markdown",
            )
        if weekly_report_path.exists():
            st.download_button(
                label="下载 weekly_report.md",
                data=weekly_report_path.read_text(encoding="utf-8"),
                file_name="weekly_report.md",
                mime="text/markdown",
            )


def _show_fetch_audit(audit_path: Path) -> None:
    if not audit_path.exists():
        st.warning("未找到抓取审计文件。")
        return
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except Exception as exc:
        st.warning(f"读取抓取审计失败：{exc}")
        return

    st.subheader("抓取审计")
    st.json(audit)
    if audit.get("matched_wos_email_count", 0) == 0:
        st.info("没有在扫描窗口内识别到 WoS/Clarivate 邮件。可以增大“最多检查邮件数”，或确认 WoS Alert 邮件是否在收件箱。")
    elif audit.get("email_count", 0) == 0 and audit.get("skipped_seen_email_count", 0) > 0:
        st.info("识别到了 WoS 邮件，但都被 seen_emails.json 过滤。请勾选“重新扫描已处理邮件”。")
    elif audit.get("parsed_paper_count", 0) == 0:
        st.info("已抓取 WoS 邮件 HTML，但没有解析出论文记录。可能是 WoS 邮件模板变化，需要更新解析器。")


@contextmanager
def _temporary_runtime_env(
    provider: str,
    api_key: str,
    base_url: str,
    model_name: str,
    email_address: str,
    email_auth_code: str,
    research_topic: str | None,
):
    prefix = PROVIDER_PREFIX[provider]
    updates = {
        "LLM_PROVIDER": provider,
        f"{prefix}_API_KEY": api_key,
        f"{prefix}_BASE_URL": base_url,
        f"{prefix}_MODEL": model_name,
        "QQ_EMAIL": email_address,
        "QQ_EMAIL_AUTH_CODE": email_auth_code,
    }
    if research_topic:
        updates["RESEARCH_TOPIC"] = research_topic

    old_values = {key: os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()
