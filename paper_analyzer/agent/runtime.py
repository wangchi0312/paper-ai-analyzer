from __future__ import annotations

import os
from pathlib import Path

from paper_analyzer.agent.memory import AcademicMemory
from paper_analyzer.agent.state import AgentResponse, PendingAction
from paper_analyzer.agent.tools import ToolRegistry, build_default_registry, log_tool_result


CONFIRM_WORDS = {"确认", "执行", "开始", "同意", "可以", "yes", "y", "ok"}
REJECT_WORDS = {"取消", "不要", "先不", "否", "no", "n"}


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
            return AgentResponse("好的，我先取消这次动作。我们可以换个方向继续。")

        intent = self._detect_intent(text)
        if intent == "screen_wos":
            return self._build_wos_response()
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
            return AgentResponse(f"{action.summary}\n\n点击确认后我再写入。", pending_action=action)
        if intent == "generate_report":
            action = PendingAction(
                tool_name="generate_report_tool",
                args={"title": "学术助手对话报告", "items": [{"title": "用户请求", "summary": text}]},
                summary="我将把当前请求整理成一份本地 Markdown 报告。",
            )
            return AgentResponse(f"{action.summary}\n\n点击确认后我再生成。", pending_action=action)

        return AgentResponse(
            "我可以和你一起做几类事：上传 PDF 后解读论文，筛选 WoS 邮件候选，检索历史论文和兴趣记忆，"
            "以及把阶段结果整理成报告。涉及批量读取、长期记忆或报告生成时，我会先说明计划再等你确认。"
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
                + (" 解读完成后会把论文摘要和分析结论写入论文记忆。" if write_memory else " 本次先只做解读，不写入长期记忆。")
            ),
        )
        return AgentResponse(
            f"{action.summary}\n\n点击确认后我会在后台执行，并持续输出工作日志。",
            pending_action=action,
        )

    def execute(self, action: PendingAction) -> AgentResponse:
        try:
            result = self.registry.get(action.tool_name).handler(**action.args)
            log_tool_result(result)
        except Exception as exc:
            return AgentResponse(f"执行失败：{exc}")
        if result.ok:
            return AgentResponse(format_tool_success(result), tool_result=result)
        return AgentResponse(f"{result.message}：{result.error or '未知错误'}", tool_result=result)

    def _build_wos_response(self) -> AgentResponse:
        wos_use_browser = _env_bool("WOS_USE_BROWSER", True)
        wos_max_emails = _env_int("WOS_MAX_EMAILS", 20)
        wos_browser_max_pages = _env_int("WOS_BROWSER_MAX_PAGES", 20)
        action = PendingAction(
            tool_name="screen_wos_alert_tool",
            args={
                "max_emails": wos_max_emails,
                "top_k": 10,
                "use_web": True,
                "use_browser": wos_use_browser,
                "browser_max_pages": wos_browser_max_pages,
                "write_memory": False,
            },
            summary=(
                f"我将读取默认邮箱中最近最多 {wos_max_emails} 封 WoS Alert 邮件，"
                f"{'并尝试进入 WoS 完整结果页补全摘要、DOI 和链接' if wos_use_browser else '只基于邮件内容做初筛'}。"
                f"{' 浏览器模式下最多处理 ' + str(wos_browser_max_pages) + ' 页结果。' if wos_use_browser else ''}"
                " 这次不会下载 PDF，也不会写入长期记忆。"
            ),
        )
        return AgentResponse(
            f"{action.summary}\n\n点击确认后我会在后台执行，并持续输出工作日志。",
            pending_action=action,
        )

    def _detect_intent(self, text: str) -> str:
        lower_text = text.lower()
        is_wos_message = (
            "wos" in lower_text
            or "alert" in lower_text
            or ("筛选" in text and "邮件" in text)
            or ("wos" in lower_text and "筛选" in text)
        )
        if is_wos_message and any(keyword in text for keyword in ("文献", "论文", "邮件", "筛选")):
            return "screen_wos"
        if any(keyword in text for keyword in ("检索", "查找", "搜索", "记忆", "历史")):
            return "search_memory"
        if any(keyword in text for keyword in ("记住", "以后", "我关注", "我不关注", "不推荐", "很相关", "不相关")):
            return "update_memory"
        if any(keyword in text for keyword in ("报告", "总结", "整理成")):
            return "generate_report"
        return "chat"


def format_tool_success(result) -> str:
    if result.tool_name == "screen_wos_alert_tool":
        recs = result.data.get("recommendations", [])
        lines = [result.message]
        for index, item in enumerate(recs[:10], start=1):
            doi = item.get("doi") or "未获取到 DOI"
            abstract = item.get("abstract") or "未获取到摘要，建议打开 WoS 记录确认。"
            lines.append(
                f"{index}. {item.get('title')}\n"
                f"   DOI：{doi}\n"
                f"   作者：{item.get('authors') or '未获取到'}\n"
                f"   期刊/会议：{item.get('venue') or '未获取到'}\n"
                f"   推荐理由：{item.get('reason')}\n"
                f"   摘要：{abstract[:500]}\n"
                f"   {item.get('manual_pdf_advice')}"
            )
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


def _looks_like_rejection(text: str) -> bool:
    return text.strip().lower() in REJECT_WORDS


def _strip_memory_prefix(text: str) -> str:
    for prefix in ("记住：", "记住:", "检索：", "检索:", "搜索：", "搜索:"):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text.strip()


def _feedback_memory_type(text: str) -> str:
    if any(keyword in text for keyword in ("不关注", "不推荐", "不相关", "排除")):
        return "negative_interest"
    if any(keyword in text for keyword in ("方法", "模型", "算法")):
        return "method_preference"
    if any(keyword in text for keyword in ("写作", "表达", "报告")):
        return "writing_preference"
    if any(keyword in text for keyword in ("目标", "课题", "方向")):
        return "research_goal"
    return "positive_interest"


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
