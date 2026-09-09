# Self-improve rubric — performance weaknesses → instructions

Review at **start of each orchestrator cycle**. Update when a new failure mode appears.

## Observed weaknesses

| Weakness | Symptom | Cost |
|----------|---------|------|
| Serial exploration | One agent greps whole repo | Slow context, late findings |
| Plan without execute | Long markdown, no diff | User waits, no RAM gained |
| Monolithic edits | Huge `{{PROJECT_NAME}}.py` patches | Break tests, hard review |
| Safety after the fact | Reclaim merged then reviewed | Risk window |
| Memory in chat only | Re-explains CORE/AGENTS each turn | Token drag, inconsistency |
| Over-registering CLI | Registry before pass stable | Broken handlers |
| Automation drift | WORK_QUEUE ≠ self_improve_context | Wrong peer tasks |
| Slow self-check | Full tests every prompt | Use `--quick`; parallel metrics |
| Wrong template match | Bare `or`/`presence` steals scope (electron/chrome) | Agent edits wrong files |
| No cycle memory | Continuous re-dispatch same queue after "ok" | Re-plans completed/stuck work |
| Verify cosmetic | Agent exit 0 → install; no verify gate | Broken tests ship into next cycle |
| Truncate drops newest | Conversation format oldest-first | Last decisions lost under budget |
| Agent gap theater | Docs without running gates | `./scripts/peer plan-gate` / `done-gate` |
| Ungrounded ideas | Generic proposals without anchors | `./scripts/peer idea-articulate` + `idea-record` |

## Instructions to improve (orchestrator MUST)

1. **Parallel first** — If ≥2 independent subtasks, launch Task peers in one message before editing yourself.
2. **Notes before code** — Read `notes/SAFETY_GATES.md` + relevant module note; cite guard in PR/commit message.
3. **Minimal diff** — Prefer extending `ram_pass`, `ram_cli`, `contrib/` over growing `{{PROJECT_NAME}}.py`.
4. **Safety peer on yellow** — Any sweep/demote/freeze/jetsam/purge change → Safety peer BLOCK/PASS before merge.
5. **Verify always** — Never mark queue item done without unittest + footprint.
6. **Honest MB claims** — Say "unknown" unless measured; point to `ram status` metrics.
7. **Update WORK_QUEUE** — Check off with `[x]` in both WORK_QUEUE and `self_improve_context.md`.
8. **Teacher mode** — After editing `scripts/*`, run `peer_orchestrate.py --self-check` and `tests/test_automation.py`.

## Automation (scripts teach themselves)

| Check | When |
|-------|------|
| `python3 scripts/peer_orchestrate.py --self-check` | After any automation edit |
| `python3 -m unittest tests.test_automation -v` | Same |
| Queue drift warnings | Sync WORK_QUEUE ↔ self_improve_context |
| Template match | Backtick modules + specific keywords beat bare `presence` |
| Last cycle block | `peer-loop-state.json` → next prompt retrospect |
| Post-agent verify | `run_verify_commands` before `ram install` / continuous |
| Plan gate | `./scripts/peer plan-gate --role ROLE` before first edit |
| Done gate | `./scripts/peer done-gate --expected ... --actual ...` before DONE |
| Noop backoff | Same queue fingerprint after ok → 120s hold |

See `notes/AUTOMATION.md`.

## Speed heuristics

- **Hot path:** `ram once`, `ram status`, launchd → footprint + lazy imports trump new features
- **Cold path:** tier-2 diagnostics → contrib only
- **Blocked on harm:** design mitigation in Safety peer; do not ship "flag day" guard later

## Intelligence heuristics

- Reuse `iter_pass_targets` instead of copy-paste loops
- Register CLI via `extra_apply` for special flags
- When unsure about product rule → `ram_experience.py` + AGENTS.md, not guess
- **Clever before obvious** — CREATIVE_RECLAIM experiments beat WORK_QUEUE chores; mine new wins before declaring done
- Set `## Loop: exhausted` only when audit finds zero non-obvious compress-in-place paths left

## Score self each cycle (1–5)

| Dimension | Question |
|-----------|----------|
| Speed | Did peers run in parallel? |
| Safety | Any yellow change without pre-review? |
| Value | Did change target RAM_VALUE_STACK tier 1–2? |
| Lean | Import RSS still &lt;budget MB? |
| Done | Tests green + queue updated? |

If any ≤2 → next cycle prioritizes fixing that dimension before new features.
