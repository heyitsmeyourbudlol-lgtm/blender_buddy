#!/usr/bin/env python3
"""One-shot INFRA fix: migrate embeddings, restart GPU/RAM holders."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
os.chdir(ROOT)

LOG = Path.home() / ".config" / "automation-hub" / "infra-fix-once.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as fh:
        fh.write(line + "\n")


def pkill(pattern: str) -> None:
    subprocess.run(["pkill", "-9", "-f", pattern], check=False)


def main() -> int:
    log("start infra fix")
    # Stop DB holders
    subprocess.run(["systemctl", "--user", "stop", "dgx-gpu-compute.service"], check=False)
    pkill("scripts/dgx_gpu_compute.py")
    pkill("scripts/knowledge_index.py --forever")
    time.sleep(2)

    import knowledge_index_config as k
    import sqlite3

    db = str(k.db_path())
    log(f"db={db}")
    conn = sqlite3.connect(db, timeout=60, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunk_embeddings_v2 (
          chunk_id INTEGER NOT NULL,
          model TEXT NOT NULL,
          dim INTEGER NOT NULL,
          quant TEXT NOT NULL DEFAULT 'float32',
          vector BLOB NOT NULL,
          updated_at REAL NOT NULL,
          PRIMARY KEY (chunk_id, model)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_v2_model ON chunk_embeddings_v2(model)"
    )
    copied = 0
    for i in range(80):
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO chunk_embeddings_v2
              (chunk_id, model, dim, quant, vector, updated_at)
            SELECT e.chunk_id, e.model, e.dim, COALESCE(e.quant,'float32'), e.vector, e.updated_at
            FROM chunk_embeddings e
            WHERE NOT EXISTS (
              SELECT 1 FROM chunk_embeddings_v2 v
              WHERE v.chunk_id=e.chunk_id AND v.model=e.model
            )
            LIMIT 5000
            """
        )
        n = cur.rowcount or 0
        if n <= 0:
            break
        copied += n
        if i % 5 == 0:
            log(f"copied +{n} total={copied}")
    old = conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
    new = conn.execute("SELECT COUNT(*) FROM chunk_embeddings_v2").fetchone()[0]
    log(f"progress {new}/{old}")
    if new >= old and old > 0:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DROP TABLE chunk_embeddings")
        conn.execute("ALTER TABLE chunk_embeddings_v2 RENAME TO chunk_embeddings")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model ON chunk_embeddings(model)"
        )
        conn.execute("COMMIT")
        log("CUTOVER DONE")
    else:
        log("partial — v2 ready for cascade writes")
    conn.close()

    # Start GPU
    subprocess.run(["systemctl", "--user", "start", "dgx-gpu-compute.service"], check=False)
    time.sleep(3)
    st = subprocess.run(
        ["systemctl", "--user", "is-active", "dgx-gpu-compute.service"],
        capture_output=True,
        text=True,
        check=False,
    )
    log(f"gpu_compute={st.stdout.strip()}")

    # Restart knowledge_index
    subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "knowledge_index.py"), "--forever"],
        stdout=open(Path.home() / ".config/automation-hub/knowledge-index.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    # RAM events holder
    if not subprocess.run(["pgrep", "-f", "dgx_ram_events.py --forever"], check=False).returncode == 0:
        subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "dgx_ram_events.py"), "--forever"],
            stdout=open(Path.home() / ".config/automation-hub/dgx-ram-events.log", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log("started ram_events")
    else:
        log("ram_events already up")

    # One fill cycle
    import dgx_ram_events as rev

    report = rev.handle_events(log_fn=log, skip_cursor_agent=True)
    log(f"ram handle actions={report.get('actions')} fp={report.get('footprint_gb')}")

    import dgx_resource_priority as rp

    snap = rp.snapshot()
    log(
        f"priority beeping={snap.get('beeping')} allowed={snap.get('development_allowed')} "
        f"worst={snap.get('worst_mode')} ram_fp={snap.get('ram',{}).get('footprint_gb')} "
        f"gpu_util={snap.get('gpu',{}).get('gpu_util_pct')} "
        f"eff={snap.get('gpu',{}).get('effective_util_pct')}"
    )
    Path("/tmp/infra_fix_snapshot.json").write_text(json.dumps(snap, indent=2))
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
