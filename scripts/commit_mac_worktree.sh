#!/usr/bin/env bash
# Mac 로컬 미커밋 변경을 단위별로 안전하게 커밋·푸시 (2026-11-12)
# 대상: ~/strategy-pilot, 브랜치 feature/kiwoom-us-tr-skeleton-local
#
#   bash scripts/commit_mac_worktree.sh            # 확인만: 단위별 파일 목록·비밀정보 검사
#   bash scripts/commit_mac_worktree.sh --apply    # 커밋 + 푸시
#
# macOS 기본 bash 3.2 호환: 한글 앞 변수는 반드시 ${var} 형태로 쓴다.
# 원칙 (인계서 6장): .env·Keychain·PIN·DB·백업·전체 계좌/주문번호 커밋 금지,
# git reset --hard / git clean 사용 안 함, 단위별 분리 커밋.
set -euo pipefail

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1
BRANCH=feature/kiwoom-us-tr-skeleton-local

cd "$(git rev-parse --show-toplevel)"
[ "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || { echo "현재 브랜치가 $BRANCH 가 아닙니다"; exit 1; }

# 1) 커밋되면 안 되는 경로를 .gitignore에 추가 (없을 때만)
IGNORE_LINES=(
  ".redesign-backup-*/"
  ".run/"
  ".publish/"
  "*.sqlite3-journal"
  "*.sqlite3-wal"
  "*.sqlite3-shm"
  "*.bundle"
  "backend/data/*.sqlite3*"
  "backend/data/backups/"
  "*.pem"
  "*.p12"
  ".env.*"
  "!.env.example"
)
for l in "${IGNORE_LINES[@]}"; do
  grep -qxF "$l" .gitignore || { [ $APPLY -eq 1 ] && echo "$l" >> .gitignore; echo "+ .gitignore: $l"; }
done

# 2) 단위 정의: "이름|커밋 메시지|경로..."
UNITS=(
  "gitignore|chore: 비밀정보·DB·백업 경로 gitignore 보강|.gitignore"
  "env-example|chore: 환경변수 예시 갱신 (값 없음)|.env.example backend/.env.example deploy/backend/.env.example"
  "docs|docs: 인계서·운영 문서 갱신 (11/12 2차 포함)|docs AGENTS.md README.md CLAUDE.md"
  "frontend|feat(web): 홈 WTS 리디자인·TOP10·SymbolPanel·매매 제어|src public index.html package.json package-lock.json vite.config.ts tailwind.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json vitest.config.ts eslint.config.js postcss.config.js components.json"
  "backend-engine|feat(engine): 키움 US/REST provider·리스크·저장소|backend/trading_engine"
  "backend-app|feat(backend): 미국 주문·2팀 러너·세션 자동 갱신·실시간 감시|backend/app backend/requirements.txt backend/Dockerfile backend/README.md"
  "backend-tests|test(backend): 세션 키퍼 등 백엔드 테스트|backend/tests"
  "backend-scripts|chore(scripts): live_on/off·원장 정리·검증 스크립트|backend/scripts"
  "agents|chore: 에이전트·스킬 설정|.claude .codex"
  "deploy|chore(deploy): 배포 설정|deploy vercel.json"
)

# 3) 스테이징 전 비밀정보 검사 함수 (값은 출력하지 않음)
scan() {
  local bad=0
  # 금지 파일
  if git diff --cached --name-only | grep -E '(^|/)\.env($|\.)|\.sqlite3|\.redesign-backup|\.bundle$|\.pem$|\.p12$|/backups?/' | grep -v '\.env\.example$'; then
    echo "!! 금지 파일이 스테이징됨"; bad=1
  fi
  # 큰 파일 (>2MB)
  git diff --cached --name-only -z | xargs -0 -I{} sh -c '[ -f "{}" ] && [ $(wc -c < "{}") -gt 2097152 ] && echo "!! 2MB 초과: {}"' | grep . && bad=1
  # 키·토큰·PIN·계좌번호 패턴 (추가된 줄만). 파일:줄 위치와 항목 종류만 출력, 값은 출력 안 함.
  # 확인 결과 가짜 테스트 값이면 SCAN_ALLOW="경로1,경로2" 로 해당 파일만 제외 가능 (PRIVATE KEY는 제외 불가)
  # awk는 위치 표시만, 정규식 판정은 grep -E (BSD/GNU 공통). 도구 오류 시 실패로 처리(fail-closed).
  local added hits="" rc kind re line f out spec
  added=$(git diff --cached -U0 | awk '
    /^\+\+\+ / { f = substr($0, 7); next }
    /^@@ / { split($3, a, ","); ln = substr(a[1], 2) + 0; next }
    /^\+/ { print f ":" ln "\t" substr($0, 2); ln++ }') || { echo "!! 검사 도구 오류(awk)"; return 1; }
  for spec in \
    'PRIVATE KEY|-----BEGIN [A-Z ]*PRIVATE KEY' \
    "키/토큰/비밀번호|(app_?key|secret_?key|appsecret|access_?token|refresh_?token|password|admin_?pin)[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9+/_-]{12,}" \
    '계좌번호 형식|(^|[^0-9])[0-9]{8}-[0-9]{2}([^0-9]|$)|(^|[^0-9])[0-9]{4}-[0-9]{4}-[0-9]{2}([^0-9]|$)'; do
    kind=${spec%%|*}; re=${spec#*|}
    rc=0; out=$(printf '%s\n' "$added" | grep -iE -- "$re") || rc=$?
    [ $rc -gt 1 ] && { echo "!! 검사 도구 오류(grep)"; return 1; }
    [ -z "$out" ] && continue
    while IFS= read -r line; do
      f=${line%%:*}
      if [ "$kind" != "PRIVATE KEY" ] && case ",${SCAN_ALLOW:-}," in *",${f},"*) true;; *) false;; esac; then continue; fi
      hits="${hits}   ${line%%	*}  [${kind}]
"
    done <<EOF
$out
EOF
  done
  if [ -n "$hits" ]; then
    echo "$hits" | head -40
    echo "!! 키·토큰·계좌번호로 보이는 값 — 위 위치를 직접 확인 필요 (값은 출력하지 않음)"; bad=1
  fi
  return $bad
}

echo "== 현재 상태"; git status --short | head -50; total=$(git status --short | wc -l | tr -d ' '); echo "(총 ${total}건)"

FAILED=""
for u in "${UNITS[@]}"; do
  IFS='|' read -r name msg paths <<<"$u"
  existing=()
  for p in $paths; do [ -e "$p" ] && existing+=("$p"); done
  [ ${#existing[@]} -eq 0 ] && continue
  changed=$(git status --short -- "${existing[@]}" | wc -l | tr -d ' ')
  [ "$changed" -eq 0 ] && continue
  echo; echo "== [${name}] ${changed}건 → ${msg}"
  git status --short -- "${existing[@]}" | head -30
  git add -- "${existing[@]}"
  if ! scan; then
    git reset -q -- "${existing[@]}"
    echo "!! [${name}] 검사 실패 — 이 단위는 커밋하지 않았습니다."
    [ $APPLY -eq 1 ] && { echo "위 항목을 정리한 뒤 다시 실행하세요. (앞 단위 커밋은 로컬에만 있고 푸시 전)"; exit 1; }
    FAILED="${FAILED} ${name}"; continue
  fi
  if [ $APPLY -eq 1 ]; then
    git commit -q -m "$msg"
    echo "커밋: $(git log -1 --format='%h %s')"
  else
    git reset -q -- "${existing[@]}"
  fi
done

echo; echo "== 단위에 속하지 않은 남은 변경 (직접 확인)"; git status --short | head -30

if [ $APPLY -eq 1 ]; then
  git push -u origin "$BRANCH"
  echo "푸시 완료: $(git log -1 --format='%h')"
elif [ -n "$FAILED" ]; then
  echo; echo "확인만 했습니다. 검사 실패 단위:${FAILED} — 정리 후 다시 확인하세요."; exit 1
else
  echo; echo "확인만 했습니다. 문제 없으면 --apply 로 실행하세요."
fi
