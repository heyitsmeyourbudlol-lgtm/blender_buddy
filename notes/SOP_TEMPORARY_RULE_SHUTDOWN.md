# SOP — Rule-change proposals (add / remove / modify / suspend)

Owner niche: **Technical Writer** (doc) · Progress Monitor (daily digest review)  
Companion: `notes/RULE_SHUTDOWN.md` · digest: `notes/RULE_SHUTDOWN_DIGEST.md`  
Needle: `OVERSEER_RULE_CHANGE_PROPOSE_ONLY_2026_09_06`

Agents may **propose** rule changes when a documented rule impedes progress or should be added/edited. **Nothing applies until a human closes** the proposal. Rules stay **ON** the entire time.

## Actions

| `action` | Meaning | Human close |
|----------|---------|-------------|
| `suspend` | Temporarily stop applying a kit/Cursor/SOP rule | `accept` → you edit sources / habits; `reject`/`reinstate` → keep rule |
| `add` | Request a new documented rule | `accept` → human adds text; `reject` → drop |
| `remove` | Request deleting a rule | `accept` → human deletes; `reject` → keep |
| `modify` | Request editing rule text | `accept` → human edits; `reject` → keep |

## Lifecycle (propose-only)

```text
draft  --(≥2 niches OR overseer ACK)-->  proposed  --(human)-->  made_permanent | rejected | reinstated
```

- **draft / proposed:** pending human review — Hot memory lists them; agents must **still apply** the rule.
- **made_permanent:** human accepted; human (or follow-up task) edits the source rule. Tool does **not** auto-edit `.mdc` / SOPs.
- **rejected / reinstated:** proposal dropped; rule unchanged.

## Scope

All documented rules: SOPs, playbooks, AGENTS.md prefs, `.cursor/rules`, notes habits.

**Catalog:** `notes/RULE_CATALOG.md` — every known rule listed **topic → severity**
(`critical` / `high` / `medium` / `low`; SAFETY_GATES `red`/`yellow`/`green` map to
critical/medium/low). Proposals must carry `topic` + `severity` (CLI `--topic` / `--severity`
or inferred). Digest + mirror + `./scripts/peer rule-shutdown list --by-topic` use the
same order. Dashboard: `http://127.0.0.1:8765/rules` (search + filters).

**Denylist (mute/remove never auto-applies):** safety RED/HITL, secrets/env scrub, kit-export no-local-secrets, illegal/child/weapons, `safety_tier=red`, paths under `.cursor/rules` when matched by denylist patterns. Agents **may still propose/question** these (`denylist_blocked=true`) — questioning boundaries is allowed; auto-mute is not.

## GLink (structured, not English standup)

```text
REQ need=rsusp  args.act=sus args.rid=<rule_id> args.why=<code>
REQ need=rchg   args.act=add|rm|mod|sus args.rid=<rule_id> args.why=<code>
ACK  id=rs-…    (second niche / progress_monitor)
```

Aliases: `rule_suspend`→`rsusp`, `rule_change`→`rchg`.

## Operator commands

```bash
./scripts/peer rule-shutdown propose --rule-id habit:never_solo --action suspend \
  --from factory_engineer --reason "blocks parallel land"
./scripts/peer rule-shutdown ack --id rs-… --from progress_monitor
./scripts/peer rule-shutdown list --pending
./scripts/peer rule-shutdown-digest          # daily review surface
./scripts/peer rule-shutdown accept <id>     # human: will apply by editing sources
./scripts/peer rule-shutdown reject <id>     # human: keep as-is
./scripts/peer rule-shutdown reinstate <id>  # suspend → keep rule
./scripts/peer standup                       # includes rule-shutdown-digest
```

## Do not

- Auto-disable `.cursor/rules` or SOPs from the registry.
- Treat pending proposals as active mutes in Hot memory.
- Invent CLI verbs beyond `./scripts/peer rule-shutdown*`.
- Drop denylist proposals silently — keep them visible for human review.
