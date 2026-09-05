# Kiwoom US Credential Policy

## Purpose

This policy applies before enabling any US stock Kiwoom read-only transport.
The current implementation is still a skeleton: it can build request shapes and
run fake transport tests, but it must not call Kiwoom REST/WebSocket services.

## Never Store In Git

The following values must never be committed, printed, copied into docs, or
stored in test fixtures:

- Kiwoom App Key.
- Kiwoom Secret Key.
- OAuth access token or refresh token.
- Account number.
- Raw live account response.
- Any webhook, database, or infrastructure secret.

## Allowed Loading Methods

Allowed credential loading boundaries are:

1. OS keyring.
2. Local `.env` files ignored by Git.
3. Server-side environment variables.

`kiwoomcli` profiles are allowed as an OS-keyring-backed source. The engine
may read the selected profile alias from `KIWOOM_US_PROFILE` or `KIWOOM_PROFILE`
when `KIWOOM_US_CREDENTIAL_SOURCE=kiwoomcli` is set. The profile settings file,
keyring entries, and token cache are read locally; actual key, secret, token,
and account values must never be printed.

Frontend-exposed variables and browser code must never receive broker
credentials. Trading decisions and broker calls must remain server-side.

## Forbidden Loading Methods

Forbidden methods:

- Hardcoding values in Python, TypeScript, tests, or scripts.
- Writing actual values into Markdown or screenshots.
- Including real credentials in mock fixtures.
- Pushing secrets to GitHub.
- Passing order-capable credentials into a read-only worker.

## Read-only Versus Order Mode

US read-only mode is the only allowed mode in this phase.

- `read_only=True` is required.
- `order_enabled=False` is required.
- `liveProvider=false` remains the default.
- `orderEnabled=true` remains prohibited.

Order TRs are inventoried only to block them:

- `ust20000`
- `ust20001`
- `ust20002`
- `ust20003`
- `F4`

## Conditions Before Read-only Calls

Before any real US read-only call is allowed:

1. The credential source is documented as env or keyring.
2. `liveProvider=true` is explicitly configured for a read-only smoke test.
3. `read_only=True` and `order_enabled=False` are verified at startup.
4. Request logs redact Authorization and never include app key, secret, token,
   or account number.
5. Response logs include only schema keys, TR IDs, HTTP status, and safe error
   types.
6. Fake transport tests pass.
7. Order TR tests prove blocked behavior.

For `kiwoomcli` profile-backed smoke checks, these additional conditions apply:

1. `kiwoomcli setup` has already completed outside this repository.
2. `KIWOOM_US_CREDENTIAL_SOURCE=kiwoomcli` is explicit.
3. `KIWOOM_US_PROFILE` or `KIWOOM_PROFILE` selects the intended local profile.
4. The selected profile mode matches the requested mode.
5. Token cache presence is treated as a configured/not-configured boolean only.

## Still Blocked

- Real HTTP transport.
- Real WebSocket transport.
- Order placement, amend, cancel, or order-confirmation stream handling.
- Dashboard controls that could enable live order behavior.
