"""AST / tree-sitter / semantic chunking for requirement coverage indexing."""

from __future__ import annotations

import ast
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180
MAX_CHUNK_CHARS = 6000
MIN_TREE_SITTER_CHUNK_BYTES = 20
_TREE_SITTER_CACHE_CONFIGURED = False

SOURCE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


@dataclass
class CodeChunk:
    file_path: str
    language: str
    chunk_id: str
    chunk_text: str
    symbol_name: str | None = None
    symbol_type: str | None = None
    start_line: int | None = None
    end_line: int | None = None

    @property
    def embedding_text(self) -> str:
        parts = [
            f"File: {self.file_path}",
            f"Language: {self.language}",
        ]
        if self.symbol_name:
            parts.append(f"Symbol: {self.symbol_name}")
        if self.symbol_type:
            parts.append(f"Symbol type: {self.symbol_type}")
        parts.append("Code:\n" + self.chunk_text)
        return "\n".join(parts)


def _semantic_chunks(text: str, file_path: str, language: str, prefix: str) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    start = 0
    idx = 0
    lines = text.splitlines()
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        piece = text[start:end].strip()
        if piece:
            start_line = text[:start].count("\n") + 1
            end_line = text[:end].count("\n") + 1 if lines else None
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    language=language,
                    chunk_id=f"{prefix}::semantic::{idx}",
                    chunk_text=piece,
                    symbol_type="semantic",
                    start_line=start_line,
                    end_line=end_line,
                )
            )
            idx += 1
        if end >= len(text):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _line_range(source: str, node: ast.AST) -> tuple[int | None, int | None]:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None:
        return None, None
    if end is None:
        lines = source.splitlines()
        end = min(start + 50, len(lines))
    return start, end


def _slice_source(source: str, start_line: int | None, end_line: int | None) -> str:
    if start_line is None:
        return source[:MAX_CHUNK_CHARS]
    lines = source.splitlines()
    start_idx = max(0, start_line - 1)
    end_idx = min(len(lines), end_line or start_line)
    text = "\n".join(lines[start_idx:end_idx])
    return text[:MAX_CHUNK_CHARS]


def chunk_python(source: str, file_path: str) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        logger.debug("Python parse failed for %s — semantic fallback", file_path)
        return _semantic_chunks(source, file_path, "python", file_path)

    idx = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start, end = _line_range(source, node)
            text = _slice_source(source, start, end)
            if not text.strip():
                continue
            symbol_type = "class" if isinstance(node, ast.ClassDef) else "function"
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    language="python",
                    chunk_id=f"{file_path}::{symbol_type}::{node.name}::{idx}",
                    chunk_text=text,
                    symbol_name=node.name,
                    symbol_type=symbol_type,
                    start_line=start,
                    end_line=end,
                )
            )
            idx += 1

    if not chunks:
        return _semantic_chunks(source, file_path, "python", file_path)
    return chunks


def _get_treesitter_parser(language: str):
    try:
        from tree_sitter_language_pack import get_language, get_parser
    except ImportError:
        return None, None

    lang_key = {
        "javascript": "javascript",
        "typescript": "typescript",
        "tsx": "tsx",
    }.get(language)
    if not lang_key:
        return None, None
    try:
        return get_parser(lang_key), get_language(lang_key)
    except Exception as exc:
        if _configure_project_treesitter_cache():
            try:
                return get_parser(lang_key), get_language(lang_key)
            except Exception as retry_exc:
                logger.debug("tree-sitter retry from project cache failed for %s: %s", language, retry_exc)
        if lang_key in {"javascript", "typescript"}:
            try:
                logger.debug("tree-sitter init failed for %s, falling back to tsx grammar: %s", language, exc)
                return get_parser("tsx"), get_language("tsx")
            except Exception as tsx_exc:
                logger.debug("tree-sitter tsx fallback init failed for %s: %s", language, tsx_exc)
        else:
            logger.debug("tree-sitter init failed for %s: %s", language, exc)
        return None, None


def _configure_project_treesitter_cache() -> bool:
    global _TREE_SITTER_CACHE_CONFIGURED
    if _TREE_SITTER_CACHE_CONFIGURED:
        return True

    try:
        from tree_sitter_language_pack import PackConfig, cache_dir, configure
    except ImportError:
        return False

    try:
        default_libs_dir = Path(cache_dir())
        default_version_dir = default_libs_dir.parent
        project_root = Path(__file__).resolve().parents[3]
        project_version_dir = project_root / ".cache" / "tree-sitter-language-pack" / default_version_dir.name
        project_libs_dir = project_version_dir / "libs"
        project_libs_dir.mkdir(parents=True, exist_ok=True)

        for name in ("manifest.json", "bundles"):
            src = default_version_dir / name
            dst = project_version_dir / name
            if not src.exists() or dst.exists():
                continue
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

        configure(PackConfig(cache_dir=str(project_libs_dir)))
        _TREE_SITTER_CACHE_CONFIGURED = True
        logger.info("Configured tree-sitter-language-pack cache: %s", project_libs_dir)
        return True
    except Exception as exc:
        logger.debug("Unable to configure project tree-sitter cache: %s", exc)
        return False


def _treesitter_symbol_types(language: str) -> set[str]:
    if language == "javascript":
        return {"function_declaration", "class_declaration", "method_definition", "lexical_declaration", "arrow_function"}
    return {"function_declaration", "class_declaration", "method_definition", "lexical_declaration"}


def _node_symbol_name(source: str, node, node_type, node_children, node_int) -> str | None:
    direct_name_types = {"identifier", "property_identifier", "type_identifier"}
    node_kind = node_type(node)

    for child in node_children(node):
        if node_type(child) in direct_name_types:
            return source[node_int(child, "start_byte") : node_int(child, "end_byte")]

    if node_kind == "lexical_declaration":
        for child in node_children(node):
            if node_type(child) != "variable_declarator":
                continue
            for grandchild in node_children(child):
                if node_type(grandchild) in direct_name_types:
                    return source[node_int(grandchild, "start_byte") : node_int(grandchild, "end_byte")]

    return None


def chunk_treesitter(source: str, file_path: str, language: str) -> list[CodeChunk]:
    parser, lang = _get_treesitter_parser(language)
    if parser is None or lang is None:
        return _semantic_chunks(source, file_path, language, file_path)

    try:
        tree = parser.parse(source)
    except Exception:
        return _semantic_chunks(source, file_path, language, file_path)

    root = tree.root_node() if callable(getattr(tree, "root_node", None)) else tree.root_node
    symbol_types = _treesitter_symbol_types(language)
    chunks: list[CodeChunk] = []
    idx = 0

    def node_type(node) -> str:
        value = getattr(node, "type", None)
        if value is None:
            value = getattr(node, "kind", None)
        return value() if callable(value) else str(value or "")

    def node_children(node):
        children = getattr(node, "children", None)
        if children is not None:
            return children
        count = getattr(node, "named_child_count", 0)
        count = count() if callable(count) else count
        child_fn = getattr(node, "named_child", None)
        if not child_fn:
            return []
        return [child_fn(i) for i in range(count)]

    def node_point(node, attr: str):
        value = getattr(node, attr, None)
        value = value() if callable(value) else value
        if value is None:
            return (0, 0)
        if hasattr(value, "row"):
            row = value.row() if callable(value.row) else value.row
            column = value.column() if callable(value.column) else value.column
            return (int(row or 0), int(column or 0))
        return value

    def node_int(node, attr: str) -> int:
        value = getattr(node, attr, 0)
        value = value() if callable(value) else value
        return int(value or 0)

    def walk(node):
        nonlocal idx
        kind = node_type(node)
        start_byte = node_int(node, "start_byte")
        end_byte = node_int(node, "end_byte")
        if kind in symbol_types and end_byte - start_byte >= MIN_TREE_SITTER_CHUNK_BYTES:
            start_point = node_point(node, "start_point")
            if start_point == (0, 0):
                start_point = node_point(node, "start_position")
            end_point = node_point(node, "end_point")
            if end_point == (0, 0):
                end_point = node_point(node, "end_position")
            start_row = start_point[0] + 1
            end_row = end_point[0] + 1
            text = source[start_byte:end_byte][:MAX_CHUNK_CHARS].strip()
            if text:
                name = _node_symbol_name(source, node, node_type, node_children, node_int)
                chunks.append(
                    CodeChunk(
                        file_path=file_path,
                        language=language,
                        chunk_id=f"{file_path}::{kind}::{idx}",
                        chunk_text=text,
                        symbol_name=name,
                        symbol_type=kind,
                        start_line=start_row,
                        end_line=end_row,
                    )
                )
                idx += 1
        for child in node_children(node):
            walk(child)

    walk(root)
    if not chunks:
        return _semantic_chunks(source, file_path, language, file_path)
    return chunks


def chunk_source_file(file_path: str, content: str) -> list[CodeChunk]:
    ext = "." + file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    language = SOURCE_EXTENSIONS.get(ext)
    if not language:
        return []

    if language == "python":
        return chunk_python(content, file_path)
    return chunk_treesitter(content, file_path, language)


def chunk_repository_files(files: Iterable[dict]) -> list[CodeChunk]:
    all_chunks: list[CodeChunk] = []
    for file_obj in files:
        path = file_obj.get("path") or file_obj.get("filename") or ""
        content = file_obj.get("content") or ""
        if not path or not content.strip():
            continue
        all_chunks.extend(chunk_source_file(path, content))
    return all_chunks
