"""End-to-end requirement coverage pipeline."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from ai_services.requirements.coverage.chunkers import chunk_repository_files
from ai_services.requirements.coverage.faiss_store import build_code_index
from ai_services.requirements.coverage.llm_evaluator import (
    evaluate_ac_coverage,
    evaluate_developer_task_implementation,
)
from ai_services.requirements.coverage.retrieval import (
    retrieve_code_for_developer_task,
    retrieve_code_for_acceptance_criterion_with_linked_tasks,
)
from ai_services.requirements.coverage.scoring import (
    ac_score_from_status,
    ac_text_by_id,
    overall_coverage_score,
    story_coverage_score,
    story_coverage_status,
    tasks_for_ac,
)
from app.db.models import (
    AcCoverageResult,
    AcCoverageStatus,
    CodeEmbeddingRecord,
    CoverageRunStatus,
    RequirementCoverageRun,
    RequirementDocument,
    StoryCoverageStatus,
    StoryCoverageSummary,
    UserStory,
)

logger = logging.getLogger(__name__)


def _ac_status_enum(status: str) -> AcCoverageStatus:
    mapping = {
        "COVERED": AcCoverageStatus.covered,
        "PARTIALLY_COVERED": AcCoverageStatus.partially_covered,
        "NOT_COVERED": AcCoverageStatus.not_covered,
    }
    return mapping.get(status, AcCoverageStatus.not_covered)


def _story_status_enum(status: str) -> StoryCoverageStatus:
    mapping = {
        "implemented": StoryCoverageStatus.implemented,
        "partially_implemented": StoryCoverageStatus.partially_implemented,
        "not_implemented": StoryCoverageStatus.not_implemented,
    }
    return mapping.get(status, StoryCoverageStatus.not_implemented)


async def build_developer_task_results_for_run(run: RequirementCoverageRun, document: RequirementDocument) -> list[dict]:
    developer_task_results: list[dict] = []
    for story in document.user_stories:
        for task in story.technical_tasks:
            linked_ac_texts = [
                ac_text_by_id(story.acceptance_criteria, ac_id)
                for ac_id in (task.ac_ids or [])
            ]
            linked_ac_texts = [text for text in linked_ac_texts if text]
            evidence = retrieve_code_for_developer_task(
                run.id,
                task.description,
                linked_ac_texts=linked_ac_texts,
            )
            task_eval = await evaluate_developer_task_implementation(
                task_description=task.description,
                linked_acceptance_criteria=linked_ac_texts,
                code_evidence=evidence,
            )
            developer_task_results.append(
                {
                    "task_id": task.id,
                    "story_id": story.id,
                    "status": task_eval.get("status"),
                    "score": ac_score_from_status(task_eval.get("status")),
                    "confidence": task_eval.get("confidence"),
                    "reason": task_eval.get("reason"),
                    "linked_ac_ids": task.ac_ids or [],
                    "evidence": [
                        {
                            "file_path": e.get("file_path"),
                            "chunk_id": e.get("chunk_id"),
                            "symbol_name": e.get("symbol_name"),
                            "symbol_type": e.get("symbol_type"),
                            "start_line": e.get("start_line"),
                            "end_line": e.get("end_line"),
                            "similarity": e.get("score"),
                            "vector_score": e.get("vector_score"),
                            "lexical_score": e.get("lexical_score"),
                            "rerank_score": e.get("rerank_score"),
                            "retrieval_source": e.get("retrieval_source") or "primary",
                            "excerpt": (e.get("chunk_text") or "")[:500],
                        }
                        for e in evidence
                    ],
                    "matched_chunk_ids": [e.get("chunk_id") for e in evidence if e.get("chunk_id")],
                }
            )
    return developer_task_results


async def backfill_developer_task_results(db: Session, *, coverage_run_id: int) -> RequirementCoverageRun:
    run = db.query(RequirementCoverageRun).filter(RequirementCoverageRun.id == coverage_run_id).first()
    if not run:
        raise ValueError(f"Coverage run {coverage_run_id} not found")
    if run.status != CoverageRunStatus.completed:
        raise ValueError("Developer task coverage can only be backfilled for completed coverage runs")
    if run.developer_task_results:
        return run

    document = (
        db.query(RequirementDocument)
        .options(joinedload(RequirementDocument.user_stories).joinedload(UserStory.technical_tasks))
        .filter(RequirementDocument.id == run.document_id)
        .first()
    )
    if not document:
        raise ValueError("Requirement document not found")

    run.developer_task_results = await build_developer_task_results_for_run(run, document)
    db.commit()
    db.refresh(run)
    return run


async def run_coverage_pipeline(
    db: Session,
    *,
    coverage_run_id: int,
    repo_path: str,
    source_files: list[dict],
) -> RequirementCoverageRun:
    run = db.query(RequirementCoverageRun).filter(RequirementCoverageRun.id == coverage_run_id).first()
    if not run:
        raise ValueError(f"Coverage run {coverage_run_id} not found")

    run.status = CoverageRunStatus.running
    db.commit()

    try:
        document = (
            db.query(RequirementDocument)
            .options(joinedload(RequirementDocument.user_stories).joinedload(UserStory.technical_tasks))
            .filter(RequirementDocument.id == run.document_id)
            .first()
        )
        if not document:
            raise ValueError("Requirement document not found")

        chunks = chunk_repository_files(source_files)
        if not chunks:
            raise ValueError("No indexable source files found in repository")
        chunk_types = Counter(c.symbol_type or "unknown" for c in chunks)
        semantic_count = chunk_types.get("semantic", 0)
        logger.info(
            "[Coverage] Chunk inventory: total=%s semantic_fallback=%s semantic_pct=%.1f%% types=%s",
            len(chunks),
            semantic_count,
            (semantic_count / len(chunks)) * 100,
            dict(chunk_types),
        )

        build_code_index(run.id, chunks)

        if not any(story.technical_tasks for story in document.user_stories):
            raise ValueError("No technical tasks found in confirmed PRD")

        for faiss_id, chunk in enumerate(chunks):
            db.add(
                CodeEmbeddingRecord(
                    coverage_run_id=run.id,
                    faiss_id=faiss_id,
                    file_path=chunk.file_path,
                    symbol_name=chunk.symbol_name,
                    symbol_type=chunk.symbol_type,
                    chunk_id=chunk.chunk_id,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    chunk_text=chunk.chunk_text,
                    language=chunk.language,
                )
            )
        db.commit()

        run.discovery_links = []
        db.commit()

        run.developer_task_results = await build_developer_task_results_for_run(run, document)
        db.commit()

        story_weight_inputs: list[tuple[float, str]] = []

        for story in document.user_stories:
            ac_statuses: list[str] = []
            matched_symbols: list[str] = []

            for ac in story.acceptance_criteria or []:
                if not isinstance(ac, dict):
                    continue
                ac_id = ac.get("id")
                ac_text = ac.get("text") or ""
                linked_tasks = tasks_for_ac(story.technical_tasks, ac_id)

                if not linked_tasks:
                    db.add(
                        AcCoverageResult(
                            coverage_run_id=run.id,
                            story_id=story.id,
                            task_id=None,
                            ac_id=ac_id,
                            status=AcCoverageStatus.not_covered,
                            score=0.0,
                            confidence=1.0,
                            evidence=[],
                            matched_chunk_ids=[],
                            llm_reason="No technical task linked to this acceptance criterion.",
                        )
                    )
                    ac_statuses.append("NOT_COVERED")
                    continue

                primary_task_id = linked_tasks[0].id
                evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
                    run.id,
                    ac_text,
                    [task.description for task in linked_tasks],
                )
                for ev in evidence:
                    sym = ev.get("symbol_name")
                    if sym:
                        matched_symbols.append(sym)

                llm_result = await evaluate_ac_coverage(
                    story_title=story.title,
                    story_description=story.description,
                    ac_text=ac_text,
                    code_evidence=evidence,
                )
                status = llm_result["status"]
                ac_statuses.append(status)

                db.add(
                    AcCoverageResult(
                        coverage_run_id=run.id,
                        story_id=story.id,
                        task_id=primary_task_id,
                        ac_id=ac_id,
                        status=_ac_status_enum(status),
                        score=ac_score_from_status(status),
                        confidence=llm_result.get("confidence"),
                        evidence=[
                            {
                                "file_path": e.get("file_path"),
                                "chunk_id": e.get("chunk_id"),
                                "symbol_name": e.get("symbol_name"),
                                "symbol_type": e.get("symbol_type"),
                                "start_line": e.get("start_line"),
                                "end_line": e.get("end_line"),
                                "similarity": e.get("score"),
                                "vector_score": e.get("vector_score"),
                                "lexical_score": e.get("lexical_score"),
                                "rerank_score": e.get("rerank_score"),
                                "retrieval_source": e.get("retrieval_source") or "primary",
                                "excerpt": (e.get("chunk_text") or "")[:500],
                            }
                            for e in evidence
                        ],
                        matched_chunk_ids=[e.get("chunk_id") for e in evidence if e.get("chunk_id")],
                        llm_reason=llm_result.get("reason"),
                    )
                )

            score = story_coverage_score(ac_statuses)
            status_label = story_coverage_status(score, ac_statuses)
            story_weight_inputs.append((score, story.priority))

            db.add(
                StoryCoverageSummary(
                    coverage_run_id=run.id,
                    story_id=story.id,
                    coverage_score=score,
                    status=_story_status_enum(status_label),
                    matched_symbols=sorted(set(matched_symbols)),
                )
            )

        run.overall_coverage = overall_coverage_score(story_weight_inputs)
        run.status = CoverageRunStatus.completed
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run

    except Exception as exc:
        logger.exception("Coverage pipeline failed for run=%s", coverage_run_id)
        run.status = CoverageRunStatus.failed
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise
