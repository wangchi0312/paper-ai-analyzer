from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from paper_analyzer.agent.state import utc_now_iso


DEFAULT_MEMORY_DIR = "data/memory"


@dataclass
class MemoryItem:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    item_id: str | None = None

    def stable_id(self, namespace: str) -> str:
        if self.item_id:
            return self.item_id
        raw = f"{namespace}:{self.text}:{json.dumps(self.metadata, ensure_ascii=False, sort_keys=True)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class AcademicMemory:
    """Two-layer academic memory backed by Chroma when available.

    The JSON fallback keeps the local app usable before Chroma is installed. It
    is deliberately simple and transparent; production semantic retrieval should
    use Chroma.
    """

    def __init__(self, persist_dir: str = DEFAULT_MEMORY_DIR) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir = self.persist_dir / "chroma"
        self._client = None
        self._paper_collection = None
        self._interest_collection = None
        self._json_path = self.persist_dir / "memory_fallback.json"
        self.backend = "json"
        self._init_chroma()

    @property
    def is_chroma_enabled(self) -> bool:
        return self.backend == "chroma"

    def add_paper(self, text: str, metadata: dict[str, Any] | None = None) -> str:
        metadata = _clean_metadata(metadata or {})
        metadata.setdefault("created_at", utc_now_iso())
        item = MemoryItem(text=text, metadata=metadata)
        return self._add("paper_corpus", item)

    def add_interest(
        self,
        text: str,
        memory_type: str = "topic_preference",
        evidence_source: str = "conversation",
        weight: float = 0.5,
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        meta = _clean_metadata(metadata or {})
        meta.update(
            {
                "memory_type": memory_type,
                "evidence_source": evidence_source,
                "weight": float(weight),
                "confidence": float(confidence),
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            }
        )
        item = MemoryItem(text=text, metadata=meta)
        return self._add("interest_memory", item)

    def search(self, query: str, collection: str = "all", limit: int = 5) -> list[dict[str, Any]]:
        if self.backend == "chroma":
            return self._search_chroma(query, collection=collection, limit=limit)
        return self._search_json(query, collection=collection, limit=limit)

    def stats(self) -> dict[str, Any]:
        if self.backend == "chroma":
            return {
                "backend": self.backend,
                "paper_corpus": self._paper_collection.count(),
                "interest_memory": self._interest_collection.count(),
            }
        data = self._load_json()
        return {
            "backend": self.backend,
            "paper_corpus": len(data.get("paper_corpus", [])),
            "interest_memory": len(data.get("interest_memory", [])),
        }

    def _init_chroma(self) -> None:
        try:
            import chromadb
        except Exception:
            return
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.chroma_dir))
        self._paper_collection = self._client.get_or_create_collection("paper_corpus")
        self._interest_collection = self._client.get_or_create_collection("interest_memory")
        self.backend = "chroma"

    def _collection(self, name: str):
        if name == "paper_corpus":
            return self._paper_collection
        if name == "interest_memory":
            return self._interest_collection
        raise ValueError(f"Unknown memory collection: {name}")

    def _add(self, collection: str, item: MemoryItem) -> str:
        item_id = item.stable_id(collection)
        if self.backend == "chroma":
            self._collection(collection).upsert(
                ids=[item_id],
                documents=[item.text],
                metadatas=[item.metadata],
            )
        else:
            data = self._load_json()
            rows = data.setdefault(collection, [])
            rows[:] = [row for row in rows if row.get("id") != item_id]
            rows.append({"id": item_id, **asdict(item)})
            self._save_json(data)
        return item_id

    def _search_chroma(self, query: str, collection: str, limit: int) -> list[dict[str, Any]]:
        collections = ["paper_corpus", "interest_memory"] if collection == "all" else [collection]
        results: list[dict[str, Any]] = []
        for collection_name in collections:
            response = self._collection(collection_name).query(query_texts=[query], n_results=max(1, limit))
            ids = response.get("ids", [[]])[0]
            docs = response.get("documents", [[]])[0]
            metas = response.get("metadatas", [[]])[0]
            distances = response.get("distances", [[]])[0] if response.get("distances") else [None] * len(ids)
            for item_id, doc, meta, distance in zip(ids, docs, metas, distances):
                results.append(
                    {
                        "id": item_id,
                        "collection": collection_name,
                        "text": doc,
                        "metadata": meta or {},
                        "distance": distance,
                    }
                )
        return results[:limit]

    def _search_json(self, query: str, collection: str, limit: int) -> list[dict[str, Any]]:
        data = self._load_json()
        query_terms = {term.lower() for term in query.split() if term.strip()}
        collections = ["paper_corpus", "interest_memory"] if collection == "all" else [collection]
        scored: list[tuple[int, dict[str, Any]]] = []
        for collection_name in collections:
            for row in data.get(collection_name, []):
                text = str(row.get("text", ""))
                haystack = text.lower()
                score = sum(1 for term in query_terms if term in haystack)
                if score or not query_terms:
                    scored.append(
                        (
                            score,
                            {
                                "id": row.get("id") or row.get("item_id"),
                                "collection": collection_name,
                                "text": text,
                                "metadata": row.get("metadata") or {},
                                "distance": None,
                            },
                        )
                    )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _score, row in scored[:limit]]

    def _load_json(self) -> dict[str, list[dict[str, Any]]]:
        if not self._json_path.exists():
            return {"paper_corpus": [], "interest_memory": []}
        return json.loads(self._json_path.read_text(encoding="utf-8"))

    def _save_json(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        self._json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            clean[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            clean[key] = value
        else:
            clean[key] = json.dumps(value, ensure_ascii=False)
    return clean
