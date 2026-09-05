# Strategy Pilot Backend

FastAPI 기반 키움 실계좌 서버입니다.

## Data Policy

- `KIWOOM_MODE=live`만 지원합니다.
- 계좌, 시세, 조건검색, 차트, 주문 상태는 키움 API 응답만 사용합니다.
- Mock/Paper 응답과 watchlist fallback은 제거되었습니다.
- API 오류는 안전한 오류 유형과 상태로 전달하며 원본 응답이나 인증정보를 노출하지 않습니다.

## Order Policy

실주문은 기본적으로 잠겨 있습니다. 주문 허용 환경변수, 읽기 전용 해제, 런타임 잠금 해제, 실계좌 세션, 전략 조건과 리스크 검사를 모두 통과한 경우에만 주문 서비스가 실행됩니다.

## Windows CLI Profile Authentication

키움 공식 `kwcli`는 대시보드 백엔드와 별도로 설치합니다. 공식 패키지는 Python 3.13 이상을 요구하며, App Key와 Secret Key는 Windows 자격 증명 관리자에 저장됩니다. 대시보드는 `platformdirs.user_config_dir("kiwoom")/settings.json`의 프로필 메타데이터와 Windows 자격 증명 관리자만 읽습니다.

```powershell
# 공식 CLI 설치
uv tool install kwcli

# 실전/모의 프로필과 키를 대화형으로 등록
kiwoomcli setup

# 자격 증명 및 토큰 상태 확인
kiwoomcli auth status

# 미국주식 안전 조회 확인
kiwoomcli overseas stocks info --exchange NASDAQ --code AAPL
```

CLI 설치 및 Windows 준비 상태만 확인하려면 저장소 루트에서 다음을 실행합니다. 이 검사는 App Key, Secret Key 또는 토큰을 출력하지 않습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\check-kiwoom-windows.ps1
```

키움 포털에서 내려받은 계좌별 파일을 사용하면 숨김 입력창의 복사 오류를 피할 수 있습니다. 파일 값은 화면에 출력하거나 저장소에 복사하지 않으며, 검증 성공 시 Windows 자격 증명 관리자에만 저장합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\register-kiwoom-real-profile-from-files.ps1 `
  -AppKeyFile "C:\path\to\account_appkey.txt" `
  -SecretKeyFile "C:\path\to\account_secretkey.txt" `
  -Alias "실전계좌"
```

대시보드 로그인에는 서버 전용 `DASHBOARD_ACCESS_PIN`도 필요합니다. 브라우저나 루트 프론트엔드 `.env`에 키움 자격 증명을 저장하지 마세요.

## Verification

```bash
PYTHONPYCACHEPREFIX=/tmp/strategy-pilot-pycache python3 -m compileall backend/app backend/scripts
PYTHONPATH=backend backend/.venv/bin/python -m pytest -p no:cacheprovider backend/tests backend/trading_engine/tests
```
