# Deployment Guide

This document describes the current AWS Lightsail deployment flow for the Strategy Pilot backend. The goal is an always-on API server that can be reached from web and mobile clients without keeping a local Mac running.

## Target Topology

```text
React dashboard on Vercel/Amplify or local browser
  -> HTTPS API endpoint
  -> AWS Lightsail static IP
  -> Caddy reverse proxy
  -> FastAPI backend container
  -> Kiwoom REST API
```

The current deployment is API-only. It does not run a real-time trading worker or order execution process yet.

## Prerequisites

- AWS account with Lightsail access
- Lightsail instance running Ubuntu 22.04 or 24.04 LTS
- Lightsail static IP attached to the instance
- Ports 22, 80, 443 open in Lightsail firewall
- Optional but recommended: API domain such as `api.example.com` pointing to the static IP
- GitHub repository access to `teaho4504/strategy-pilot`

## 1. Create AWS Lightsail Instance

1. Open AWS Lightsail.
2. Create an instance.
3. Select Linux/Unix and Ubuntu LTS.
4. Choose a region close to Kiwoom/API users. Seoul is preferred if available, otherwise Tokyo.
5. Start with at least 1 vCPU / 2 GB RAM for account lookup and dashboard API.
6. Attach a static IP.
7. Open firewall ports:
   - 22 TCP for SSH
   - 80 TCP for HTTP and certificate issuance
   - 443 TCP for HTTPS

Register the static IP with Kiwoom only when live mode testing is ready.

## 2. Install Docker

SSH into the instance and run:

```bash
git clone https://github.com/teaho4504/strategy-pilot.git
cd strategy-pilot
git checkout feature/backend-account-integration
bash deploy/aws/lightsail/install-docker.sh
```

Log out and reconnect so the Docker group membership is applied.

Verify:

```bash
docker --version
docker compose version
```

## 3. Configure Environment

Create backend env:

```bash
cd strategy-pilot
cp backend/.env.example backend/.env
nano backend/.env
```

Mock mode example:

```env
KIWOOM_MODE=mock
BACKEND_CORS_ORIGINS=https://your-frontend-domain.com,http://localhost:8080,http://15.165.117.114
KIWOOM_READ_ONLY=true
KIWOOM_ENABLE_ORDER=false
KIWOOM_WATCHLIST=005930,000660,035420
```

Live account lookup example:

```env
KIWOOM_MODE=live
BACKEND_CORS_ORIGINS=https://your-frontend-domain.com,http://15.165.117.114
KIWOOM_APP_KEY=...
KIWOOM_SECRET_KEY=...
KIWOOM_ACCOUNT_NO=...
KIWOOM_BASE_URL=https://api.kiwoom.com
KIWOOM_TOKEN_URL=https://api.kiwoom.com/oauth2/token
KIWOOM_READ_ONLY=true
KIWOOM_ENABLE_ORDER=false
KIWOOM_STEX_TP=0
KIWOOM_QRY_TP=3
KIWOOM_DMST_STEX_TP=KRX
KIWOOM_WATCHLIST=005930,000660,035420
```

Do not put Kiwoom credentials in frontend `.env` or `VITE_*` variables.

## 4. Configure API Host

If you have a domain pointing to the Lightsail static IP:

```bash
cd deploy/aws/lightsail
cat > .env <<'EOF'
API_HOST=api.example.com
EOF
```

Caddy will automatically issue and renew HTTPS certificates.

For temporary IP-only testing, omit this file or use:

```env
API_HOST=:80
```

Use HTTPS before mobile production testing.

## 5. Run Docker Compose

From the repository root:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
```

Check status:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml ps
```

Check logs:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml logs -f backend
```

## 6. API Smoke Tests

Local on the server:

```bash
curl http://127.0.0.1/api/health
curl http://127.0.0.1/api/kiwoom/status
curl http://127.0.0.1/api/accounts
curl http://127.0.0.1/api/account/portfolio
curl http://127.0.0.1/api/account/performance
curl http://127.0.0.1/api/account/cash
curl http://127.0.0.1/api/account/holdings
curl http://127.0.0.1/api/market/watchlist
```

Public static IP:

```bash
curl http://15.165.117.114/api/health
curl http://15.165.117.114/api/kiwoom/status
```

With domain:

```bash
curl https://api.example.com/api/health
curl https://api.example.com/api/kiwoom/status
curl https://api.example.com/api/accounts
curl https://api.example.com/api/account/performance
```

Expected mock mode behavior:

- `/api/health` returns `mode=mock`.
- `/api/kiwoom/status` returns `readOnly=true` and `orderEnabled=false`.
- Account and portfolio endpoints return demo data.
- Order endpoints return 403.

Order guard test:

```bash
curl -i -X POST http://127.0.0.1/api/orders
curl -i -X POST http://127.0.0.1/api/orders/cancel
```

Expected live mode before valid credentials:

- `/api/health` and `/api/kiwoom/status` report missing Kiwoom configuration.
- Account endpoints return explicit API errors.
- The frontend shows the error instead of silently falling back to mock data.

Expected live mode after valid credentials:

- `/api/kiwoom/status` reports credentials and account configured.
- `/api/accounts` tests `ka00001` account lookup.
- `/api/account/performance` tests `ka10085` performance lookup.
- Order endpoints still return 403 while `KIWOOM_READ_ONLY=true` and `KIWOOM_ENABLE_ORDER=false`.

## 7. Frontend Deployment Setting

Set this environment variable in Vercel or AWS Amplify:

```env
VITE_API_BASE_URL=https://api.example.com
```

For temporary static IP testing:

```env
VITE_API_BASE_URL=http://15.165.117.114
```

## Troubleshooting

### Container does not start

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml logs backend
```

Common causes:

- `backend/.env` missing
- invalid environment variable name
- Python package install failure during image build
- wrong Docker build context

### Caddy cannot issue HTTPS certificate

Check:

- domain A record points to the Lightsail static IP
- ports 80 and 443 are open
- `API_HOST` is a real domain, not an IP address
- no other process is already using ports 80/443

Logs:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml logs caddy
```

### API is reachable on server but not from browser

Check:

- Lightsail firewall permits 80/443
- `BACKEND_CORS_ORIGINS` includes the frontend origin
- frontend has `VITE_API_BASE_URL` set to the public API URL
- browser is not blocking mixed content. HTTPS frontend should call HTTPS API.

### Kiwoom live mode fails

Check:

- `KIWOOM_MODE=live`
- `KIWOOM_READ_ONLY=true`
- `KIWOOM_ENABLE_ORDER=false`
- App key and secret are correct
- account number is correct
- Lightsail static IP is registered with Kiwoom if required
- `/api/kiwoom/status` token state
- Kiwoom TR payload and response fields match the current official guide
- token issue flow works before account TR tests

### Roll back

```bash
git fetch origin
git checkout feature/backend-account-integration
git reset --hard <known-good-commit>
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
```

Do not run destructive rollback commands until you have confirmed the target commit.
