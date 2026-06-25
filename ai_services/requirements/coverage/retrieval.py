"""Hybrid retrieval over one code index for requirement coverage."""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from ai_services.requirements.coverage.faiss_store import load_code_index, search_index

DEFAULT_TASK_TO_CODE_K = 5
DEFAULT_TASK_TO_CODE_CANDIDATES = 32
DEFAULT_DEVELOPER_TASK_TO_CODE_K = 8
DEFAULT_DEVELOPER_TASK_TO_CODE_CANDIDATES = 64
MAX_DEVELOPER_EVIDENCE_CHUNKS = 8
PRIMARY_EVIDENCE_THRESHOLD = 0.45
FALLBACK_EVIDENCE_THRESHOLD = 0.35
MIN_EVIDENCE_CHUNKS = 2
MAX_EVIDENCE_CHUNKS = 5
IMPLEMENTATION_TIE_MARGIN = 0.03
MIN_IMPLEMENTATION_EVIDENCE = 1
CALL_NEIGHBOR_SCORE_PENALTY = 0.015

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_CALL_RE = re.compile(r"(?<!def\s)(?<!class\s)\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_METHOD_CALL_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+[.\w]+\s+import|import)\s+(.+)$", re.MULTILINE)
_JS_IMPORT_RE = re.compile(r"^\s*import\s+(?:\{([^}]+)\}|([A-Za-z_][A-Za-z0-9_]*))\s+from\s+['\"][^'\"]+['\"]", re.MULTILINE)
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "user", "users",
    "story", "technical", "task", "tasks", "acceptance", "criteria", "system",
    "should", "shall", "must", "can", "able",
}
_MODAL_WORDS = {"shall", "should", "must", "can", "could", "may", "will", "would"}
_HELPER_WORDS = {"be", "able", "to", "allow", "allows", "allowed", "let", "lets"}
_PRONOUN_WORDS = {"their", "his", "her", "its", "our", "your", "my", "them", "they", "it"}
_ACTOR_SUFFIXES = ("er", "or", "ist", "ian")
_NOUN_SUFFIXES = ("tion", "sion", "ment", "ness", "ity", "ship", "age", "ance", "ence", "hood")
_FRONTEND_EXTENSIONS = (".jsx", ".tsx", ".vue", ".svelte")
_UI_DISPLAY_VERBS = {"view", "display", "list"}
_UI_DISPLAY_PATTERNS = (
    re.compile(r"<\s*(table|ul|ol|li|tbody|thead|tr|td|th)\b", re.IGNORECASE),
    re.compile(r"<\s*[^>\s]*(table|list|grid|collection|feed)[^>\s]*\b", re.IGNORECASE),
    re.compile(r"\brole\s*=\s*['\"](?:table|list|grid|row|cell|listitem)['\"]", re.IGNORECASE),
    re.compile(r"\.map\s*\([^)]*=>\s*<", re.IGNORECASE | re.DOTALL),
)
_UI_HEADING_PATTERN = re.compile(r"<\s*h[1-6]\b[^>]*>\s*([^<]{3,120})\s*<\s*/\s*h[1-6]\s*>", re.IGNORECASE)
_UI_MUTATION_HINTS = {
    "add", "approve", "assign", "create", "delete", "edit", "export", "import", "login",
    "register", "reject", "remove", "reassign", "save", "sign", "submit", "update", "upload",
}
_FRAMEWORK_CALLS = {
    "all", "append", "catch", "commit", "filter", "find", "forEach", "get", "json", "map",
    "order_by", "post", "push", "query", "render", "replace", "save", "send", "set", "then",
    "useEffect", "useMemo", "useRef", "useState",
}


def _split_identifier(token: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", token.replace("_", " "))
    return [p.lower() for p in re.split(r"[^A-Za-z0-9]+", spaced) if len(p) > 2]


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for raw in _TOKEN_RE.findall(text or ""):
        for token in _split_identifier(raw):
            if token not in _STOPWORDS:
                out.add(token)
    return out


def _raw_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for raw in _TOKEN_RE.findall(text or ""):
        terms.update(_split_identifier(raw))
    return terms


def _normalize_term(token: str) -> str:
    token = token.lower()
    if len(token) > 5 and token.endswith("ing"):
        root = token[:-3]
        if len(root) > 3 and root[-1] == root[-2]:
            root = root[:-1]
        return root
    if len(token) > 4 and token.endswith("ied"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ed"):
        if token.endswith("red"):
            return token[:-1]
        root = token[:-2]
        if root.endswith(("at", "iz", "is", "iv", "ur", "os")):
            root += "e"
        return root
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _normalized_terms(tokens: set[str]) -> set[str]:
    return {_normalize_term(t) for t in tokens if t and t not in _STOPWORDS}


def _looks_like_actor(token: str) -> bool:
    singular = _normalize_term(token)
    return singular.endswith(_ACTOR_SUFFIXES) or token.endswith(tuple(f"{suffix}s" for suffix in _ACTOR_SUFFIXES))


def _looks_like_noun(token: str) -> bool:
    return token.endswith(_NOUN_SUFFIXES)


def _first_requirement_verb(tokens: list[str]) -> str | None:
    for idx, token in enumerate(tokens):
        if token not in _MODAL_WORDS:
            continue
        for candidate in tokens[idx + 1:]:
            if candidate in _HELPER_WORDS or candidate in _PRONOUN_WORDS or candidate in _STOPWORDS or _looks_like_actor(candidate):
                continue
            return candidate
    for token in tokens[:5]:
        if token in _STOPWORDS or token in _PRONOUN_WORDS or _looks_like_actor(token):
            continue
        return token
    return None


def _symbol_verbs(symbol_name: str | None) -> set[str]:
    parts = _raw_sequence(symbol_name or "")
    if len(parts) < 2:
        return set()
    first = parts[0]
    if first in _STOPWORDS or _looks_like_noun(first):
        return set()
    return {_normalize_term(first)}


def _is_frontend_path(file_path: str | None) -> bool:
    path = (file_path or "").replace("\\", "/").lower()
    return path.endswith(_FRONTEND_EXTENSIONS) or "/frontend/" in path or "/components/" in path or "/pages/" in path


def _frontend_display_verbs(text: str, *, file_path: str | None = None, symbol_name: str | None = None) -> set[str]:
    if not _is_frontend_path(file_path):
        return set()

    source = text or ""
    has_display_structure = any(pattern.search(source) for pattern in _UI_DISPLAY_PATTERNS)
    heading_labels = [match.group(1) for match in _UI_HEADING_PATTERN.finditer(source)]
    has_entity_heading = any(_tokens(label) and not (_tokens(label) & _UI_MUTATION_HINTS) for label in heading_labels)

    symbol_parts = _raw_sequence(symbol_name or "")
    has_collection_component_name = bool(
        symbol_parts
        and not (set(symbol_parts) & _UI_MUTATION_HINTS)
        and _normalize_term(symbol_parts[-1]) != symbol_parts[-1]
    )

    if has_display_structure or has_entity_heading or has_collection_component_name:
        return set(_UI_DISPLAY_VERBS)
    return set()


def _raw_sequence(text: str) -> list[str]:
    out: list[str] = []
    for raw in _TOKEN_RE.findall(text or ""):
        out.extend(_split_identifier(raw))
    return out


def _source_priority(source: str) -> int:
    order = {"primary": 0, "linked_task": 1, "linked_ac": 1, "call_neighbor": 2}
    return order.get(source, 99)


def _merge_retrieval_sources(*sources: str | None) -> str:
    parts: set[str] = set()
    for source in sources:
        if not source:
            continue
        parts.update(part for part in str(source).split("+") if part)
    if not parts:
        return "primary"
    return "+".join(sorted(parts, key=_source_priority))


def _intent_signals(text: str, *, symbol_name: str | None = None, file_path: str | None = None, requirement_text: bool = False) -> tuple[set[str], set[str]]:
    sequence = _raw_sequence(text)
    raw = set(sequence)
    verbs: set[str] = set()
    if requirement_text:
        verb = _first_requirement_verb(sequence)
        if verb:
            verbs.add(_normalize_term(verb))
    verbs.update(_symbol_verbs(symbol_name))
    verbs.update(_frontend_display_verbs(text, file_path=file_path, symbol_name=symbol_name))

    # Docstrings and comments often contain natural-language behavior labels.
    quoted_phrases = re.findall(r'["\']{3}([^"\']{3,80})["\']{3}|["\']([^"\']{3,80})["\']', text or "")
    for phrase_group in quoted_phrases:
        phrase = " ".join(p for p in phrase_group if p)
        verb = _first_requirement_verb(_raw_sequence(phrase))
        if not verb:
            phrase_tokens = _raw_sequence(phrase)
            verb = phrase_tokens[0] if phrase_tokens else None
        if verb and verb not in _STOPWORDS:
            verbs.add(_normalize_term(verb))

    objects = _normalized_terms(raw)
    objects.difference_update(verbs)
    objects.difference_update(_normalized_terms(_MODAL_WORDS | _HELPER_WORDS | _PRONOUN_WORDS))
    objects = {token for token in objects if not _looks_like_actor(token)}
    if file_path:
        objects.update(_normalized_terms(_raw_terms(file_path)))
    return verbs, objects


def _set_coverage(query_items: set[str], hit_items: set[str]) -> float:
    if not query_items:
        return 0.0
    return len(query_items & hit_items) / len(query_items)


def _is_test_file(file_path: str | None) -> bool:
    path = (file_path or "").replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    return (
        "/test/" in path
        or "/tests/" in path
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.tsx")
        or name.endswith(".test.js")
        or name.endswith(".spec.js")
    )


def _implementation_role_score(file_path: str | None) -> float:
    path = (file_path or "").replace("\\", "/").lower()
    if _is_test_file(path):
        return -0.16
    if any(part in path for part in (
        "/services/", "_service.", "/service.", "/routes.", "_routes.", "/controllers/", "_controller.",
        "/pages/", "/components/", "/publishers/", "/events/", "/handlers/", "/jobs/", "/repositories/",
        "/helpers/", "/utils/",
    )):
        return 0.08
    return 0.0


def _is_business_logic_chunk(hit: dict) -> bool:
    path = (hit.get("file_path") or "").replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    if _is_test_file(path):
        return False
    return (
        _is_frontend_path(path)
        or any(part in path for part in (
            "/services/", "_service.", "/service.", "/controllers/", "_controller.", "/pages/", "/components/",
            "/publishers/", "/events/", "/handlers/", "/jobs/", "/repositories/", "/helpers/", "/utils/",
        ))
        or name in {"services.py", "service.py", "controllers.py", "controller.py", "publishers.py", "events.py", "handlers.py", "jobs.py"}
        or name.endswith((
            "_services.py", "_service.py", "_controllers.py", "_controller.py", "_publishers.py",
            "_events.py", "_handlers.py", "_jobs.py", "_repository.py", "_repositories.py",
            "_helpers.py", "_utils.py",
        ))
    )


def _is_model_schema_route_chunk(hit: dict) -> bool:
    path = (hit.get("file_path") or "").replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    symbol_type = (hit.get("symbol_type") or "").lower()
    return (
        symbol_type == "class"
        or name in {"models.py", "model.py", "schemas.py", "schema.py", "routes.py"}
        or name.endswith(("_model.py", "_schema.py", "_routes.py", ".model.ts", ".schema.ts", ".routes.ts"))
    )


def _is_placeholder_chunk(hit: dict) -> bool:
    text = (hit.get("chunk_text") or "").lower()
    return any(
        marker in text
        for marker in (
            "todo",
            "placeholder",
            "mock",
            "stub",
            "pass",
            "notimplemented",
            "not implemented",
            "return []",
            "return none",
            "return null",
        )
    )


def _chunk_search_text(hit: dict) -> str:
    return "\n".join(
        str(part or "")
        for part in (
            hit.get("file_path"),
            hit.get("symbol_name"),
            hit.get("symbol_type"),
            hit.get("chunk_text"),
        )
    )


def lexical_relevance(query_text: str, hit: dict) -> float:
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return 0.0
    hit_text = _chunk_search_text(hit)
    hit_tokens = _tokens(hit_text)
    if not hit_tokens:
        return 0.0
    overlap = query_tokens & hit_tokens
    base = len(overlap) / max(1, len(query_tokens))

    path_symbol = f"{hit.get('file_path') or ''} {hit.get('symbol_name') or ''}"
    path_tokens = _tokens(path_symbol)
    path_boost = len(query_tokens & path_tokens) / max(1, len(query_tokens))

    query_verbs, query_objects = _intent_signals(query_text, requirement_text=True)
    hit_verbs, hit_objects = _intent_signals(
        hit_text,
        symbol_name=hit.get("symbol_name"),
        file_path=hit.get("file_path"),
    )
    verb_score = _set_coverage(query_verbs, hit_verbs)
    object_score = _set_coverage(query_objects, hit_objects)
    verb_mismatch_penalty = 0.0
    if query_verbs and hit_verbs and not (query_verbs & hit_verbs):
        verb_mismatch_penalty = 0.18

    role_score = _implementation_role_score(hit.get("file_path"))
    return max(
        0.0,
        min(
            1.0,
            base
            + (0.55 * path_boost)
            + (0.34 * verb_score)
            + (0.34 * object_score)
            - verb_mismatch_penalty
            + role_score,
        ),
    )


def rerank_code_hits(
    query_text: str,
    hits: list[dict],
    top_k: int = DEFAULT_TASK_TO_CODE_K,
    *,
    max_evidence_limit: int = MAX_EVIDENCE_CHUNKS,
    per_file_limit: int = 3,
) -> list[dict]:
    ranked = _rank_all_code_hits(query_text, hits)
    max_evidence = min(top_k, max_evidence_limit)
    ranked = _prefer_implementation_hits(ranked)
    selected = _select_adaptive_evidence(ranked, max_evidence=max_evidence)
    return _diversify_by_file(selected, len(selected), per_file_limit=per_file_limit)


def _rank_all_code_hits(query_text: str, hits: list[dict]) -> list[dict]:
    ranked = []
    for hit in hits:
        vector_score = float(hit.get("score") or 0.0)
        lexical_score = lexical_relevance(query_text, hit)
        final_score = (0.62 * vector_score) + (0.38 * lexical_score)
        ranked.append({
            **hit,
            "vector_score": vector_score,
            "lexical_score": round(lexical_score, 4),
            "rerank_score": round(final_score, 6),
        })
    ranked.sort(key=lambda h: (-float(h.get("rerank_score") or 0.0), str(h.get("file_path") or ""), str(h.get("chunk_id") or "")))
    return ranked


def _weak_evidence(evidence: list[dict]) -> bool:
    if len(evidence) < MIN_EVIDENCE_CHUNKS:
        return True
    implementation_count = sum(1 for hit in evidence if _is_business_logic_chunk(hit))
    if implementation_count < MIN_IMPLEMENTATION_EVIDENCE:
        return True
    structural_count = sum(1 for hit in evidence if _is_model_schema_route_chunk(hit))
    placeholder_count = sum(1 for hit in evidence if _is_placeholder_chunk(hit))
    return (
        (structural_count >= len(evidence) and implementation_count == 0)
        or placeholder_count >= len(evidence)
    )


def _prefer_implementation_hits(hits: list[dict]) -> list[dict]:
    output: list[dict] = []
    used: set[int] = set()
    for idx, hit in enumerate(hits):
        if idx in used:
            continue
        if _is_test_file(hit.get("file_path")):
            test_score = float(hit.get("rerank_score") or 0.0)
            for impl_idx, impl_hit in enumerate(hits):
                if impl_idx in used or impl_idx <= idx or _is_test_file(impl_hit.get("file_path")):
                    continue
                impl_score = float(impl_hit.get("rerank_score") or 0.0)
                if impl_score >= test_score - IMPLEMENTATION_TIE_MARGIN:
                    output.append(impl_hit)
                    used.add(impl_idx)
                    break
        output.append(hit)
        used.add(idx)
    return output


def _select_adaptive_evidence(
    hits: list[dict],
    *,
    primary_threshold: float = PRIMARY_EVIDENCE_THRESHOLD,
    fallback_threshold: float = FALLBACK_EVIDENCE_THRESHOLD,
    min_evidence: int = MIN_EVIDENCE_CHUNKS,
    max_evidence: int = MAX_EVIDENCE_CHUNKS,
) -> list[dict]:
    max_evidence = max(0, max_evidence)
    if max_evidence == 0:
        return []

    min_evidence = min(max(0, min_evidence), max_evidence)
    selected: list[dict] = [
        hit
        for hit in hits
        if float(hit.get("rerank_score") or 0.0) >= primary_threshold
    ][:max_evidence]
    if len(selected) >= min_evidence:
        return selected

    selected_keys = {hit.get("chunk_id") or hit.get("faiss_id") for hit in selected}
    for hit in hits:
        key = hit.get("chunk_id") or hit.get("faiss_id")
        if key in selected_keys:
            continue
        if float(hit.get("rerank_score") or 0.0) < fallback_threshold:
            continue
        selected.append(hit)
        selected_keys.add(key)
        if len(selected) >= max_evidence:
            break
    return selected[:max_evidence]


def _diversify_by_file(hits: list[dict], top_k: int, per_file_limit: int = 3) -> list[dict]:
    counts: Counter[str] = Counter()
    selected: list[dict] = []
    deferred: list[dict] = []
    for hit in hits:
        file_path = hit.get("file_path") or ""
        if counts[file_path] < per_file_limit:
            selected.append(hit)
            counts[file_path] += 1
        else:
            deferred.append(hit)
        if len(selected) >= top_k:
            return selected
    for hit in deferred:
        selected.append(hit)
        if len(selected) >= top_k:
            break
    return selected


def _raw_code_hits_for_query(
    code_index,
    code_meta: list[dict],
    query_text: str,
    *,
    source: str,
    top_k: int,
) -> list[dict]:
    hits = search_index(code_index, query_text, code_meta, top_k)
    return [
        {
            "faiss_id": faiss_id,
            "score": score,
            "retrieval_source": source,
            **record,
        }
        for faiss_id, score, record in hits
    ]


def _merge_code_candidates(candidate_groups: list[list[dict]]) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in candidate_groups:
        for hit in group:
            key = hit.get("chunk_id") or f"{hit.get('file_path')}::{hit.get('symbol_name')}::{hit.get('faiss_id')}"
            existing = merged.get(key)
            if existing is None:
                merged[key] = hit
                continue

            existing_score = float(existing.get("score") or 0.0)
            hit_score = float(hit.get("score") or 0.0)
            sources = _merge_retrieval_sources(
                existing.get("retrieval_source") or "primary",
                hit.get("retrieval_source") or "primary",
            )
            if hit_score > existing_score:
                merged[key] = {
                    **hit,
                    "retrieval_source": sources,
                }
            else:
                existing["retrieval_source"] = sources
    return list(merged.values())


def _chunk_key(hit: dict) -> str:
    return str(hit.get("chunk_id") or f"{hit.get('file_path')}::{hit.get('symbol_name')}::{hit.get('faiss_id')}")


def _symbol_key(symbol_name: str | None) -> str:
    return (symbol_name or "").strip().lower()


def _extract_imported_symbols(text: str) -> set[str]:
    symbols: set[str] = set()
    for match in _PY_IMPORT_RE.finditer(text or ""):
        for item in match.group(1).split(","):
            name = item.strip().split(" as ", 1)[0].strip()
            if name and name != "*":
                symbols.add(name)
    for match in _JS_IMPORT_RE.finditer(text or ""):
        group = match.group(1) or match.group(2) or ""
        for item in group.split(","):
            name = item.strip().split(" as ", 1)[0].strip()
            if name:
                symbols.add(name)
    return symbols


def _referenced_project_symbols(hit: dict) -> list[tuple[str, str]]:
    text = hit.get("chunk_text") or ""
    current_symbol = _symbol_key(hit.get("symbol_name"))
    references: dict[str, str] = {}

    def add(symbol: str, reason: str) -> None:
        if (
            not symbol
            or symbol in _FRAMEWORK_CALLS
            or symbol.startswith(("use", "set"))
            or _symbol_key(symbol) == current_symbol
        ):
            return
        key = _symbol_key(symbol)
        # Direct calls are stronger evidence than import presence if both appear.
        if key not in references or references[key].startswith("imported_symbol:"):
            references[key] = reason

    for symbol in _extract_imported_symbols(text):
        add(symbol, f"imported_symbol:{symbol}")
    for symbol in set(_CALL_RE.findall(text)) | set(_METHOD_CALL_RE.findall(text)):
        add(symbol, f"direct_call:{symbol}")

    return sorted((reason.split(":", 1)[1], reason) for reason in references.values())


def _implementation_symbol(record: dict) -> bool:
    symbol_type = (record.get("symbol_type") or "").lower()
    return (
        _is_business_logic_chunk(record)
        and symbol_type not in {"class", "semantic"}
        and bool(record.get("symbol_name"))
    )


def _neighbor_hit(record: dict, parent: dict, query_text: str, reason: str, penalty: float) -> dict:
    parent_score = float(parent.get("rerank_score") or parent.get("score") or 0.0)
    final_score = max(0.0, parent_score - penalty)
    return {
        **record,
        "score": float(record.get("score") or 0.0),
        "vector_score": float(record.get("score") or 0.0),
        "lexical_score": round(lexical_relevance(query_text, record), 4),
        "rerank_score": round(final_score, 6),
        "retrieval_source": "call_neighbor",
        "neighbor_reason": reason,
        "neighbor_parent_chunk_id": parent.get("chunk_id"),
        "neighbor_parent_symbol": parent.get("symbol_name"),
    }


def _add_neighbor_candidate(
    candidates: dict[str, dict],
    record: dict,
    parent: dict,
    query_text: str,
    reason: str,
    penalty: float,
) -> None:
    key = _chunk_key(record)
    candidate = _neighbor_hit(record, parent, query_text, reason, penalty)
    existing = candidates.get(key)
    if existing is None or float(candidate.get("rerank_score") or 0.0) > float(existing.get("rerank_score") or 0.0):
        candidates[key] = candidate


def _expand_call_neighbors(
    query_text: str,
    selected: list[dict],
    code_meta: list[dict],
    *,
    max_evidence: int,
) -> list[dict]:
    if not selected or max_evidence <= 0 or len(selected) >= max_evidence:
        return selected[:max_evidence]

    selected_by_key = {_chunk_key(hit): {**hit} for hit in selected}
    symbol_index: dict[str, list[dict]] = defaultdict(list)
    for faiss_id, record in enumerate(code_meta):
        enriched = {"faiss_id": faiss_id, **record}
        symbol = _symbol_key(enriched.get("symbol_name"))
        if symbol:
            symbol_index[symbol].append(enriched)

    neighbor_candidates: dict[str, dict] = {}
    for parent in selected:
        parent_key = _chunk_key(parent)
        referenced_symbols = _referenced_project_symbols(parent)
        for symbol, reason in referenced_symbols:
            for record in symbol_index.get(_symbol_key(symbol), []):
                target_key = _chunk_key(record)
                if target_key == parent_key:
                    continue
                if target_key in selected_by_key:
                    continue
                if not _implementation_symbol(record):
                    continue
                _add_neighbor_candidate(
                    neighbor_candidates,
                    record,
                    parent,
                    query_text,
                    reason,
                    CALL_NEIGHBOR_SCORE_PENALTY,
                )

    ordered_selected = [selected_by_key[_chunk_key(hit)] for hit in selected]
    slots = max(0, max_evidence - len(ordered_selected))
    if not slots:
        return ordered_selected[:max_evidence]

    ordered_neighbors = sorted(
        neighbor_candidates.values(),
        key=lambda hit: (
            -float(hit.get("rerank_score") or 0.0),
            str(hit.get("file_path") or ""),
            str(hit.get("chunk_id") or ""),
        ),
    )
    return (ordered_selected + ordered_neighbors[:slots])[:max_evidence]


def retrieve_code_for_task(
    run_id: int,
    task_embedding_text: str,
    top_k: int = DEFAULT_TASK_TO_CODE_K,
) -> list[dict]:
    code_index, code_meta = load_code_index(run_id)
    raw_hits = _raw_code_hits_for_query(
        code_index,
        code_meta,
        task_embedding_text,
        source="primary",
        top_k=max(top_k, DEFAULT_TASK_TO_CODE_CANDIDATES),
    )
    return rerank_code_hits(task_embedding_text, raw_hits, top_k)


def retrieve_code_for_acceptance_criterion(
    run_id: int,
    ac_text: str,
    top_k: int = DEFAULT_TASK_TO_CODE_K,
) -> list[dict]:
    """Manager scoring retrieval: AC-only query against the code index."""
    return retrieve_code_for_task(run_id, ac_text, top_k)


def retrieve_code_for_acceptance_criterion_with_linked_tasks(
    run_id: int,
    ac_text: str,
    linked_task_descriptions: list[str],
    top_k: int = DEFAULT_TASK_TO_CODE_K,
    include_call_neighbors: bool = True,
) -> list[dict]:
    """Manager scoring retrieval: AC primary, linked-task fallback against the same code index."""
    code_index, code_meta = load_code_index(run_id)
    candidate_top_k = max(top_k, DEFAULT_DEVELOPER_TASK_TO_CODE_CANDIDATES)
    primary_candidates = _raw_code_hits_for_query(
        code_index,
        code_meta,
        ac_text,
        source="primary",
        top_k=candidate_top_k,
    )
    primary_evidence = rerank_code_hits(ac_text, primary_candidates, top_k)
    if not linked_task_descriptions or not _weak_evidence(primary_evidence):
        if not include_call_neighbors:
            return primary_evidence
        return _expand_call_neighbors(
            ac_text,
            primary_evidence,
            code_meta,
            max_evidence=min(top_k, MAX_EVIDENCE_CHUNKS),
        )

    linked_candidate_groups = []
    for description in linked_task_descriptions:
        if not (description or "").strip():
            continue
        linked_candidate_groups.append(
            _raw_code_hits_for_query(
                code_index,
                code_meta,
                description,
                source="linked_task",
                top_k=candidate_top_k,
            )
        )

    if not linked_candidate_groups:
        if not include_call_neighbors:
            return primary_evidence
        return _expand_call_neighbors(
            ac_text,
            primary_evidence,
            code_meta,
            max_evidence=min(top_k, MAX_EVIDENCE_CHUNKS),
        )

    merged_candidates = _merge_code_candidates([primary_candidates, *linked_candidate_groups])
    merged_evidence = rerank_code_hits(ac_text, merged_candidates, top_k)
    if not include_call_neighbors:
        return merged_evidence
    return _expand_call_neighbors(
        ac_text,
        merged_evidence,
        code_meta,
        max_evidence=min(top_k, MAX_EVIDENCE_CHUNKS),
    )


def retrieve_code_for_developer_task(
    run_id: int,
    task_description: str,
    linked_ac_texts: list[str] | None = None,
    top_k: int = DEFAULT_DEVELOPER_TASK_TO_CODE_K,
    include_call_neighbors: bool = True,
) -> list[dict]:
    """Developer retrieval: assigned task primary, linked AC fallback, one shared code index."""
    code_index, code_meta = load_code_index(run_id)
    candidate_top_k = max(top_k, DEFAULT_DEVELOPER_TASK_TO_CODE_CANDIDATES)
    primary_candidates = _raw_code_hits_for_query(
        code_index,
        code_meta,
        task_description,
        source="primary",
        top_k=candidate_top_k,
    )
    evidence_budget = min(top_k, MAX_DEVELOPER_EVIDENCE_CHUNKS)
    primary_evidence = rerank_code_hits(
        task_description,
        primary_candidates,
        top_k,
        max_evidence_limit=MAX_DEVELOPER_EVIDENCE_CHUNKS,
        per_file_limit=MAX_DEVELOPER_EVIDENCE_CHUNKS,
    )
    if not linked_ac_texts or not _weak_evidence(primary_evidence):
        if not include_call_neighbors:
            return primary_evidence
        return _expand_call_neighbors(
            task_description,
            primary_evidence,
            code_meta,
            max_evidence=evidence_budget,
        )

    linked_candidate_groups = []
    for ac_text in linked_ac_texts:
        if not (ac_text or "").strip():
            continue
        linked_candidate_groups.append(
            _raw_code_hits_for_query(
                code_index,
                code_meta,
                ac_text,
                source="linked_ac",
                top_k=candidate_top_k,
            )
        )

    if not linked_candidate_groups:
        if not include_call_neighbors:
            return primary_evidence
        return _expand_call_neighbors(
            task_description,
            primary_evidence,
            code_meta,
            max_evidence=evidence_budget,
        )

    merged_candidates = _merge_code_candidates([primary_candidates, *linked_candidate_groups])
    merged_evidence = rerank_code_hits(
        task_description,
        merged_candidates,
        top_k,
        max_evidence_limit=MAX_DEVELOPER_EVIDENCE_CHUNKS,
        per_file_limit=MAX_DEVELOPER_EVIDENCE_CHUNKS,
    )
    if not include_call_neighbors:
        return merged_evidence
    return _expand_call_neighbors(
        task_description,
        merged_evidence,
        code_meta,
        max_evidence=evidence_budget,
    )


def merge_task_code_hits(hits_by_task: list[list[dict]], max_chunks: int = 12) -> list[dict]:
    """Deduplicate code chunks retrieved from multiple tasks linked to one AC."""
    by_key: dict[str, dict] = {}
    for hits in hits_by_task:
        for hit in hits:
            key = hit.get("chunk_id") or str(hit.get("faiss_id"))
            existing = by_key.get(key)
            if existing is None or float(hit.get("rerank_score", hit.get("score", 0.0)) or 0.0) > float(existing.get("rerank_score", existing.get("score", 0.0)) or 0.0):
                by_key[key] = hit

    grouped: dict[str, list[dict]] = defaultdict(list)
    for hit in by_key.values():
        grouped[hit.get("file_path") or ""].append(hit)
    for file_hits in grouped.values():
        file_hits.sort(key=lambda h: (-float(h.get("rerank_score", h.get("score", 0.0)) or 0.0), str(h.get("chunk_id") or "")))

    merged: list[dict] = []
    while len(merged) < max_chunks and grouped:
        for file_path in sorted(list(grouped.keys())):
            if not grouped[file_path]:
                grouped.pop(file_path, None)
                continue
            merged.append(grouped[file_path].pop(0))
            if len(merged) >= max_chunks:
                break
        grouped = {k: v for k, v in grouped.items() if v}
    return merged
