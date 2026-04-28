import json
import re

from paper_analyzer.data.schema import PaperAnalysis
from paper_analyzer.llm.client import OpenAICompatibleClient
from paper_analyzer.llm.prompt import build_prompt
from paper_analyzer.utils.config import load_llm_config


class Analyzer:
    def __init__(self, provider: str | None = None):
        config = load_llm_config(provider)
        self.client = OpenAICompatibleClient(config)

    def analyze(self, text: str, research_topic: str | None = None) -> PaperAnalysis:
        raw = self.client.complete(build_prompt(text, research_topic=research_topic))
        data = _parse_json_object(raw)
        return PaperAnalysis.from_dict(data)


def _parse_json_object(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code blocks first (```json ... ```)
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: find the first balanced { ... } with non-greedy match
    depth = 0
    start = None
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(raw[start : i + 1])
                except json.JSONDecodeError:
                    start = None
                    continue

    raise ValueError(f"LLM 未返回有效 JSON：{raw[:200]}")
