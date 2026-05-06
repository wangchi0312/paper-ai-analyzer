from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class PendingAction:
    tool_name: str
    args: dict[str, Any]
    summary: str
    requires_confirmation: bool = True
    action_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolResult:
    tool_name: str
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str = field(default_factory=utc_now_iso)
    wrote_memory: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentResponse:
    message: str
    pending_action: PendingAction | None = None
    tool_result: ToolResult | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.pending_action is None:
            data["pending_action"] = None
        if self.tool_result is None:
            data["tool_result"] = None
        return data
