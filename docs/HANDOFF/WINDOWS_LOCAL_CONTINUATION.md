# Windows Local Continuation

## Source PC

Create a verified, secret-free archive from the repository root:

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
& '.\.venv\Scripts\python.exe' backend\scripts\export_usb_safe_snapshot.py --output-dir 'D:\transfer'
```

Copy both the generated `.tar.gz` and `.tar.gz.sha256` files. The exporter rejects archives containing `.run`, dashboard PINs, `.env` files, runtime databases, logs, temporary Codex transcripts/test output, dependencies, build output, or Git metadata.

## Destination PC

1. Install Git, Node.js, Python 3.13+, `uv`, and Codex.
2. Extract the archive into a new local folder.
3. Recreate dependencies instead of copying virtual environments or `node_modules`.

```powershell
npm install
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r backend\requirements.txt
uv tool install --python 3.13 kwcli
```

4. Configure the Kiwoom profile on the destination PC. Credentials stored in Windows Credential Manager are deliberately not transferred.

```powershell
kiwoomcli auth login --alias '<NEW_LOCAL_ALIAS>' --mode real
kiwoomcli auth status
```

5. Keep these safe defaults in the destination machine's local environment:

```text
KIWOOM_READ_ONLY=true
KIWOOM_ENABLE_ORDER=false
KIWOOM_US_READ_ONLY=true
KIWOOM_US_ENABLE_ORDER=false
```

6. Run verification and start locally:

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
& '.\.venv\Scripts\python.exe' -m pytest backend\tests backend\trading_engine\tests -q -p no:cacheprovider
npm run build
& '.\tools\start-local-windows.ps1' -Restart
```

The dashboard PIN, OAuth token, account information, SQLite events, and FRED runtime cache must be recreated or downloaded independently on the destination PC.
