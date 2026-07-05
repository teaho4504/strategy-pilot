# AutoTrader KR — 자동매매 데모 대시보드

개인용 한국 주식 자동매매 운영 대시보드의 **프론트엔드 프로토타입**입니다. 모바일 퍼스트 다크 테마, TypeScript, Vite/React/Tailwind/shadcn 기반입니다. 홈 대시보드는 FastAPI read-only backend의 `/api/*` 계좌 조회 데이터를 표시할 수 있으며, 주문·정정·취소·자동매매 실행은 포함되지 않습니다.

## 로컬 Read-only API 연결

프론트엔드는 기본적으로 아래 backend를 호출합니다.

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

브로커 App Key, Secret, Token, 계좌번호는 frontend 환경변수에 넣지 않습니다. Kiwoom 인증정보는 `backend/.env`에서만 관리합니다.

## 디렉토리 구조 (핸드오프)

```
src/
├── pages/                # 라우트별 화면 (Home, Strategies, Builder, Orders, Analytics, Settings)
├── components/
│   ├── layout/           # AppShell, TopBar, BottomNav
│   ├── common/           # Card, DemoBadge, DeltaPct ...
│   ├── home/             # 홈 대시보드 위젯
│   └── ui/               # shadcn 프리미티브
├── services/
│   ├── apiClient.ts      # FastAPI /api/* read-only HTTP client
│   ├── adapters.ts       # UI ↔ 데이터 어댑터
│   └── mock/data.ts      # 데모 데이터 단일 소스
├── types/                # 도메인 타입 (Portfolio, Strategy, Order ...)
├── store/                # zustand 앱 상태 (자동매매 on/off, 선택 계좌)
└── lib/                  # format, utils
```

## 실연동 시 주의 (반드시 읽기)

1. **주문 실행은 서버 측 워커에서만**. 대시보드는 내부 API(`/api/*`)만 호출하도록 유지.
2. **증권사 API 키/시크릿은 프론트엔드 코드·환경변수에 절대 포함하지 말 것.** 서버 사이드 시크릿 매니저 사용.
3. `src/services/adapters.ts`는 project-owned FastAPI `/api/*`만 호출. 브라우저에서 Kiwoom API 직접 호출 금지.
4. Kill Switch, 일일 손실 한도, 동시 보유 종목 수 등 안전 한도는 **서버에서도 강제** 해야 함. 클라이언트만 신뢰 금지.
5. PWA·모바일 안전영역(safe-area-inset)을 고려한 레이아웃. Vercel 배포 시 SPA fallback 설정 필요.

## 디자인 토큰

전 색상/그라데이션/섀도/타이포는 `src/index.css`의 HSL 시맨틱 토큰 + `tailwind.config.ts`로 관리. 컴포넌트에서 `text-white`, `bg-[#...]` 등 하드코딩 금지.

## 데모 안전장치

- 기본 상태: `모의투자 · 자동매매 일시정지`
- 모든 토글·Kill Switch는 확인 모달 후 동작
- 수동 주문 UI는 비활성화 (전략 발동 주문만)
