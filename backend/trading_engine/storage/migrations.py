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
CREATE TABLE IF NOT EXISTS paper_fills (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  symbol_name TEXT NOT NULL,
  side TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  price INTEGER NOT NULL,
  fee INTEGER NOT NULL,
  slippage INTEGER NOT NULL,
  realized_pnl INTEGER NOT NULL,
  reason TEXT NOT NULL,
  strategy_name TEXT NOT NULL,
  condition_name TEXT NOT NULL,
  filled_at TEXT NOT NULL
);
"""
