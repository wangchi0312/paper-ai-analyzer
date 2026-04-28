from paper_analyzer.llm.analyzer import _parse_json_object


def test_parse_json_object_pure_json():
    raw = '{"first_author": "Zhang San", "venue": "NeurIPS"}'
    result = _parse_json_object(raw)
    assert result["first_author"] == "Zhang San"
    assert result["venue"] == "NeurIPS"


def test_parse_json_object_with_surrounding_text():
    raw = '这是一些文字 {"first_author": "Li Si"} 更多文字'
    result = _parse_json_object(raw)
    assert result["first_author"] == "Li Si"


def test_parse_json_object_from_markdown_code_block():
    raw = '```json\n{"first_author": "Wang Wu"}\n```'
    result = _parse_json_object(raw)
    assert result["first_author"] == "Wang Wu"


def test_parse_json_object_nested_braces():
    raw = '{"outer": {"inner": "value"}, "key": "val"}'
    result = _parse_json_object(raw)
    assert result["outer"]["inner"] == "value"
    assert result["key"] == "val"


def test_parse_json_object_no_json_raises():
    import pytest

    with pytest.raises(ValueError, match="LLM 未返回有效 JSON"):
        _parse_json_object("没有 JSON 内容")


def test_parse_json_object_multiple_json_blocks_picks_first():
    raw = '{"first": 1} some text {"second": 2}'
    result = _parse_json_object(raw)
    assert result["first"] == 1
