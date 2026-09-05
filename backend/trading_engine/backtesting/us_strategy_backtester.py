from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from dataclasses import replace

from trading_engine.strategies.us_day_trading import (
    ET,
    CandidateSnapshot,
    MarketContext,
    StrategyDecision,
    StrategyRuntimeState,
    StrategySettings,
    UsCandle,
    UsQuote,
    evaluate_1m_volume_breakout,
    evaluate_5m_trend_pullback,
    normalize_candles,
)


@dataclass(frozen=True)
class BacktestCostModel:
    commission_rate: float = 0.0005
    fx_cost_rate: float = 0.001
    entry_slippage_pct: float = 0.03
    exit_slippage_pct: float = 0.03
    spread_cost_pct: float = 0.05
    fx_rate_krw_per_usd: float | None = None


@dataclass(frozen=True)
class BacktestTrade:
    strategy_id: str
    symbol: str
    exchange: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    quantity: int
    gross_pnl: float
    execution_cost: float
    commission_cost: float
    fx_cost: float
    total_cost: float
    net_pnl: float
    net_pnl_krw: float | None
    r_multiple: float
    exit_reason: str


@dataclass(frozen=True)
class BacktestSummary:
    trades: list[BacktestTrade] = field(default_factory=list)
    total_trades: int = 0
    win_rate: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    max_drawdown: float = 0.0
    max_consecutive_losses: int = 0
    average_holding_minutes: float = 0.0
    gross_pnl: float = 0.0
    execution_cost: float = 0.0
    commission_cost: float = 0.0
    fx_cost: float = 0.0
    total_cost: float = 0.0
    net_pnl: float = 0.0
    net_pnl_krw: float | None = None
    fx_rate_krw_per_usd: float | None = None
    equity_curve: list[float] = field(default_factory=list)


def backtest_single_candidate(
    *,
    strategy_id: str,
    candidate: CandidateSnapshot,
    candles: list[UsCandle],
    account_equity: float,
    settings: StrategySettings | None = None,
    cost_model: BacktestCostModel | None = None,
    market_context: MarketContext | None = None,
) -> BacktestSummary:
    settings = settings or StrategySettings()
    cost_model = cost_model or BacktestCostModel()
    normalized = normalize_candles(candles)
    trades: list[BacktestTrade] = []
    open_trade: tuple[StrategyDecision, datetime] | None = None
    runtime = StrategyRuntimeState(account_equity=account_equity)
    prior_sessions: dict[date, list[UsCandle]] = {}
    current_session: list[UsCandle] = []
    current_session_date: date | None = None
    for index in range(60, len(normalized)):
        latest = normalized[index]
        latest_date = latest.timestamp.astimezone(ET).date()
        if current_session_date != latest_date:
            if current_session_date is not None and current_session:
                prior_sessions[current_session_date] = current_session
            current_session_date = latest_date
            current_session = [
                item
                for item in normalized[:index]
                if item.timestamp.astimezone(ET).date() == latest_date
            ]
        current_session.append(latest)
        point_in_time_candidate = _candidate_from_sessions(candidate, current_session, prior_sessions)
        decision = (
            evaluate_5m_trend_pullback(point_in_time_candidate, current_session, market_context or MarketContext(), runtime, settings, now=latest.timestamp)
            if strategy_id == "US_5M_TREND_PULLBACK"
            else evaluate_1m_volume_breakout(point_in_time_candidate, current_session, runtime, settings, now=latest.timestamp)
        )
        if open_trade is None:
            if decision.ready:
                open_trade = (decision, latest.timestamp)
            continue
        open_decision, entry_time = open_trade
        trade = _try_exit(open_decision, current_session, cost_model, entry_time=entry_time)
        if trade is not None:
            trades.append(trade)
            open_trade = None
    return summarize_trades(trades, fx_rate_krw_per_usd=cost_model.fx_rate_krw_per_usd)


def candidate_from_window(candidate: CandidateSnapshot, candles: list[UsCandle]) -> CandidateSnapshot:
    """Rebuild mutable candidate fields using only candles known at this point."""
    if not candles:
        return candidate
    sessions: dict[date, list[UsCandle]] = {}
    for item in candles:
        sessions.setdefault(item.timestamp.astimezone(ET).date(), []).append(item)
    session_date = candles[-1].timestamp.astimezone(ET).date()
    current_session = sessions.pop(session_date)
    return _candidate_from_sessions(candidate, current_session, sessions)


def _candidate_from_sessions(
    candidate: CandidateSnapshot,
    session: list[UsCandle],
    prior_sessions: dict[date, list[UsCandle]],
) -> CandidateSnapshot:
    latest = session[-1]
    session_open = session[0].open
    latest_price = latest.close
    prior_dates = sorted(prior_sessions)[-20:]
    recent_dates = prior_dates[-5:]
    average_volume_5d = (
        round(sum(sum(item.volume for item in prior_sessions[day]) for day in recent_dates) / len(recent_dates))
        if recent_dates
        else candidate.avg_volume_5d
    )
    average_volume_20d = (
        round(sum(sum(item.volume for item in prior_sessions[day]) for day in prior_dates) / len(prior_dates))
        if prior_dates
        else candidate.avg_volume_20d
    )
    same_time_average_volume = (
        round(
            sum(
                sum(item.volume for item in prior_sessions[day][:len(session)])
                for day in recent_dates
            ) / len(recent_dates)
        )
        if recent_dates
        else candidate.same_time_avg_volume
    )
    relative_spread = None
    if candidate.quote and candidate.quote.bid and candidate.quote.ask and candidate.quote.last:
        relative_spread = (candidate.quote.ask - candidate.quote.bid) / candidate.quote.last
    half_spread = latest_price * max(0.0, relative_spread or 0.0) / 2
    quote = UsQuote(
        symbol=candidate.symbol,
        exchange=candidate.exchange,
        bid=max(0.0001, latest_price - half_spread),
        ask=latest_price + half_spread,
        last=latest_price,
        cumulative_volume=sum(item.volume for item in session),
        trade_value=sum(item.close * item.volume for item in session),
        updated_at=latest.timestamp,
    )
    return replace(
        candidate,
        price=latest_price,
        open_price=session_open,
        day_high=max(item.high for item in session),
        change_rate=((latest_price / session_open) - 1) * 100 if session_open > 0 else 0.0,
        cumulative_volume=sum(item.volume for item in session),
        avg_volume_5d=average_volume_5d,
        avg_volume_20d=average_volume_20d,
        same_time_avg_volume=same_time_average_volume,
        trade_value=sum(item.close * item.volume for item in session),
        quote=quote,
    )


def summarize_trades(
    trades: list[BacktestTrade],
    *,
    fx_rate_krw_per_usd: float | None = None,
) -> BacktestSummary:
    if not trades:
        return BacktestSummary(
            net_pnl_krw=0.0 if fx_rate_krw_per_usd is not None else None,
            fx_rate_krw_per_usd=fx_rate_krw_per_usd,
        )
    pnls = [trade.net_pnl for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    curve: list[float] = []
    consecutive = 0
    max_consecutive = 0
    holding_minutes = []
    for trade in trades:
        equity += trade.net_pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
        curve.append(equity)
        if trade.net_pnl <= 0:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0
        holding_minutes.append(_minutes_between(trade.entry_time, trade.exit_time))
    return BacktestSummary(
        trades=trades,
        total_trades=len(trades),
        win_rate=len(wins) / len(trades),
        average_win=sum(wins) / len(wins) if wins else 0.0,
        average_loss=sum(losses) / len(losses) if losses else 0.0,
        profit_factor=gross_profit / gross_loss if gross_loss else float("inf"),
        expectancy=sum(pnls) / len(pnls),
        max_drawdown=abs(max_dd),
        max_consecutive_losses=max_consecutive,
        average_holding_minutes=sum(holding_minutes) / len(holding_minutes) if holding_minutes else 0.0,
        gross_pnl=sum(trade.gross_pnl for trade in trades),
        execution_cost=sum(trade.execution_cost for trade in trades),
        commission_cost=sum(trade.commission_cost for trade in trades),
        fx_cost=sum(trade.fx_cost for trade in trades),
        total_cost=sum(trade.total_cost for trade in trades),
        net_pnl=sum(trade.net_pnl for trade in trades),
        net_pnl_krw=(
            sum(trade.net_pnl for trade in trades) * fx_rate_krw_per_usd
            if fx_rate_krw_per_usd is not None
            else None
        ),
        fx_rate_krw_per_usd=fx_rate_krw_per_usd,
        equity_curve=curve,
    )


def _try_exit(
    decision: StrategyDecision,
    candles: list[UsCandle],
    cost_model: BacktestCostModel,
    *,
    entry_time,
) -> BacktestTrade | None:
    if decision.entry_price is None or decision.stop_price is None or decision.quantity <= 0:
        return None
    latest = candles[-1]
    risk = decision.entry_price - decision.stop_price
    if risk <= 0:
        return None
    exit_price = None
    reason = ""
    if latest.low <= decision.stop_price:
        exit_price = decision.stop_price
        reason = "stop"
    elif decision.target_2 is not None and latest.high >= decision.target_2:
        exit_price = decision.target_2
        reason = "target_2"
    elif latest.timestamp - entry_time >= timedelta(minutes=30):
        exit_price = latest.close
        reason = "time_exit"
    if exit_price is None:
        return None
    adjusted_entry = decision.entry_price * (1 + (cost_model.entry_slippage_pct + cost_model.spread_cost_pct) / 100)
    adjusted_exit = exit_price * (1 - (cost_model.exit_slippage_pct + cost_model.spread_cost_pct) / 100)
    gross = (exit_price - decision.entry_price) * decision.quantity
    execution_cost = (
        (adjusted_entry - decision.entry_price) + (exit_price - adjusted_exit)
    ) * decision.quantity
    traded_notional = (adjusted_entry + adjusted_exit) * decision.quantity
    commission_cost = traded_notional * cost_model.commission_rate
    fx_cost = traded_notional * cost_model.fx_cost_rate
    total_cost = execution_cost + commission_cost + fx_cost
    net = gross - total_cost
    return BacktestTrade(
        strategy_id=decision.strategy_id,
        symbol=decision.symbol,
        exchange=decision.exchange,
        entry_time=entry_time.isoformat(),
        exit_time=latest.timestamp.isoformat(),
        entry_price=decision.entry_price,
        exit_price=exit_price,
        quantity=decision.quantity,
        gross_pnl=gross,
        execution_cost=execution_cost,
        commission_cost=commission_cost,
        fx_cost=fx_cost,
        total_cost=total_cost,
        net_pnl=net,
        net_pnl_krw=(
            net * cost_model.fx_rate_krw_per_usd
            if cost_model.fx_rate_krw_per_usd is not None
            else None
        ),
        r_multiple=net / (risk * decision.quantity),
        exit_reason=reason,
    )


def _minutes_between(start: str, end: str) -> float:
    # ISO strings here are generated by datetime.isoformat and are timezone-aware.
    from datetime import datetime

    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60
