# Vercel Frontend Deployment

This guide deploys the mobile-first React dashboard to Vercel while keeping the FastAPI backend on AWS Lightsail.

## Target Architecture

```text
Mobile / PC browser
  -> Vercel React dashboard
  -> Vercel /api proxy rewrite
  -> AWS Lightsail FastAPI backend
  -> Kiwoom REST API
```

Backend API currently running:

```text
http://15.165.117.114
```

Public frontend:

```text
https://strategy-pilot.vercel.app
```

## Why Vercel For Frontend

- React/Vite deployment is simple.
- GitHub push can trigger automatic deployments.
- HTTPS is provided by default.
- The AWS Lightsail server can focus on FastAPI and later Python workers.
- Frontend secrets are not needed. Kiwoom credentials remain only on the backend server.

## Required Repository Files

The repository includes:

- `vercel.json`
- `.env.example`
- Vite build script in `package.json`

Vercel settings should be:

```text
Framework Preset: Vite
Build Command: npm run build
Output Directory: dist
Install Command: npm install
```

`vercel.json` includes:

- `/api/:path*` rewrite to the AWS Lightsail backend
- SPA fallback rewrite to `/index.html`

This allows the frontend to call same-origin API paths such as `/api/health` from `https://strategy-pilot.vercel.app`.

## 1. Import Project

1. Open Vercel dashboard.
2. Click `Add New` -> `Project`.
3. Import GitHub repository:

```text
teaho4504/strategy-pilot
```

4. Select branch:

```text
feature/backend-account-integration
```

If Vercel defaults to `main`, change the production branch or create a deployment from the feature branch first.

## 2. Configure Environment Variables

For the current proxy-based setup, `VITE_API_BASE_URL` can be omitted in Vercel. The frontend will call `/api/*`, and Vercel will proxy those requests to AWS Lightsail.

Optional direct API mode:

```env
VITE_API_BASE_URL=https://api.your-domain.com
```

Use direct API mode only after the AWS backend has an HTTPS domain.

Do not add any of these to Vercel:

```text
KIWOOM_APP_KEY
KIWOOM_SECRET_KEY
KIWOOM_ACCOUNT_NO
ACCESS_TOKEN
```

Kiwoom credentials must stay only in `backend/.env` on the AWS server.

## 3. Deploy

Click `Deploy` in Vercel.

After deployment completes, open the Vercel URL on mobile and PC.

Expected behavior:

- Dashboard loads from Vercel.
- API calls use `https://strategy-pilot.vercel.app/api/*`.
- Vercel proxies `/api/*` to `http://15.165.117.114/api/*`.
- `/api/health` and account data are loaded from AWS Lightsail backend.
- If backend is down or Kiwoom credentials are invalid, UI shows an error state instead of silently using mock data.

## 4. Verify From Browser

Open these URLs:

```text
https://strategy-pilot.vercel.app
https://strategy-pilot.vercel.app/api/health
https://strategy-pilot.vercel.app/api/kiwoom/status
```

Direct backend checks:

```bash
curl http://15.165.117.114/api/health
curl http://15.165.117.114/api/kiwoom/status
curl http://15.165.117.114/api/accounts
```

Expected browser network requests:

```text
https://strategy-pilot.vercel.app/api/health
https://strategy-pilot.vercel.app/api/accounts
https://strategy-pilot.vercel.app/api/account/performance
```

## 5. HTTP/HTTPS Note

The proxy rewrite avoids browser mixed-content blocking because the browser only calls HTTPS Vercel URLs.

For a production-grade setup, still add a real HTTPS API domain:

```text
https://api.your-domain.com
```

Then either:

- keep the Vercel `/api/*` proxy and update `vercel.json` destination to the HTTPS API domain, or
- set `VITE_API_BASE_URL=https://api.your-domain.com` in Vercel and call the API directly.

The backend deployment already includes Caddy. Point the API domain A record to the Lightsail static IP and set:

```bash
cd ~/strategy-pilot/deploy/aws/lightsail
cat > .env <<'EOF'
API_HOST=api.your-domain.com
EOF
cd ~/strategy-pilot
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d
```

## 6. Redeploy After Code Changes

Push or merge changes to the branch connected to Vercel. Vercel will build automatically.

Manual redeploy:

1. Open Vercel project.
2. Go to Deployments.
3. Select latest deployment.
4. Click Redeploy.

## 7. Troubleshooting

### Build fails

Check Vercel build logs for:

- dependency install failure
- TypeScript errors
- missing environment variable usage
- wrong output directory

Expected output directory:

```text
dist
```

### App loads but API data fails

Check:

- `vercel.json` includes the `/api/:path*` rewrite.
- AWS backend is running.
- `curl http://15.165.117.114/api/health` works.
- `https://strategy-pilot.vercel.app/api/health` works after Vercel redeploy.
- Vercel deployed the latest `feature/backend-account-integration` commit.

### CORS error

The proxy-based setup usually avoids browser CORS because the browser calls the same Vercel origin. If direct API mode is used, add the Vercel URL to `backend/.env` on AWS:

```env
BACKEND_CORS_ORIGINS=https://strategy-pilot.vercel.app,http://15.165.117.114
```

Then redeploy backend:

```bash
cd ~/strategy-pilot
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
```

### Mixed content error

Use the Vercel `/api/*` proxy rewrite or an HTTPS API domain instead of direct browser calls to `http://15.165.117.114`.

## 8. Current Safety Position

Frontend must remain display/control UI only:

- No Kiwoom credentials in browser.
- No direct Kiwoom API calls from React.
- No direct order execution from React.
- All order-related endpoints remain disabled until risk engine and worker are implemented.
