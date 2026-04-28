from paper_analyzer.llm.prompt import build_prompt


def test_prompt_requires_json_fields():
    prompt = build_prompt("paper text")
    assert "first_author" in prompt
    assert "paper_title" in prompt
    assert "core_problem" in prompt
    assert "core_hypotheses" in prompt
    assert "relevance_to_my_research" in prompt
