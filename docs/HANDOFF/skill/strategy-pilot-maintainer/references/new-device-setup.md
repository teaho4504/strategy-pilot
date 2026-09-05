# New Device Setup

## 1. Transfer model

Because the source worktree is not clean, use both:

1. Git repository/history from the configured remote or a Git bundle.
2. A secret-free worktree overlay created by `scripts/export_worktree.sh`.

The overlay is temporary migration material. After verification, split and commit intentional changes so Git becomes authoritative.

Use an encrypted USB volume if possible. Do not transfer broker credentials, Keychain data, PIN files or runtime databases.

## 2. Export on the source Mac

From the bundled skill directory:

```bash
./scripts/export_worktree.sh /Volumes/<USB_NAME>/strategy-pilot-transfer
```

The script excludes `.git`, dependencies, build output, Python caches, actual env files, databases, logs, backup files and `pnpm-lock.yaml`. Review the generated archive listing before removing the source copy.

Optionally export Git history without network access:

```bash
cd ~/strategy-pilot
git bundle create /Volumes/<USB_NAME>/strategy-pilot-transfer/strategy-pilot.git.bundle --all
```

## 3. Install prerequisites on the new Mac

Required:

- Git
- Python compatible with the project (the source currently uses Python 3.14; Python 3.13+ is the target baseline)
- Node.js and npm
- `uv`
- macOS Keychain-compatible keyring
- `kiwoomcli` installed through `uv tool install kwcli`

Do not copy `node_modules` or `backend/.venv` from another architecture/machine.

## 4. Restore source

Clone from the remote when available, or clone the bundle:

```bash
git clone /Volumes/<USB_NAME>/strategy-pilot-transfer/strategy-pilot.git.bundle ~/strategy-pilot
cd ~/strategy-pilot
git switch feature/kiwoom-us-tr-skeleton-local
```

Extract the worktree overlay into that clone:

```bash
tar -xzf /Volumes/<USB_NAME>/strategy-pilot-transfer/strategy-pilot-worktree-*.tar.gz -C ~/strategy-pilot
```

Immediately inspect:

```bash
git status --short --branch
git diff --check
```

Do not clean the restored changes.

## 5. Recreate dependencies

```bash
cd ~/strategy-pilot
npm install

python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

If the project standardizes on `uv` later, document and use one reproducible lock strategy. Do not stage the unrelated `pnpm-lock.yaml`.

## 6. Configure credentials locally

Run on the new Mac:

```bash
export PATH="$HOME/.local/bin:$PATH"
kiwoomcli setup
kiwoomcli auth status --profile <PROFILE_ALIAS>
```

Enter App Key and Secret only into the CLI prompt. Never paste them into frontend fields, source files or documentation.

Create local environment files from examples only as needed. Keep safe defaults:

```text
KIWOOM_READ_ONLY=true
KIWOOM_ENABLE_ORDER=false
KIWOOM_US_ENABLE_ORDER=false
KIWOOM_US_AUTOTRADE_OBSERVATION_ENABLED=false
```

## 7. Verify before starting

```bash
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
PYTHONPATH=backend backend/.venv/bin/python -m pytest -p no:cacheprovider backend/tests backend/trading_engine/tests
npm test -- --run
npx tsc --noEmit
npm run build
git diff --check
```

Scan the restored tree for accidental secrets without printing matching values to shared logs. Manually inspect filenames and use a local secret scanner if available.

## 8. Start in safe local mode

```bash
backend/scripts/start_mobile_local.sh start
backend/scripts/start_mobile_local.sh status
backend/scripts/start_mobile_local.sh pin
```

Expected defaults:

- dashboard `http://127.0.0.1:8080/`
- backend `http://127.0.0.1:8000/`
- read-only true
- order enabled false
- runtime order lock present

The PIN is machine-local. Do not document or commit it.

## 9. Acceptance checklist

- Frontend and backend return HTTP 200 locally.
- CLI profiles list only after the correct local PIN.
- Token issuance returns direct HTTPS JSON; redirects fail closed.
- Account and market read-only pages show explicit live/empty/error state, never mock data.
- All automated tests pass.
- No order TR is invoked.
- Git status contains only understood source/document changes.
