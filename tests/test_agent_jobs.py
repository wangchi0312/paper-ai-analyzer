import time

from paper_analyzer.agent.memory import AcademicMemory
from paper_analyzer.agent.runtime import AcademicAgent
from paper_analyzer.agent.state import PendingAction, ToolResult
from paper_analyzer.agent.tools import AgentTool, ToolRegistry
from paper_analyzer.server.jobs import JobManager


def test_job_manager_runs_tool_and_records_logs(tmp_path):
    registry = ToolRegistry()

    def fake_tool(progress_callback=None):
        if progress_callback:
            progress_callback("step one")
        return ToolResult(tool_name="fake_tool", ok=True, message="done", data={"value": 1})

    registry.register(AgentTool("fake_tool", "fake", fake_tool))
    agent = AcademicAgent(memory=AcademicMemory(str(tmp_path / "memory")), registry=registry)
    manager = JobManager(agent)

    job = manager.start(PendingAction(tool_name="fake_tool", args={}, summary="run fake"))
    for _ in range(50):
        current = manager.get(job.job_id)
        if current and current.status == "completed":
            break
        time.sleep(0.02)

    current = manager.get(job.job_id)
    assert current is not None
    assert current.status == "completed"
    assert any("step one" in line for line in current.logs)
    assert current.result["message"] == "done"


def test_job_manager_can_cancel_running_job(tmp_path):
    registry = ToolRegistry()

    def fake_tool(progress_callback=None):
        for index in range(20):
            time.sleep(0.02)
            if progress_callback:
                progress_callback(f"step {index}")
        return ToolResult(tool_name="fake_tool", ok=True, message="done", data={})

    registry.register(AgentTool("fake_tool", "fake", fake_tool))
    agent = AcademicAgent(memory=AcademicMemory(str(tmp_path / "memory")), registry=registry)
    manager = JobManager(agent)

    job = manager.start(PendingAction(tool_name="fake_tool", args={}, summary="run fake"))
    time.sleep(0.05)
    manager.cancel(job.job_id)

    for _ in range(100):
        current = manager.get(job.job_id)
        if current and current.status == "cancelled":
            break
        time.sleep(0.02)

    current = manager.get(job.job_id)
    assert current is not None
    assert current.status == "cancelled"
    assert current.error == "用户已取消"
    assert current.result is not None
    assert current.result["message"] == "任务已取消"
