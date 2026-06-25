# ai_services/rag/rag_retriever.py
import json
import logging
from pathlib import Path

import faiss
import numpy as np

from ai_services.rag.rag_store import embed_chunks, INDEX_DIR

logger = logging.getLogger(__name__)
TOP_K_DEFAULT = 5


def _index_path(doc_id: str) -> Path:
    return INDEX_DIR / f"{doc_id}.faiss"

def _meta_path(doc_id: str) -> Path:
    return INDEX_DIR / f"{doc_id}.meta.json"


def retrieve(query: str, doc_id: str, top_k: int = TOP_K_DEFAULT) -> list[dict]:
    idx_path  = _index_path(doc_id)
    meta_path = _meta_path(doc_id)

    if not idx_path.exists():
        raise FileNotFoundError(f"No index found for doc_id='{doc_id}'.")

    index = faiss.read_index(str(idx_path))
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    chunks = meta["chunks"]

    q_vec = embed_chunks([query])
    faiss.normalize_L2(q_vec)

    k = min(top_k, len(chunks))
    scores, indices = index.search(q_vec, k)

    results = []
    for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), start=1):
        if idx == -1:
            continue
        results.append({"chunk": chunks[idx], "score": float(score), "rank": rank})
    return results


def retrieve_multi(queries: list[str], doc_id: str, top_k_per_query: int = 3, deduplicate: bool = True) -> list[dict]:
    seen:   set[str]   = set()
    merged: list[dict] = []

    for query in queries:
        try:
            hits = retrieve(query, doc_id, top_k=top_k_per_query)
        except FileNotFoundError:
            logger.warning(f"Index missing for doc_id={doc_id}")
            break
        for hit in hits:
            key = hit["chunk"][:80]
            if deduplicate and key in seen:
                continue
            seen.add(key)
            merged.append(hit)

    merged.sort(key=lambda x: x["score"], reverse=True)
    return merged


def build_rag_context(doc_id: str, analysis_result: dict, security_report: dict, max_chunks: int = 8) -> str:
    if not doc_id or not _index_path(doc_id).exists():
        return ""

    queries = [
        "clean code rules functions size complexity duplication style",
        "documentation docstrings comments maintainability readability",
        "SOLID principles architecture coupling cohesion design patterns modules",
        "testing unit tests pytest test coverage TDD",
        "OWASP security vulnerabilities authentication injection access control",
    ]

    if security_report.get("total_findings", 0) > 0:
        owasp_cats = security_report.get("owasp_distribution", {})
        for cat in list(owasp_cats.keys())[:3]:
            queries.append(f"OWASP {cat} prevention mitigation")

    hits = retrieve_multi(queries, doc_id=doc_id, top_k_per_query=2, deduplicate=True)
    top  = hits[:max_chunks]

    if not top:
        return ""

    lines = ["=== CODING STANDARDS CONTEXT (from official references) ==="]
    for i, hit in enumerate(top, 1):
        lines.append(f"[Ref {i}] {hit['chunk']}")
    lines.append("=== END STANDARDS ===")
    return "\n".join(lines)


def index_exists(doc_id: str) -> bool:
    return _index_path(doc_id).exists()