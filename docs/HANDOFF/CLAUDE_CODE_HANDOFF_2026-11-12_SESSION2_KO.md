# Strategy Pilot · Claude Code 작업 인계 (2026-11-12 2차)

작성: 2026-11-12 21:24 KST · 대상: `/Users/designt/strategy-pilot` (브랜치 `feature/kiwoom-us-tr-skeleton-local`, 마지막 커밋 `a6689d2`, 미커밋 변경 다수)
이전 인계서: `docs/HANDOFF/CLAUDE_CODE_HANDOFF_2026-11-12_KO.md` (1차, 같은 날 오전). 이 문서는 그 이후 작업만 다룬다.

> 실매매 활성화 승인 문서가 아니다. 이번 세션의 모든 코드 변경은 **커밋되지 않았다**. 변경 파일 원본은 `.redesign-backup-20261112/`에 있다.

## 0. 한눈에

| 항목 | 상태 |
|---|---|
| 서버 실행 설정 | 잠금 설정(읽기 전용·주문 차단·비상 차단·관리자 OFF·러너 OFF) · 21:00경 확인 |
| 2팀 계좌 귀속 차단 | **해제됨** (`team2Blockers: []`, 구형 미확인 기록 0) |
| 남은 주문 차단 | 의도된 잠금 설정만: `US_ORDER_DISABLED`, `READ_ONLY_ENABLED`, `SERVER_CONFIRM_NOT_CONFIGURED`, `LIVE_ORDER_UNLOCK_REQUIRED`, `LIVE_RUNNER_NOT_READY`, 비상 차단 ON |
| 홈 리디자인 | 코드 반영 + `dist` 교체로 서빙 중 |
| 세션 자동 갱신 | 코드 반영, **서버 재시작 후 적용** (아직 미로드) |
| 실매매 체결 검증 | 여전히 미완료 (매수→매도→잔고·원장 일치) |

## 1. 이번 세션 변경 파일

### 1.1 프런트 (Vite/React) — 홈 WTS 스타일 리디자인
| 파일 | 변경 |
|---|---|
| `src/index.css` | 색 토큰 교체(배경 `216 19% 5%`, 강조 파랑 `--primary: 218 100% 65%`, up `355 86% 60%`, down `215 92% 58%`), radius 12px, 홈 격자 배경 제거, `.wts-panel`·`.wts-pill` 추가, `.department-roster` 격자 제거 |
| `src/pages/Home.tsx` | 3열 레이아웃: `lg:[300px_1fr]`, `xl:[300px_1fr_320px]`. 좌 TOP10 / 중 SymbolPanel + BotDepartment(hideTop10) / 우 Portfolio·DepartmentPerformance·OperationsEvidence. 선택 종목은 URL `?symbol=&exchange=` (정규식 검증, 미선택 시 첫 적격 종목) |
| `src/components/home/Top10Watch.tsx` | 표 → 목록 버튼. props `selectedSymbol` 추가. 적격·구독/구독 대기/제외 사유 칩 |
| `src/components/home/useTop10Universe.ts` (신규) | TOP10 조회 훅(queryKey `["home","team2-universe",token]`, 5초, 유효기간 검사) |
| `src/components/home/SymbolPanel.tsx` (신규) | 현재가·등락률·체결강도·스프레드·호가·수신지연, 화면에서 수신한 체결가 선(분봉 아님), `usTeam2Plan` 판단표(processSteps·criteria·차단 사유·nextAction). 읽기 전용 |
| `src/components/home/BotDepartment.tsx` | prop `hideTop10`, URL symbol/exchange 변경 시 내부 override 초기화, 캐릭터 96→64px, 제목 축소 |
| `src/components/layout/TopBar.tsx` | ET 시계(1초), `읽기 전용`·주문 상태 pill |
| `src/auth/LoginScreen.tsx` | PIN 저장용 숨김 username(`strategy-pilot-dashboard`) + `name="password"` |
| `src/components/home/TradingControl.tsx` | 관리자 PIN 입력 `autoComplete="current-password"`, 숨김 username 추가 (브라우저 저장 PIN 자동 채움용, 관리자 ON·확인 클릭은 수동 유지) |
| `src/test/home-layout.test.tsx`, `src/test/top10-watch.test.tsx` | 새 구조 기준으로 갱신(만료 순위 숨김·선택=조회 전용·조회 OFF 검사 유지) |

### 1.2 백엔드 — 세션 자동 갱신 (P0-1 부분 해결)
| 파일 | 변경 |
|---|---|
| `backend/app/services/kiwoom_session.py` | `KiwoomSessionManager.renew_session(session_token, margin_seconds=600)`: 만료 10분 전부터 같은 CLI 프로필로 토큰 재발급(캐시 토큰 우선). **session_token 유지**, `account_identity`(app_key sha256) 불일치 시 거부, 로그아웃·revoke된 세션은 None |
| `backend/app/services/us_order_service.py` | `keep_runtime_session_alive()`, `session_keeper_status()`, `_session_keeper_state`. 실패 시 30초 백오프. 성공 시 `_auto_trade_runtime_session` 교체 |
| `backend/app/services/autotrade_runner.py` | live 분기에서 `owner = bound_runtime_session()` 직전에 `await keep_runtime_session_alive()`. `autotrade_runner_status()`에 `sessionKeeper` 키 추가(현재 API 응답 모델에는 미노출) |
| `backend/tests/test_session_keeper.py` (신규) | 5개: 토큰 유지·조기 갱신 안 함·다른 계좌 거부·키퍼 교체+백오프·로그아웃 |

### 1.3 스크립트·문서·데이터
| 파일 | 내용 |
|---|---|
| `backend/scripts/reconcile_20261112.py` | 원장 정리 1회성 스크립트(실행 완료). 재실행해도 사전조건 불일치로 변경 없음 |
| `backend/scripts/live_on.sh` | `실매매 진행` 입력 시에만 실주문 설정으로 재시작(`ENABLE_LIVE_ORDERS=true`, 비상 차단 OFF, 관리자 ON, 러너 ON, `TEAM2_ENTRY_POLICY` 기본 legacy). 이후 UI에서 PIN·관리자 ON·팀·자동매매 ON 필요 |
| `backend/scripts/live_off.sh` | 1차 인계서의 잠금 설정으로 재시작 |
| `docs/RECONCILIATION_2026-11-12.md` | 2팀 차단 원인 대조·복구안 |
| `backend/data/trading_engine.pre-reconcile-20261112.sqlite3` | 실패한 1차 시도 때 만든 사본. 금융정보 포함, gitignore 대상. **삭제 필요**(세션 권한으로 삭제 불가) |
| `.redesign-backup-20261112/` | 이번 세션에 바꾼 파일 원본 + `dist-before/` (미추적. 정리 시 커밋 금지) |

## 2. DB 원장 정리 (실행 완료, 20:51 KST 사용자 실행)
- 백업: `~/.strategy-pilot/backups/pre-reconcile-20261112-205137.sqlite3`
- 결과: `updated A=1 B=1 · quick_check: ok`
- A: `us_order_attempts` id=8 AIOK 매수 1주(10/23, 주문 ***101) → `auto_exit_completed=1`, `auto_exit_reason='buy_cancelled_unfilled_reconciled_20261112'`. **account_scope는 NULL 유지**(끝자리 자동 귀속 금지 원칙). 근거: 예약 id=6 `취소완료·체결0·released`, 11/02 ust21150 주문1/체결0/취소1, 11/12 잔고 0
- B: `us_capital_allocation_reservations` id=3 QSI(10/09, 주문 ***941, 구형 cycle) `filled` → `closed`, `reconcile_result='closed_holdings_zero_user_approved_20261112'`. **매도 체결 증거(ust21150 2026-10-09 QSI ND) 미확보**, 잔고 0 + 사용자 승인으로 종결
- 차단 함수: `us_order_service._legacy_order_ownership_blocker()` (4개 조건: 무귀속 매수 대기 / 구형 청산 작업 / 구형 예약 reserved·submitted·filled / 구형 진입 주장)
- 참고: 운영 DB journal_mode=delete. Cowork VM 마운트에서는 SQLite 잠금이 안 돼 쓰기 시 `disk I/O error` → **DB 쓰기는 Mac 로컬 python으로만**

## 3. 검증 결과
| 검증 | 결과 | 비고 |
|---|---|---|
| 프런트 tsc / ESLint(변경 파일) | 통과 | |
| 프런트 vitest | 103/103 | Linux 임시 복사본에서 실행(Mac node_modules는 darwin 바이너리) |
| 프런트 build | 통과 | `VITE_API_BASE_URL=same-origin`으로 빌드 후 `dist` 덮어씀(구 해시 파일 잔존) |
| 백엔드 pytest | 687 통과 + 신규 5 통과, 1 실패 | 실패 `test_engine_config::test_relative_database_path...`는 임시 폴더명(`bk`≠`backend`) 탓, 무관. Python 3.10/임시 HOME/프록시 차단 환경 |
| 실서버 확인 | `/api/health` readOnly=true, orderEnabled=false · `/api/us/orders/control/status` team2Blockers=[] | 21:00경 |
| 브로커 조회 | 잔고 0건 / 미체결 조회 HTTP 502 | 502 원인 미확인 |

## 4. 알려진 문제·미완료 (우선순위)
### P0 — 실매매 전
1. **세션 갱신 미적용**: 서버 재시작 전까지 구버전 코드. `live_on.sh` 또는 `live_off.sh` 실행 시 로드
2. **세션 갱신 범위 한계**: runtime 세션만 갱신. `kiwoom_quote_monitor`, `kiwoom_order_state_monitor` 등이 이전 세션 객체/토큰을 들고 있는지 미확인 → 갱신 후 시세·체결 감시가 옛 토큰으로 실패할 수 있음. `get_active_or_latest_kiwoom_session` 사용처 점검 필요
3. **토큰이 이미 만료된 뒤**에는 `get_session`이 세션을 pop → 갱신 불가 → 러너가 자동매매 OFF(기존 동작). 장시간 오프라인 대비 필요
4. **손절 매도가 매수용 precheck에 막힐 수 있음**: `us_order_service.py` auto-exit 경로(약 1295행)가 `precheck_order` 통과 필요. 권한 해제 후, 또는 1주 > 30만원(`EXIT_SINGLE_SHARE_EXCEEDS_CAP`)이면 손절 차단. 청산은 진입 한도·권한과 분리 권장
5. **브로커 보호 주문 없음**: 손절은 서버 감시 후 시장가(`03`). Mac 절전·프로세스 중단 시 미발동 (`caffeinate`는 스크립트에서 실행 중)
6. **QSI 10/09 매도 체결 증거** 확보: `us_account_service.get_order_history(order_date="20261009", symbol="QSI", exchange="ND")` — 현재 API 미노출
7. 미체결 조회 502 원인

### P1
- **TradingControl 오표시**: 패널 접힘 상태(`enabled: open`)로 `state.data` 없을 때 `teamSupported=false` → "2팀 실행 서버 업데이트 필요 · 시작 차단" 오경고. `state.data` 로딩 전에는 문구 숨기기
- **스프레드 0.1% 기준**: $10 미만 종목은 1틱만으로 탈락(예: PLCE $1.02 → 0.99%). TOP10 적격 다수가 $1 미만이라 2팀 진입이 사실상 불가. 틱 기준 규칙 검토(`scalp_core/safety.py spread_ok` 참고 구현 있음 — 저장소 밖, 이전 대화 산출물)
- **호가 역전 데이터**: NXXT bid 1.97 > ask 1.61, spreadPct null 관측(11/12 01:33). 정규화 경로 점검
- **분봉 차트 API 없음**: SymbolPanel은 수신 체결가 선만 표시. 분봉 OHLC 조회 엔드포인트 추가 시 캔들로 교체
- `sessionKeeper` 상태를 `UsAutoTradeRuntimeStatus`/운영 점검 화면에 노출
- 상단 바에 긴급 정지 버튼 미배치(매매 제어에만 존재)

### P2
- 디자인 시안(Claude Design 캔버스 "Strategy Pilot 대시보드 리디자인")과 차이: 캔들 차트, 하단 봇 칩 압축, 긴급 정지 위치
- `dist`에 구 해시 파일 잔존(정상 빌드 1회로 정리)
- 부서별 성과 원장·분봉/신호/성과 영구 저장 미구현 (이전 검토 보고서 5·6장)

## 5. 운영 명령
```bash
# 잠금 상태로 재시작 (기본 권장)
bash ~/strategy-pilot/backend/scripts/live_off.sh
# 실주문 설정으로 재시작 ('실매매 진행' 입력 필요) → 이후 UI에서 PIN·관리자 ON·팀·자동매매 ON
bash ~/strategy-pilot/backend/scripts/live_on.sh
# 로그
tail -50 /tmp/strategy-pilot-backend.log; tail -50 /tmp/strategy-pilot-frontend.log
```
- 터미널에 문서의 `…` 축약을 그대로 입력하면 `command not found` (11/12 실제 발생 → 그때 재시작·빌드 안 됨)
- 시작 스크립트 기본값 주의: `TEAM2_ENTRY_POLICY=squeeze_1m`, 관찰 러너 기본 true, localhost면 관리자 기본 true

## 6. 작업 원칙 (유지)
- `AGENTS.md`의 실주문 게이트 우선. 무단 프레임워크 통합 금지(Vite 유지)
- 비밀정보(.env, Keychain, PIN, 원본 DB·백업, 전체 계좌·주문번호) 업로드·커밋 금지
- `git reset --hard`, `git clean`, 광범위 병합 금지. 변경은 문서/UI/백엔드/스크립트 단위로 분리 커밋
- 테스트는 소스 격리 복사 + 임시 HOME/DB + 외부 통신 차단
- 운영 DB 변경은 백업·사전조건·단일 트랜잭션·감사 기록, Mac 로컬에서만
- 실매매 활성화·주문은 사용자가 직접 수행

## 7. Claude Code 시작 지시문
```text
이 인계서(2차)와 1차 인계서, AGENTS.md를 먼저 읽어라.
이번 세션 변경은 모두 미커밋이다. git status로 1장 파일 목록을 확인하고 단위별로 정리하라.
주문 차단·관리자 OFF를 유지한 채 작업하라. 실주문 설정 재시작과 주문은 하지 마라.
우선순위: 4장 P0-2(세션 갱신 후 시세·체결 감시 토큰 일관성) → P0-4(청산을 진입 precheck에서 분리) → P1 TradingControl 오표시.
각 수정은 격리 테스트를 추가하고 결과를 확인된 구현 / 미검증 / 차단 상태로 보고하라.
```
