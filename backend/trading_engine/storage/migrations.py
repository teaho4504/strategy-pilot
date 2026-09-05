from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS condition_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  condition_name TEXT NOT NULL,
  symbol TEXT NOT NULL,
  symbol_name TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS market_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  last_price INTEGER NOT NULL,
  change_rate REAL NOT NULL,
  trade_volume INTEGER NOT NULL,
  cumulative_volume INTEGER NOT NULL,
  bid INTEGER NOT NULL,
  ask INTEGER NOT NULL,
  timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS realtime_quote_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  symbol TEXT NOT NULL,
  provider TEXT NOT NULL,
  price REAL,
  change_rate REAL,
  volume INTEGER,
  trade_strength REAL,
  bid REAL,
  ask REAL,
  bid_size INTEGER,
  ask_size INTEGER,
  levels_json TEXT NOT NULL DEFAULT '[]',
  source_event_time TEXT,
  received_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_realtime_quote_events_symbol_received
ON realtime_quote_events(symbol, received_at);
CREATE TABLE IF NOT EXISTS strategy_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_type TEXT NOT NULL,
  symbol TEXT NOT NULL,
  strategy_name TEXT NOT NULL,
  reason TEXT NOT NULL,
  score INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS risk_blocks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS us_strategy_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  exchange TEXT NOT NULL,
  ready INTEGER NOT NULL,
  entry_price REAL,
  stop_price REAL,
  quantity INTEGER NOT NULL,
  blocked_reasons TEXT NOT NULL,
  criteria_json TEXT NOT NULL,
  decided_at TEXT NOT NULL,
  decided_at_et TEXT NOT NULL,
  us_market_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_us_strategy_decisions_symbol_date
ON us_strategy_decisions(symbol, us_market_date);
"""
