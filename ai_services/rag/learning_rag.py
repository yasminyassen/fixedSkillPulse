from __future__ import annotations

import json
import logging
import math
import os
import re
from importlib.util import find_spec
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
RESOURCES_PATH = BASE_DIR / "learning_resources.json"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

_embedding_model: Any | None = None
_faiss_index: Any | None = None
_indexed_resources: list[dict[str, Any]] | None = None
_indexed_texts: list[str] | None = None
_last_retriever = "keyword_fallback"


def is_faiss_available() -> bool:
    return find_spec("faiss") is not None


def is_sentence_transformers_available() -> bool:
    return find_spec("sentence_transformers") is not None


def _local_model_available(model_name: str) -> bool:
    candidate = Path(model_name)
    if candidate.exists():
        return True

    cache_name = model_name.replace("/", "_")
    hub_name = "models--" + model_name.replace("/", "--")
    roots = [
        os.environ.get("SENTENCE_TRANSFORMERS_HOME"),
        os.environ.get("HF_HOME"),
        os.environ.get("TRANSFORMERS_CACHE"),
        str(Path.home() / ".cache" / "torch" / "sentence_transformers"),
        str(Path.home() / ".cache" / "huggingface" / "hub"),
    ]
    for root in roots:
        if not root:
            continue
        root_path = Path(root)
        if (root_path / cache_name).exists() or (root_path / hub_name).exists():
            return True
    return False


def load_learning_resources() -> list[dict[str, Any]]:
    if not RESOURCES_PATH.exists():
        logger.warning("[Learning RAG] Resource file not found: %s", RESOURCES_PATH)
        return []

    try:
        with RESOURCES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("[Learning RAG] Failed to load resources: %s", exc)
        return []

    if not isinstance(data, list):
        logger.warning("[Learning RAG] Resource file must contain a JSON list")
        return []

    resources: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if not item.get("id") or not item.get("title") or not item.get("url"):
            continue
        resources.append(item)
    return resources


def build_resource_text(resource: dict[str, Any]) -> str:
    topics = resource.get("topics")
    if isinstance(topics, list):
        topic_text = ", ".join(str(topic) for topic in topics if topic)
    else:
        topic_text = str(topics or "")

    parts = [
        str(resource.get("title") or ""),
        str(resource.get("type") or ""),
        str(resource.get("provider") or ""),
        topic_text,
        str(resource.get("difficulty") or ""),
        str(resource.get("estimated_effort") or ""),
        str(resource.get("content") or ""),
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def get_embedding_model() -> Any | None:
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    # By default the API must not pause startup or requests to download a model.
    # Set LEARNING_RAG_ALLOW_MODEL_DOWNLOAD=1 to let sentence-transformers fetch
    # all-MiniLM-L6-v2; otherwise only an existing local cache/path is used.
    allow_download = str(os.environ.get("LEARNING_RAG_ALLOW_MODEL_DOWNLOAD") or "").lower() in {"1", "true", "yes"}
    model_name = os.environ.get("LEARNING_RAG_MODEL_PATH") or EMBEDDING_MODEL_NAME
    if not allow_download and not _local_model_available(model_name):
        logger.warning("[Learning RAG] Embedding model unavailable. Using keyword fallback.")
        return None

    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        logger.warning("[Learning RAG] sentence-transformers unavailable. Using keyword fallback.")
        logger.debug("[Learning RAG] sentence-transformers import error: %s", exc)
        return None

    try:
        if allow_download:
            _embedding_model = SentenceTransformer(model_name)
        else:
            old_transformers_offline = os.environ.get("TRANSFORMERS_OFFLINE")
            old_hf_offline = os.environ.get("HF_HUB_OFFLINE")
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_OFFLINE"] = "1"
            try:
                _embedding_model = SentenceTransformer(model_name)
            finally:
                if old_transformers_offline is None:
                    os.environ.pop("TRANSFORMERS_OFFLINE", None)
                else:
                    os.environ["TRANSFORMERS_OFFLINE"] = old_transformers_offline
                if old_hf_offline is None:
                    os.environ.pop("HF_HUB_OFFLINE", None)
                else:
                    os.environ["HF_HUB_OFFLINE"] = old_hf_offline
    except Exception as exc:
        logger.warning("[Learning RAG] Embedding model unavailable. Using keyword fallback.")
        logger.debug("[Learning RAG] Embedding model load error: %s", exc)
        return None
    return _embedding_model


def build_faiss_index(resources: list[dict[str, Any]]) -> Any | None:
    global _faiss_index, _indexed_resources, _indexed_texts

    if _faiss_index is not None and _indexed_resources == resources:
        return _faiss_index

    try:
        import faiss
    except Exception as exc:
        logger.warning("[Learning RAG] FAISS unavailable. Using keyword fallback.")
        logger.debug("[Learning RAG] FAISS import error: %s", exc)
        return None

    model = get_embedding_model()
    if model is None or not resources:
        return None

    texts = [build_resource_text(resource) for resource in resources]
    try:
        embeddings = model.encode(texts, show_progress_bar=False).astype("float32")
        faiss.normalize_L2(embeddings)
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
    except Exception as exc:
        logger.warning("[Learning RAG] Failed to build FAISS index: %s", exc)
        return None

    _faiss_index = index
    _indexed_resources = list(resources)
    _indexed_texts = texts
    return index


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_+#.-]+", (text or "").lower())


def _keyword_score(query_tokens: list[str], resource_text: str) -> float:
    if not query_tokens:
        return 0.0

    text_tokens = _tokens(resource_text)
    if not text_tokens:
        return 0.0

    query_counts = Counter(query_tokens)
    text_counts = Counter(text_tokens)
    overlap = sum(min(count, text_counts.get(token, 0)) for token, count in query_counts.items())
    coverage = overlap / max(1, len(query_tokens))
    density = overlap / math.sqrt(max(1, len(text_tokens)))
    return round(coverage + density, 6)


def _keyword_retrieve(query: str, resources: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for resource in resources:
        score = _keyword_score(query_tokens, build_resource_text(resource))
        if score > 0:
            ranked.append((score, resource))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            **resource,
            "score": float(score),
            "retriever": "keyword_fallback",
        }
        for score, resource in ranked[:top_k]
    ]


def retrieve_learning_resources(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    global _last_retriever

    resources = load_learning_resources()
    if not resources:
        _last_retriever = "keyword_fallback"
        return []

    top_k = max(1, min(int(top_k or 5), len(resources)))
    try:
        index = build_faiss_index(resources)
        model = get_embedding_model() if index is not None else None
    except Exception as exc:
        logger.warning("[Learning RAG] FAISS setup failed, falling back to keywords: %s", exc)
        index = None
        model = None

    if index is not None and model is not None:
        try:
            import faiss

            query_embedding = model.encode([query or ""], show_progress_bar=False).astype("float32")
            faiss.normalize_L2(query_embedding)
            scores, indices = index.search(query_embedding, top_k)
            results: list[dict[str, Any]] = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(resources):
                    continue
                results.append({
                    **resources[int(idx)],
                    "score": float(score),
                    "retriever": "faiss",
                })
            _last_retriever = "faiss"
            return results
        except Exception as exc:
            logger.warning("[Learning RAG] FAISS retrieval failed, falling back to keywords: %s", exc)

    _last_retriever = "keyword_fallback"
    try:
        return _keyword_retrieve(query, resources, top_k)
    except Exception as exc:
        logger.warning("[Learning RAG] Keyword fallback failed: %s", exc)
        return []


def get_last_retriever() -> str:
    return _last_retriever


def validate_learning_rag_startup() -> dict[str, Any]:
    resources = load_learning_resources()
    faiss_available = is_faiss_available()
    sentence_transformers_available = is_sentence_transformers_available()
    model_available = get_embedding_model() is not None if sentence_transformers_available else False
    retriever = "faiss" if faiss_available and model_available and resources else "keyword_fallback"

    logger.info("[Learning RAG] Loaded %d learning resources", len(resources))
    if faiss_available:
        logger.info("[Learning RAG] FAISS available")
    else:
        logger.warning("[Learning RAG] FAISS unavailable. Using keyword fallback.")

    if sentence_transformers_available:
        logger.info("[Learning RAG] sentence-transformers available")
    else:
        logger.warning("[Learning RAG] sentence-transformers unavailable. Using keyword fallback.")

    logger.info("[Learning RAG] Retriever mode: %s", retriever)
    return {
        "resource_count": len(resources),
        "faiss_available": faiss_available,
        "sentence_transformers_available": sentence_transformers_available,
        "model_available": model_available,
        "retriever": retriever,
    }
