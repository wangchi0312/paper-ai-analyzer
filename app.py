from pathlib import Path
import time

import streamlit as st

from pipeline.analyze_papers import analyze_pdf
from paper_analyzer.utils.config import load_research_topic


INCOMING_DIR = Path("data/incoming_pdfs")
DEFAULT_PROFILE = Path("data/processed/profile.npy")


def main() -> None:
    st.set_page_config(page_title="文献追踪助手", layout="wide")

    st.title("文献追踪助手")

    with st.sidebar:
        st.header("参数")
        profile_path = st.text_input("兴趣向量", value=str(DEFAULT_PROFILE))
        threshold = st.slider("相关性阈值", min_value=0.0, max_value=1.0, value=0.5, step=0.05)
        provider = st.selectbox("LLM provider", ["deepseek", "siliconflow", "modelscope"], index=0)
        skip_llm = st.checkbox("只计算相似度", value=False)
        research_topic = st.text_input("研究主题", value=load_research_topic())
        max_chars = st.number_input("Embedding 文本长度", min_value=500, max_value=20000, value=4000, step=500)
        llm_max_chars = st.number_input("LLM 文本长度", min_value=1000, max_value=50000, value=12000, step=1000)

    uploaded_file = st.file_uploader("上传 PDF", type=["pdf"])

    if not DEFAULT_PROFILE.exists():
        st.warning("尚未找到默认兴趣向量，请先运行 build_profile.py。")

    if uploaded_file is None:
        return

    saved_pdf = _save_uploaded_pdf(uploaded_file)
    st.info(f"已保存：{saved_pdf}")

    if st.button("开始分析", type="primary"):
        with st.spinner("正在分析 PDF..."):
            try:
                output_dir = analyze_pdf(
                    pdf_path=str(saved_pdf),
                    profile_path=profile_path,
                    threshold=threshold,
                    provider=provider,
                    max_chars=int(max_chars),
                    llm_max_chars=int(llm_max_chars),
                    skip_llm=skip_llm,
                    research_topic=research_topic or None,
                )
            except Exception as exc:
                _cleanup_pdf(saved_pdf)
                st.error(f"分析失败：{exc}")
                return

        st.success(f"分析完成：{output_dir}")
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
    report_path = output_dir / "report.md"
    results_path = output_dir / "results.json"

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("报告")
        if report_path.exists():
            st.markdown(report_path.read_text(encoding="utf-8"))
        else:
            st.warning("未找到 report.md")

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


if __name__ == "__main__":
    main()
