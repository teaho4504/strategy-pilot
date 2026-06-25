# AutoTrader KR — 자동매매 데모 대시보드

개인용 한국 주식 자동매매 운영 대시보드의 **프론트엔드 프로토타입**입니다. 모바일 퍼스트 다크 테마, TypeScript, Vite/React/Tailwind/shadcn 기반. 모든 데이터는 **모의(mock)** 이며 실제 증권사 API 연동·실주문·로그인은 포함되지 않습니다.

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
│   ├── adapters.ts       # 🔌 UI ↔ 데이터 어댑터 (이 파일만 교체하면 실연동)
│   └── mock/data.ts      # 데모 데이터 단일 소스
├── types/                # 도메인 타입 (Portfolio, Strategy, Order ...)
├── store/                # zustand 앱 상태 (자동매매 on/off, 선택 계좌)
└── lib/                  # format, utils
```

## 실연동 시 주의 (반드시 읽기)

1. **주문 실행은 서버 측 워커에서만**. 대시보드는 내부 API(`/api/*`)만 호출하도록 유지.
2. **증권사 API 키/시크릿은 프론트엔드 코드·환경변수에 절대 포함하지 말 것.** 서버 사이드 시크릿 매니저 사용.
3. `src/services/adapters.ts`의 시그니처를 유지한 채로 HTTP/SSE 클라이언트로 교체. 타입(`src/types`)을 공유 패키지로 이관 권장.
4. Kill Switch, 일일 손실 한도, 동시 보유 종목 수 등 안전 한도는 **서버에서도 강제** 해야 함. 클라이언트만 신뢰 금지.
5. PWA·모바일 안전영역(safe-area-inset)을 고려한 레이아웃. Vercel 배포 시 SPA fallback 설정 필요.

## 디자인 토큰

전 색상/그라데이션/섀도/타이포는 `src/index.css`의 HSL 시맨틱 토큰 + `tailwind.config.ts`로 관리. 컴포넌트에서 `text-white`, `bg-[#...]` 등 하드코딩 금지.

## 데모 안전장치

- 기본 상태: `모의투자 · 자동매매 일시정지`
- 모든 토글·Kill Switch는 확인 모달 후 동작
- 수동 주문 UI는 비활성화 (전략 발동 주문만)
