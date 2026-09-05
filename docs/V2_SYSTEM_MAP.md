# Strategy Pilot V2 System Map

## 전체 지도

```mermaid
flowchart TB
  classDef user fill:#ecfdf5,stroke:#059669,color:#064e3b
  classDef ui fill:#eff6ff,stroke:#2563eb,color:#1e3a8a
  classDef api fill:#f5f3ff,stroke:#7c3aed,color:#4c1d95
  classDef engine fill:#fff7ed,stroke:#ea580c,color:#7c2d12
  classDef data fill:#f8fafc,stroke:#475569,color:#0f172a
  classDef broker fill:#fef2f2,stroke:#dc2626,color:#7f1d1d
  classDef guard fill:#fefce8,stroke:#ca8a04,color:#713f12

  User["사용자<br/>Mac / iPhone"]:::user

  subgraph Frontend["Vite React Dashboard"]
    Login["CLI 프로필 + PIN 로그인"]:::ui
    Home["홈<br/>계좌·활성 전략"]:::ui
    Quotes["시세<br/>랭킹·차트·호가"]:::ui
    Strategies["전략<br/>ON/OFF·판정"]:::ui
    Builder["AI 전략 빌더"]:::ui
    Analytics["분석<br/>손익·성과·실패"]:::ui
    Settings["설정<br/>리스크·알림"]:::ui
  end

  subgraph Backend["Python FastAPI"]
    Auth["세션/인증 API"]:::api
    AccountAPI["계좌 API"]:::api
    MarketAPI["시세/차트 API"]:::api
    StrategyAPI["전략/분석 API"]:::api
    OrderAPI["주문 API 경계"]:::api
  end

  subgraph Engine["Python Trading Engine"]
    Candidate["조건검색 후보 관리자"]:::engine
    Cache["Tick·호가·캔들 캐시"]:::engine
    Decision["전략 지표·신호 판정"]:::engine
    Risk["리스크 검사<br/>Kill switch·한도"]:::guard
    Runner["Auto-trade runner"]:::engine
    Paper["Paper broker"]:::engine
  end

  subgraph Data["Local Data"]
    Keychain["macOS Keychain<br/>App Key / Secret"]:::data
    SQLite["SQLite<br/>이벤트·신호·체결·손익"]:::data
    Config["서버 환경변수<br/>모드·한도·허용정책"]:::data
  end

  subgraph Kiwoom["Kiwoom Server"]
    OAuth["OAuth au10001"]:::broker
    Rest["REST<br/>계좌·시세·조건·차트"]:::broker
    WS["WebSocket<br/>FE·FT·F4·F5"]:::broker
    LiveOrder["실주문<br/>ust20000~ust20003"]:::broker
  end

  User --> Login
  Login --> Auth
  Auth --> Keychain
  Auth --> Home
  Home --> AccountAPI
  User --> Quotes
  User --> Strategies
  Strategies --> Builder
  User --> Analytics
  User --> Settings

  Quotes --> MarketAPI
  Strategies --> StrategyAPI
  Analytics --> StrategyAPI

  AccountAPI --> Rest
  MarketAPI --> Rest
  MarketAPI --> WS
  StrategyAPI --> Candidate
  Candidate --> Cache
  Rest --> Cache
  WS --> Cache
  Cache --> Decision
  Decision --> Risk
  Risk --> Runner
  Runner --> Paper
  Paper --> SQLite
  Decision --> SQLite
  Risk --> SQLite
  SQLite --> StrategyAPI

  Keychain --> OAuth
  OAuth --> Rest
  OAuth --> WS
  Config --> Auth
  Config --> Risk
  Config --> OrderAPI
  Runner -. "현재 read-only/Paper 상태에서는 차단" .-> OrderAPI
  OrderAPI -. "별도 운영 승인 필요" .-> LiveOrder
  LiveOrder --> WS
```

## 새 버전의 핵심 경계

```mermaid
flowchart LR
  UI["Dashboard<br/>표시와 제어"] --> API["FastAPI<br/>인증·검증·데이터 계약"]
  API --> Engine["Trading Engine<br/>후보·전략·리스크"]
  Engine --> Paper["기본값<br/>Paper"]
  Engine -. "명시적 운영 승인" .-> Live["Live Order Adapter"]
  Engine --> Audit["SQLite Audit"]

  BrowserSecret["브라우저 Secret"]:::bad
  BrowserDecision["브라우저 매매 판단"]:::bad
  BrowserSecret -. "금지" .-> UI
  BrowserDecision -. "금지" .-> UI

  classDef bad fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
```

## V2 권장 제작 순서

| 단계 | 결과물 | 완료 기준 |
| ---: | --- | --- |
| 1 | 현재 자산 동결/분류 | 재사용·폐기·보류 목록 확정 |
| 2 | 단일 API 계약 | 화면별 응답 schema와 오류 형식 확정 |
| 3 | 데이터 모델 정리 | 계좌·시세·전략·주문 이벤트 모델 확정 |
| 4 | 대시보드 재구성 | 5개 탭과 버튼 흐름 구현 |
| 5 | Paper runner 통합 | 전략 ON/OFF부터 Paper 체결/분석까지 연결 |
| 6 | 운영 안정화 | 재시작 복원, stale data 차단, 감사 로그 |
| 7 | 실주문 별도 승인 | 주문/체결/미체결/청산 검증 후 제한적으로 개방 |

## V2의 기본 원칙

- 브라우저는 Kiwoom API를 직접 호출하지 않는다.
- 거래 판단은 Python trading engine에서만 수행한다.
- 기본 실행은 read-only 또는 Paper이다.
- 실주문은 전략 ON/OFF와 분리된 서버 안전 게이트를 통과해야 한다.
- 모든 신호, 차단, 주문 시도, 체결, 손익을 재현할 수 있어야 한다.
- 실제 Secret, Token, 계좌번호, 원본 계좌 응답은 Git과 문서에 저장하지 않는다.
