# Strategy Pilot V2 Current System Inventory

작성 기준: 2026-08-22, 현재 로컬 작업 폴더

이 문서는 새 버전을 만들기 전에 현재 코드에서 실제로 확인된 자산을 정리한다. 파일명이나 과거 계획만으로 구현 여부를 판단하지 않았으며, 현재 코드에 존재하는 기능과 런타임 안전 상태를 기준으로 분류했다.

## 상태 표기

| 상태 | 의미 |
| --- | --- |
| 구현 | 코드와 화면 또는 API 경로가 존재함 |
| 부분 구현 | 핵심 구조는 있으나 운영 검증, 데이터 품질 또는 UI 정리가 남음 |
| 안전 차단 | 코드 경로는 있으나 현재 설정에서 실행되지 않음 |
| 과거/참고 | 이전 단계 기록이며 현재 상태와 다를 수 있음 |

## 1. 프론트엔드

### 구조

```text
src/
├── auth/                    # Kiwoom CLI 프로필/PIN 세션 화면
├── components/
│   ├── home/               # 계좌 요약, 자동매매 상태, 시세 요약
│   ├── layout/             # 상단바, 하단 탭, 공통 레이아웃
│   └── ui/                 # 공통 UI 컴포넌트
├── pages/
│   ├── Home.tsx
│   ├── Quotes.tsx
│   ├── Strategies.tsx
│   ├── Analytics.tsx
│   └── Settings.tsx
├── services/
│   └── apiClient.ts        # 프로젝트 FastAPI 호출
└── types/                  # 프론트엔드 데이터 타입
```

### 화면별 기능

| 화면 | 경로 | 현재 기능 | 상태 |
| --- | --- | --- | --- |
| 로그인 | 앱 진입 전 | 저장된 Kiwoom CLI 프로필 조회, PIN 인증, 프로필 선택 | 구현 |
| 홈 | `/` | 평가자산/주문가능금액/보유종목, 활성 HTS 조건 요약 | 구현, 실계좌 대조 지속 필요 |
| 시세 | `/quotes` | 미국주식 등락률·거래량 랭킹, 종목 선택, FE/FT 2초 상태 | 구현, 장시간 검증 필요 |
| 전략 | `/strategies` | HTS 저장 조건식, 조건별 ON/OFF, 현재 편입 종목 | 구현 |
| 분석 | `/analytics` | 실현손익, 일별 손익 캘린더, 당일 실제 체결 | 구현, 키움 화면 대조 필요 |
| 설정 | `/settings` | 읽기 전용·주문 잠금·세션 안전상태 | 구현 |
| 주문 | `/orders` | 별도 화면 대신 `/strategies`로 이동 | 정리 완료 |

### 프론트엔드 상태 관리

- TanStack React Query가 서버 데이터 조회, 캐시, 재조회 주기를 관리한다.
- `apiClient.ts`가 API 기본 URL, 세션 헤더, 안전한 오류 형식을 담당한다.
- 로그인 전에는 보호된 대시보드를 렌더링하지 않는다.
- 화면에 Kiwoom App Key, Secret Key, OAuth Token을 저장하지 않는다.

## 2. 백엔드

### 구조

```text
backend/
├── app/
│   ├── api/                # FastAPI 라우트
│   ├── core/               # 설정, 인증, 보안
│   ├── schemas/            # API 요청/응답 모델
│   └── services/           # Kiwoom, 계좌, 시세, 전략, 주문 서비스
├── trading_engine/
│   ├── providers/          # Kiwoom REST/미국주식 provider
│   ├── strategies/         # 미국주식 전략 판정
│   ├── backtesting/        # 전략 백테스트 기반
│   ├── services/           # 캐시, 리스크, runner, paper broker
│   └── storage/            # SQLite 저장소와 migration
├── scripts/                # 로컬 실행, 안전 점검, smoke 도구
└── tests/                  # FastAPI 및 trading engine 테스트
```

### 주요 API

| 영역 | 대표 API | 상태 |
| --- | --- | --- |
| 상태 | `/api/health`, `/api/kiwoom/status` | 구현 |
| 로그인 | `/api/auth/kiwoom/profiles`, `/api/auth/kiwoom/login`, `/api/auth/kiwoom/profile-login` | 구현 |
| 국내 계좌(초기 단계) | `/api/accounts`, `/api/account/*` | 구현, V2에서는 분리 검토 |
| 미국 계좌 | `/api/us/account/cash`, `valuation`, `holdings`, `realized-pnl`, `period-return`, `daily-returns`, `order-fills` | 구현/부분 구현 |
| 미국 시세 | `/api/market/rankings/us/*`, `/api/market/us/chart/*`, `/api/market/us/realtime-window` | 구현/부분 구현 |
| 조건/전략 | `/api/market/us/conditions`, `/api/us/autotrade/strategies` | HTS 조건 전용 구현 |
| 주문/자동매매 | `/api/us/orders`, `/api/us/autotrade/*`, `/api/us/liquidation/*` | 코드 존재, 현재 안전 차단 |
| 분석 | `/api/us/analytics/strategy-pnl` | 구현/부분 구현 |

### 주요 서비스

| 서비스 | 역할 |
| --- | --- |
| `token_manager.py` | Kiwoom OAuth 토큰 발급과 캐시 |
| `kiwoom_cli_profile.py` | macOS Keychain의 Kiwoom CLI 프로필 접근 |
| `kiwoom_session.py` | 대시보드 세션과 프로필 연결 |
| `kiwoom_client.py` | 공통 Kiwoom REST 조회 |
| `us_account_service.py` | 미국주식 예수금·평가·잔고·손익 조회 |
| `realtime_quote_service.py` | 실시간 시세 이벤트 처리 |
| `kiwoom_websocket.py` | WebSocket 연결/구독 경계 |
| `market_ranking_service.py` | 등락률·거래량 랭킹 |
| `autotrade_runner.py` | 전략 tick 실행과 진입/청산 조정 |
| `us_order_service.py` | 미국주식 주문 계약과 안전 검사 |

### 현재 런타임 안전 상태

- Python FastAPI 및 Python trading engine으로 제작되어 있다.
- 현재 확인된 실행 상태는 `readOnly=true`, 주문 기능 OFF, runner OFF, 런타임 주문 잠금이다.
- 주문 API와 자동매매 코드가 존재해도 현재 설정에서는 실주문을 전송하지 않는다.
- 실주문 모드는 코드 존재만으로 활성화하면 안 되며, 계좌 대조·미체결 복원·시장시간·리스크·감사로그를 별도 승인해야 한다.

## 3. Kiwoom 데이터/TR 구조

| 구분 | TR/채널 | 용도 | 현재 수준 |
| --- | --- | --- | --- |
| OAuth | `au10001` | 접근토큰 발급 | 구현 및 과거 실검증 |
| 미국 조건검색 | `usa20280`, `usa20281`, `usa20290`, `usa20291` | 목록/조회/실시간 등록/해제 | 구현, 장시간 재연결 검증 필요 |
| 미국 차트 | `usa06011`~`usa06016` | 분·일·주·월·분기·연 차트 | 주요 화면 연결 |
| 미국 종목/호가 | `usa20100`, `usa20101` | 현재가 종목정보, 10호가 | 부분 구현 |
| 미국 랭킹 | `usa20520`, `usa20540` | 거래량 급등락, 거래대금 상위 | 부분 구현 |
| 미국 실시간 | `FE`, `FT` | 체결가, 10호가 | 실수신 및 2초 화면 갱신 확인 |
| 미국 계좌 | `ust21110`, `ust21120`, `ust21150`, `ust21510`, `ust21630`, `ust21650`, `usa21670`, `ust21070` | 예수금, 평가, 체결, 손익, 잔고 | 조회 경로 구현/보정 중 |
| 미국 주문 | `ust20000`~`ust20003` | 매수, 매도, 정정, 취소 | 코드 존재, 현재 안전 차단 |
| 주문 실시간 | `F4`, `F5` | 주문 확인, 체결 | 운영 완성도 검증 필요 |

## 4. 데이터 구조

### 메모리/캐시

- React Query 캐시: 화면용 API 응답과 로딩/오류 상태.
- 시장 데이터 캐시: 종목별 최신 tick, 호가, 캔들, 갱신 시각.
- runner 상태: 전략 활성 여부, Paper/Live 모드, 최근 tick과 오류.

### SQLite

기본 로컬 경로는 `backend/data/trading_engine.sqlite3`이며 Git에 포함하면 안 된다.

| 테이블 | 저장 내용 |
| --- | --- |
| `condition_events` | 조건검색 편입·이탈 |
| `market_events` | 시장 데이터 이벤트 |
| `realtime_quote_events` | 실시간 체결/호가 저장창 |
| `strategy_signals` | 전략 신호 |
| `risk_blocks` | 리스크 차단 이유 |
| `us_strategy_decisions` | 미국주식 전략 조건별 판정 |
| `us_order_attempts` | 주문 시도와 안전 결과 |
| `us_auto_trade_events` | 자동매매 runner 이벤트 |
| `us_strategy_pnl_snapshots` | 전략별 손익 스냅샷 |

### 데이터 흐름

```text
Kiwoom CLI/Keychain
  -> FastAPI session
  -> Kiwoom REST/WebSocket provider
  -> account/market services
  -> HTS condition strategy state + read-only runner model
  -> risk/order boundary에서 실제 주문 차단
  -> SQLite audit data
  -> FastAPI /api/*
  -> React Query
  -> Dashboard
```

## 5. 사용 프로그램과 기술

| 영역 | 프로그램/기술 | 사용 목적 |
| --- | --- | --- |
| 프론트엔드 | Vite, React 18, TypeScript | 모바일 우선 대시보드 |
| UI | Tailwind CSS, Radix/shadcn UI, Lucide | 화면 구성과 아이콘 |
| 상태/검증 | TanStack React Query, Zod, React Hook Form | 서버 상태, 데이터 검증, 입력 |
| 차트 | Recharts 및 커스텀 캔들 UI | 시세/성과 시각화 |
| 프론트 테스트 | Vitest, Testing Library, jsdom | 화면 및 인증/API 테스트 |
| 백엔드 | Python 3, FastAPI, Uvicorn, Pydantic | API 서버와 데이터 모델 |
| 통신 | httpx, websockets | Kiwoom REST/WebSocket 서버 통신 |
| 인증 | Kiwoom CLI, macOS Keychain, PyJWT 코드 자산 | 키 보관 및 대시보드 인증 경계 |
| 데이터 | SQLite | 이벤트, 전략, 주문 시도, Paper 기록 |
| 테스트 | pytest | 백엔드/엔진 회귀 테스트 |
| 운영 도구 | macOS `screen`, shell scripts | 로컬 백엔드/Vite 장시간 실행 |
| 배포 자산 | Docker Compose, Caddy, AWS Lightsail 파일 | 과거/향후 서버 배포 기반 |
| 외부 문서 | Kiwoom REST API 문서/GitHub, Google Sheets | TR 계약과 프로젝트 로드맵 |

## 6. V2에서 재사용할 것

- FastAPI의 server-only credential 경계.
- 미국주식 TR 분류와 request/response mapper.
- React Query 기반 API 상태 처리.
- 전략 지표와 판정 로직을 API 호출 코드에서 분리한 구조.
- SQLite 이벤트/audit 저장 구조.
- read-only/order/runner safety guard.

## 7. V2에서 정리할 것

- 초기 국내주식 Phase 1 코드와 미국주식 MVP의 경계를 명확히 분리한다.
- Supabase 코드 자산과 현재 Kiwoom CLI/PIN 인증 중 하나를 공식 인증 방식으로 확정한다.
- 전략 화면의 “계획”, “Paper”, “Live 준비” 문구를 실행 상태와 일치시킨다.
- 주문 화면 잔여 컴포넌트와 사용하지 않는 mock 데이터를 정리한다.
- 여러 문서에 중복된 상태 설명을 이 문서와 최신 로드맵으로 통합한다.
- 실주문은 V2의 기본 기능이 아니라 별도 승인 게이트로 유지한다.
