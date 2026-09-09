# Precision habits — needle in a haystack

_Updated 2026-09-08 16:16:24_ · all models · develop surgical accuracy every cycle

**Precision habits** — needle-in-a-haystack (every agent, every model):

Develop **surgical accuracy** over time. The repo is the haystack; your job is the **needle** — one root cause, one minimal diff, one verified outcome.

**Habit stack (build these every cycle):**
1. **Locate** — shrink the search space before reading randomly (stack trace → file:line → grep unique symbol).
2. **Isolate** — reproduce with the **smallest** surface (one test, one command, one log tail).
3. **Pinpoint** — name the needle in writing: "The bug is `_foo` in `path:line` because ___."
4. **Touch one** — edit ≤1 file first; run targeted verify; then expand only if needed.
5. **Measure** — report `{files, lines, test}` in GLink DONE; **compare expected vs actual output** before DONE; reject your own diff if scope ballooned.

**Needle-in-a-haystack method (mandatory workflow):**

```
Symptom → evidence path → grep/read ≤3 files → hypothesis (1 sentence)
    → single-file minimal fix → targeted verify → full verify → learn-record
```

| Step | Precision rule |
|------|----------------|
| Search | `rg` / grep with **specific** symbols — never bare marker searches or whole-repo skim |
| Read | Read **±40 lines** around the needle — not entire modules |
| Hypothesis | One active hypothesis; falsify before switching |
| Edit | Default **≤15 lines** changed unless assignment requires more — justify in Plan |
| Verify | Run **narrowest** test first (`pytest path::test` / one script), then gate |
| Abort | If >3 files touched before green verify — stop, revert scope, re-pinpoint |

## Haystack questions

1. Where is the **needle** (exact file:line or config key) — not the haystack (whole subsystem)?
2. What **single** grep or log line proved it — did I read that line myself?
3. Can I fix it in **one file** first — what would break if I'm wrong?
4. Did I name the needle in one sentence before editing?
5. After edit: files/lines touched — is this still surgical?

## Model tiers

### inherit
- Do not explore the whole repo — **3-file read budget** before first edit.
- Prefer inherited repo conventions over inventing new patterns.
- Parallel breadth is for orchestrator — you stay on one needle.

### composer-2.5-fast
- Speed ≠ sloppiness — **same read gates** as slower models; never skip file:line.
- Shell/verify role: run commands precisely; capture **first** failure line only.
- No bulk sed/replace without ripgrep proof of unique match count.

### default
- Subagent type does not relax precision — locate → pinpoint → touch one.
- If unsure, post GLink REQ with exact file:line question — don't guess.


## Subagent types

### shell
- Output is the measurement — copy exact failing line, exit code, command.
- No code edits unless assignment explicitly scopes test fixtures.

### generalPurpose
- Implementation peers: ≤3 files before first targeted verify.

### explore
- Explore to **narrow**, not to refactor — return file:line map, then stop exploring.

### web-researcher
- Research cites **repo file:line** for kit changes — not generic blog advice.

### security-review
- Precision = PASS/BLOCK with **file:line + gate id** — zero vague warnings.


## Niche needle focus

### Adapt Specialist
- Needle = adapt audit finding category + path — heal that path only first.

### Command Builder
- Needle = one compound command replacing one logged loop pattern.

### Communications Engineer
- Needle = one hot path byte/token win with before/after count.

### Compression Engineer
- Needle = one cache/TTL knob with measured MB delta.

### Efficiency Researcher
- Needle = one hot path with metric proof — one file-scoped diff.

### Factory Engineer
- Pinpoint dispatch bug in peer_loop/orchestrate — don't rewrite both.
- One mechanical fix per cycle (wake, noop, verify gate) — measure factory %.

### Integration Architect
- Needle = one registry repo + one worktree verify failure — not hub-wide adapt.

### Output Researcher
- Needle = one registry step toward proof — honest deferral if not executable.

### Pen Test Researcher
- Needle = one fail-open/secret/injection at file:line — harden fail-closed.

### Queue Steward
- Needle = one drift line or one theater marker — sync pair, don't rewrite queue essay.

### Safety Auditor
- Needle = one gate violation at one line — or explicit PASS with files reviewed list.

### Verify Runner
- Needle = first failing test **file:line** — ignore downstream failures until fixed.
