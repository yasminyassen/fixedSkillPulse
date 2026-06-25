"""Jina code embedding model wrapper."""

from __future__ import annotations

import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

_model = None
MODEL_NAME = os.environ.get("COVERAGE_EMBED_MODEL", "jinaai/jina-embeddings-v2-base-code")


def get_embedding_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("[Coverage] Loading embedding model: %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 768), dtype="float32")
    vectors = get_embedding_model().encode(texts, show_progress_bar=False)
    arr = np.asarray(vectors, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms
