#!/usr/bin/env bash
set -euo pipefail

CONFIRM_VALUE="I_UNDERSTAND_LIVE_US_ORDER"

if [[ "${STRATEGY_PILOT_LIVE_ORDER_CONFIRM:-}" != "$CONFIRM_VALUE" ]]; then
  echo "Live order startup blocked."
  echo "Set STRATEGY_PILOT_LIVE_ORDER_CONFIRM=$CONFIRM_VALUE only for intentional 1-share live order testing."
  exit 2
fi

export STRATEGY_PILOT_ENABLE_LIVE_ORDERS=true
exec "$(dirname "${BASH_SOURCE[0]}")/start_mobile_local.sh" "${1:-start}"
