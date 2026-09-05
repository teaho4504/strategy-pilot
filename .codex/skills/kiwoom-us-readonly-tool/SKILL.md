---
name: kiwoom-us-readonly-tool
description: Maintain and extend the local Kiwoom REST API US-stock research and automation foundation. Use when Codex must analyze an official Kiwoom Excel/JSON TR specification, rebuild the US TR catalog, add read-only market/chart/account integrations, update the Vite dashboard or separate FastAPI backend, audit credential handling, or verify that live orders, amendments, cancellations, and other financial mutations remain blocked.
---

# Kiwoom US Read-only Tool

## Workflow

1. Read repository `AGENTS.md`, `package.json`, `vite.config.ts`, backend configuration, and current tree before changing architecture.
2. Treat the Vite root frontend and separate FastAPI backend as fixed boundaries.
3. For an Excel source, inspect it with the spreadsheet workflow. Prefer the JSON counterpart for deterministic catalog generation.
4. Run `scripts/rebuild_catalog.py <spec.json>` after a specification change.
5. Compare catalog `implemented` flags with production code, excluding tests and documentation.
6. Add one read-only TR slice at a time: request builder, response mapper, service, authenticated endpoint, frontend adapter, and fixture tests.
7. Verify secrets never enter frontend code, responses, logs, fixtures, or generated catalog files.
8. Run backend tests, frontend tests, build, and safety checks before handoff.

## Non-negotiable safety

- Keep `ust20000`, `ust20001`, `ust20002`, `ust20003`, and `ust31302` blocked.
- Do not add a network sender for an order, amendment, cancellation, liquidation, or exchange request.
- Keep browser-to-Kiwoom calls forbidden; call Kiwoom only from FastAPI services.
- Keep credentials server-side and redact account labels.
- Default to read-only behavior and require explicit user approval for any future architecture phase that changes these boundaries.
- Stop if a requested change would enable live financial mutations; explain the boundary instead of implementing it.

## References

- Read `references/architecture.md` before changing runtime boundaries or deployment.
- Read `references/spec-workflow.md` before importing a new Kiwoom specification or adding TRs.
