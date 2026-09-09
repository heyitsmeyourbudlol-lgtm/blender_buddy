# Session ledger (amnesia combat)

Needle: `OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07`

Write-through decisions land here as `YYYY-MM-DD.jsonl` (hub SoT). Chat dies; ledger stays.

- Append: `./scripts/peer session-ledger-append --decision "…" --paths a,b --needle NEEDLE`
- Claims: `notes/session_ledger/claims/YYYY-MM-DD.jsonl` via `./scripts/peer session-claim`
- Daily `*.jsonl` is local runtime (gitignored) — scrub secrets on write; never commit secrets.

See `notes/SOP_AGENT_REMEMBRANCE.md` · `scripts/peer_session_amnesia.py`.
