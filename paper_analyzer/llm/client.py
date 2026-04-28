from paper_analyzer.utils.config import LLMConfig


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("缺少 openai 包，请先安装 requirements.txt。") from exc

        self.config = config
        self.client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    def complete(self, prompt: str) -> str:
        chunks = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": "你是严谨的学术论文分析助手。"},
                {"role": "user", "content": prompt},
            ],
            temperature=self.config.temperature,
            stream=True,
        )
        parts: list[str] = []
        for chunk in chunks:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                parts.append(content)
        return "".join(parts)
