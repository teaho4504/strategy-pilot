# Repository Agent Guide

## Current Repository Baseline

This repository is `teaho4504/strategy-pilot`.

The current production baseline is a Vite + React root application:

- Frontend framework: Vite + React + TypeScript
- Frontend location: repository root `src/`
- Build script: `npm run build`
- Vite config: `vite.config.ts`
- Current production branch: `main`
- Current deployment assumption: Vercel deploys the Vite root frontend

Do not assume Next.js, `apps/web`, or App Router unless those structures exist in the current branch.

## Architecture Decision Gate

Before making architecture changes, verify the actual repository framework from:

- `package.json`
- `vite.config.ts`
- deployment configuration
- current branch file tree

Do not introduce a new frontend framework during backend work.

The planned backend is separate from the Vercel frontend runtime:

```text
Vercel
  -> Vite React Dashboard

AWS or equivalent backend host
  -> FastAPI read-only backend
  -> Kiwoom REST account APIs
```

FastAPI must remain separate from the Vercel frontend runtime.

## Current Safety Position

The current app is a frontend mock dashboard. The following are not implemented in `main`:

- FastAPI backend
- Kiwoom REST account lookup
- Kiwoom realtime connection
- WebSocket gateway
- Strategy Worker
- Risk Worker
- Order Worker
- Paper Trading
- Live trading

Live trading, order placement, order amendment, and order cancellation must remain unimplemented and blocked.

## Scope Rules

- Do not expose Kiwoom App Key, Secret Key, OAuth token, account number, webhook secrets, or database credentials in frontend code.
- Do not add live order execution.
- Do not implement browser-direct Kiwoom API calls.
- Keep default behavior in mock/demo mode.
- Preserve the current Vite frontend unless a separate migration is explicitly approved.
- Keep backend work read-only until a later risk-controlled phase.

## Worktree Hygiene

- Documentation-only tasks must change documentation files only.
- Do not mix architecture documents with runtime code, Docker, CI, package scripts, Vercel config, or environment changes.
- Do not merge broad backend branches directly into `main`.
- Treat previous backend branches as source material for selective reuse, not as direct merge targets.
- Before starting FastAPI work, confirm the branch starts from current `main`.

## Codex Multi-Agent Orchestration

- For Kiwoom real-time condition-search analysis, PROACTIVELY delegate the bounded workflow to the project custom agent `kiwoom_orchestrator` when parallel specialist evidence materially improves the result.
- The coordinator must use `condition_intake`, then run `realtime_market_analyst` and `pullback_pattern_learner` in parallel, then use `risk_signal_gate`, and only after approval use `signal_publisher`.
- Wait for all required specialists and return their distilled evidence instead of raw logs.
- Keep parallel work read-heavy and read-only. No agent may place, amend, cancel, replace, or liquidate an order.
- Every published signal must remain advisory with `execution_authorized=false`.
