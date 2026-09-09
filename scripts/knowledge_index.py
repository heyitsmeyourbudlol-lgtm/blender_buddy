#!/usr/bin/env python3
"""Local knowledge index — FTS5 + hybrid dense/Mamba rerank on 2TB corpus."""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import knowledge_index_config as kcfg  # noqa: E402
import project_automation as auto  # noqa: E402


def _kmamba():
    """Lazy import — peer_loop must not pull torch/mamba at module import time."""
    import knowledge_mamba as kmamba  # noqa: E402

    return kmamba


def _stable_hex(raw: bytes, *, width: int = 64) -> str:
    """Non-crypto digest for chunk/file/cache keys.

    COMPRESSION_ZLIB_KNOWLEDGE_INDEX_2026_09_04 — eager ``hashlib`` pulled
    libcrypto (~4.9 MB r-xp) into every cold-memory import via peer_memory_span.
    Adler+CRC is enough for FTS chunk identity / hot-cache keys (not security).
    Hub re-land 2026-09-07 (peer-6 already zlib; live PYTHONPATH was hub).
    """
    parts: list[str] = []
    seed = raw
    while len("".join(parts)) < width:
        chunk = f"{zlib.adler32(seed) & 0xFFFFFFFF:08x}{zlib.crc32(seed) & 0xFFFFFFFF:08x}"
        parts.append(chunk)
        seed = seed + chunk.encode()
    return "".join(parts)[:width]


TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".json",
    ".jsonl",
    ".txt",
    ".rst",
    ".yaml",
    ".yml",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".toml",
    ".sql",
    ".sh",
}
SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache"}
MANIFEST_NAME = "manifest.json"
STATUS_NAME = "last_index.json"


@dataclass
class ChunkHit:
    source: str
    path: str
    text: str
    sparse_score: float
    hybrid_score: float = 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(source: str, path: str, chunk_idx: int, text: str) -> str:
    text_fp = _stable_hex(text.encode(), width=64)
    raw = f"{source}|{path}|{chunk_idx}|{text_fp}".encode()
    return _stable_hex(raw, width=64)


def _connect() -> sqlite3.Connection:
    kcfg.data_root().mkdir(parents=True, exist_ok=True)
    kcfg.corpus_root().mkdir(parents=True, exist_ok=True)
    kcfg.hot_cache_root().mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(kcfg.db_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS chunks (
          id INTEGER PRIMARY KEY,
          source TEXT NOT NULL,
          path TEXT NOT NULL,
          chunk_idx INTEGER NOT NULL,
          mtime REAL NOT NULL,
          fingerprint TEXT NOT NULL UNIQUE,
          text TEXT NOT NULL,
          bytes INTEGER NOT NULL DEFAULT 0
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
          text,
          path UNINDEXED,
          source UNINDEXED,
          tokenize='porter'
        );
        CREATE TABLE IF NOT EXISTS files (
          path TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          mtime REAL NOT NULL,
          size INTEGER NOT NULL,
          fingerprint TEXT NOT NULL
        );
        """
    )
    conn.commit()


def storage_bytes(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(SUM(bytes), 0) AS n FROM chunks").fetchone()
    return int(row["n"] if row else 0)


def storage_budget_exceeded(conn: sqlite3.Connection) -> bool:
    cap = int(kcfg.max_storage_gb() * 1024 * 1024 * 1024)
    return storage_bytes(conn) >= cap


def chunk_text(text: str) -> list[str]:
    size = kcfg.chunk_chars()
    overlap = kcfg.chunk_overlap()
    cleaned = text.replace("\r\n", "\n").strip()
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def _should_index_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    if any(part in SKIP_PARTS for part in path.parts):
        return False
    try:
        if path.stat().st_size > 8_000_000:
            return False
    except OSError:
        return False
    return True


def _iter_files(root: Path) -> Iterator[Path]:
    if not root.is_dir():
        return
    for path in root.rglob("*"):
        if _should_index_file(path):
            yield path


def _file_fingerprint(path: Path) -> str:
    st = path.stat()
    return _stable_hex(f"{path}:{st.st_mtime_ns}:{st.st_size}".encode(), width=64)


def _upsert_chunk(
    conn: sqlite3.Connection,
    *,
    source: str,
    path: str,
    chunk_idx: int,
    mtime: float,
    text: str,
) -> bool:
    if storage_budget_exceeded(conn):
        return False
    fp = _fingerprint(source, path, chunk_idx, text)
    payload = text.encode("utf-8", errors="replace")
    existing = conn.execute(
        "SELECT id FROM chunks WHERE fingerprint = ?",
        (fp,),
    ).fetchone()
    if existing:
        return False
    cur = conn.execute(
        """
        INSERT INTO chunks (source, path, chunk_idx, mtime, fingerprint, text, bytes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (source, path, chunk_idx, mtime, fp, text, len(payload)),
    )
    row_id = cur.lastrowid
    conn.execute(
        "INSERT INTO chunks_fts(rowid, text, path, source) VALUES (?, ?, ?, ?)",
        (row_id, text, path, source),
    )
    return True


def index_file(conn: sqlite3.Connection, *, source: str, path: Path) -> int:
    if not _should_index_file(path):
        return 0
    try:
        st = path.stat()
        fp = _file_fingerprint(path)
    except OSError:
        return 0
    row = conn.execute("SELECT fingerprint FROM files WHERE path = ?", (str(path),)).fetchone()
    if row and row["fingerprint"] == fp:
        return 0
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    conn.execute("DELETE FROM chunks WHERE path = ?", (str(path),))
    conn.execute("DELETE FROM chunks_fts WHERE path = ?", (str(path),))
    added = 0
    for idx, piece in enumerate(chunk_text(text)):
        if _upsert_chunk(
            conn,
            source=source,
            path=str(path),
            chunk_idx=idx,
            mtime=st.st_mtime,
            text=piece,
        ):
            added += 1
    conn.execute(
        """
        INSERT INTO files(path, source, mtime, size, fingerprint)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          source=excluded.source,
          mtime=excluded.mtime,
          size=excluded.size,
          fingerprint=excluded.fingerprint
        """,
        (str(path), source, st.st_mtime, st.st_size, fp),
    )
    return added


def _index_tree(conn: sqlite3.Connection, *, source: str, root: Path) -> int:
    total = 0
    for path in _iter_files(root):
        total += index_file(conn, source=source, path=path)
    return total


def _index_transcripts(conn: sqlite3.Connection) -> int:
    import peer_transcript as pt

    total = 0
    for root in pt.transcript_roots():
        total += _index_tree(conn, source="transcripts", root=root)
    return total


def _index_notes(conn: sqlite3.Connection) -> int:
    notes = auto.ROOT / "notes"
    return _index_tree(conn, source="notes", root=notes)


def _index_scripts(conn: sqlite3.Connection) -> int:
    return _index_tree(conn, source="scripts", root=SCRIPTS)


def _index_debrief(conn: sqlite3.Connection) -> int:
    total = 0
    for rel in ("notes/DEBRIEF_LOG.md", "notes/debrief-entries.jsonl"):
        path = auto.ROOT / rel
        if path.is_file():
            total += index_file(conn, source="debrief", path=path)
    return total


def _index_glink(conn: sqlite3.Connection) -> int:
    bus = auto.CONFIG_DIR / "agent-comms" / "bus.jsonl"
    if not bus.is_file():
        return 0
    return index_file(conn, source="glink", path=bus)


def _index_work_queue(conn: sqlite3.Connection) -> int:
    total = 0
    for rel in ("notes/WORK_QUEUE.md", "scripts/self_improve_context.md", "notes/PEER_CONVERSATION.md"):
        path = auto.ROOT / rel
        if path.is_file():
            total += index_file(conn, source="work_queue", path=path)
    return total


def _index_registry(conn: sqlite3.Connection) -> int:
    try:
        import factory_fanout as fanout
    except ImportError:
        return 0
    total = 0
    for entry in fanout.load_candidates():
        repo = Path(str(entry.get("resolved_path") or ""))
        if repo.is_dir():
            total += _index_tree(conn, source="registry", root=repo)
    return total


def _index_library(conn: sqlite3.Connection) -> int:
    total = 0
    for root in kcfg.library_corpus_paths():
        total += _index_tree(conn, source="library", root=root)
    for root in kcfg.extra_index_roots():
        total += _index_tree(conn, source="library", root=root)
    return total


_SOURCE_INDEXERS: dict[str, Callable[[sqlite3.Connection], int]] = {
    "transcripts": _index_transcripts,
    "notes": _index_notes,
    "scripts": _index_scripts,
    "debrief": _index_debrief,
    "glink": _index_glink,
    "work_queue": _index_work_queue,
    "registry": _index_registry,
    "library": _index_library,
}


def run_index_pass(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    conn = _connect()
    init_db(conn)
    report: dict[str, Any] = {"ts": _now_iso(), "sources": {}, "chunks_added": 0}
    for source in kcfg.sources():
        indexer = _SOURCE_INDEXERS.get(source)
        if not indexer:
            continue
        if storage_budget_exceeded(conn):
            log_fn(f"knowledge_index: storage cap {kcfg.max_storage_gb()}GB reached — skip {source}")
            break
        try:
            added = indexer(conn)
        except Exception as exc:  # noqa: BLE001
            log_fn(f"knowledge_index: {source} failed — {exc}")
            added = 0
        report["sources"][source] = added
        report["chunks_added"] += added
        conn.commit()
    report["storage_gb"] = round(storage_bytes(conn) / (1024**3), 3)
    report["chunk_count"] = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    conn.close()
    manifest = {
        "updated_at": report["ts"],
        "chunk_count": report["chunk_count"],
        "storage_gb": report["storage_gb"],
        "max_storage_gb": kcfg.max_storage_gb(),
        "mamba_model": kcfg.mamba_model(),
        "data_root": str(kcfg.data_root()),
    }
    kcfg.data_root().mkdir(parents=True, exist_ok=True)
    (kcfg.data_root() / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")
    (kcfg.data_root() / STATUS_NAME).write_text(json.dumps(report, indent=2) + "\n")
    return report


def _fts_query(query: str) -> str:
    tokens = [t for t in re.findall(r"[A-Za-z0-9_./-]{2,}", query) if t]
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens[:24])


def _search_sparse(conn: sqlite3.Connection, query: str, *, limit: int) -> list[dict[str, Any]]:
    fts_q = _fts_query(query)
    if not fts_q:
        return []
    rows = conn.execute(
        """
        SELECT c.source, c.path, c.text, bm25(chunks_fts) AS rank
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        WHERE chunks_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (fts_q, limit),
    ).fetchall()
    hits: list[dict[str, Any]] = []
    for row in rows:
        rank = float(row["rank"])
        sparse = 1.0 / (1.0 + max(0.0, rank))
        hits.append(
            {
                "source": row["source"],
                "path": row["path"],
                "text": row["text"],
                "sparse_score": sparse,
            }
        )
    return hits


def retrieve(
    query: str,
    *,
    top_k: int | None = None,
    hybrid: bool | None = None,
) -> list[ChunkHit]:
    """Sparse FTS retrieve; optional Mamba hybrid rerank.

    ``hybrid=False`` keeps FTS-only (peer_loop cold memory) so torch/mamba
    never enter the forever daemon. Default follows ``mamba_enabled()``.
    Always unload weights after hybrid rerank — residency belongs in
    ``dgx_gpu_compute``, not peer_loop / improve.
    """
    if not kcfg.enabled() or not query.strip():
        return []
    top_k = top_k or kcfg.retrieve_top_k()
    # Opt-in only — None/False => sparse. Never default-on from mamba_enabled().
    # COMPRESSION_2026_09_03 — memory-recall footgun loaded mamba-2.8b ≈26GB RSS.
    use_hybrid = bool(hybrid)
    # Cache key must distinguish sparse vs hybrid so peer_loop sparse hits
    # cannot freeze a prior mamba-ranked payload (and skip unload forever).
    cache_key = _stable_hex(f"{int(use_hybrid)}|{query}".encode(), width=16)
    cache_path = kcfg.hot_cache_root() / f"{cache_key}.json"
    if cache_path.is_file() and (time.time() - cache_path.stat().st_mtime) < 90:
        try:
            cached = json.loads(cache_path.read_text())
            return [ChunkHit(**item) for item in cached.get("hits", [])]
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    if not kcfg.db_path().is_file():
        return []
    conn = _connect()
    init_db(conn)
    candidates = _search_sparse(conn, query, limit=kcfg.retrieve_candidate_k())
    conn.close()
    if use_hybrid:
        kmamba = _kmamba()
        try:
            reranked = kmamba.rerank(query, candidates, top_k=top_k)
        finally:
            kmamba.unload()
    else:
        reranked = []
        for item in candidates[:top_k]:
            enriched = dict(item)
            sparse = float(enriched.get("sparse_score") or 0.0)
            enriched.setdefault("hybrid_score", sparse)
            reranked.append(enriched)
    hits = [
        ChunkHit(
            source=str(item.get("source") or ""),
            path=str(item.get("path") or ""),
            text=str(item.get("text") or ""),
            sparse_score=float(item.get("sparse_score") or 0.0),
            hybrid_score=float(item.get("hybrid_score") or 0.0),
        )
        for item in reranked
    ]
    try:
        cache_path.write_text(
            json.dumps(
                {
                    "query": query[:500],
                    "hybrid": use_hybrid,
                    "hits": [hit.__dict__ for hit in hits],
                }
            )
        )
    except OSError:
        pass
    return hits


def format_hits(hits: list[ChunkHit], *, max_chars: int | None = None) -> str:
    if not hits:
        return ""
    max_chars = max_chars or kcfg.max_inject_chars()
    lines = [
        "## Retrieved knowledge (local index — needle precision)",
        "",
        "Use these excerpts before re-reading whole files. Cite paths when acting.",
        "",
    ]
    used = 0
    for idx, hit in enumerate(hits, start=1):
        header = f"### [{idx}] `{hit.path}` ({hit.source}, score {hit.hybrid_score:.3f})"
        body = hit.text.strip()
        room = max_chars - used - len(header) - 8
        if room <= 120:
            break
        if len(body) > room:
            body = body[: room - 3] + "..."
        block = f"{header}\n\n{body}\n"
        lines.append(block)
        used += len(block)
    return "\n".join(lines).strip()


def ingest_path(path: Path, *, source: str = "library") -> dict[str, Any]:
    conn = _connect()
    init_db(conn)
    added = _index_tree(conn, source=source, root=path) if path.is_dir() else index_file(
        conn, source=source, path=path
    )
    conn.commit()
    report = {"path": str(path), "chunks_added": added, "storage_gb": round(storage_bytes(conn) / (1024**3), 3)}
    conn.close()
    return report


def status_report() -> dict[str, Any]:
    root = kcfg.data_root()
    manifest_path = root / MANIFEST_NAME
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            manifest = {}
    chunk_count = 0
    storage_gb = 0.0
    if kcfg.db_path().is_file():
        conn = _connect()
        init_db(conn)
        chunk_count = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        storage_gb = round(storage_bytes(conn) / (1024**3), 3)
        conn.close()
    return {
        "enabled": kcfg.enabled(),
        "data_root": str(root),
        "db_path": str(kcfg.db_path()),
        "chunk_count": chunk_count,
        "storage_gb": storage_gb,
        "max_storage_gb": kcfg.max_storage_gb(),
        "mamba_model": kcfg.mamba_model(),
        "mamba": _kmamba().status() if kcfg.mamba_enabled() else {"enabled": False, "loaded": False},
        "manifest": manifest,
    }


def _embed_backlog_pending() -> int:
    """Chunks awaiting L1 Mamba embed — indexer yields when backlog is large."""
    if not kcfg.mamba_enabled():
        return 0
    db = kcfg.db_path()
    if not db.is_file():
        return 0
    model = kcfg.cascade_student_model() if kcfg.mamba_cascade_enabled() else (kcfg.mamba_model() or "")
    if not model:
        return 0
    conn = _connect()
    try:
        total = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        done = int(
            conn.execute("SELECT COUNT(*) FROM chunk_embeddings WHERE model = ?", (model,)).fetchone()[0]
        )
        return max(0, total - done)
    finally:
        conn.close()


def run_forever() -> int:
    if not kcfg.enabled():
        print("knowledge_index: disabled in config", file=sys.stderr)
        return 0
    print(f"knowledge_index: forever — root {kcfg.data_root()} cap {kcfg.max_storage_gb()}GB")
    while True:
        pending = _embed_backlog_pending()
        if pending > 1000:
            print(
                f"{datetime.now().isoformat()}  knowledge_index: embed backlog {pending} "
                f"— skip index pass (yield GPU/DB to dgx-gpu-compute)"
            )
            time.sleep(min(600.0, kcfg.index_interval_sec()))
            continue
        report = run_index_pass()
        print(
            f"{datetime.now().isoformat()}  indexed +{report.get('chunks_added', 0)} chunks "
            f"({report.get('chunk_count', 0)} total, {report.get('storage_gb', 0)}GB)"
        )
        time.sleep(kcfg.index_interval_sec())


def main() -> int:
    parser = argparse.ArgumentParser(description="Local knowledge index — FTS + Mamba hybrid")
    parser.add_argument("--index", action="store_true", help="Run one indexing pass")
    parser.add_argument("--forever", action="store_true", help="Daemon indexing loop")
    parser.add_argument("--query", default="", help="Retrieve query")
    parser.add_argument("--top-k", type=int, default=0)
    parser.add_argument("--hybrid", action="store_true", help="Opt into Mamba rerank")
    parser.add_argument("--ingest", default="", help="Ingest a file or directory into library corpus")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.status:
        report = status_report()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(
                f"knowledge_index: {'on' if report['enabled'] else 'off'} "
                f"chunks={report['chunk_count']} storage={report['storage_gb']}GB/"
                f"{report['max_storage_gb']}GB root={report['data_root']}"
            )
        return 0
    if args.ingest:
        target = Path(args.ingest).expanduser()
        report = ingest_path(target)
        print(json.dumps(report, indent=2) if args.json else report)
        return 0 if target.exists() else 1
    if args.query:
        hits = retrieve(args.query, top_k=args.top_k or None, hybrid=bool(getattr(args, "hybrid", False)))
        if args.json:
            print(json.dumps([hit.__dict__ for hit in hits], indent=2))
        else:
            print(format_hits(hits))
        return 0
    if args.forever:
        return run_forever()
    report = run_index_pass()
    print(json.dumps(report, indent=2) if args.json else report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
