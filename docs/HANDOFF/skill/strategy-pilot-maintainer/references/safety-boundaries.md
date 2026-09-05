# Safety Boundaries and Prohibited Actions

## Secrets and identity

Do not:

- Put App Key, Secret Key, broker token, account number, PIN or database credentials in source, tests, documentation, screenshots or chat output.
- Copy the macOS Keychain database or `~/.strategy-pilot/dashboard.pin` to another device.
- Put broker credentials in any `VITE_*`, `NEXT_PUBLIC_*` or browser-readable variable.
- Log request headers, token responses or unrestricted broker payloads.
- Commit `.env`, `.env.local`, backend/deploy env files, backups, SQLite files or runtime logs.

Configure `kiwoomcli setup` independently on the new Mac. Use masked account labels only.

## Network and authentication

Do not:

- Make browser-direct Kiwoom REST/WebSocket calls.
- Follow HTTPS token issuance redirects to HTTP.
- Disable TLS verification.
- Treat a generic HTTP 200/302 page as a token response.
- Add automatic aggressive token retries; respect rate limits and broker availability.
- Expose ports 8000/8080 on a public IP without a reviewed VPN/TLS/auth boundary.

## Orders

Do not:

- Remove the runtime lock or change default order flags to true to “make it work.”
- Execute a real order as part of unit testing, smoke testing, documentation, migration or debugging.
- Treat `ust20000`/`ust20001` acceptance as execution.
- Submit a second order while an earlier state is uncertain.
- Sell more than the reconciled sellable quantity.
- Use stale/zero/missing prices as valid references.
- Use premarket market orders where current policy requires a fresh FT limit price.
- Let condition entry or strategy ON state bypass account, cash, risk, freshness, session and lock checks.
- Weaken entry/risk criteria solely because no trades occur.

## Data and state

Do not:

- Commit or casually transfer `backend/data/*.sqlite3`.
- Use mock fallback values in a live-only dashboard.
- Delete reservation/order recovery state before reconciling with the broker.
- Assume WebSocket messages are ordered, complete or unique.
- Assume candle rows arrive sorted.
- Mix KST display date with the ET trading date.
- Persist raw broker rows when normalized safe fields are sufficient.

## Git and migration

Do not:

- Assume `git clone` contains the current application while the source Mac has a dirty worktree.
- Run `git clean`, `git reset --hard`, `git checkout --`, or broad deletion on the source worktree.
- Copy `node_modules`, `dist`, virtual environments, caches or generated files between Macs.
- Stage `pnpm-lock.yaml` unless the package-manager decision is explicitly changed and validated.
- Combine hundreds of unrelated changes into one commit.

## Documentation honesty

Use these labels consistently:

- **Implemented**: code and automated tests exist.
- **Observed**: a controlled read-only live observation succeeded.
- **Partially validated**: some production shapes/events were seen, but recovery or edge cases remain.
- **Blocked**: policy or external dependency prevents execution.
- **Planned**: no reliable runtime implementation exists.

Never label a fake-transport test as live verification or an order submission as a confirmed fill.
