# SOP — Self-heal success log (bottleneck id)

Owner niche: **Technical Writer** (doc) · heal code: Factory Engineer  
Related Active: `[kit] peer_self_heal: heal registry clear must log bottleneck id on success`  
Companion: `notes/SOP_DUAL_NAMESPACE_SELF_HEAL.md` (dual-ns PEER_LOG + log_fn)  
Needle: `OVERSEER_HEAL_REGISTRY_CLEAR_LOG_BOTTLENECK_ID_2026_09_04`

Factory meter phrase **self-heal registry clear** (factory_progress) means auto-healable bottlenecks were healed / history not stuck open — **not** a CLI verb. Do not invent `./scripts/peer registry-clear`.

## Contract (operators + Progress Monitor)

Two durable `log_fn` shapes must include the **bottleneck id** (never silent):

### 1. Live heal success (`apply_heals`)

```text
self-heal: <bottleneck_id> → <result>
```

- `<bottleneck_id>` is `Bottleneck.id` (e.g. `adapt_stale`, `missing_last_cycle`, `dual_brain_hub_peer`).
- Failure: `self-heal: <bottleneck_id> failed (…)`.
- Cooldown skip: must log `self-heal: <id> → cooldown (deferred)` (never silent).

### 2. History clear when scan no longer sees the id (`_merge_history`)

```text
self-heal registry clear: <bottleneck_id> (absent_from_scan)
```

- Emitted when an open history entry is closed because the live scan omitted that id.
- Land-proof needles also grep this exact prefix in `scripts/peer_self_heal.py`.

### 3. Cooldown deferral (must not be silent)

```text
self-heal: <bottleneck_id> → cooldown (deferred)
```

When progress fingerprint is idle ≥180s, high/critical heals may log:

```text
self-heal: <bottleneck_id> → cooldown bypass (progress stalled)
```

Needle: `OVERSEER_SELF_HEAL_PROGRESS_FP_2026_09_06`. Forever watcher: `scripts/peer_progress_watch.py`.

Silent success on either path is a defect — playbook ingest and oversight parse these token shapes.

## Code anchor

| Path | Role |
|------|------|
| `scripts/peer_self_heal.py` `_merge_history` (~1262) | `log(f"self-heal registry clear: {hid} (absent_from_scan)")` |
| `scripts/peer_self_heal.py` `apply_heals` (~2528) | `log(f"self-heal: {bn.id} → {result}")` after healer returns |
| `scripts/peer_self_heal.py` `_HEALERS` | id → healer dispatch |
| `tests/test_peer_self_heal.py` `TestPeerSelfHeal.test_apply_heals_logs_bottleneck_id_on_success` | asserts `self-heal: adapt_stale →` |
| `tests/test_peer_self_heal.py` `TestPeerSelfHeal.test_merge_history_marks_absent_ids_healed` | asserts `self-heal registry clear: unittest_storm` |

## Operator commands (real `./scripts/peer` only)

```bash
./scripts/peer self-heal         # scan + apply mechanical heals
./scripts/peer self-heal-scan    # detect only
./scripts/peer self-heal-status  # bottleneck registry table
./scripts/peer heal-all          # self-heal → compact → sync-queue → verify-gate
./scripts/peer green             # check + progress + self-heal-scan
./scripts/peer test-quick        # fast unittest after heal/doc land
```

Tail evidence:

```bash
rg "self-heal: .+ →|self-heal registry clear:" ~/.config/automation*/peer-loop.log
```

## Acceptance / verify (code niche)

```bash
./scripts/peer test-quick
# or targeted:
python3 -m unittest \
  tests.test_peer_self_heal.TestPeerSelfHeal.test_apply_heals_logs_bottleneck_id_on_success \
  tests.test_peer_self_heal.TestPeerSelfHeal.test_merge_history_marks_absent_ids_healed \
  -q
```

Expected: exit 0; arrow success log for a non-dual-ns heal **and** registry-clear log with bottleneck id.

QA smoke (peer-5): `notes/INTEGRATION_PROOF_SELF_HEAL_SUCCESS_LOG.md`.

## Do not

- Invent CLI verbs (`registry-clear`, `log-bottleneck`, etc.).
- Document only dual-ns / only the arrow form and imply the other path may stay silent.
- Cite a fictional test class (`HealTests`) — real class is `TestPeerSelfHeal`.
- Mark Active `[x]` from docs alone — Factory/QA land unittest + land-proof needles (Queue Steward closes WQ).

## Dual-ns note

Dual-namespace bootout still requires **two** surfaces (see companion SOP): apply_heals `log_fn` **and** PEER_LOG `self-heal dual-namespace bootout:`. This SOP covers the **shared** success / registry-clear tokens every heal path must emit with the bottleneck id.
