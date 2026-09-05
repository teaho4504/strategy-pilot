# Strategy Pilot Documentation Index

새 버전에서는 이 파일을 문서 시작점으로 사용한다. 기존 문서는 삭제하지 않고 목적과 현재성을 구분한다.

## 1. V2 기준 문서

| 파일 | 역할 |
| --- | --- |
| `V2_CURRENT_SYSTEM_INVENTORY.md` | 현재 프론트엔드·백엔드·데이터·도구의 실제 구현 목록 |
| `V2_DASHBOARD_PROTOTYPE_MAP.md` | 화면 탭, 버튼 이동, 사용자 흐름 |
| `V2_DOCUMENT_INDEX.md` | 전체 Markdown 문서 색인 |
| `V2_SYSTEM_MAP.md` | 전체 시스템 지도와 V2 재구축 경계 |

## 2. 기존 문서 정리

| 파일 | 주요 내용 | 현재 판단 | V2 처리 |
| --- | --- | --- | --- |
| `AI_RECOMMENDED_5M_STRATEGY.md` | AI 추천 5분봉 눌림 전략과 Kiwoom 매핑 | 전략 자산 | 유지 후 전략 명세로 확장 |
| `ARCHITECTURE_DECISIONS.md` | Vite/FastAPI 기준 아키텍처 결정 | 일부 유효 | V2 아키텍처 결정 문서로 재작성 |
| `CODEX_WORKFLOW.md` | 브랜치/문서/개발 작업 규칙 | 유효 | 유지 |
| `ENGINE_SAFETY_RULES.md` | DB, 시간, 리스크, 주문 차단 | 핵심 자산 | 최신 runner 상태에 맞게 갱신 |
| `KIWOOM_US_CREDENTIAL_POLICY.md` | Key/Secret/Token/계좌 관리 원칙 | 핵심 자산 | 유지 |
| `LOCAL_MOBILE_SECURITY.md` | Mac 로컬 서버와 Tailscale 보안 | 유효 | V2 운영 가이드로 유지 |
| `PHASE_1_READONLY_SUMMARY.md` | 국내계좌 read-only Phase 1 | 과거 완료 기록 | archive 성격으로 유지 |
| `PLAN.md` | 전체 단계별 개발 계획 | 상태 혼재 | V2 로드맵으로 대체 |
| `PROJECT_CONTEXT.md` | 초기 Vite/FastAPI 범위 | 과거 기준 | V2 inventory로 대체 |
| `RISK_GUARDRAILS.md` | 프론트/백엔드/주문 안전 경계 | 핵심이나 상태 혼재 | 구현 상태와 정책을 분리해 갱신 |
| `TASK_LOG.md` | 2026-07 이후 전체 작업 이력 | 감사 기록 | 수정 최소화, append-only 유지 |
| `TRADING_ENGINE_HARNESS.md` | Paper worker와 provider skeleton | 핵심 자산 | 현재 runner와 일치하도록 갱신 |
| `TRADING_ENGINE_PAPER_ARCHITECTURE.md` | Paper 엔진 데이터 흐름 | 핵심 자산 | V2 engine 설계의 입력 |
| `US_STOCK_AUTO_TRADING_PLAN.md` | 미국주식 자동매매 단계 계획 | 상태가 오래됨 | V2 실행 로드맵으로 재작성 |
| `US_STOCK_READONLY_CLIENT_PLAN.md` | 미국주식 read-only transport | 구현 역사 | provider 기술 문서로 축약 |
| `US_STOCK_READONLY_SMOKE_TEST_PLAN.md` | 실제 조회 전 안전 점검 | 운영 자산 | 유지 |
| `US_STOCK_TR_INVENTORY.md` | 미국주식 TR 목록과 상태 | 핵심 자산 | 코드와 대조해 단일 TR 원장으로 확장 |

## 3. 권장 문서 폴더 구조

```text
docs/
├── current/
│   ├── SYSTEM_INVENTORY.md
│   ├── DASHBOARD_MAP.md
│   ├── SYSTEM_MAP.md
│   └── TR_INVENTORY.md
├── architecture/
│   ├── DECISIONS.md
│   ├── DATA_MODEL.md
│   ├── TRADING_ENGINE.md
│   └── SECURITY.md
├── strategies/
│   ├── US_1M_VOLUME_BREAKOUT.md
│   └── US_5M_TREND_PULLBACK.md
├── operations/
│   ├── LOCAL_RUNBOOK.md
│   ├── MOBILE_SECURITY.md
│   └── SMOKE_TEST.md
└── archive/
    └── phase-1-and-task-history/
```

## 4. 문서 작성 원칙

- 문서 첫 줄에 상태를 `implemented`, `partial`, `planned`, `blocked`, `archived` 중 하나로 표시한다.
- 현재 기본 실행 모드와 실주문 허용 여부를 모든 운영 문서에 명시한다.
- TR 코드는 `US_STOCK_TR_INVENTORY.md`를 단일 원장으로 사용한다.
- 실제 키, 토큰, 계좌번호, 잔고, 원본 응답은 문서에 기록하지 않는다.
- 화면 설명은 `V2_DASHBOARD_PROTOTYPE_MAP.md`와 Google Sheet를 함께 갱신한다.
- 과거 기록인 `TASK_LOG.md`는 기존 내용을 고치지 않고 새 항목만 추가한다.
