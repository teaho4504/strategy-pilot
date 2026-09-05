#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <output-directory>" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT_DIR" ]]; then
  echo "Run this script from a copy located inside the strategy-pilot Git worktree." >&2
  exit 1
fi

OUTPUT_DIR="$1"
mkdir -p "$OUTPUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$OUTPUT_DIR/strategy-pilot-worktree-$STAMP.tar.gz"

tar -C "$ROOT_DIR" -czf "$ARCHIVE" \
  --exclude='./.git' \
  --exclude='./node_modules' \
  --exclude='./dist' \
  --exclude='./backend/.venv' \
  --exclude='*/__pycache__' \
  --exclude='*/.pytest_cache' \
  --exclude='*/.mypy_cache' \
  --exclude='*/.ruff_cache' \
  --exclude='./.env' \
  --exclude='./.env.local' \
  --exclude='./.env.save' \
  --exclude='./backend/.env' \
  --exclude='./backend/.env.local' \
  --exclude='./deploy/backend/.env' \
  --exclude='*.sqlite3' \
  --exclude='*.db' \
  --exclude='*.log' \
  --exclude='*.bak' \
  --exclude='*.save' \
  --exclude='pnpm-lock.yaml' \
  .

if tar -tzf "$ARCHIVE" | grep -E '(^|/)(node_modules|dist|\.git)(/|$)|(^|/)\.env($|\.local$|\.save$)|\.sqlite3$|(^|/)pnpm-lock\.yaml$' >/dev/null; then
  echo "Archive verification failed: a prohibited path was included." >&2
  rm -f "$ARCHIVE"
  exit 1
fi

tar -tzf "$ARCHIVE" > "$ARCHIVE.files.txt"
echo "Created: $ARCHIVE"
echo "Listing: $ARCHIVE.files.txt"
echo "Review the listing before transferring. This script cannot detect secrets pasted into ordinary source files."
