from __future__ import annotations

import json
import queue
import threading
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from paper_analyzer.agent import AcademicAgent, PendingAction
from paper_analyzer.agent.runtime import format_tool_success
from paper_analyzer.agent.state import ToolResult, utc_now_iso
from paper_analyzer.agent.tools import log_tool_result


class JobCancelledError(RuntimeError):
    """Raised when a running job is cancelled by the user."""


@dataclass
class AgentJob:
    job_id: str
    action: dict[str, Any]
    status: str = "queued"
    logs: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobManager:
    def __init__(self, agent: AcademicAgent) -> None:
        self.agent = agent
        self._jobs: dict[str, AgentJob] = {}
        self._events: dict[str, queue.Queue[str]] = {}
        self._lock = threading.Lock()

    def start(self, action: PendingAction) -> AgentJob:
        job = AgentJob(job_id=uuid4().hex, action=action.to_dict())
        with self._lock:
            self._jobs[job.job_id] = job
            self._events[job.job_id] = queue.Queue()
        threading.Thread(target=self._run, args=(job.job_id,), daemon=True).start()
        return job

    def get(self, job_id: str) -> AgentJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.to_dict() for job in self._jobs.values()]

    def cancel(self, job_id: str) -> AgentJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in {"completed", "failed", "cancelled"}:
                return job
            job.cancel_requested = True
            job.updated_at = utc_now_iso()
        self._log(job_id, "已收到停止请求，正在尝试中断任务")
        self._emit(job_id, "status", {"status": "cancelling"})
        return self.get(job_id)

    def events(self, job_id: str):
        event_queue = self._events[job_id]
        job = self.get(job_id)
        if job:
            for line in job.logs:
                yield _sse("log", {"message": line})
        while True:
            try:
                message = event_queue.get(timeout=1.0)
            except queue.Empty:
                job = self.get(job_id)
                if job and job.status in {"completed", "failed", "cancelled"}:
                    yield _sse("done", job.to_dict())
                    break
                yield _sse("heartbeat", {"ok": True})
                continue
            yield message

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        self._set_status(job_id, "running")
        self._log(job_id, "任务已开始")
        try:
            action = PendingAction(**job.action)
            tool = self.agent.registry.get(action.tool_name)
            kwargs = dict(action.args)
            kwargs["progress_callback"] = lambda message: self._progress(job_id, message)
            result: ToolResult = tool.handler(**kwargs)
            log_tool_result(result)
            result_dict = result.to_dict()
            result_dict["display_message"] = (
                format_tool_success(result)
                if result.ok
                else f"{result.message}：{result.error or '未知错误'}"
            )
            self._finish(job_id, result_dict, "completed" if result.ok else "failed", result.error)
            self._log(job_id, "任务已完成" if result.ok else f"任务失败：{result.error or result.message}")
            self._emit(job_id, "result", result_dict)
        except JobCancelledError:
            result_dict = {
                "tool_name": job.action.get("tool_name", ""),
                "ok": False,
                "message": "任务已取消",
                "data": {},
                "error": "用户已取消",
                "display_message": "这次任务已按你的要求停止。",
            }
            self._finish(job_id, result_dict, "cancelled", "用户已取消")
            self._log(job_id, "任务已取消")
            self._emit(job_id, "result", result_dict)
        except Exception as exc:
            self._finish(job_id, None, "failed", str(exc))
            self._log(job_id, f"任务异常：{exc}")

    def _finish(
        self,
        job_id: str,
        result: dict[str, Any] | None,
        status: str,
        error: str | None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.result = result
            job.status = status
            job.error = error
            job.updated_at = utc_now_iso()

    def _set_status(self, job_id: str, status: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            job.updated_at = utc_now_iso()
        self._emit(job_id, "status", {"status": status})

    def _log(self, job_id: str, message: str) -> None:
        line = f"{utc_now_iso()} {message}"
        with self._lock:
            job = self._jobs[job_id]
            job.logs.append(line)
            job.updated_at = utc_now_iso()
        self._emit(job_id, "log", {"message": line})

    def _progress(self, job_id: str, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.cancel_requested:
                raise JobCancelledError()
        self._log(job_id, message)

    def _emit(self, job_id: str, event: str, data: dict[str, Any]) -> None:
        event_queue = self._events.get(job_id)
        if event_queue is not None:
            event_queue.put(_sse(event, data))


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
