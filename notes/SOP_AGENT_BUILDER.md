# SOP — Agent Builder (task → specialist in seconds)

Owner: **`agent_builder`**  
Needle: `OVERSEER_AGENT_BUILDER_2026_09_07`  
Script: `scripts/peer_agent_builder.py` · CLI: `./scripts/peer agent-build`

## Goal

Main factory spins specialist agents fast: **role + rules + reads + template + match + optional Cursor rule + vault stub** — mechanical, repeatable, **NO PAY** (free desktop / local / CLEAN only).

After provision, **queue items auto-route** via `match_rules` + `agent_roles.strengths` → `pick_role` / orchestrate dry-run / `agent-who`.

## Protocol (spec → validate → provision → self-check → dispatch)

| Step | Action | Verify |
|------|--------|--------|
| 1. **Spec** | Write JSON (or flags): `id`, `job_title`, `strengths[]`, `responsibilities`, `niche_task`, `reads[]`, `legacy_peer`, `safety_tier`, `prefer_remote`, `match` keywords, `template_prompt`, optional `always_apply_rule`, `domain_sme` | `./scripts/peer agent-build --validate <id>` or schema check on `--dry-run` |
| 2. **Validate** | Schema + NO-PAY refuse (paid/billing/Stripe without `--human-ack`) + id uniqueness / upsert-safe | exit 0; no other roles deleted |
| 3. **Provision** | `--write`: patch `scripts/peer_tasks.json` (`agent_roles` + `task_templates` + `match_rules`); optional vault `notes/agent_vaults/<id>/`; optional `.cursor/rules/<id>.mdc`; AUTOMATION.md row; domain SME if given | atomic replace of peer_tasks.json |
| 4. **Self-check** | `python3 scripts/peer_orchestrate.py --self-check` (auto after `--write` unless `--skip-self-check`) | ISSUES: none (or known soft) |
| 5. **Dispatch** | Prove assignment: `./scripts/peer agent-who "<matching task>"` → role + template; optional smoke Active line via `--enqueue-smoke` | role_id matches new specialist |

## Task → worker map

| Signal | Mechanism |
|--------|-----------|
| Queue text hits `match_rules[].any` | `template_match.match_template` → `task_templates.<id>` |
| Queue text hits `agent_roles[].strengths` | `peer_roles.pick_role` → specialist |
| Combined preview | `./scripts/peer agent-who "…"` |
| Live dry-run plan | `python3 scripts/peer_orchestrate.py --dry-run` / `./scripts/peer plan` |
| Peer ASN | `./scripts/peer assign --from … --to <role> --task "…"` (use agent-who first) |

```bash
# Build from flags (dry-run first)
./scripts/peer agent-build --dry-run \
  --id demo_widget_sme --title "Demo Widget SME" \
  --strengths "demo_widget,[demo-widget],widget SME" \
  --reads "notes/AGENT_WORKING_MEMORY.md,AGENTS.md" \
  --match "demo_widget,[demo-widget]" \
  --prompt "You own demo widget SME tasks only. NO PAY."

# Write for real
./scripts/peer agent-build --write --spec notes/agent_builder_specs/<id>.json [--enqueue-smoke]

# Who would get this task?
./scripts/peer agent-who "[demo-widget] fix tooltip copy"
./scripts/peer agent-build-list
./scripts/peer agent-build-validate agent_builder
```

## Do not

- Paid API / Stripe / billing roles without human `--human-ack`
- Delete or overwrite unrelated roles / templates / match_rules
- Jump ladder rungs (sequencing lock) — builder is kit capability, not Newdrop ship
- Invent work outside the new role’s `reads` / niche

## Related

- Roles SoT: `scripts/peer_tasks.json` · `notes/AGENT_ROLES.md`
- Remembrance / domain SMEs: `notes/SOP_AGENT_REMEMBRANCE.md`
- Commands: `notes/AGENT_COMMANDS.md` · `notes/HUB_PEER_VERBS.md`
