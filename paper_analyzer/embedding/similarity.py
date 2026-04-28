import numpy as np


def cosine_similarity(vec1, vec2) -> float:
    a = np.asarray(vec1, dtype=float)
    b = np.asarray(vec2, dtype=float)

    if a.shape != b.shape:
        raise ValueError(f"向量维度不一致：{a.shape} vs {b.shape}")

    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        return 0.0

    return float(np.dot(a, b) / denominator)
