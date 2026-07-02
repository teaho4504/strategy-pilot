# AutoTrader KR — 자동매매 데모 대시보드

개인용 한국 주식 자동매매 운영 대시보드 프로토타입입니다. 모바일 퍼스트 다크 테마, TypeScript, Vite/React/Tailwind/shadcn 기반입니다.

이번 브랜치에서는 FastAPI 백엔드를 추가해 **키움 계좌 조회와 대시보드 데이터 연결이 가능한 구조**를 만들었습니다. 실주문·정정·취소·자동매매 실행 API는 포함하지 않습니다.

## 우선순위

1. 24시간 접속 가능한 AWS 백엔드 배포 구조 구축
2. mock 모드에서 React와 FastAPI 연동 확인
3. 키움 live 설정 전 오류 상태 확인
4. 키움 live 설정 후 `ka00001`, `ka10085` 등 계좌 조회 TR 확인
5. 실제 응답 샘플 기준 mapper 보정
6. 2차/3차 작업에서 실시간 WebSocket worker와 주문 실행 계층 분리

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
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md

deploy/aws/lightsail/
├── docker-compose.yml
├── Caddyfile
├── install-docker.sh
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

## 로컬 실행

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
cp .env.example .env
npm run dev
```

Vite 개발 서버는 `/api/*`를 `http://localhost:8000`으로 proxy합니다. 모바일/클라우드에서는 `VITE_API_BASE_URL`을 API 서버 주소로 지정합니다.

```env
VITE_API_BASE_URL=https://api.your-domain.com
```

## AWS 24시간 접속 배포

첫 배포 대상은 AWS Lightsail 또는 EC2 + Docker Compose입니다.

```bash
git clone https://github.com/teaho4504/strategy-pilot.git
cd strategy-pilot
git checkout feature/backend-account-integration
bash deploy/aws/lightsail/install-docker.sh
cp backend/.env.example backend/.env
# backend/.env 수정 후
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
```

상세 절차는 `deploy/aws/lightsail/README.md`를 확인합니다.

도메인이 있으면 `API_HOST=api.your-domain.com`으로 Caddy HTTPS를 사용합니다. 도메인이 없으면 임시로 `http://STATIC_IP` 테스트만 가능합니다. 모바일 상시 접속은 HTTPS 도메인 사용을 권장합니다.

## Vercel 프론트엔드 배포

React/Vite 프론트엔드는 Vercel에 배포하고, FastAPI 백엔드는 AWS Lightsail에 유지하는 구성을 권장합니다.

Vercel 프로젝트 설정:

```text
Repository: teaho4504/strategy-pilot
Branch: feature/backend-account-integration
Framework Preset: Vite
Build Command: npm run build
Output Directory: dist
Install Command: npm install
```

Vercel 환경변수:

```env
VITE_API_BASE_URL=http://15.165.117.114
```

위 주소는 현재 AWS Lightsail 백엔드 임시 주소입니다. Vercel은 HTTPS로 서비스되므로 브라우저에서 HTTP API 호출이 차단될 수 있습니다. 운영 배포에서는 `https://api.your-domain.com` 같은 HTTPS API 도메인을 연결한 뒤 `VITE_API_BASE_URL`을 해당 주소로 바꿉니다.

상세 절차는 `docs/VERCEL.md`를 확인합니다. Vercel에는 키움 App Key, Secret Key, Access Token, 계좌번호를 넣지 않습니다.

## API 목록

- `GET /api/health`
- `GET /api/accounts`
- `GET /api/account/portfolio`
- `GET /api/account/performance`
- `GET /api/account/cash`
- `GET /api/account/holdings`
- `GET /api/market/watchlist`

## Kiwoom TR 매핑

- `GET /api/accounts` → `ka00001`
- `GET /api/account/performance` → `ka10085`
- `GET /api/account/cash` → `kt00001`
- `GET /api/account/portfolio` → `kt00004` + `ka10085`
- `GET /api/account/holdings` → `kt00005` + `ka10085`
- `GET /api/market/watchlist` → `ka10001`

실계좌 조회 전에는 키움 공식 REST 문서에서 TR ID, endpoint, payload, response field, `cont-yn`, `next-key`, 토큰 발급, IP 등록 요건을 다시 확인해야 합니다. 실제 응답 샘플을 받은 뒤 mapper를 보정합니다.

## 테스트 방법

Mock mode:

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/accounts
curl http://localhost:8000/api/account/portfolio
curl http://localhost:8000/api/account/performance
curl http://localhost:8000/api/account/cash
curl http://localhost:8000/api/account/holdings
curl http://localhost:8000/api/market/watchlist
```

Live 설정 전 오류 표시:

```bash
KIWOOM_MODE=live uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/api/health
curl http://localhost:8000/api/accounts
```

정상적으로 missing credential 또는 Kiwoom 설정 오류가 표시되어야 합니다. 프론트엔드는 이 오류를 mock 데이터로 조용히 대체하지 않고 화면에 표시해야 합니다.

Live 계좌 조회:

```bash
# backend/.env 설정 후
KIWOOM_MODE=live
KIWOOM_APP_KEY=...
KIWOOM_SECRET_KEY=...
KIWOOM_ACCOUNT_NO=...

curl http://localhost:8000/api/accounts          # ka00001
curl http://localhost:8000/api/account/performance # ka10085
```

## 실시간 자동매매 성능 방향

현재 구조는 계좌 조회와 대시보드 상태 조회에는 적합합니다. 실시간 자동매매에서는 아래처럼 역할을 분리해야 합니다.

- React: 화면 표시
- FastAPI: 조회 API, 설정, 상태, 제어 plane
- Python worker: Kiwoom WebSocket 수신, 전략 판단, 리스크 검증
- Redis/DB: 최근 시세 캐시, 이벤트 로그, 상태 저장
- Order adapter: 서버 측 주문 실행 계층

실시간 매매 판단 루프를 React 또는 일반 HTTP 요청에 넣지 않습니다. 2차/3차 작업에서도 이 기준으로 구조를 유지합니다.

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