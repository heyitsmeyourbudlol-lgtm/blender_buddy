# Hallucination guard — self-aware strategy

_Updated 2026-09-08 16:16:24_ · assume drift imminent · strategize to defy

**Hallucination guard (self-aware — assume drift is imminent):**

You **will** hallucinate — wrong paths, APIs that do not exist, tests you did not
run, queue state you misremember. It is not *if*; treat it as **soon**.

**Self-awareness rule:** confidence without file:line evidence is a hallucination risk signal.

**Strategize to defy hallucination (mandatory before edit):**

Do not improvise from memory. **Write a 5-line strategy** naming evidence paths,
falsifier, and verify command — then execute the strategy.

| Strategy step | Defy tactic | Kit command |
|---------------|-------------|-------------|
| **Ground** | Read file:line yourself — never cite from recall | `rg` / Read tool |
| **Externalize** | Hot/warm/cold tiers — chat memory lies | `./scripts/peer memory-recall` |
| **Pinpoint** | One needle, one hypothesis | `./scripts/peer precision` habits |
| **Compare** | Expected vs actual output | `./scripts/peer output-compare` |
| **Diagnose** | System red ≠ your guess | `./scripts/peer diagnose` |
| **Falsify** | What proves you wrong? | `./scripts/peer check-questions` |
| **Teach** | Record only verified facts | `./scripts/peer learn-record` / `memory-record` |

**Strategy block (write before first edit):**

```
Assumption: I will hallucinate unless grounded.
Evidence:   <file:line or log I will read first>
Hypothesis: <one sentence fix>
Falsifier:  <observation that proves me wrong>
Verify:     <narrowest command>
Defy:       memory-recall + output-compare + diagnose if unsure
```

## Risk triggers

1. You "remember" a path but have not opened the file this cycle.
2. You claim verify passed without pasting exit code + key output line.
3. You describe queue state without reading WORK_QUEUE / TEAM_CONTEXT this cycle.
4. You name a function/API without `rg` proof in this repo.
5. You merge scope from another niche's assignment from chat context.
6. You feel confident — that is when to run `./scripts/peer diagnose`.

## Defy strategy checklist

1. **Read gate** — Open evidence file; quote ≤3 lines in Plan · `Read / rg`
2. **Memory gate** — Recall external journal before re-discovering · `./scripts/peer memory-recall`
3. **Precision gate** — Name needle file:line before edit · `PRECISION_HABITS / haystack Q`
4. **Compare gate** — State expected output; diff actual · `./scripts/peer output-compare`
5. **Diagnose gate** — Scan errors before blaming code · `./scripts/peer diagnose`
6. **Think gate** — Answer Plan + Done self-check · `./scripts/peer check-questions`
7. **BLOCK gate** — Unsure → GLink BLOCK, not guess · `peer_agent_comms MSG_BLOCK`

## Niche guards

### Factory Engineer
- grep callers before claiming function behavior.
- self-check output pasted or BLOCK — no "should pass".

### Orchestrator
- Hero memory collapse — re-read TEAM_CONTEXT assignments each dispatch.
- Do not assume peer DONE without GLink bus line this cycle.

### Output Researcher
- Defer external proof honestly — do not invent registry status.

### Queue Steward
- Drift: read both queue files — never sync from memory.

### Safety Auditor
- PASS requires file:line list you opened — not from prior review.

### Verify Runner
- Never claim flake without two-run evidence or log excerpt.
- First failure line must be pasted — not paraphrased.
