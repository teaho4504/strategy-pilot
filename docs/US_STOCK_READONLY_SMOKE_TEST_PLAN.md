# US Stock Read-only Smoke Test Plan

## Status

This is the guard specification for local US read-only smoke checks. It does
not add WebSocket or order execution. The codebase has an injected-sender HTTP
transport model and a guarded `urllib` sender that can execute only approved
read-only TRs after explicit operator confirmation.

## Required Confirmation

The smoke test must stay blocked unless the operator explicitly sets:

```text
KIWOOM_US_SMOKE_CONFIRM=I_UNDERSTAND_US_READ_ONLY_ONLY
```

The smoke test must also require:

```text
KIWOOM_US_READ_ONLY=true
KIWOOM_US_ENABLE_ORDER=false
KIWOOM_US_LIVE_PROVIDER=true
```

Credential source can be an ignored local env file, server environment, or the
local `kiwoomcli` profile/keyring store. For the `kiwoomcli` path:

```text
KIWOOM_US_CREDENTIAL_SOURCE=kiwoomcli
KIWOOM_US_PROFILE=<local profile alias>
```

The profile loader may report only configured/not-configured booleans. It must
not print the profile's app key, secret, token, account number, or raw token
cache content.

The concrete HTTP sender must stay blocked unless these additional variables
are set:

```text
KIWOOM_US_HTTP_SENDER_ENABLED=true
KIWOOM_US_HTTP_SENDER_CONFIRM=I_UNDERSTAND_US_READ_ONLY_HTTP_SENDER
KIWOOM_US_ACCESS_TOKEN=<provided outside git>
```

## TR Order

Stop on the first error.

| Order | TR | Purpose |
| --- | --- | --- |
| 1 | `ust21110` | US cash/deposit read-only check |
| 2 | `ust21120` | US currency cash and valuation read-only check |
| 3 | `ust21630` | US realized PnL read-only check |
| 4 | `ust21650` | US period return read-only check |
| 5 | `usa21670` | US daily account return read-only check |

The smoke test deliberately excludes:

- `ust20000`
- `ust20001`
- `ust20002`
- `ust20003`
- `F4`

## Safe Output Only

Allowed output:

- TR ID.
- return code.
- return message.
- schema key names.
- safe error type.

Forbidden output:

- App key.
- Secret key.
- Token.
- Account number.
- Cash balance.
- Holding symbols or names.
- Raw response JSON.

## Required Pre-checks

Before any future implementation can call Kiwoom:

1. Validate credential policy.
2. Validate `order_enabled=false`.
3. Validate smoke confirmation phrase.
4. Validate all smoke TRs are read-only.
5. Validate order TRs and `F4` are blocked.
6. Validate console output uses schema keys only.

## Next Implementation Step

The pre-check script skeleton is:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/verify_us_readonly_precheck.py
```

It performs only local guard checks and exits before network transport.
With `KIWOOM_US_CREDENTIAL_SOURCE=kiwoomcli`, it additionally verifies that the
local profile/keyring/token-cache structure can be read without printing secret
values.

The fake runner skeleton is:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/run_us_readonly_smoke.py --fake
```

The first real read-only HTTP smoke must be narrowed to one TR:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/run_us_readonly_smoke.py --live-http --tr ust21110
```

Only TRs already included in the read-only smoke plan can be selected with
`--tr`. Order TRs such as `ust20000` remain blocked before transport execution.

Without `--fake` or `--live-http`, the runner is intentionally blocked. The
`--live-http` path uses a concrete `urllib` sender, but only after the base
smoke confirmation, the extra HTTP sender confirmation, read-only mode,
`order_enabled=false`, and access-token presence are all verified. The sender
must preserve the same read-only TR list, safe output rules, and order blocking.

## Current Local Smoke Results

Verified locally with safe schema-key output only:

- `ust21110`: success.
- `ust21120`: success.
- `ust21650`: success.
- `usa21670`: success using `from` / `to` request fields.

Observed non-order read-only response:

- `ust21630`: request reached Kiwoom and returned a safe no-data style response
  for the tested account/date context. This is not an order path and did not
  expose raw values.
