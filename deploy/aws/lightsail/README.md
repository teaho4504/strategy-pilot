# AWS Lightsail Backend Deployment

This is the first always-on deployment target for the Strategy Pilot backend. It is designed for mobile/web access from anywhere without keeping a local Mac running.

## Recommended Architecture

```text
Mobile / Web browser
  -> Vercel or AWS Amplify React app
  -> HTTPS API domain
  -> AWS Lightsail or EC2 Docker host
  -> FastAPI backend
  -> Kiwoom REST API now, Kiwoom WebSocket/worker in later phases
```

For the first backend account lookup milestone, Lightsail is sufficient. Move to ECS/EKS only after real-time workers, Redis, queues, and monitoring become necessary.

## 1. Create Lightsail Instance

Recommended starting size:

- Region: Seoul if available for your account, otherwise Tokyo
- OS: Ubuntu 24.04 LTS
- Plan: 1 vCPU / 2 GB RAM minimum for API-only mock/live account lookup
- Static IP: required
- Firewall: allow 22, 80, 443

Register the Lightsail static IP in Kiwoom only after live API testing is ready.

## 2. Install Docker

SSH into the instance and run:

```bash
git clone https://github.com/teaho4504/strategy-pilot.git
cd strategy-pilot
git checkout feature/lightsail-readonly-deployment
bash deploy/aws/lightsail/install-docker.sh
```

Log out and back in so the Docker group takes effect.

## 3. Configure Backend Environment

```bash
cd strategy-pilot
mkdir -p deploy/backend
cp deploy/backend/.env.example deploy/backend/.env
nano deploy/backend/.env
```

Minimum mock mode:

```env
KIWOOM_MODE=mock
BACKEND_CORS_ORIGINS=https://your-frontend-domain.com,http://localhost:8080
```

Live account lookup mode:

```env
KIWOOM_MODE=live
KIWOOM_APP_KEY=...
KIWOOM_SECRET_KEY=...
KIWOOM_ACCOUNT_NO=...
KIWOOM_READ_ONLY=true
KIWOOM_ENABLE_ORDER=false
BACKEND_CORS_ORIGINS=https://your-frontend-domain.com
```

Do not put Kiwoom credentials in frontend `VITE_*` variables.

## 4. Configure API Host

If you have a domain such as `api.example.com` pointing to the Lightsail static IP:

```bash
cd deploy/aws/lightsail
cat > .env <<'EOF'
API_HOST=api.example.com
EOF
```

Caddy will request and renew HTTPS certificates automatically.

If you do not have a domain yet, keep `API_HOST=:80` and use `http://STATIC_IP` only for temporary testing.

## 5. Start Backend

From repository root:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
```

Check logs:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml logs -f backend
```

Smoke test:

```bash
curl http://127.0.0.1/api/health
curl http://127.0.0.1/api/accounts
curl http://127.0.0.1/api/account/performance
```

With a domain:

```bash
curl https://api.example.com/api/health
curl https://api.example.com/api/accounts
curl https://api.example.com/api/account/performance
```

## 6. Frontend Mobile/Web Setting

Set this in Vercel/Amplify frontend environment variables:

```env
VITE_API_BASE_URL=https://api.example.com
```

For temporary IP testing:

```env
VITE_API_BASE_URL=http://STATIC_IP
```

HTTPS domain is strongly recommended for mobile browser reliability.

## 7. Kiwoom TRs Required For Current Account Lookup

Current read-only account lookup uses these TRs:

- `ka00001`: account number lookup, used by `GET /api/accounts`
- `ka10085`: account performance, used by `GET /api/account/performance`
- `kt00001`: cash/deposit lookup, used by `GET /api/account/cash`
- `kt00004`: account portfolio snapshot, used by `GET /api/account/portfolio`
- `kt00005`: holdings/fill balance, used by `GET /api/account/holdings`
- `GET /api/market/watchlist` remains mock/demo data in this read-only deployment branch.

Before live mode, verify Kiwoom's official REST guide for request payloads, response fields, continuation headers, token flow, and IP registration requirements. Adjust mappers after collecting real response samples.

## 8. Performance Review For Later Real-Time Trading

Current structure is good for account lookup and dashboard state:

- React: UI only
- FastAPI: read APIs, health, settings, control plane
- Python worker later: Kiwoom WebSocket, strategy loop, risk checks

For real-time automated trading, do not route the trading decision loop through React or ordinary dashboard HTTP requests. The later production structure should add:

- a long-running Python WebSocket worker
- Redis or another low-latency state/cache layer
- durable event log/database
- server-side risk engine
- separated order execution adapter

FastAPI remains the dashboard/control API. The low-latency market-data and strategy loop should live in the worker process.
