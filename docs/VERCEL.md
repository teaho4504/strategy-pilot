# Vercel Frontend Deployment

This guide deploys the mobile-first React dashboard to Vercel while keeping the FastAPI backend on AWS Lightsail.

## Target Architecture

```text
Mobile / PC browser
  -> Vercel React dashboard
  -> AWS Lightsail FastAPI backend
  -> Kiwoom REST API
```

Backend API currently running:

```text
http://15.165.117.114
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

`vercel.json` also includes an SPA fallback rewrite to `/index.html`.

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

Add this variable in Vercel Project Settings -> Environment Variables:

```env
VITE_API_BASE_URL=http://15.165.117.114
```

Apply it to:

- Production
- Preview
- Development, optional

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
- API calls go to `http://15.165.117.114`.
- `/api/health` and account data are loaded from AWS Lightsail backend.
- If backend is down or Kiwoom credentials are invalid, UI shows an error state instead of silently using mock data.

## 4. Verify From Browser

Open the Vercel app and inspect network requests.

Expected API base:

```text
http://15.165.117.114/api/health
http://15.165.117.114/api/accounts
http://15.165.117.114/api/account/performance
```

Direct API checks:

```bash
curl http://15.165.117.114/api/health
curl http://15.165.117.114/api/kiwoom/status
curl http://15.165.117.114/api/accounts
```

## 5. Important HTTP/HTTPS Note

Vercel serves the frontend over HTTPS. Browsers may block HTTPS pages calling plain HTTP APIs as mixed content.

If the browser blocks API calls to `http://15.165.117.114`, use a real API domain with HTTPS:

```text
https://api.your-domain.com
```

Then update Vercel environment variable:

```env
VITE_API_BASE_URL=https://api.your-domain.com
```

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

- `VITE_API_BASE_URL` is set in Vercel.
- AWS backend is running.
- `curl http://15.165.117.114/api/health` works.
- Browser is not blocking mixed content.
- `BACKEND_CORS_ORIGINS` includes the Vercel app origin.

### CORS error

Add the Vercel URL to `backend/.env` on AWS:

```env
BACKEND_CORS_ORIGINS=https://your-vercel-app.vercel.app,http://15.165.117.114
```

Then redeploy backend:

```bash
cd ~/strategy-pilot
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
```

### Mixed content error

Use HTTPS API domain instead of `http://15.165.117.114`.

## 8. Current Safety Position

Frontend must remain display/control UI only:

- No Kiwoom credentials in browser.
- No direct Kiwoom API calls from React.
- No direct order execution from React.
- All order-related endpoints remain disabled until risk engine and worker are implemented.
