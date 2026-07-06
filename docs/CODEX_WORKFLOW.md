# Codex Workflow

## Repository Reality Check

Before changing architecture or backend code, verify:

- `package.json`
- `vite.config.ts`
- deployment configuration
- current branch tree

For this repository, the current baseline is Vite + React in the root `src/` directory.

Do not assume Next.js, `apps/web`, or App Router unless those files exist in the current branch.

## Documentation Tasks

Documentation-only tasks may edit:

- `AGENTS.md`
- `docs/*.md`

They must not edit:

- runtime code
- Vercel config
- Docker files
- CI workflows
- environment files
- package files

## Phase 1 FastAPI Preparation

Before implementation:

1. Confirm branch is based on `origin/main`.
2. Confirm Vite frontend remains unchanged.
3. Confirm no Vercel config changes are included.
4. Confirm no order endpoints are included.
5. Confirm selected backend files are reviewed before reuse.

## Branch Reuse Policy

Use `feature/backend-account-integration` as reference only.

Do not directly merge:

- Vercel proxy config
- AWS deploy files
- Dockerfile
- disabled order API
- broad UI changes

Selective reuse may be done in a later implementation task only after reviewing each file.

