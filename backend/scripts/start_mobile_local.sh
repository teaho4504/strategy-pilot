#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_LOG="${STRATEGY_PILOT_BACKEND_LOG:-/tmp/strategy-pilot-backend.log}"
FRONTEND_LOG="${STRATEGY_PILOT_FRONTEND_LOG:-/tmp/strategy-pilot-frontend.log}"
BACKEND_PID_FILE="${STRATEGY_PILOT_BACKEND_PID_FILE:-/tmp/strategy-pilot-backend.pid}"
FRONTEND_PID_FILE="${STRATEGY_PILOT_FRONTEND_PID_FILE:-/tmp/strategy-pilot-frontend.pid}"
CAFFEINATE_PID_FILE="${STRATEGY_PILOT_CAFFEINATE_PID_FILE:-/tmp/strategy-pilot-caffeinate.pid}"
BACKEND_PORT="${STRATEGY_PILOT_BACKEND_PORT:-8000}"
FRONTEND_PORT="${STRATEGY_PILOT_FRONTEND_PORT:-8080}"
FRONTEND_RUNTIME="${STRATEGY_PILOT_FRONTEND_RUNTIME:-preview}"
BACKEND_SCREEN="${STRATEGY_PILOT_BACKEND_SCREEN:-strategy-pilot-backend}"
FRONTEND_SCREEN="${STRATEGY_PILOT_FRONTEND_SCREEN:-strategy-pilot-frontend}"
CAFFEINATE_SCREEN="${STRATEGY_PILOT_CAFFEINATE_SCREEN:-strategy-pilot-caffeinate}"
SERVER_BIND_HOST="${STRATEGY_PILOT_BIND_HOST:-127.0.0.1}"
AUTH_RATE_LIMIT="${BACKEND_AUTH_RATE_LIMIT:-20/60}"
ORDER_RATE_LIMIT="${BACKEND_ORDER_RATE_LIMIT:-30/60}"
ALLOWED_CLIENT_IPS="${BACKEND_ALLOWED_CLIENT_IPS:-}"
TRUST_PROXY_HEADERS="${BACKEND_TRUST_PROXY_HEADERS:-false}"
US_ORDER_CONFIRM="I_UNDERSTAND_LIVE_US_ORDER"
US_ORDER_UNLOCK="I_ACCEPT_REAL_US_ORDER_RISK"
ENABLE_LIVE_ORDERS="${STRATEGY_PILOT_ENABLE_LIVE_ORDERS:-false}"
AUTOTRADE_OBSERVATION_ENABLED="${KIWOOM_US_AUTOTRADE_OBSERVATION_ENABLED:-true}"
runner_default="$AUTOTRADE_OBSERVATION_ENABLED"
[[ "$ENABLE_LIVE_ORDERS" == "true" ]] && runner_default="true"
AUTOTRADE_RUNNER_ENABLED="${KIWOOM_US_AUTOTRADE_RUNNER_ENABLED:-$runner_default}"
AUTOTRADE_RUNNER_INTERVAL="${KIWOOM_US_AUTOTRADE_RUNNER_INTERVAL_SECONDS:-5}"
PREMARKET_ENTRY_ENABLED="${KIWOOM_US_PREMARKET_ENTRY_ENABLED:-$ENABLE_LIVE_ORDERS}"
ACCESS_PIN_FILE="${STRATEGY_PILOT_ACCESS_PIN_FILE:-$HOME/.strategy-pilot/dashboard.pin}"

generate_pin() {
  if [[ -n "${DASHBOARD_ACCESS_PIN:-}" ]]; then
    printf "%s" "$DASHBOARD_ACCESS_PIN"
    return
  fi
  if [[ -n "${STRATEGY_PILOT_ACCESS_PIN:-}" ]]; then
    printf "%s" "$STRATEGY_PILOT_ACCESS_PIN"
    return
  fi

  if [[ -s "$ACCESS_PIN_FILE" ]]; then
    chmod 600 "$ACCESS_PIN_FILE"
    tr -d '\r\n' < "$ACCESS_PIN_FILE"
    return
  fi

  local pin pin_dir
  pin_dir="$(dirname "$ACCESS_PIN_FILE")"
  mkdir -p "$pin_dir"
  chmod 700 "$pin_dir"
  if command -v openssl >/dev/null 2>&1; then
    pin="$(openssl rand -hex 4)"
  else
    pin="$(date +%s | shasum | awk '{print substr($1, 1, 8)}')"
  fi
  (umask 077 && printf "%s\n" "$pin" > "$ACCESS_PIN_FILE")
  printf "%s" "$pin"
}

detect_host() {
  if [[ -n "${STRATEGY_PILOT_MOBILE_HOST:-}" ]]; then
    printf "%s" "$STRATEGY_PILOT_MOBILE_HOST"
    return
  fi

  local host
  host="$(ifconfig | awk '
    /inet / {
      ip=$2
      if (ip == "127.0.0.1" || ip ~ /^169\\.254\\./) next
      if (ip ~ /^192\\.168\\./ || ip ~ /^10\\./ || ip ~ /^172\\.(1[6-9]|2[0-9]|3[0-1])\\./) {
        print ip
        exit
      }
      candidate=ip
    }
    END {
      if (!printed && candidate) print candidate
    }
  ' | head -n 1)"
  printf "%s" "${host:-127.0.0.1}"
}

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

stop_pid_file() {
  local pid_file="$1"
  if is_running "$pid_file"; then
    kill "$(cat "$pid_file")" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

stop_ports() {
  local pid
  pid="$(lsof -tiTCP:"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill $pid 2>/dev/null || true
  pid="$(lsof -tiTCP:"$FRONTEND_PORT" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill $pid 2>/dev/null || true
  for _ in {1..50}; do
    if ! lsof -tiTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1 \
      && ! lsof -tiTCP:"$FRONTEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
      return
    fi
    sleep 0.1
  done
}

stop_screen() {
  local name="$1"
  if command -v screen >/dev/null 2>&1; then
    screen -S "$name" -X quit >/dev/null 2>&1 || true
  fi
}

wait_for_backend() {
  for _ in {1..100}; do
    if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/" >/dev/null 2>&1; then
      return
    fi
    sleep 0.1
  done
  echo "Backend did not become ready on port ${BACKEND_PORT}" >&2
  return 1
}

stop_stale_backend_processes() {
  local pid process_cwd
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    process_cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true)"
    if [[ "$process_cwd" == "$ROOT_DIR" ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done < <(pgrep -f "uvicorn app\\.main:app" 2>/dev/null || true)

  for _ in {1..20}; do
    local remaining=false
    while IFS= read -r pid; do
      [[ -n "$pid" ]] || continue
      process_cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true)"
      if [[ "$process_cwd" == "$ROOT_DIR" ]]; then
        remaining=true
        break
      fi
    done < <(pgrep -f "uvicorn app\\.main:app" 2>/dev/null || true)
    [[ "$remaining" == "false" ]] && return
    sleep 0.1
  done

  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    process_cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true)"
    if [[ "$process_cwd" == "$ROOT_DIR" ]]; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done < <(pgrep -f "uvicorn app\\.main:app" 2>/dev/null || true)
}

status() {
  local host
  if [[ "$SERVER_BIND_HOST" == "127.0.0.1" || "$SERVER_BIND_HOST" == "localhost" ]]; then
    host="127.0.0.1"
  else
    host="$(detect_host)"
  fi
  echo "Dashboard: http://${host}:${FRONTEND_PORT}/"
  echo "Backend:   http://${host}:${BACKEND_PORT}/api/kiwoom/status"
  echo "Bind host: ${SERVER_BIND_HOST}"
  lsof -iTCP:"$BACKEND_PORT" -sTCP:LISTEN -n -P 2>/dev/null || true
  lsof -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN -n -P 2>/dev/null || true
  if is_running "$CAFFEINATE_PID_FILE"; then
    echo "Sleep prevention: on ($(cat "$CAFFEINATE_PID_FILE"))"
  elif command -v screen >/dev/null 2>&1 && [[ "$(screen -ls 2>&1 || true)" == *"$CAFFEINATE_SCREEN"* ]]; then
    echo "Sleep prevention: on (${CAFFEINATE_SCREEN})"
  else
    echo "Sleep prevention: off"
  fi
}

start() {
  local host cors access_pin read_only enable_order kiwoom_enable_order order_confirm order_unlock
  if [[ "$SERVER_BIND_HOST" == "127.0.0.1" || "$SERVER_BIND_HOST" == "localhost" ]]; then
    host="127.0.0.1"
  else
    host="$(detect_host)"
  fi
  cors="http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT},http://${host}:${FRONTEND_PORT}"
  access_pin="$(generate_pin)"

  read_only="true"
  enable_order="false"
  kiwoom_enable_order="false"
  order_confirm=""
  order_unlock=""
  if [[ "$ENABLE_LIVE_ORDERS" == "true" ]]; then
    read_only="false"
    enable_order="true"
    kiwoom_enable_order="true"
    order_confirm="$US_ORDER_CONFIRM"
    order_unlock="$US_ORDER_UNLOCK"
  fi

  stop
  cd "$ROOT_DIR"

  export BACKEND_CORS_ORIGINS="$cors"
  export DASHBOARD_ACCESS_PIN="$access_pin"
  export BACKEND_ALLOWED_CLIENT_IPS="$ALLOWED_CLIENT_IPS"
  export BACKEND_TRUST_PROXY_HEADERS="$TRUST_PROXY_HEADERS"
  export BACKEND_AUTH_RATE_LIMIT="$AUTH_RATE_LIMIT"
  export BACKEND_ORDER_RATE_LIMIT="$ORDER_RATE_LIMIT"
  export KIWOOM_MODE=live
  export KIWOOM_READ_ONLY="$read_only"
  export KIWOOM_ENABLE_ORDER="$kiwoom_enable_order"
  export KIWOOM_US_ENABLE_ORDER="$enable_order"
  export KIWOOM_US_AUTO_EXIT_ENABLED=true
  export KIWOOM_US_AUTOTRADE_RUNNER_ENABLED="$AUTOTRADE_RUNNER_ENABLED"
  export KIWOOM_US_AUTOTRADE_OBSERVATION_ENABLED="$AUTOTRADE_OBSERVATION_ENABLED"
  export KIWOOM_US_AUTOTRADE_RUNNER_INTERVAL_SECONDS="$AUTOTRADE_RUNNER_INTERVAL"
  export KIWOOM_US_PREMARKET_ENTRY_ENABLED="$PREMARKET_ENTRY_ENABLED"
  export KIWOOM_US_ORDER_CONFIRM="$order_confirm"
  export KIWOOM_US_LIVE_ORDER_UNLOCK="$order_unlock"
  export KIWOOM_US_MAX_ORDER_QUANTITY=1
  export KIWOOM_US_MAX_ORDER_KRW=30000
  export KIWOOM_US_ORDER_USD_KRW_RATE=1400
  export KIWOOM_US_ALLOW_ALL_COMMON_STOCKS=true
  export KIWOOM_US_COMMON_STOCK_ONLY=true
  export PYTHONPATH=backend

  if command -v screen >/dev/null 2>&1; then
    screen -dmS "$BACKEND_SCREEN" bash -lc "cd '$ROOT_DIR' && backend/.venv/bin/python -m uvicorn app.main:app --host '$SERVER_BIND_HOST' --port '$BACKEND_PORT' > '$BACKEND_LOG' 2>&1"
    wait_for_backend
    if [[ "$FRONTEND_RUNTIME" == "dev" ]]; then
      screen -dmS "$FRONTEND_SCREEN" bash -lc "cd '$ROOT_DIR' && VITE_API_BASE_URL='same-origin' VITE_BACKEND_PROXY_TARGET='http://127.0.0.1:${BACKEND_PORT}' npm run dev -- --host '$SERVER_BIND_HOST' --port '$FRONTEND_PORT' > '$FRONTEND_LOG' 2>&1"
    else
      screen -dmS "$FRONTEND_SCREEN" bash -lc "cd '$ROOT_DIR' && VITE_API_BASE_URL='same-origin' VITE_BACKEND_PROXY_TARGET='http://127.0.0.1:${BACKEND_PORT}' npm run build >> '$FRONTEND_LOG' 2>&1 && VITE_API_BASE_URL='same-origin' VITE_BACKEND_PROXY_TARGET='http://127.0.0.1:${BACKEND_PORT}' npm run preview -- --host '$SERVER_BIND_HOST' --port '$FRONTEND_PORT' >> '$FRONTEND_LOG' 2>&1"
    fi
    screen -dmS "$CAFFEINATE_SCREEN" bash -lc "caffeinate -dimsu > /tmp/strategy-pilot-caffeinate.log 2>&1"
  else
    BACKEND_CORS_ORIGINS="$cors" \
      DASHBOARD_ACCESS_PIN="$access_pin" \
      BACKEND_ALLOWED_CLIENT_IPS="$ALLOWED_CLIENT_IPS" \
      BACKEND_TRUST_PROXY_HEADERS="$TRUST_PROXY_HEADERS" \
      BACKEND_AUTH_RATE_LIMIT="$AUTH_RATE_LIMIT" \
      BACKEND_ORDER_RATE_LIMIT="$ORDER_RATE_LIMIT" \
      KIWOOM_MODE=live \
      KIWOOM_READ_ONLY="$read_only" \
      KIWOOM_ENABLE_ORDER="$kiwoom_enable_order" \
      KIWOOM_US_ENABLE_ORDER="$enable_order" \
      KIWOOM_US_AUTO_EXIT_ENABLED=true \
      KIWOOM_US_AUTOTRADE_RUNNER_ENABLED="$AUTOTRADE_RUNNER_ENABLED" \
      KIWOOM_US_AUTOTRADE_OBSERVATION_ENABLED="$AUTOTRADE_OBSERVATION_ENABLED" \
      KIWOOM_US_AUTOTRADE_RUNNER_INTERVAL_SECONDS="$AUTOTRADE_RUNNER_INTERVAL" \
      KIWOOM_US_PREMARKET_ENTRY_ENABLED="$PREMARKET_ENTRY_ENABLED" \
      KIWOOM_US_ORDER_CONFIRM="$order_confirm" \
      KIWOOM_US_LIVE_ORDER_UNLOCK="$order_unlock" \
      KIWOOM_US_MAX_ORDER_QUANTITY=1 \
      KIWOOM_US_MAX_ORDER_KRW=30000 \
      KIWOOM_US_ORDER_USD_KRW_RATE=1400 \
      KIWOOM_US_ALLOW_ALL_COMMON_STOCKS=true \
      KIWOOM_US_COMMON_STOCK_ONLY=true \
      PYTHONPATH=backend \
      backend/.venv/bin/python -m uvicorn app.main:app --host "$SERVER_BIND_HOST" --port "$BACKEND_PORT" \
      > "$BACKEND_LOG" 2>&1 &
    echo "$!" > "$BACKEND_PID_FILE"
    wait_for_backend

    if [[ "$FRONTEND_RUNTIME" == "dev" ]]; then
      VITE_API_BASE_URL="same-origin" \
        VITE_BACKEND_PROXY_TARGET="http://127.0.0.1:${BACKEND_PORT}" \
        npm run dev -- --host "$SERVER_BIND_HOST" --port "$FRONTEND_PORT" \
        > "$FRONTEND_LOG" 2>&1 &
    else
      (
        VITE_API_BASE_URL="same-origin" VITE_BACKEND_PROXY_TARGET="http://127.0.0.1:${BACKEND_PORT}" npm run build
        VITE_API_BASE_URL="same-origin" VITE_BACKEND_PROXY_TARGET="http://127.0.0.1:${BACKEND_PORT}" npm run preview -- --host "$SERVER_BIND_HOST" --port "$FRONTEND_PORT"
      ) > "$FRONTEND_LOG" 2>&1 &
    fi
    echo "$!" > "$FRONTEND_PID_FILE"

    caffeinate -dimsu > /tmp/strategy-pilot-caffeinate.log 2>&1 &
    echo "$!" > "$CAFFEINATE_PID_FILE"
  fi

  sleep 2
  status
  echo "Dashboard access PIN: $access_pin"
  if [[ -n "$ALLOWED_CLIENT_IPS" ]]; then
    echo "Allowed client IPs: $ALLOWED_CLIENT_IPS"
  else
    echo "Allowed client IPs: not restricted"
  fi
  echo "Rate limits: auth=$AUTH_RATE_LIMIT order=$ORDER_RATE_LIMIT"
  echo "Auto-trade backend runner: $AUTOTRADE_RUNNER_ENABLED (${AUTOTRADE_RUNNER_INTERVAL}s)"
  echo "Read-only observation auto-start: $AUTOTRADE_OBSERVATION_ENABLED"
  echo "Frontend runtime: $FRONTEND_RUNTIME"
  echo "Dashboard PIN file: $ACCESS_PIN_FILE"
  if [[ "$ENABLE_LIVE_ORDERS" == "true" ]]; then
    echo "Live orders: ENABLED (1 share / 30000 KRW cap)"
  else
    echo "Live orders: DISABLED (set STRATEGY_PILOT_ENABLE_LIVE_ORDERS=true only when intentionally testing)"
  fi
  echo
  echo "Backend log:  $BACKEND_LOG"
  echo "Frontend log: $FRONTEND_LOG"
}

stop() {
  stop_screen "$BACKEND_SCREEN"
  stop_screen "$FRONTEND_SCREEN"
  stop_screen "$CAFFEINATE_SCREEN"
  stop_pid_file "$BACKEND_PID_FILE"
  stop_pid_file "$FRONTEND_PID_FILE"
  stop_pid_file "$CAFFEINATE_PID_FILE"
  stop_stale_backend_processes
  stop_ports
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) start ;;
  status) status ;;
  pin) generate_pin; echo ;;
  *)
    echo "Usage: $0 [start|stop|restart|status|pin]"
    exit 2
    ;;
esac
