#!/usr/bin/env python3
"""One-shot: reopen ~126k teacher embed backlog for productive GPU util."""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import knowledge_index_config as kcfg  # noqa: E402

TARGET = 126_000
TEACHER = "state-spaces/mamba-2.8b-hf"


def main() -> int:
    db = kcfg.db_path()
    print(f"db={db}")
    for attempt in range(12):
        try:
            conn = sqlite3.connect(str(db), timeout=90)
            conn.execute("PRAGMA busy_timeout=90000")
            chunks = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
            before = int(
                conn.execute(
                    "SELECT COUNT(*) FROM chunk_embeddings WHERE model = ?",
                    (TEACHER,),
                ).fetchone()[0]
            )
            pending = max(0, chunks - before)
            print(f"attempt={attempt} chunks={chunks} done={before} pending={pending}")
            if pending >= TARGET:
                print(f"already have pending>={TARGET}")
                conn.close()
                return 0
            need = TARGET - pending
            cur = conn.execute(
                "DELETE FROM chunk_embeddings WHERE rowid IN ("
                "SELECT rowid FROM chunk_embeddings WHERE model=? "
                "ORDER BY rowid LIMIT ?)",
                (TEACHER, need),
            )
            conn.commit()
            left = int(
                conn.execute(
                    "SELECT COUNT(*) FROM chunk_embeddings WHERE model = ?",
                    (TEACHER,),
                ).fetchone()[0]
            )
            print(f"deleted={cur.rowcount} left={left} pending_est={chunks - left}")
            conn.close()
            return 0
        except sqlite3.OperationalError as exc:
            print(f"locked attempt={attempt}: {exc}")
            time.sleep(2.0)
    print("FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
