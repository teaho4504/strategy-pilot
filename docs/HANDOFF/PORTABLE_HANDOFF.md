# Strategy Pilot Portable Handoff

This directory is the portable source of truth for continuing the current experimental Strategy Pilot worktree on another local machine.

## Read in this order

1. [Current state](skill/strategy-pilot-maintainer/references/current-state.md)
2. [End-to-end implementation flows](skill/strategy-pilot-maintainer/references/implementation-flows.md)
3. [Architecture and data](skill/strategy-pilot-maintainer/references/architecture-and-data.md)
4. [Roadmap](skill/strategy-pilot-maintainer/references/roadmap.md)
5. [Safety boundaries](skill/strategy-pilot-maintainer/references/safety-boundaries.md)
6. [New device setup](skill/strategy-pilot-maintainer/references/new-device-setup.md)
7. [Windows local continuation](WINDOWS_LOCAL_CONTINUATION.md)

## Skill installation on the new device

Copy the complete skill folder:

```bash
mkdir -p ~/.codex/skills
cp -R docs/HANDOFF/skill/strategy-pilot-maintainer ~/.codex/skills/
```

Restart Codex, then ask it to use `strategy-pilot-maintainer` when continuing this project.

## Critical migration warning

The audited local branch has substantial uncommitted and untracked implementation work. A plain Git clone does not reproduce the current dashboard/backend. Use the secret-free export script and overlay procedure in the new-device setup document.

## What this bundle does not contain

- App Key or Secret Key
- Broker access token
- Account number
- Dashboard PIN
- `.run` runtime directory
- Temporary Codex transcripts and test output
- `.env` files
- SQLite runtime databases
- `node_modules`, `dist`, Python virtual environment or caches

Configure credentials separately on every machine through the OS keyring and `kiwoomcli`.
