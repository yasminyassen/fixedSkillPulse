"""FAISS code index for requirement coverage."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

import faiss
import numpy as np

from ai_services.requirements.coverage.chunkers import CodeChunk
from ai_services.requirements.coverage.embeddings import embed_texts

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent / "rag" / "faiss_index" / "requirements"
BASE_DIR.mkdir(parents=True, exist_ok=True)


def _code_index_path(run_id: int) -> Path:
    return BASE_DIR / f"run_{run_id}_code.faiss"


def _meta_path(run_id: int, kind: str) -> Path:
    return BASE_DIR / f"run_{run_id}_{kind}.meta.json"


def build_code_index(run_id: int, chunks: list[CodeChunk]) -> tuple[faiss.IndexFlatIP, list[dict]]:
    texts = [c.embedding_text for c in chunks]
    vectors = embed_texts(texts)
    dim = vectors.shape[1] if len(vectors) else 768
    index = faiss.IndexFlatIP(dim)
    if len(vectors):
        index.add(vectors)
    faiss.write_index(index, str(_code_index_path(run_id)))
    meta = []
    for c in chunks:
        record = asdict(c)
        record["embedding_text"] = c.embedding_text
        meta.append(record)
    with open(_meta_path(run_id, "code"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    logger.info("[Coverage] Code index built: run=%s chunks=%s", run_id, len(chunks))
    return index, meta


def load_code_index(run_id: int) -> tuple[faiss.IndexFlatIP, list[dict]]:
    index = faiss.read_index(str(_code_index_path(run_id)))
    with open(_meta_path(run_id, "code"), encoding="utf-8") as f:
        meta = json.load(f)
    return index, meta


def search_index(index: faiss.IndexFlatIP, query_text: str, meta: list[dict], top_k: int) -> list[tuple[int, float, dict]]:
    if not meta:
        return []
    query_vec = embed_texts([query_text])
    k = min(top_k, len(meta))
    scores, indices = index.search(query_vec, k)
    results: list[tuple[int, float, dict]] = []
    raw_results: list[tuple[int, float, dict]] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(meta):
            continue
        raw_results.append((int(idx), float(score), meta[idx]))
    return sorted(raw_results, key=lambda item: (-item[1], item[0]))
