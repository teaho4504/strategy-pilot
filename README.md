# AutoTrader KR — 자동매매 데모 대시보드

개인용 한국 주식 자동매매 운영 대시보드의 **프론트엔드 프로토타입**입니다. 모바일 퍼스트 다크 테마, TypeScript, Vite/React/Tailwind/shadcn 기반. 기본 데이터 경로는 FastAPI 백엔드이며, 백엔드 기본값은 **mock 모드**입니다. 실제 증권사 주문·실로그인은 포함하지 않습니다.

## 실행

### Frontend

```bash
npm install
npm run dev
```

Vite 개발 서버는 `/api` 요청을 `http://localhost:8000`으로 프록시합니다.

모바일 또는 클라우드 배포에서는 `.env`에 API 서버 주소를 지정합니다.

```bash
cp .env.example .env
# 같은 Wi-Fi 모바일 테스트 예시
VITE_API_BASE_URL=http://192.168.0.10:8000
# 클라우드 배포 예시
VITE_API_BASE_URL=https://api.your-domain.com
```

`VITE_API_BASE_URL`이 비어 있으면 기존 로컬 proxy(`/api`)를 사용합니다. 프론트엔드 `.env`에는 키움 App Key, Secret, Access Token, 계좌번호를 절대 넣지 않습니다.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

모바일 기기에서 같은 Wi-Fi로 로컬 백엔드에 접근하려면 백엔드를 외부 인터페이스에 바인딩합니다.

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

그 다음 Mac 또는 서버의 LAN IP를 프론트 `.env`의 `VITE_API_BASE_URL`에 넣습니다. 예: `http://192.168.0.10:8000`.

클라우드 모바일 접속은 FastAPI 백엔드를 AWS Lightsail/EC2 같은 서버에 배포하고, 프론트는 Vercel/Amplify에서 `VITE_API_BASE_URL=https://api.your-domain.com`으로 빌드합니다. 이 방식이면 Mac을 꺼도 모바일에서 접속할 수 있습니다.

## 백엔드 환경변수 예시

```bash
KIWOOM_MODE=mock
KIWOOM_API_BASE_URL=https://api.kiwoom.com
KIWOOM_APP_KEY=
KIWOOM_APP_SECRET=
KIWOOM_ACCESS_TOKEN=
KIWOOM_ACCOUNT_NO=
CORS_ORIGINS=http://localhost:8080,http://localhost:5173,http://localhost:3000,http://192.168.0.10:8080,https://your-frontend-domain.com
```

민감정보는 `backend/.env`에서만 관리합니다. `VITE_*` 환경변수에 키움 App Key, Secret, Access Token, 계좌번호를 넣지 않습니다. `.env`는 Git에 포함하지 않습니다.

## API

- `GET /api/health`
- `GET /api/accounts`
- `GET /api/account/portfolio`
- `GET /api/account/performance`
- `GET /api/account/holdings`
- `GET /api/market/watchlist`

`/api/account/performance`는 live 모드에서 키움 REST `ka10085` 계좌수익률 조회를 사용하도록 구성했습니다. `cont-yn`, `next-key`가 있으면 서버에서 자동 연속조회합니다. 주문 API는 구현하지 않았고 호출하지 않습니다.

## 디렉토리 구조 (핸드오프)

```
backend/
├── app/
│   ├── api/               # health, account, market HTTP routes
│   ├── core/              # 환경 설정, 마스킹
│   ├── schemas/           # API 응답 모델
│   └── services/          # Kiwoom client, token manager, portfolio mapper
├── requirements.txt
├── .env.example
└── README.md

src/
├── pages/                # 라우트별 화면 (Home, Strategies, Builder, Orders, Analytics, Settings)
├── components/
│   ├── layout/           # AppShell, TopBar, BottomNav
│   ├── common/           # Card, DemoBadge, DeltaPct ...
│   ├── home/             # 홈 대시보드 위젯
│   └── ui/               # shadcn 프리미티브
├── services/
│   ├── apiClient.ts      # HTTP client, API error model
│   ├── adapters.ts       # UI ↔ API/데모 데이터 어댑터
│   └── mock/data.ts      # 아직 백엔드가 없는 도메인의 데모 데이터
├── types/                # 도메인 타입 (Portfolio, Strategy, Order ...)
├── store/                # zustand 앱 상태 (자동매매 on/off, 선택 계좌)
└── lib/                  # format, utils
```

## 이번 변경 파일

- `backend/app/main.py`
- `backend/app/api/health.py`
- `backend/app/api/account.py`
- `backend/app/api/market.py`
- `backend/app/core/config.py`
- `backend/app/schemas/account.py`
- `backend/app/schemas/portfolio.py`
- `backend/app/services/kiwoom_client.py`
- `backend/app/services/token_manager.py`
- `backend/app/services/portfolio_mapper.py`
- `backend/requirements.txt`
- `backend/.env.example`
- `backend/README.md`
- `.env.example`
- `src/services/apiClient.ts`
- `src/services/adapters.ts`
- `src/components/home/PortfolioCard.tsx`
- `src/components/home/AutomationControl.tsx`
- `src/components/home/ActiveStrategiesCard.tsx`
- `src/components/home/TimelineCard.tsx`
- `src/components/home/MarketSummary.tsx`
- `src/pages/Strategies.tsx`
- `src/pages/Orders.tsx`
- `src/pages/Analytics.tsx`
- `src/pages/Settings.tsx`
- `vite.config.ts`
- `.gitignore`

## 실연동 시 주의 (반드시 읽기)

1. **주문 실행은 서버 측 워커에서만**. 대시보드는 내부 API(`/api/*`)만 호출하도록 유지.
2. **증권사 API 키/시크릿은 프론트엔드 코드·환경변수에 절대 포함하지 말 것.** 서버 사이드 시크릿 매니저 사용.
3. Kill Switch, 일일 손실 한도, 동시 보유 종목 수 등 안전 한도는 **서버에서도 강제** 해야 함. 클라이언트만 신뢰 금지.
4. PWA·모바일 안전영역(safe-area-inset)을 고려한 레이아웃. Vercel 배포 시 SPA fallback 설정 필요.

## 디자인 토큰

전 색상/그라데이션/섀도/타이포는 `src/index.css`의 HSL 시맨틱 토큰 + `tailwind.config.ts`로 관리. 컴포넌트에서 `text-white`, `bg-[#...]` 등 하드코딩 금지.

## 데모 안전장치

- 기본 상태: `KIWOOM_MODE=mock`
- 기본 UI 상태: `모의투자 · 자동매매 일시정지`
- 모든 토글·Kill Switch는 확인 모달 후 동작
- 수동 주문 UI는 비활성화
- 실전 주문 API 없음
