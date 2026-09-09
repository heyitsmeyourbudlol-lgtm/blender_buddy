# Import peer automation kit

Portable **Cursor peer loop** — parallel agent orchestration, forever loop, self-check teacher mode.

## Quick import

From your **target repo root**:

```bash
# Option A — copy folder from ram-park (or extract automation-kit.tar.gz)
cp -R /path/to/ram/automation-kit/. .

# Option B — run installer (copies + merges)
/path/to/ram/automation-kit/install.sh /path/to/your-repo
```

Then customize and verify:

```bash
# 1. Edit project identity + hooks
$EDITOR automation.config.json

# 2. Self-check
python3 scripts/peer_orchestrate.py --self-check
python3 -m unittest tests.test_automation -v

# 3. Optional — start forever loop (background, $0)
./scripts/peer-loop-run
# or daemon:
python3 scripts/peer_loop.py --install
./scripts/peer-watch   # WORKING vs IDLE dashboard
```

## What you get

| Piece | Purpose |
|-------|---------|
| `scripts/peer_orchestrate.py` | Decompose queue → parallel peer prompt |
| `scripts/cursor_self_improve.py` | Build + save peer prompt |
| `scripts/peer_loop.py` | Forever loop — kqueue wake on transcript + git |
| `scripts/peer_watch.py` | Terminal dashboard |
| `scripts/project_automation.py` | Queue parsing, metrics, cache |
| `scripts/automation_adapt.py` | Detect stack, heal drift, install kit, export bundle |
| `scripts/bundle_automation_kit.py` | Write `dist/automation-kit-*.tar.gz` |
| `scripts/peer_tasks.json` | Peer roles + task templates (customize!) |
| `notes/WORK_QUEUE.md` | Live queue (sync with self_improve_context) |
| `.cursor/rules/plan-to-peer-tasks.mdc` | Plan doc → queue automation |

## Adapt to any project (self-heal)

```bash
# Probe what the kit would configure (JSON)
python3 scripts/automation_adapt.py --probe

# Apply detected config + sync queue drift + repair missing files
python3 scripts/automation_adapt.py --heal --write
# or:
./scripts/peer adapt

# Install into another repo (copy kit + adapt)
python3 scripts/automation_adapt.py --install /path/to/repo --profile node
./install.sh --profile caas /path/to/repo

# Export portable tarball
python3 scripts/bundle_automation_kit.py --tar
# or:
./scripts/peer export
```

`automation_adapt.py` detects stack (node/python/ram/caas/rust/go), probes package managers and CI for working verify commands, writes a dynamic `profiles/local.json` overlay (module_scope + match_rules), syncs queue drift, and re-adapts when git fingerprint changes.

```bash
./scripts/peer adapt        # quick — skip re-probe if git unchanged
./scripts/peer adapt-deep   # full re-probe + rewrite local profile
```

## Configure `automation.config.json`

```json
{
  "project_name": "My App",
  "project_slug": "my-app",
  "config_namespace": "my-app",
  "launch_agent_label": "com.you.my-app-peer-loop",
  "post_cycle_hook": ["./my-cli", "reload"],
  "rss_budget_mb": 50,
  "rss_entrypoint": "src/main.py",
  "test_command": ["npm", "test"]
}
```

| Key | Required | Notes |
|-----|----------|-------|
| `project_name` | yes | Shown in peer prompts and watch UI |
| `config_namespace` | yes | `~/.config/<namespace>/` for loop state, logs, cache |
| `launch_agent_label` | yes | macOS LaunchAgent id for `--install` |
| `post_cycle_hook` | no | Command after successful verify (was `ram install`) |
| `rss_budget_mb` | no | Omit to skip RSS metric |
| `rss_entrypoint` | no | Python file to import for RSS delta |
| `test_command` | yes | Replaces default unittest discover |

## Customize for your project

1. **`scripts/peer_tasks.json`** — add task templates with `scope`, `peer`, `prompt`
2. **`notes/SAFETY_GATES.md`** — your harm matrix (replace ram-park guards)
3. **`notes/WORK_QUEUE.md`** + **`scripts/self_improve_context.md`** — keep identical
4. **`AGENTS.md`** — agent preferences (Cursor reads this)
5. **`LAUNCH.md`** — optional phased launch track

## Forever loop modes

| Mode | Command | Cost |
|------|---------|------|
| Background terminal (default) | `./scripts/peer-loop-run` | $0 |
| Clipboard paste | `peer_loop.py --forever --clipboard-only` | $0 |
| Cursor UI inject | `peer_loop.py --forever --cursor-ui` | $0 + Accessibility setup |
| Paid API | `peer_loop.py --forever --paid-api` | Bills Cursor API |

State/logs: `~/.config/<config_namespace>/`

## Accessibility (UI inject only)

One-shot setup (opens all panes + triggers every macOS prompt):

```bash
./scripts/grant-all-permissions.command   # double-click in Finder
# or from Cursor's terminal (so Cursor gets file prompts too):
./scripts/grant-all-permissions.sh --cursor-only
```

Verify only:

```bash
./scripts/peer-accessibility.sh --verify
```

## Upstream

Generated from [ram-park](https://github.com/your-org/ram) via:

```bash
python3 scripts/bundle_automation_kit.py --tar
```

Re-run in ram-park to refresh the kit when automation scripts change.
