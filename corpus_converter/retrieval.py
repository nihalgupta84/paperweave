"""Dependency-free local lexical and sparse-vector retrieval."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from .io import read_json, read_jsonl

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{1,}")
VECTOR_DIMENSIONS = 512


def tokenize(text: str) -> list[str]:
    """Return normalized scientific-search tokens."""
    return [token.casefold() for token in TOKEN_PATTERN.findall(text)]


def _vector(tokens: list[str], document_frequencies: dict[str, int], document_count: int) -> dict[int, float]:
    counts = Counter(tokens)
    values: dict[int, float] = {}
    for token, count in counts.items():
        dimension = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big") % VECTOR_DIMENSIONS
        weight = (1.0 + math.log(count)) * (
            math.log((document_count + 1) / (document_frequencies.get(token, 0) + 1)) + 1.0
        )
        values[dimension] = values.get(dimension, 0.0) + weight
    norm = math.sqrt(sum(value * value for value in values.values())) or 1.0
    return {key: value / norm for key, value in values.items()}


def _cosine(left: dict[int, float], right: dict[int, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())


def build_search_index(corpus: Path) -> dict[str, Any]:
    """Build an atomic SQLite FTS5 plus hashed TF-IDF block index."""
    index_dir = corpus / "indexes"
    index_dir.mkdir(parents=True, exist_ok=True)
    target = index_dir / "search.sqlite3"
    temporary = index_dir / ".search.sqlite3.tmp"
    if temporary.exists():
        temporary.unlink()

    rows: list[dict[str, Any]] = []
    frequencies: Counter[str] = Counter()
    for paper_dir in sorted((corpus / "papers").glob("doc_*")):
        document = read_json(paper_dir / "document.json", {})
        blocks = read_jsonl(paper_dir / "sections.jsonl") or read_jsonl(paper_dir / "blocks.jsonl")
        for block in blocks:
            text = block.get("text", "").strip()
            if not text:
                continue
            tokens = tokenize(text)
            frequencies.update(set(tokens))
            rows.append(
                {
                    "work_id": document.get("work_id", ""),
                    "document_id": document.get("document_id", paper_dir.name),
                    "block_id": block.get("block_id", ""),
                    "title": document.get("title", ""),
                    "section": block.get("section_role") or " > ".join(block.get("section_path") or []),
                    "page_index": block.get("page_index"),
                    "text": text,
                    "tokens": tokens,
                }
            )

    connection = sqlite3.connect(temporary)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute(
            "CREATE TABLE blocks (id INTEGER PRIMARY KEY, work_id TEXT, document_id TEXT, block_id TEXT, "
            "title TEXT, section TEXT, page_index INTEGER, text TEXT, vector_json TEXT)"
        )
        fts5 = True
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE blocks_fts USING fts5(title, section, text, content='blocks', content_rowid='id')"
            )
        except sqlite3.OperationalError:
            fts5 = False
        document_count = len(rows)
        for row in rows:
            vector = _vector(row.pop("tokens"), frequencies, document_count)
            cursor = connection.execute(
                "INSERT INTO blocks(work_id, document_id, block_id, title, section, page_index, text, vector_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (*row.values(), json.dumps(vector, separators=(",", ":"))),
            )
            if fts5:
                connection.execute(
                    "INSERT INTO blocks_fts(rowid, title, section, text) VALUES (?, ?, ?, ?)",
                    (cursor.lastrowid, row["title"], row["section"], row["text"]),
                )
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            (
                ("document_count", str(document_count)),
                ("document_frequencies", json.dumps(frequencies, separators=(",", ":"))),
                ("fts5", "1" if fts5 else "0"),
                ("vector_kind", "hashed_tfidf_v1"),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    temporary.replace(target)
    return {
        "blocks": len(rows),
        "documents": len({row["document_id"] for row in rows}),
        "index": str(target),
        "fts5": fts5,
    }


def _row_result(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "work_id": row["work_id"],
        "document_id": row["document_id"],
        "block_id": row["block_id"],
        "title": row["title"],
        "section": row["section"],
        "page_index": row["page_index"],
        "text": row["text"],
    }


def search_corpus(corpus: Path, query: str, limit: int = 10, mode: str = "hybrid") -> dict[str, Any]:
    """Search normalized blocks using lexical, sparse-vector, or fused ranking."""
    if mode not in {"hybrid", "lexical", "vector"}:
        raise ValueError(f"Unsupported search mode: {mode}")
    index = corpus / "indexes" / "search.sqlite3"
    if not index.exists():
        build_search_index(corpus)

    connection = sqlite3.connect(index)
    connection.row_factory = sqlite3.Row
    try:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        rows = connection.execute("SELECT * FROM blocks").fetchall()
        frequencies = json.loads(metadata.get("document_frequencies", "{}"))
        query_vector = _vector(tokenize(query), frequencies, int(metadata.get("document_count", "0")))

        vector_scores = {
            row["id"]: _cosine(query_vector, {int(key): value for key, value in json.loads(row["vector_json"]).items()})
            for row in rows
        }
        lexical_scores: dict[int, float] = {}
        query_tokens = tokenize(query)
        if query_tokens and metadata.get("fts5") == "1":
            expression = " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in query_tokens)
            matches = connection.execute(
                "SELECT rowid, bm25(blocks_fts) AS score FROM blocks_fts WHERE blocks_fts MATCH ? ORDER BY score LIMIT ?",
                (expression, max(limit * 20, 100)),
            ).fetchall()
            lexical_scores = {row["rowid"]: 1.0 / rank for rank, row in enumerate(matches, start=1)}
        elif query_tokens:
            query_set = set(query_tokens)
            lexical_scores = {
                row["id"]: len(query_set.intersection(tokenize(row["title"] + " " + row["text"]))) / len(query_set)
                for row in rows
            }

        ranked = []
        for row in rows:
            lexical = lexical_scores.get(row["id"], 0.0)
            vector = vector_scores.get(row["id"], 0.0)
            score = lexical if mode == "lexical" else vector if mode == "vector" else 0.45 * lexical + 0.55 * vector
            if score <= 0:
                continue
            ranked.append((_row_result(row), lexical, vector, score))
        ranked.sort(key=lambda item: item[3], reverse=True)
        results = []
        for item, lexical, vector, score in ranked[:limit]:
            results.append(
                {**item, "lexical_score": round(lexical, 6), "vector_score": round(vector, 6), "score": round(score, 6)}
            )
        return {"query": query, "mode": mode, "count": len(results), "results": results}
    finally:
        connection.close()
