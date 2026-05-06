from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import streamlit as st

from paper_analyzer.agent import AcademicAgent, PendingAction
from paper_analyzer.agent.memory import AcademicMemory
from paper_analyzer.utils.config import load_research_topic


UPLOAD_DIR = Path("data/library/uploads")
DEFAULT_MEMORY_DIR = Path("data/memory")


def main() -> None:
    st.set_page_config(page_title="学术助手", layout="wide")
    st.title("学术助手")

    agent = _get_agent()
    _render_sidebar(agent)
    _render_upload_area(agent)
    _render_chat(agent)


def _get_agent() -> AcademicAgent:
    if "memory" not in st.session_state:
        st.session_state.memory = AcademicMemory(str(DEFAULT_MEMORY_DIR))
    if "agent" not in st.session_state:
        st.session_state.agent = AcademicAgent(
            memory=st.session_state.memory,
            research_topic=load_research_topic(),
        )
    return st.session_state.agent


def _render_sidebar(agent: AcademicAgent) -> None:
    with st.sidebar:
        st.header("本地 Agent")
        stats = agent.memory.stats()
        st.caption(f"记忆后端：{stats['backend']}")
        col1, col2 = st.columns(2)
        col1.metric("论文记忆", stats["paper_corpus"])
        col2.metric("兴趣记忆", stats["interest_memory"])
        st.divider()
        st.subheader("工具")
        for name in agent.registry.names():
            st.write(f"- `{name}`")
        st.caption("自动下载 PDF 已退出默认主流程。WoS 工具只做候选筛选和下载建议。")


def _render_upload_area(agent: AcademicAgent) -> None:
    uploaded = st.file_uploader("上传一篇 PDF，Agent 会先提出解读计划", type=["pdf"], accept_multiple_files=False)
    write_memory = st.checkbox("解读完成后请求写入论文记忆", value=False)
    if uploaded is None:
        return

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = UPLOAD_DIR / uploaded.name
    if not pdf_path.exists() or pdf_path.stat().st_size != uploaded.size:
        pdf_path.write_bytes(uploaded.getbuffer())

    if st.button("让 Agent 处理这篇 PDF", type="primary"):
        response = agent.handle_pdf_upload(str(pdf_path), write_memory=write_memory)
        _append_message("assistant", response.message)
        if response.pending_action:
            st.session_state.pending_action = response.pending_action.to_dict()
        st.rerun()


def _render_chat(agent: AcademicAgent) -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "你好，我是你的本地学术助手。你可以上传 PDF 让我解读，也可以让我筛选 WoS 邮件、检索记忆或记录研究偏好。",
            }
        ]

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    pending = _load_pending_action()
    if pending:
        with st.container(border=True):
            st.markdown(f"**待确认动作**：`{pending.tool_name}`")
            st.write(pending.summary)
            col1, col2 = st.columns(2)
            if col1.button("确认执行", type="primary"):
                response = agent.execute(pending)
                _append_message("assistant", response.message)
                st.session_state.pending_action = None
                st.rerun()
            if col2.button("取消"):
                _append_message("assistant", "好的，我已取消这次动作。")
                st.session_state.pending_action = None
                st.rerun()

    user_text = st.chat_input("和学术助手对话")
    if not user_text:
        return
    _append_message("user", user_text)
    response = agent.handle_message(user_text, pending_action=_load_pending_action())
    _append_message("assistant", response.message)
    if response.pending_action:
        st.session_state.pending_action = response.pending_action.to_dict()
    elif response.tool_result:
        st.session_state.pending_action = None
    st.rerun()


def _append_message(role: str, content: str) -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.messages.append({"role": role, "content": content})


def _load_pending_action() -> PendingAction | None:
    raw = st.session_state.get("pending_action")
    if not raw:
        return None
    if isinstance(raw, PendingAction):
        return raw
    return PendingAction(**raw)


def _analysis_summary(results_path: Path) -> dict[str, Any] | None:
    if not results_path.exists():
        return None
    results = json.loads(results_path.read_text(encoding="utf-8"))
    stage_counter = Counter(item.get("stage_status") or "unknown" for item in results)
    reason_counter = Counter(
        str(item.get("skipped_reason"))
        for item in results
        if item.get("skipped_reason")
    )
    fulltext_downloaded = sum(1 for item in results if item.get("full_text_status") == "downloaded")
    fulltext_failed = sum(
        1
        for item in results
        if item.get("stage_status") in {"fulltext_failed", "fulltext_text_failed"}
        or (item.get("full_text_status") and item.get("full_text_status") != "downloaded")
    )
    return {
        "total": len(results),
        "completed": stage_counter.get("completed", 0),
        "fulltext_downloaded": fulltext_downloaded,
        "fulltext_failed": fulltext_failed,
        "stage_counts": [{"阶段": key, "数量": value} for key, value in stage_counter.most_common()],
        "top_reasons": [{"原因": key, "数量": value} for key, value in reason_counter.most_common(8)],
    }


def _fetch_timing_summary(audit: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {
        "email_scan_seconds": "邮箱扫描",
        "email_parse_seconds": "邮件解析",
        "requests_expand_seconds": "WoS requests 扩展",
        "browser_expand_seconds": "WoS 浏览器扩展",
        "metadata_enrich_seconds": "元数据补全",
    }
    rows = []
    for key, label in labels.items():
        value = audit.get(key) or 0
        if value:
            rows.append({"阶段": label, "耗时秒": round(float(value), 2)})
    return rows


if __name__ == "__main__":
    main()
