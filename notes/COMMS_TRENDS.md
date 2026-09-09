# Agent communication trends

_Updated 2026-09-08T20:19:28.651429+00:00_ · curated 8 · gaps 2 · partial 2_

Research input for **comms improve forever** (`automation_comms_improve.py`).

## Curated patterns

### [PARTIAL] Structured file bus (GLink) vs English

Text agents gain more from append-only JSONL buses than from natural-language standups.

- **Opportunity:** Extend GLink schema: binary refs, path hashes, REQ/ACK correlation ids.
- **Efficiency:** ~10–50× fewer tokens than prose status updates when agents use STAT/DIFF codes.
- **Sources:** https://techcrunch.com/2025/03/05/gibberlink-lets-ai-agents-call-each-other-in-robo-language/

### [GAP] GibberLink / GGWave (audio A2A)

Voice-channel agents can switch to GGWave tones; file-based agents should not copy audio.

- **Opportunity:** Document when to use GLink (disk) vs MCP (RPC) vs GGWave (voice) — no audio in peer_loop.
- **Efficiency:** GGWave wins on phone calls; JSONL bus wins on Cursor text peers.
- **Sources:** https://github.com/PennyroyalTea/gibberlink

### [HAVE] MCP / tool protocol for structured calls

GLink REQ→MCP landed (PROTOCOL=1): need=mcp:<tool> or need=mcp+args.tool → mcp=1 + args.tool; fixed codes vfy|adapt|heal|sync|assign|review|audit|comms|rsusp|rchg; free-text need rejected; open threads via materialize_open_reqs_mcp; bus records intent — Cursor MCP namespaces execute tools.

- **Opportunity:** Dogfood mcp:<tool> on bus for Cursor MCP namespaces; optional live RPC bridge later. Schema: glink_schema().mcp_prefix / validators.mcp_need.
- **Efficiency:** Schema-bound args beat free-text handoffs for verify/adapt triggers.
- **Sources:** https://modelcontextprotocol.io/, scripts/peer_agent_comms.py

### [HAVE] Shared blackboard + private scratchpads

Broadcast facts on a bus; keep todos/summaries in per-agent vaults.

- **Opportunity:** Auto-summarize bus → vault SUM lines; prune bus after N messages.
- **Efficiency:** O(1) append broadcast; agents read tail only.
- **Sources:** https://en.wikipedia.org/wiki/Blackboard_system

### [GAP] Compact encodings (msgpack / CBOR / columnar)

Beyond JSON: binary or columnar logs for high-frequency agent telemetry.

- **Opportunity:** Optional msgpack line mode for bus.jsonl when message rate > threshold.
- **Efficiency:** Smaller disk + parse cost at scale; JSONL fine until ~1k msgs/day.
- **Sources:** https://msgpack.org/

### [HAVE] Agent2Agent (A2A) task delegation

Cards/tasks with explicit capability negotiation between agents.

- **Opportunity:** Map GLink REQ/ACK to A2A-style task cards for cross-repo agents.
- **Efficiency:** Structured delegation reduces ambiguous handoffs.
- **Sources:** https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/

### [PARTIAL] Event-sourced agent memory

Append-only logs as source of truth; materialized views for dashboards.

- **Opportunity:** Dashboard /api/comms streams bus tail; materialize per-role last STAT.
- **Efficiency:** Replay bus to rebuild state without re-running agents.
- **Sources:** https://martinfowler.com/eaaDev/EventSourcing.html

### [HAVE] Hub-and-spoke vs mesh P2P

Orchestrator + shared bus beats N² direct chats for 8 fixed niches.

- **Opportunity:** Keep targeted GLink `to:` field; discourage English side-channels.
- **Efficiency:** 8 agents × bus read << 56 pairwise chat sessions.
- **Sources:** notes/OPERATING_SYSTEM.md

## Recent headlines (HN)

- [Show HN: Toq protocol – An open-source, agent-to-agent communication protocol](https://github.com/toqprotocol/toq) (2 pts)
- [Beacon Protocol – Agent-to-Agent Communication Protocol](http://50.28.86.131:8070/beacon/) (1 pts)
- [Show HN: Ziran, security testing for AI agents](https://github.com/taoq-ai/ziran) (1 pts)
- [A2H: A Protocol for Agent-to-Human Communication](https://www.twilio.com/en-us/blog/products/introducing-a2h-agent-to-human-communication-protocol) (2 pts)
- Show HN: A2A Protocol – Infrastructure for an Agent-to-Agent Economy (4 pts)
- [Show HN: AI-powered web service combining FastAPI, Pydantic-AI, and MCP servers](https://github.com/Aherontas/Pycon_Greece_2025_Presentation_Agents) (46 pts)
- [Show HN: Axon – A Kubernetes-native framework for AI coding agents](https://github.com/axon-core/axon) (1 pts)
- I Built LiveAuth: POW and Lightning Network Authentication for AI Agents (1 pts)
