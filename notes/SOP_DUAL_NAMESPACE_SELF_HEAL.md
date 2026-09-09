# SOP — Dual-namespace LaunchAgent self-heal

Owner niche: **Technical Writer** (doc) · heal code: Factory Engineer  
Needle: `OVERSEER_DUAL_NAMESPACE_BOOTOUT_LOG_2026_09_04`

When hub and kit LaunchAgent labels both run (dual-brain), mechanical heal bootouts the rogue labels and must leave durable log evidence.

## Symptoms

- Bottleneck id `dual_brain_hub_peer` (also `dual_brain_hub_improve` / oversight twins)
- Playbook / cycle ingest: `self-heal: dual_brain_hub_peer → stopped …`
- Factory meter: dual brain / single peer brain not 100%

## What the kit does

1. Scan emits bottleneck `dual_brain_hub_peer` when rogue peer/improve labels collide (`scripts/peer_self_heal.py`).
2. Healer `_heal_dual_namespace_collision` calls `_bootout` on collision labels.
3. Two log surfaces (both required for operators vs tests):
   - **PEER_LOG** (`~/.config/<ns>/peer-loop.log`): `self-heal dual-namespace bootout: …` via `_log_dual_namespace_heal_action`
   - **apply_heals `log_fn`**: `self-heal: dual_brain_hub_peer → <bootout result>`

## Operator commands (real `./scripts/peer` only)

```bash
./scripts/peer heal-all          # self-heal → compact → sync-queue → verify-gate
./scripts/peer self-heal         # scan + apply mechanical heals
./scripts/peer self-heal-scan    # detect only
./scripts/peer green             # check + progress + self-heal-scan
./scripts/peer test-quick        # fast unittest gate after heal/doc land
```

Tail evidence (path from config dir):

```bash
# peer-loop.log under CONFIG_DIR (PEER_LOG in peer_self_heal.py)
rg "self-heal dual-namespace bootout:|self-heal: dual_brain_hub_peer" ~/.config/automation*/peer-loop.log
```

## Acceptance / verify

```bash
python3 -m unittest \
  tests.test_peer_self_heal.TestPeerSelfHeal.test_apply_heals_dual_brain_hub_peer_logs_log_fn \
  tests.test_peer_self_heal.TestPeerSelfHeal.test_heal_dual_namespace_bootout_logs_peer_log \
  -q
```

Expected: exit 0; AC token `self-heal: dual_brain_hub_peer →` asserted on `log_fn`.

QA smoke: `notes/INTEGRATION_PROOF_DUAL_NS_BOOTOUT_LOG.md` (PASS closed).

## Do not

- Invent new CLI verbs — use `heal-all` / `self-heal` / `test-quick` only.
- Treat apply_heals stdout alone as enough for operators — PEER_LOG is the durable trail.
- Re-open Active when land-proof + unittests are green (see WORK_QUEUE landed lines).

## Anchors

| Path | Role |
|------|------|
| `scripts/peer_self_heal.py` `_log_dual_namespace_heal_action` | PEER_LOG append |
| `scripts/peer_self_heal.py` `apply_heals` | `log(f"self-heal: {bn.id} → {result}")` |
| `scripts/peer_self_heal.py` `_HEALERS["dual_brain_hub_peer"]` | dispatch |
| `tests/test_peer_self_heal.py` `test_apply_heals_dual_brain_hub_peer_logs_log_fn` | log_fn AC |
| `tests/test_peer_self_heal.py` `test_heal_dual_namespace_bootout_logs_peer_log` | PEER_LOG AC |
