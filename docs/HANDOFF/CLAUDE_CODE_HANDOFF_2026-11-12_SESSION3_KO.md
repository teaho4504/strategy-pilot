# Strategy Pilot · 작업 인계 (2026-11-12 3차, 클라우드 세션 → 로컬 전환)

이전 인계서: `CLAUDE_CODE_HANDOFF_2026-11-12_SESSION2_KO.md` (2차). 이 문서는 2차 이후 클라우드 Claude Code 세션의 작업과 Mac 로컬 상태를 정리한다.

> 실매매 활성화 승인 문서가 아니다. 다음 작업은 **Mac 로컬 Claude Code**에서 이어간다 (클라우드 세션은 Mac 서버·키움 브로커에 접근 불가).

## 0. 한눈에

| 항목 | 상태 |
|---|---|
| GitHub 브랜치 정리 | **완료.** 남은 브랜치: `main`, `claude/happy-tesla-tuq30m`, `feature/kiwoom-us-tr-skeleton-local` |
| 정리 전 백업 | 원격 태그 `archive/*-20261112` 11개(원래 커밋과 일치 확인) + Mac `~/strategy-pilot-all-branches-20261112.bundle` |
| Mac 미커밋 변경 | **329건 그대로 미커밋.** GitHub의 Mac 브랜치는 7/11 커밋 `a6689d2`뿐. 커밋은 사용자 결정으로 보류 |
| Mac `.gitignore` | 커밋 스크립트(`--apply` 첫 시도)가 13줄 추가(수정 상태, 미커밋). 서버 실행에는 영향 없음 |
| 실주문 설정 재시작 | `live_on.sh` 실행 완료. 백엔드 `127.0.0.1:8000` 기동, `/api/health` 200 |
| 실주문 플래그 확인 | **미확인.** `curl /api/health` 결과(`readOnly:false`, `orderEnabled:true`) 미보고 |
| 팀 자동매매 ON·실매매 체결 | 미보고 (사용자 진행 여부 미확인) |
| P0-2·P0-4·P1 수정 | **미착수.** Mac 코드가 GitHub에 없어 클라우드에서 수정 불가 |

## 1. 클라우드 세션 산출물 (`claude/happy-tesla-tuq30m`)

이 브랜치는 Lovable 기반 프로토타입(`main` 계열)이다. Mac 실서버 코드와는 별개이며, 필요한 것만 Mac 쪽으로 옮겨 쓴다.

| 파일 | 내용 | Mac 적용 |
|---|---|---|
| `docs/HANDOFF/CLAUDE_CODE_HANDOFF_2026-11-12_SESSION2_KO.md` | 2차 인계서 사본 | Mac에 원본 있음 |
| `docs/OPERATING_PROTOCOL.md` | `자동매매 시작 요청` / `자동매매 종료 요청` 운영 규칙 | **로컬 Claude Code에 적용 필요** (3장) |
| `docs/STATUS_2026-11-12.md` | 저장소 동기화 현황 | 참고용 |
| `src/lib/verification.ts` | 게이트 요약, 세션 상태, 저가주 틱 기준 스프레드(P1), 매수→매도→잔고·원장 7항목 검증 | 이식 후보 |
| `src/pages/UsConsole.tsx`, `src/pages/Verify.tsx`, `src/components/us/*` | WTS 3열 콘솔·검증 화면 (조회 전용, mock / `VITE_US_API_BASE`) | Mac 홈 리디자인과 중복. `/verify`만 이식 후보 |
| `scripts/cleanup_branches_20261112.sh` | 브랜치 보관·삭제 (실행 완료) | — |
| `scripts/commit_mac_worktree.sh` | Mac 미커밋 변경 단위별 안전 커밋 (비밀정보·DB·2MB 검사) | 커밋할 때 사용 (5장) |
| 테스트 | vitest 20/20, tsc·eslint·build 통과 | — |

가져오는 방법 (커밋 없이 파일만):
```bash
cd ~/strategy-pilot && git fetch origin claude/happy-tesla-tuq30m
```
```bash
git show origin/claude/happy-tesla-tuq30m:docs/OPERATING_PROTOCOL.md > docs/OPERATING_PROTOCOL.md
```

## 2. Mac 로컬 실행 상태

- `live_on.sh`: 첫 시도는 확인 입력 자리에 다른 명령이 들어가 **취소(변경 없음)**, 재시도에서 정상 실행
- 백엔드 로그: `Uvicorn running on http://127.0.0.1:8000`, `GET /api/health 200 OK`, 오류 없음
- 로그 위치: `/tmp/strategy-pilot-backend.log`, `/tmp/strategy-pilot-frontend.log`
- 대시보드 주소: 프런트 로그의 `Local:` 주소, 없으면 `http://127.0.0.1:8000` (dist 서빙)
- 스크립트 안내 순서: 대시보드 > 매매 제어 > PIN 입력 > 관리자 ON > 실행 팀 선택 > 자동매매 ON
- Mac에 `claude` CLI 미설치 (`command not found`)

## 3. 운영 규칙 (사용자 지정) — `docs/OPERATING_PROTOCOL.md` 요약

- **`자동매매 시작 요청`**: 로컬 Claude Code가 사전 점검(테스트·`/api/health`·2팀 차단 0·세션 만료 10분 이상) 후 `live_on.sh` 실행. 주문 비활성·읽기 전용·비상 차단·서버 확인·실주문 잠금·관리자·러너 잠금 해제
- **유지**: 1회 주문 한도(1주 ≤ 30만원), 일일 손실 한도, 손절·청산, 계좌 귀속 검사, 긴급 정지 버튼
- **마지막 확인은 사용자**: 대시보드에서 팀별 자동매매 ON/OFF만 사용자가 직접 누름. Claude는 대신 누르지 않음
- **`자동매매 종료 요청`** 또는 검증 완료: 팀 OFF·미체결 0 확인 → `live_off.sh` → 잠금 확인. 잔고가 남으면 보고 후 사용자 결정
- 현재 코드는 PIN·관리자 ON을 UI에서 요구 → "팀별 ON/OFF만" 구조는 코드 수정 필요

## 4. 알려진 위험 (2차 인계서 4장, 미해결)

| 우선 | 내용 | 수정 전 운영 대응 |
|---|---|---|
| P0-2 | 세션 갱신 후 `kiwoom_quote_monitor`·`kiwoom_order_state_monitor`가 이전 토큰 사용 가능성 | 로그·수신 지연 감시, 시세 멈추면 `live_off.sh` |
| P0-3 | 토큰 만료 후에는 갱신 불가 → 러너가 자동매매 OFF | 장시간 무인 운용 금지 |
| P0-4 | 손절 매도가 매수용 `precheck_order`에 막힐 수 있음 (`us_order_service.py` auto-exit 경로) | 1주 < 30만원 종목만, 매매 중 권한 해제 금지 |
| P0-5 | 브로커 보호 주문 없음, Mac 절전 시 손절 미발동 | 전원 연결·덮개 열기 (`caffeinate` 스크립트 실행) |
| P0-6 | QSI 10/09 매도 체결 증거 미확보 | — |
| P0-7 | 미체결 조회 HTTP 502 원인 미확인 | — |
| P1 | TradingControl 접힘 상태 오경고, 스프레드 0.1% 기준(저가주 탈락), 호가 역전 데이터 | 틱 기준 구현은 1장 `verification.ts` 참고 |

## 5. 로컬 전환 후 순서 (권장)

1. Claude Code 설치 및 실행
   ```bash
   curl -fsSL https://claude.ai/install.sh | bash
   ```
   ```bash
   cd ~/strategy-pilot && claude
   ```
2. 첫 지시 예시
   ```text
   docs/HANDOFF의 2차·3차 인계서와 AGENTS.md, docs/OPERATING_PROTOCOL.md를 읽어라.
   현재 서버는 live_on.sh로 실주문 설정 상태다. /api/health로 실제 플래그부터 확인하라.
   우선순위: P0-4(청산을 진입 precheck에서 분리) → P0-2(세션 갱신 후 감시 토큰 일관성) → P1 TradingControl 오표시 → 팀별 ON/OFF만 남기는 구조.
   각 수정은 격리 테스트를 추가하고 확인된 구현 / 미검증 / 차단으로 보고하라. 주문·팀 자동매매 ON은 하지 마라.
   ```
3. 실매매 1회 검증: `자동매매 시작 요청` → 대시보드 팀 ON → $10 미만·1주 체결 → 매도 → 체결·잔고·미체결·원장·계좌 귀속·예약 종결 대조 → `자동매매 종료 요청`
4. (선택) GitHub 커밋을 재개할 때: 아래 8개 파일은 테스트용 가짜 값으로 확인됨(보관 태그 대조). 단, `test_auth_recovery.py:22`, `test_kiwoom_cli_profile.py:23`은 9/05 이후 새 파일이라 **직접 확인 후** 사용
   ```bash
   SCAN_ALLOW="src/test/auth-api.test.tsx,backend/trading_engine/tests/test_kiwoom_us_account_shape_audit.py,backend/trading_engine/tests/test_kiwoom_us_credential_policy.py,backend/trading_engine/tests/test_kiwoom_us_order_state_audit.py,backend/tests/test_auth_recovery.py,backend/tests/test_kiwoom_cli_profile.py,backend/tests/test_readonly_backend.py,backend/tests/test_us_order_state_monitor.py" bash <(git show origin/claude/happy-tesla-tuq30m:scripts/commit_mac_worktree.sh) --apply
   ```
   `outputs/`, `pnpm-lock.yaml`은 커밋하지 않음(스크립트가 gitignore 처리)

## 6. 운영 명령

```bash
curl -s http://127.0.0.1:8000/api/health; echo
```
```bash
tail -f /tmp/strategy-pilot-backend.log
```
```bash
bash ~/strategy-pilot/backend/scripts/live_off.sh
```
```bash
bash ~/strategy-pilot/backend/scripts/live_on.sh
```
- `live_on.sh` 확인 프롬프트에는 `실매매 진행`만 입력 (다른 명령을 붙여 넣으면 취소됨)
- 명령은 한 번에 하나씩 실행

## 7. 작업 원칙 (유지)

- 비밀정보(.env, Keychain, PIN, DB·백업, 전체 계좌·주문번호) 업로드·커밋 금지
- `git reset --hard`, `git clean`, 광범위 병합 금지
- 운영 DB 변경은 백업·사전조건·단일 트랜잭션·감사 기록, Mac 로컬에서만
- 실매매의 마지막 확인(팀별 자동매매 ON)은 사용자가 직접
