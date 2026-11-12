#!/usr/bin/env bash
# 원격 브랜치 정리 (2026-11-12, 사용자 승인: "보관 후 지금 전부 정리")
# - 삭제 대상 11개 브랜치를 archive/<이름>-20261112 태그로 원격에 보관한 뒤 삭제
# - main, claude/happy-tesla-tuq30m, Mac 작업 브랜치(feature/kiwoom-us-tr-skeleton-local)는 유지
# - 기본은 확인만(dry-run). 실제 실행: bash scripts/cleanup_branches_20261112.sh --apply
set -euo pipefail

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

BRANCHES=(
  codex/backend-kiwoom-account-foundation
  codex/kiwoom-dashboard-readonly
  docs/architecture-harness
  feature/api-auth-supabase
  feature/backend-account-integration
  feature/fastapi-readonly-account
  feature/frontend-readonly-api-integration
  feature/frontend-supabase-auth
  feature/kiwoom-rest-github-provider-skeleton
  feature/lightsail-readonly-deployment
  feature/trading-engine-paper
)

git fetch origin --prune --tags

BUNDLE="$HOME/strategy-pilot-all-branches-20261112.bundle"
git bundle create "$BUNDLE" --all >/dev/null 2>&1
git bundle verify "$BUNDLE" >/dev/null
echo "로컬 백업 번들: $BUNDLE"

for b in "${BRANCHES[@]}"; do
  sha=$(git rev-parse --verify --quiet "origin/$b" || true)
  if [ -z "$sha" ]; then echo "건너뜀(원격에 없음): $b"; continue; fi
  tag="archive/${b//\//-}-20261112"
  echo "$b ($sha) → $tag"
  if [ $APPLY -eq 1 ]; then
    git tag -f "$tag" "$sha"
    git push origin "refs/tags/$tag"
    remote_sha=$(git ls-remote origin "refs/tags/$tag" | cut -f1)
    if [ "$remote_sha" != "$sha" ]; then echo "태그 확인 실패: $tag — 삭제 중단"; exit 1; fi
    git push origin --delete "$b"
  fi
done

[ $APPLY -eq 1 ] && echo "완료. 남은 브랜치:" && git ls-remote --heads origin | cut -f2
[ $APPLY -eq 0 ] && echo "확인만 했습니다. 실행하려면 --apply 를 붙이세요."
exit 0
