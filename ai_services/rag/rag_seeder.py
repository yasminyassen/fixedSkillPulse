# ai_services/rag/rag_seeder.py

import logging
from pathlib import Path
from ai_services.rag.rag_store import DOCS_DIR, build_index_from_text, index_exists

logger = logging.getLogger(__name__)

STANDARDS_DOC_ID = "skillpulse_builtin_standards_v1"


def seed_standards():
    print(">>> [RAG] seed_standards() called")

    if index_exists(STANDARDS_DOC_ID):
        print(">>> [RAG] Index already exists — skipping.")
        return

    if not DOCS_DIR.exists():
        print(f">>> [RAG] docs/ folder NOT FOUND at {DOCS_DIR}")
        return

    md_files = list(DOCS_DIR.glob("*.md")) + list(DOCS_DIR.glob("*.txt"))
    print(f">>> [RAG] Found {len(md_files)} files in docs/")

    if not md_files:
        print(">>> [RAG] No .md or .txt files found — nothing to index.")
        return

    all_text = []
    for file_path in md_files:
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                all_text.append(f"### {file_path.stem}\n\n{text}")
                print(f">>> [RAG] Loaded: {file_path.name}")
        except Exception as e:
            print(f">>> [RAG] Failed to read {file_path.name}: {e}")

    if not all_text:
        print(">>> [RAG] All files were empty — nothing to index.")
        return

    combined = "\n\n\n".join(all_text)
    count = build_index_from_text(STANDARDS_DOC_ID, combined)
    print(f">>> [RAG] Standards seeded successfully — {count} chunks indexed.")