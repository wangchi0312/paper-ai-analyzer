from __future__ import annotations

from pathlib import Path
from typing import Any

from paper_analyzer.agent.memory import AcademicMemory
from paper_analyzer.agent.state import AgentResponse, PendingAction
from paper_analyzer.agent.tools import ToolRegistry, build_default_registry, log_tool_result


CONFIRM_WORDS = {"确认", "执行", "开始", "同意", "可以", "yes", "y", "ok"}


class AcademicAgent:
    def __init__(
        self,
        memory: AcademicMemory | None = None,
        registry: ToolRegistry | None = None,
        provider: str | None = None,
        research_topic: str | None = None,
    ) -> None:
        self.memory = memory or AcademicMemory()
        self.registry = registry or build_default_registry(self.memory)
        self.provider = provider
        self.research_topic = research_topic

    def handle_message(self, message: str, pending_action: PendingAction | None = None) -> AgentResponse:
        text = message.strip()
        if pending_action and text.lower() in CONFIRM_WORDS:
            return self.execute(pending_action)
        if pending_action and _looks_like_rejection(text):
            return AgentResponse("好的，我已取消这次动作。你可以继续告诉我下一步想做什么。")

        intent = self._detect_intent(text)
        if intent == "screen_wos":
            action = PendingAction(
                tool_name="screen_wos_alert_tool",
                args={"max_emails": 20, "top_k": 10, "write_memory": False},
                summary="我将读取默认邮箱中的 WoS Alert，提取候选论文摘要并按你的研究兴趣给出推荐；不会下载 PDF，也不会写入长期记忆。",
            )
            return AgentResponse(f"{action.summary}\n\n回复“确认”后我再执行。", pending_action=action)
        if intent == "search_memory":
            query = _strip_memory_prefix(text)
            action = PendingAction(
                tool_name="search_memory_tool",
                args={"query": query, "collection": "all", "limit": 5},
                summary=f"我将检索本地论文库和兴趣记忆：{query}",
                requires_confirmation=False,
            )
            return self.execute(action)
        if intent == "update_memory":
            memory_text = _strip_memory_prefix(text)
            action = PendingAction(
                tool_name="update_memory_tool",
                args={
                    "text": memory_text,
                    "memory_type": _feedback_memory_type(text),
                    "evidence_source": "conversation",
                    "weight": 0.9,
                    "confidence": 0.85,
                },
                summary=f"我会把这条研究偏好写入长期兴趣记忆：{memory_text}",
            )
            return AgentResponse(f"{action.summary}\n\n回复“确认”后我再写入。", pending_action=action)
        if intent == "generate_report":
            action = PendingAction(
                tool_name="generate_report_tool",
                args={"title": "学术助手对话报告", "items": [{"title": "用户请求", "summary": text}]},
                summary="我将把当前请求整理成一份本地 Markdown 报告。",
            )
            return AgentResponse(f"{action.summary}\n\n回复“确认”后我再生成。", pending_action=action)

        return AgentResponse(
            "我可以作为学术助手与你协作：上传 PDF 后我能解读论文；你也可以说“帮我筛选 WoS 邮件”、"
            "“检索记忆中的 PINN 论文”、或“记住：我关注自适应激活函数”。关键动作我会先说明计划，再等你确认。"
        )

    def handle_pdf_upload(self, pdf_path: str, write_memory: bool = False) -> AgentResponse:
        path = Path(pdf_path)
        action = PendingAction(
            tool_name="analyze_pdf_tool",
            args={
                "pdf_path": str(path),
                "provider": self.provider,
                "research_topic": self.research_topic,
                "write_memory": write_memory,
            },
            summary=(
                f"我将解读你上传的 PDF：{path.name}。"
                + (" 解读完成后会把论文摘要和分析结论写入论文记忆。" if write_memory else " 本次不会写入长期记忆。")
            ),
        )
        return AgentResponse(f"{action.summary}\n\n回复“确认”后我再执行。", pending_action=action)

    def execute(self, action: PendingAction) -> AgentResponse:
        try:
            result = self.registry.get(action.tool_name).handler(**action.args)
            log_tool_result(result)
        except Exception as exc:
            return AgentResponse(f"执行失败：{exc}")
        if result.ok:
            return AgentResponse(_format_success(result), tool_result=result)
        return AgentResponse(f"{result.message}：{result.error or '未知错误'}", tool_result=result)

    def _detect_intent(self, text: str) -> str:
        lowered = text.lower()
        if any(key in text for key in ("筛选", "WoS", "wos", "邮件", "Alert", "alert")) and any(
            key in text for key in ("文献", "论文", "邮件", "WoS", "wos", "Alert", "alert")
        ):
            return "screen_wos"
        if any(key in text for key in ("检索", "查找", "搜索", "记忆", "历史")):
            return "search_memory"
        if any(key in text for key in ("记住", "以后", "我关注", "我不关注", "不推荐", "很相关", "不相关")):
            return "update_memory"
        if any(key in text for key in ("报告", "总结", "整理成")):
            return "generate_report"
        return "chat"


def _looks_like_rejection(text: str) -> bool:
    return text.strip().lower() in {"取消", "不要", "先不", "否", "no", "n"}


def _strip_memory_prefix(text: str) -> str:
    for prefix in ("记住：", "记住:", "检索：", "检索:", "搜索：", "搜索:"):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text.strip()


def _feedback_memory_type(text: str) -> str:
    if any(key in text for key in ("不关注", "不推荐", "不相关", "排除")):
        return "negative_interest"
    if any(key in text for key in ("方法", "模型", "算法")):
        return "method_preference"
    if any(key in text for key in ("写作", "表达", "报告")):
        return "writing_preference"
    if any(key in text for key in ("目标", "课题", "方向")):
        return "research_goal"
    return "positive_interest"


def _format_success(result) -> str:
    if result.tool_name == "screen_wos_alert_tool":
        recs = result.data.get("recommendations", [])
        lines = [result.message]
        for index, item in enumerate(recs[:10], start=1):
            doi = f" DOI: {item.get('doi')}" if item.get("doi") else ""
            lines.append(f"{index}. {item.get('title')}{doi}\n   推荐理由：{item.get('reason')}\n   {item.get('manual_pdf_advice')}")
        return "\n".join(lines)
    if result.tool_name == "search_memory_tool":
        rows = result.data.get("results", [])
        if not rows:
            return "没有找到相关记忆。"
        lines = [result.message]
        for index, row in enumerate(rows, start=1):
            lines.append(f"{index}. [{row.get('collection')}] {str(row.get('text', ''))[:220]}")
        return "\n".join(lines)
    if result.tool_name == "analyze_pdf_tool":
        output_dir = result.data.get("output_dir")
        return f"{result.message}\n输出目录：{output_dir}"
    return result.message
