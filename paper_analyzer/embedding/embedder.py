from typing import Union

import numpy as np


class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("缺少 sentence-transformers，请先安装 requirements.txt。") from exc

        try:
            self.model = SentenceTransformer(model_name, local_files_only=True)
        except Exception:
            try:
                self.model = SentenceTransformer(model_name)
            except Exception as exc:
                raise RuntimeError(
                    "加载 embedding 模型失败。首次运行需要联网下载模型；"
                    "如果模型已经下载，请检查 Hugging Face 缓存是否可访问。"
                ) from exc

    def encode(self, texts: Union[str, list[str]]) -> np.ndarray:
        single = isinstance(texts, str)
        if single:
            texts = [texts]
        result = self.model.encode(texts, convert_to_numpy=True)
        if single:
            return result[0]
        return result
