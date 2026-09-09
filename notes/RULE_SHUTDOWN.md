# Rule-change proposals (live mirror)

_Updated 2026-09-06T13:33:36Z_ · registry=`rule-shutdown-registry.json` · **propose-only** (nothing applies until human close)

Grouped **topic → severity**. Catalog: `notes/RULE_CATALOG.md` · UI: `http://127.0.0.1:8765/rules`

## Pending human review

_None._

## Commands

```bash
./scripts/peer rule-shutdown list --pending --by-topic
./scripts/peer rule-shutdown accept <id>   # human: apply change (edit sources yourself)
./scripts/peer rule-shutdown reject <id>   # human: keep current rule
./scripts/peer rule-shutdown-digest
```
