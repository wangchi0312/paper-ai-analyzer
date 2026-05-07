from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from paper_analyzer.agent import AcademicAgent, PendingAction
from paper_analyzer.agent.memory import AcademicMemory
from paper_analyzer.server.config import read_public_config, save_config
from paper_analyzer.server.jobs import JobManager
from paper_analyzer.utils.config import load_research_topic


UPLOAD_DIR = Path("data/library/uploads")


class ChatRequest(BaseModel):
    message: str


class ConfigRequest(BaseModel):
    email_address: str | None = None
    email_auth_code: str | None = None
    email_provider: str | None = None
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_temperature: str | None = None
    research_topic: str | None = None
    wos_use_browser: bool | None = None
    wos_max_emails: int | None = None
    wos_browser_max_pages: int | None = None


class JobRequest(BaseModel):
    action: dict[str, Any]


class InterestMemoryRequest(BaseModel):
    text: str
    memory_type: str = "positive_interest"
    evidence_source: str = "wos_feedback"
    weight: float = 0.9
    confidence: float = 0.85
    metadata: dict[str, Any] | None = None


class PaperMemoryRequest(BaseModel):
    text: str
    metadata: dict[str, Any] | None = None


def create_app() -> FastAPI:
    app = FastAPI(title="Academic Agent API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    memory = AcademicMemory()
    agent = AcademicAgent(memory=memory, research_topic=load_research_topic())
    jobs = JobManager(agent)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        data = read_public_config()
        data["memory"] = memory.stats()
        return data

    @app.post("/api/config")
    def post_config(payload: ConfigRequest) -> dict[str, Any]:
        data = save_config(payload.model_dump(exclude_none=True))
        data["memory"] = memory.stats()
        return data

    @app.get("/api/memory/stats")
    def memory_stats() -> dict[str, Any]:
        return memory.stats()

    @app.post("/api/memory/interest")
    def add_interest_memory(payload: InterestMemoryRequest) -> dict[str, Any]:
        item_id = memory.add_interest(
            text=payload.text,
            memory_type=payload.memory_type,
            evidence_source=payload.evidence_source,
            weight=payload.weight,
            confidence=payload.confidence,
            metadata=payload.metadata,
        )
        return {"memory_id": item_id, "memory": memory.stats()}

    @app.post("/api/memory/paper")
    def add_paper_memory(payload: PaperMemoryRequest) -> dict[str, Any]:
        item_id = memory.add_paper(text=payload.text, metadata=payload.metadata)
        return {"memory_id": item_id, "memory": memory.stats()}

    @app.post("/api/chat")
    def chat(payload: ChatRequest) -> dict[str, Any]:
        response = agent.handle_message(payload.message)
        return response.to_dict()

    @app.post("/api/upload")
    async def upload_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="只支持 PDF 文件")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target = UPLOAD_DIR / Path(file.filename).name
        content = await file.read()
        target.write_bytes(content)
        response = agent.handle_pdf_upload(str(target), write_memory=False)
        data = response.to_dict()
        data["uploaded_path"] = str(target)
        return data

    @app.post("/api/jobs")
    def start_job(payload: JobRequest) -> dict[str, Any]:
        action = PendingAction(**payload.action)
        job = jobs.start(action)
        return job.to_dict()

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, Any]:
        job = jobs.cancel(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        return job.to_dict()

    @app.get("/api/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return jobs.list()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="任务不存在")
        return job.to_dict()

    @app.get("/api/jobs/{job_id}/events")
    def job_events(job_id: str) -> StreamingResponse:
        if not jobs.get(job_id):
            raise HTTPException(status_code=404, detail="任务不存在")
        return StreamingResponse(jobs.events(job_id), media_type="text/event-stream")

    return app


app = create_app()
