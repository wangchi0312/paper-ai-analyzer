from pathlib import Path
import time

import streamlit as st

from pipeline.analyze_papers import analyze_papers, analyze_pdf
from pipeline.fetch_papers import load_fetched_papers
from paper_analyzer.notification.feishu import send_feishu_text
from paper_analyzer.utils.config import load_research_topic


INCOMING_DIR = Path("data/incoming_pdfs")
DEFAULT_PROFILE = Path("data/processed/profile.npy")
DEFAULT_FETCHED = Path("data/processed/fetched_papers.json")


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

    pdf_tab, batch_tab = st.tabs(["单篇 PDF", "邮件批量"])
    with pdf_tab:
        _render_pdf_tab(params)
    with batch_tab:
        _render_batch_tab(params)


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


if __name__ == "__main__":
    main()
