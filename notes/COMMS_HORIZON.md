# Comms horizon — agent communication efficiency

_Updated 2026-09-08 16:21:59 · cycle 1021_ · comms improve forever

**North star:** Minimum tokens + maximum signal between 8 niches: structured GLink bus, per-agent vaults, targeted REQ/ACK — never English standups on the hot path.

## Live

| Signal | Value |
|--------|-------|
| Self-test | **GREEN** — green light — comms kit self-tests passed |
| GLink | enabled=True · bus=291 msgs |
| Research | gaps 2 · partial 2 |
| Queue | launch · 1 open |

## NOW — efficiency first

1. **[better]** [comms] Structured file bus (GLink) vs English
   - Extend GLink schema: binary refs, path hashes, REQ/ACK correlation ids. — ~10–50× fewer tokens than prose status updates when agents use STAT/DIFF codes.
   - priority `12`
2. **[efficiency]** [comms] GibberLink / GGWave (audio A2A)
   - Document when to use GLink (disk) vs MCP (RPC) vs GGWave (voice) — no audio in peer_loop. — GGWave wins on phone calls; JSONL bus wins on Cursor text peers.
   - priority `40`
3. **[efficiency]** [comms] Compact encodings (msgpack / CBOR / columnar)
   - Optional msgpack line mode for bus.jsonl when message rate > threshold. — Smaller disk + parse cost at scale; JSONL fine until ~1k msgs/day.
   - priority `45`

## GLink REQ → MCP

Landed on hub `scripts/peer_agent_comms.py` (PROTOCOL_VERSION=1, additive — no bump).

| Form | Result |
|------|--------|
| `need=mcp:<tool>` | `mcp=1`, `args.tool=<tool>` |
| `need=mcp` + `args.tool` | same after `_normalize_req_need` |
| fixed `vfy\|adapt\|heal\|…` | niche REQ (not MCP) |
| free-text need | **rejected** |
| ACK `cid\|ref` | closes open REQ (`materialize_open_reqs_mcp`) |

Disk bus = structured intent; Cursor MCP namespaces = tool execution. See `notes/COMMS_TRENDS.md` **[HAVE] MCP / tool protocol**.

## Research map

See `notes/COMMS_TRENDS.md` · refresh: `python3 scripts/automation_comms_research.py --refresh --write`

## Commands

```bash
./scripts/peer comms-improve-status
./scripts/peer comms
./scripts/peer comms-bus
curl http://127.0.0.1:8765/api/comms
```

