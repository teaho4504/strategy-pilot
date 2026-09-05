#!/usr/bin/env bash
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  echo "Tailscale CLI was not found."
  echo "Install Tailscale and log in on this Mac and the mobile device first."
  exit 2
fi

TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | head -n 1 | tr -d '[:space:]')"
if [[ -z "$TAILSCALE_IP" ]]; then
  echo "Tailscale IPv4 address was not found."
  echo "Run: tailscale status"
  exit 2
fi

export STRATEGY_PILOT_MOBILE_HOST="${STRATEGY_PILOT_MOBILE_HOST:-$TAILSCALE_IP}"
export STRATEGY_PILOT_BIND_HOST="${STRATEGY_PILOT_BIND_HOST:-$TAILSCALE_IP}"
export BACKEND_ALLOWED_CLIENT_IPS="${BACKEND_ALLOWED_CLIENT_IPS:-100.64.0.0/10}"
export BACKEND_TRUST_PROXY_HEADERS="${BACKEND_TRUST_PROXY_HEADERS:-false}"

exec "$(dirname "${BASH_SOURCE[0]}")/start_mobile_local.sh" "${1:-start}"
