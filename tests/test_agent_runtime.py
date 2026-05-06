from paper_analyzer.agent.memory import AcademicMemory
from paper_analyzer.agent.runtime import AcademicAgent
from paper_analyzer.agent.state import ToolResult
from paper_analyzer.agent.tools import AgentTool, ToolRegistry


def test_agent_proposes_wos_screening_before_execution(tmp_path):
    agent = AcademicAgent(memory=AcademicMemory(str(tmp_path / "memory")))

    response = agent.handle_message("帮我筛选最近 WoS 邮件里的文献")

    assert response.pending_action is not None
    assert response.pending_action.tool_name == "screen_wos_alert_tool"
    assert "不会下载 PDF" in response.message


def test_default_registry_does_not_expose_auto_download_tool(tmp_path):
    agent = AcademicAgent(memory=AcademicMemory(str(tmp_path / "memory")))

    names = agent.registry.names()

    assert "analyze_pdf_tool" in names
    assert "screen_wos_alert_tool" in names
    assert all("download" not in name and "fulltext" not in name for name in names)


def test_agent_executes_confirmed_action_with_registry(tmp_path):
    registry = ToolRegistry()

    def fake_tool(**kwargs):
        return ToolResult(tool_name="update_memory_tool", ok=True, message="done", data=kwargs)

    registry.register(AgentTool("update_memory_tool", "fake", fake_tool))
    agent = AcademicAgent(memory=AcademicMemory(str(tmp_path / "memory")), registry=registry)
    response = agent.handle_message("记住：我关注 PINN 和自适应激活函数")

    executed = agent.handle_message("确认", pending_action=response.pending_action)

    assert executed.tool_result is not None
    assert executed.tool_result.ok is True
    assert "done" in executed.message


def test_agent_searches_memory_without_confirmation(tmp_path):
    memory = AcademicMemory(str(tmp_path / "memory"))
    memory.add_interest("我关注 PINN 求解偏微分方程", memory_type="topic_preference")
    agent = AcademicAgent(memory=memory)

    response = agent.handle_message("检索 PINN")

    assert response.pending_action is None
    assert response.tool_result is not None
    assert response.tool_result.ok is True
    assert "PINN" in response.message
