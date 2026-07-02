# AutoTrader KR — 자동매매 데모 대시보드

개인용 한국 주식 자동매매 운영 대시보드 프로토타입입니다. 모바일 퍼스트 다크 테마, TypeScript, Vite/React/Tailwind/shadcn 기반입니다.

이번 브랜치에서는 FastAPI 백엔드를 추가해 **키움 계좌 조회와 대시보드 데이터 연결이 가능한 구조**를 만들었습니다. 실주문·정정·취소·자동매매 실행 API는 포함하지 않습니다.

## 디렉토리 구조

```
src/
├── pages/                # 라우트별 화면
├── components/           # 대시보드 UI
├── services/
│   ├── adapters.ts       # UI ↔ 데이터 단일 진입점
│   ├── apiClient.ts      # /api HTTP 클라이언트
│   └── mock/data.ts      # 어댑터 내부 데모 데이터
├── types/                # 프론트 도메인 타입
├── store/                # zustand 앱 상태
└── lib/                  # format, utils

backend/
├── app/
│   ├── main.py
│   ├── api/              # health/account/market routes
│   ├── core/config.py
│   ├── schemas/
│   └── services/         # Kiwoom TR client, token manager, mappers
├── requirements.txt
├── .env.example
└── README.md
```

## 핵심 원칙

1. React 프론트엔드는 키움 API에 직접 연결하지 않습니다.
2. 키움 API 호출은 FastAPI 백엔드에서만 수행합니다.
3. Access Token, App Key, Secret Key, 계좌번호 원문은 프론트엔드에 노출하지 않습니다.
4. `VITE_*` 환경변수에 키움 인증정보를 넣지 않습니다.
5. 기본값은 `KIWOOM_MODE=mock`입니다.
6. `KIWOOM_MODE=live`를 명시하기 전까지 키움 실전 서버 호출은 금지됩니다.
7. 이번 단계는 계좌/시세 조회 전용이며 주문 API는 없습니다.

## 실행

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
npm install
npm run dev
```

Vite 개발 서버는 `/api/*`를 `http://localhost:8000`으로 proxy합니다.

## API 목록

- `GET /api/health`
- `GET /api/accounts`
- `GET /api/account/portfolio`
- `GET /api/account/performance`
- `GET /api/account/cash`
- `GET /api/account/holdings`
- `GET /api/market/watchlist`

## 실연동 시 주의

- 주문 실행은 서버 측 워커에서만 구현해야 합니다.
- 대시보드는 내부 API(`/api/*`)만 호출해야 합니다.
- 증권사 API 키/시크릿은 백엔드 `.env` 또는 시크릿 매니저에만 저장합니다.
- Kill Switch, 일일 손실 한도, 동시 보유 종목 수 등 안전 한도는 서버에서도 강제해야 합니다.
- API 오류 시 프론트엔드는 조용히 mock으로 대체하지 않고 오류 상태를 표시합니다.

## 디자인 토큰

전 색상/그라데이션/섀도/타이포는 `src/index.css`의 HSL 시맨틱 토큰 + `tailwind.config.ts`로 관리합니다. 컴포넌트에서 `text-white`, `bg-[#...]` 등 하드코딩은 피합니다.

## 현재 범위

- 기존 대시보드 UI 레이아웃 유지
- mock 직접 import를 UI 컴포넌트/페이지에서 제거
- React Query 기반 조회, 로딩, 오류, 재시도, 캐시 관리
- FastAPI 기반 키움 계좌 조회 백엔드 골격
- 공식 키움 REST API 문서 기준 TR ID/URI/header 반영
- 실주문 API 미구현
