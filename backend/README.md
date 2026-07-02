# Strategy Pilot Backend

FastAPI 기반 읽기 전용 백엔드입니다. 기본값은 `KIWOOM_MODE=mock`이며, live 모드로 명시적으로 전환하기 전까지 키움 실서버를 호출하지 않습니다.

## 실행

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

프론트엔드는 로컬 개발에서 Vite proxy를 통해 `/api` 요청을 `http://localhost:8000`으로 전달합니다.

## 모바일 접속

같은 Wi-Fi의 모바일 기기에서 로컬 백엔드에 접근하려면 백엔드를 `0.0.0.0`으로 실행합니다.

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

프론트엔드 `.env`에는 Mac 또는 서버의 LAN IP를 넣습니다.

```bash
VITE_API_BASE_URL=http://192.168.0.10:8000
```

백엔드 `.env`의 `CORS_ORIGINS`에는 모바일에서 접속하는 프론트 주소를 추가합니다.

```bash
CORS_ORIGINS=http://localhost:8080,http://192.168.0.10:8080
```

Mac을 꺼도 모바일에서 접속해야 한다면 백엔드는 AWS Lightsail/EC2 같은 상시 서버에 배포하고, 프론트는 Vercel/Amplify에서 `VITE_API_BASE_URL=https://api.your-domain.com`으로 빌드합니다.

## 환경변수

```bash
KIWOOM_MODE=mock
KIWOOM_API_BASE_URL=https://api.kiwoom.com
KIWOOM_APP_KEY=
KIWOOM_APP_SECRET=
KIWOOM_ACCESS_TOKEN=
KIWOOM_ACCOUNT_NO=
CORS_ORIGINS=http://localhost:8080,http://localhost:5173,http://localhost:3000,http://192.168.0.10:8080,https://your-frontend-domain.com
```

`.env`에는 실제 값을 넣을 수 있지만 Git에 포함하지 않습니다. App Key, Secret, Access Token, 계좌번호는 프론트엔드 `VITE_*` 환경변수에 절대 넣지 않습니다.

## API

- `GET /api/health`
- `GET /api/accounts`
- `GET /api/account/portfolio`
- `GET /api/account/performance`
- `GET /api/account/holdings`
- `GET /api/market/watchlist`

## 키움 ka10085 연동

`KIWOOM_MODE=live`일 때만 `ka10085` 계좌수익률 조회를 호출합니다. `cont-yn`과 `next-key` 응답 헤더가 있으면 서버에서 최대 20페이지까지 자동 연속조회합니다.

주문 API는 구현하지 않았고 호출하지 않습니다. 실전 주문은 별도 서버 측 자동매매 엔진에서 리스크 검증과 함께 구현해야 합니다.
