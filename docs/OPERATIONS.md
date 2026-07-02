# Operations Runbook

This runbook covers the current AWS Lightsail Docker deployment. Commands assume the repository is checked out at `~/strategy-pilot` on the server and the active branch is `feature/backend-account-integration`.

## Quick Status Check

```bash
cd ~/strategy-pilot
git status --short
git branch --show-current
docker compose -f deploy/aws/lightsail/docker-compose.yml ps
curl http://127.0.0.1/api/health
```

For public API domain:

```bash
curl https://api.example.com/api/health
```

## Server Restart

Restart the whole Lightsail instance from AWS Console if the OS is unhealthy.

After SSH reconnect:

```bash
cd ~/strategy-pilot
docker compose -f deploy/aws/lightsail/docker-compose.yml ps
curl http://127.0.0.1/api/health
```

If containers did not start automatically:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d
```

## Restart Containers Only

Restart backend and Caddy:

```bash
cd ~/strategy-pilot
docker compose -f deploy/aws/lightsail/docker-compose.yml restart
```

Restart backend only:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml restart backend
```

Restart Caddy only:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml restart caddy
```

## Docker Redeploy

Use this when code has changed on GitHub.

```bash
cd ~/strategy-pilot
git fetch origin
git checkout feature/backend-account-integration
git pull --ff-only origin feature/backend-account-integration
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
```

Verify:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml ps
curl http://127.0.0.1/api/health
curl http://127.0.0.1/api/accounts
```

## Logs

Backend logs:

```bash
cd ~/strategy-pilot
docker compose -f deploy/aws/lightsail/docker-compose.yml logs -f backend
```

Caddy logs:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml logs -f caddy
```

Recent logs only:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml logs --tail=200 backend
```

Container health and resource usage:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml ps
docker stats
```

Disk usage:

```bash
df -h
docker system df
```

Safe cleanup of unused Docker build cache/images:

```bash
docker system prune -f
```

Do not prune volumes unless you have verified no important persistent data is stored there.

## Environment Changes

Edit backend environment:

```bash
cd ~/strategy-pilot
nano backend/.env
```

Apply changes:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
```

Important rules:

- Keep Kiwoom secrets only in `backend/.env` or a managed secret store.
- Do not commit `.env`.
- Keep frontend `VITE_API_BASE_URL` free of secrets.
- Switch to `KIWOOM_MODE=live` only when IP registration and credentials are ready.

## Backup

Current deployment has no production PostgreSQL volume yet. Backups currently focus on config and future database state.

### Backup Backend Env

```bash
cd ~/strategy-pilot
mkdir -p ~/backups/strategy-pilot
cp backend/.env ~/backups/strategy-pilot/backend.env.$(date +%Y%m%d-%H%M%S)
chmod 600 ~/backups/strategy-pilot/backend.env.*
```

Store this backup securely. It may contain Kiwoom credentials.

### Future PostgreSQL Backup

When PostgreSQL is added:

```bash
docker compose -f deploy/aws/lightsail/docker-compose.yml exec postgres \
  pg_dump -U strategy_pilot strategy_pilot > ~/backups/strategy-pilot/postgres.$(date +%Y%m%d-%H%M%S).sql
```

For compressed backup:

```bash
gzip ~/backups/strategy-pilot/postgres.YYYYMMDD-HHMMSS.sql
```

### Future Redis Backup

Redis should be treated as fast/volatile state. If persistence is enabled later, back up RDB/AOF files from the Redis volume only after documenting the volume path.

## Restore

### Restore Backend Env

```bash
cd ~/strategy-pilot
cp ~/backups/strategy-pilot/backend.env.YYYYMMDD-HHMMSS backend/.env
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
```

### Future PostgreSQL Restore

```bash
cat ~/backups/strategy-pilot/postgres.YYYYMMDD-HHMMSS.sql | \
  docker compose -f deploy/aws/lightsail/docker-compose.yml exec -T postgres \
  psql -U strategy_pilot strategy_pilot
```

Restore only after confirming target environment and backup timestamp.

## Rollback

Identify a known-good commit:

```bash
cd ~/strategy-pilot
git log --oneline -20
```

Rollback:

```bash
git checkout feature/backend-account-integration
git reset --hard <known-good-commit>
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
```

This is destructive to local uncommitted changes. Do not run it if the server has local changes that must be preserved.

## GitHub Actions Deployment Procedure

Automated deployment is not enabled yet. Recommended next workflow:

1. Create a GitHub Actions workflow triggered by pushes to `feature/backend-account-integration` or `main`.
2. Store SSH connection values as GitHub repository secrets:
   - `LIGHTSAIL_HOST`
   - `LIGHTSAIL_USER`
   - `LIGHTSAIL_SSH_KEY`
   - `LIGHTSAIL_DEPLOY_PATH`
3. Workflow connects over SSH and runs:

```bash
cd "$LIGHTSAIL_DEPLOY_PATH"
git fetch origin
git checkout feature/backend-account-integration
git pull --ff-only origin feature/backend-account-integration
docker compose -f deploy/aws/lightsail/docker-compose.yml up -d --build
docker compose -f deploy/aws/lightsail/docker-compose.yml ps
curl -f http://127.0.0.1/api/health
```

4. On failure, workflow should stop and preserve logs.
5. Keep production `.env` on the server. Do not inject Kiwoom secrets into the frontend build.

## Manual Deployment Checklist

Before deploy:

- Confirm branch: `feature/backend-account-integration`
- Confirm `.env` exists on server
- Confirm no order API is being introduced
- Confirm CORS includes frontend domain
- Confirm domain DNS points to Lightsail static IP

After deploy:

- `curl /api/health`
- `curl /api/accounts`
- `curl /api/account/performance`
- check backend logs
- check frontend can call API from mobile browser

## Incident Notes Template

```text
Time:
Impact:
Detected by:
Current mode: mock/live
Recent deploy commit:
Symptoms:
Immediate action:
Root cause:
Follow-up fix:
```
