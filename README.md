# Strategy Pilot

키움 REST API 기반 미국주식 읽기 전용 분석·자동화 대시보드입니다.

## Runtime Policy

- 런타임 데이터는 서버를 통과한 키움 REST/WebSocket 조회 응답만 사용합니다.
- Mock/Paper 데이터와 자동 fallback은 제공하지 않습니다.
- 키움 연결 실패 시 화면에 오류를 표시하며 가짜 잔고·시세·체결을 만들지 않습니다.
- App Key, Secret Key, 접근 토큰과 계좌번호는 브라우저 코드에 저장하지 않습니다.
- 실주문·정정·취소·환전 신청은 구현 기준선에서 차단합니다.
- 전략 저장과 전략 ON은 주문 차단을 우회하지 않습니다.

## Local URLs

- Frontend: `http://127.0.0.1:8080`
- Backend: `http://127.0.0.1:8000`

## Windows Kiwoom CLI

공식 `kwcli` 프로필 인증을 사용합니다. 프로필 메타데이터는 Windows AppData에, App Key와 Secret Key는 Windows 자격 증명 관리자에 보관되며 브라우저로 전달되지 않습니다.

```powershell
kiwoomcli setup
kiwoomcli auth status
powershell -ExecutionPolicy Bypass -File .\tools\check-kiwoom-windows.ps1
```

CLI 설치와 백엔드 구성은 [backend/README.md](backend/README.md)를 참고하세요. 실주문·정정·취소는 계속 차단됩니다.

공식 명세 기반 미국주식 TR 카탈로그와 안전한 확장 절차는 [docs/KIWOOM_US_TOOL_OVERVIEW.md](docs/KIWOOM_US_TOOL_OVERVIEW.md)를 참고하세요.
