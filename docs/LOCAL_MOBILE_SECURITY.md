# Local Mobile Security

This project can run from the Mac and be opened on a mobile device for local testing.
Do not expose the dashboard through a public IP when live orders are enabled.

## Recommended Path: Tailscale

Use Tailscale on both the Mac and the mobile device.

```bash
cd ~/strategy-pilot
backend/scripts/start_tailscale_local.sh restart
```

The script:

- detects the Mac Tailscale IPv4 address,
- binds FastAPI and Vite to that Tailscale IP,
- sets `BACKEND_ALLOWED_CLIENT_IPS=100.64.0.0/10`,
- keeps live orders disabled by default,
- creates a local dashboard access PIN on first use and reuses it after restarts,
- stores the PIN at `~/.strategy-pilot/dashboard.pin` with owner-only permissions.

Open the printed dashboard URL on the mobile device while it is connected to the same tailnet.
To display the local PIN again, run `backend/scripts/start_mobile_local.sh pin`.

## Live Order Mode

Live order mode remains separate and requires an explicit confirmation.

```bash
cd ~/strategy-pilot
STRATEGY_PILOT_LIVE_ORDER_CONFIRM=I_UNDERSTAND_LIVE_US_ORDER \
STRATEGY_PILOT_MOBILE_HOST=<mac-tailscale-ip> \
STRATEGY_PILOT_BIND_HOST=<mac-tailscale-ip> \
BACKEND_ALLOWED_CLIENT_IPS=100.64.0.0/10 \
backend/scripts/start_mobile_live_orders.sh
```

Keep live order mode off unless actively testing. The order caps still apply.

## 5G Public IP Caveat

5G public IP addresses can change and can be carrier NAT addresses. A single allowed IP may stop working after a network change.
If direct 5G access is used anyway, restart with the current IP:

```bash
BACKEND_ALLOWED_CLIENT_IPS=<current-mobile-ip> backend/scripts/start_mobile_local.sh restart
```

CIDR ranges are supported but should be avoided for live order mode because they allow more clients than a single device.

## Values That Must Not Be Committed

- Kiwoom App Key
- Kiwoom Secret Key
- OAuth token
- account number
- backend `.env`
- raw account/order responses
