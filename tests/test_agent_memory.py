from paper_analyzer.agent.memory import AcademicMemory


def test_memory_json_fallback_adds_and_searches_interest(tmp_path, monkeypatch):
    monkeypatch.setattr(AcademicMemory, "_init_chroma", lambda self: None)
    memory = AcademicMemory(str(tmp_path / "memory"))

    memory_id = memory.add_interest(
        "用户关注物理信息神经网络和自适应激活函数",
        memory_type="positive_interest",
        evidence_source="conversation",
        weight=0.9,
        confidence=0.8,
    )
    results = memory.search("物理信息神经网络", collection="interest_memory", limit=3)

    assert memory_id
    assert memory.stats()["backend"] == "json"
    assert memory.stats()["interest_memory"] == 1
    assert results[0]["metadata"]["memory_type"] == "positive_interest"


def test_memory_json_fallback_separates_paper_and_interest(tmp_path, monkeypatch):
    monkeypatch.setattr(AcademicMemory, "_init_chroma", lambda self: None)
    memory = AcademicMemory(str(tmp_path / "memory"))

    memory.add_paper("A paper about PINN", {"title": "PINN Paper"})
    memory.add_interest("用户不关注纯综述", memory_type="negative_interest")

    stats = memory.stats()

    assert stats["paper_corpus"] == 1
    assert stats["interest_memory"] == 1
