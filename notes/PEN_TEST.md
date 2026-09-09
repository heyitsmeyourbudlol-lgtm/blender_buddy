# Pen-test / security hardening

_Updated 2026-09-06 21:54:56. Defensive scan only — remediate; never ship exploit PoCs._

## Summary

| Targets | Automation |
| Open findings | 0 |
| New this cycle | 0 |
| Enqueued | 0 |
| Agent | mechanical only |

## Scope

- Secrets in tree, tracked `.env`, service-role leaks
- Injection sinks: `eval`, `shell=True`, f-string SQL, HTML sinks
- Fail-open auth / secrets in query strings
- Product forge target (Newdrop/CaaS) when active

## Agent notes

_Pen Test Researcher appends dated bullets here._

## Commands

- `./scripts/peer pen-test` — scan + enqueue + optional agent
- `./scripts/peer pen-test-digest` — mechanical only
- `./scripts/peer pen-test-status` — last run
