# ai_services/rag/rag_store.py

import os
import json
import logging
from pathlib import Path

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ===================================================
#  CONFIG
# ===================================================

BASE_DIR  = Path(__file__).resolve().parent       
DOCS_DIR  = BASE_DIR / "docs"                     
INDEX_DIR = BASE_DIR / "faiss_index"              
INDEX_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE    = 400
CHUNK_OVERLAP = 80

_model: SentenceTransformer | None = None

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("[RAG] Loading embedding model...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed_chunks(texts: list[str]) -> np.ndarray:
    """يحول list of strings لـ numpy array of vectors."""
    return _get_model().encode(texts, show_progress_bar=False).astype("float32")


# ===================================================
#  CHUNKING
# ===================================================

def _chunk_text(text: str) -> list[str]:
    chunks = []
    start  = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c.strip() for c in chunks if c.strip()]


# ===================================================
#  INDEX PATH HELPERS
# ===================================================

def _faiss_path(doc_id: str) -> Path:
    return INDEX_DIR / f"{doc_id}.faiss"

def _meta_path(doc_id: str) -> Path:
    return INDEX_DIR / f"{doc_id}.meta.json"

def index_exists(doc_id: str) -> bool:
    return _faiss_path(doc_id).exists() and _meta_path(doc_id).exists()


# ===================================================
#  BUILD INDEX
# ===================================================

def build_index_from_text(doc_id: str, text: str) -> int:
    chunks = _chunk_text(text)
    if not chunks:
        logger.warning(f"[RAG] No chunks generated for doc_id={doc_id}")
        return 0

    embeddings = embed_chunks(chunks)
    dim        = embeddings.shape[1]
    index      = faiss.IndexFlatL2(dim)
    index.add(embeddings)

    faiss.write_index(index, str(_faiss_path(doc_id)))

    with open(_meta_path(doc_id), "w", encoding="utf-8") as f:
        json.dump({"chunks": chunks, "doc_id": doc_id}, f, ensure_ascii=False)

    logger.info(f"[RAG] Index built: doc_id={doc_id}, chunks={len(chunks)}")
    return len(chunks)


# ===================================================
#  SEARCH
# ===================================================

def search_index(doc_id: str, query: str, top_k: int = 6) -> list[str]:
    if not index_exists(doc_id):
        logger.warning(f"[RAG] Index not found: doc_id={doc_id}")
        return []

    query_vec          = embed_chunks([query])
    index              = faiss.read_index(str(_faiss_path(doc_id)))
    distances, indices = index.search(query_vec, top_k)

    with open(_meta_path(doc_id), "r", encoding="utf-8") as f:
        meta = json.load(f)
    chunks = meta["chunks"]

    return [chunks[idx] for idx in indices[0] if 0 <= idx < len(chunks)]