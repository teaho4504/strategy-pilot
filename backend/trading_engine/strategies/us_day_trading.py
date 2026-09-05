from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from math import floor
from statistics import median
from typing import Iterable
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")

STRATEGY_5M_TREND_PULLBACK = "US_5M_TREND_PULLBACK"
STRATEGY_1M_VOLUME_BREAKOUT = "US_1M_VOLUME_BREAKOUT"


@dataclass(frozen=True)
class UsCandle:
    symbol: str
    exchange: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime


@dataclass(frozen=True)
class UsQuote:
    symbol: str
    exchange: str
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    cumulative_volume: int | None = None
    trade_value: float | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class MarketContext:
    qqq_candles: list[UsCandle] = field(default_factory=list)
    spy_candles: list[UsCandle] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateSnapshot:
    symbol: str
    exchange: str
    price: float
    open_price: float
    day_high: float
    change_rate: float
    cumulative_volume: int
    avg_volume_5d: int | None = None
    avg_volume_20d: int | None = None
    same_time_avg_volume: int | None = None
    trade_value: float | None = None
    is_common_stock: bool = True
    is_leveraged_or_inverse_etf: bool = False
    quote: UsQuote | None = None
    condition_name: str | None = None
    condition_entered_at: datetime | None = None


@dataclass(frozen=True)
class StrategySettings:
    price_min: float = 10.0
    price_max: float = 300.0
    min_trade_value: float = 20_000_000.0
    min_rvol: float = 1.5
    max_spread_pct: float = 0.15
    max_data_age_seconds: int = 15
    risk_per_trade_pct: float = 0.0025
    max_position_notional_pct: float = 0.10
    daily_max_loss_pct: float = 0.01
    max_open_positions: int = 2
    max_same_symbol_trades_per_day: int = 2
    max_consecutive_losses: int = 3
    force_flat_time_et: time = time(15, 50)
    include_leveraged_inverse_etf: bool = False


@dataclass(frozen=True)
class StrategyRuntimeState:
    account_equity: float
    open_positions: int = 0
    daily_loss: float = 0.0
    consecutive_losses: int = 0
    symbol_trades_today: dict[str, int] = field(default_factory=dict)
    has_open_order_symbols: set[str] = field(default_factory=set)
    has_position_symbols: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class CriterionResult:
    key: str
    passed: bool
    value: str | None
    reason: str


@dataclass(frozen=True)
class StrategyDecision:
    strategy_id: str
    symbol: str
    exchange: str
    ready: bool
    side: str = "buy"
    entry_price: float | None = None
    stop_price: float | None = None
    quantity: int = 0
    risk_per_share: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    force_exit_at_et: time | None = None
    criteria: list[CriterionResult] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, float | int | str] = field(default_factory=dict)


def normalize_candles(candles: Iterable[UsCandle]) -> list[UsCandle]:
    merged: dict[datetime, UsCandle] = {}
    for candle in candles:
        ts = candle.timestamp.astimezone(ET)
        existing = merged.get(ts)
        normalized = UsCandle(
            symbol=candle.symbol.upper(),
            exchange=candle.exchange,
            open=float(candle.open),
            high=float(candle.high),
            low=float(candle.low),
            close=float(candle.close),
            volume=max(0, int(candle.volume)),
            timestamp=ts,
        )
        if existing is None:
            merged[ts] = normalized
            continue
        merged[ts] = UsCandle(
            symbol=existing.symbol,
            exchange=existing.exchange,
            open=existing.open,
            high=max(existing.high, normalized.high),
            low=min(existing.low, normalized.low),
            close=normalized.close,
            volume=existing.volume + normalized.volume,
            timestamp=ts,
        )
    return [merged[key] for key in sorted(merged)]


def ema(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("EMA period must be positive")
    result: list[float | None] = []
    multiplier = 2 / (period + 1)
    current: float | None = None
    for index, value in enumerate(values):
        if index + 1 < period:
            result.append(None)
            continue
        if current is None:
            current = sum(values[index + 1 - period:index + 1]) / period
        else:
            current = value * multiplier + current * (1 - multiplier)
        result.append(current)
    return result


def vwap(candles: list[UsCandle]) -> list[float | None]:
    total_value = 0.0
    total_volume = 0
    values: list[float | None] = []
    for candle in candles:
        typical = (candle.high + candle.low + candle.close) / 3
        total_value += typical * candle.volume
        total_volume += candle.volume
        values.append(total_value / total_volume if total_volume else None)
    return values


def atr(candles: list[UsCandle], period: int = 14) -> list[float | None]:
    if period <= 0:
        raise ValueError("ATR period must be positive")
    true_ranges: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        if previous_close is None:
            tr = candle.high - candle.low
        else:
            tr = max(candle.high - candle.low, abs(candle.high - previous_close), abs(candle.low - previous_close))
        true_ranges.append(max(0.0, tr))
        previous_close = candle.close
    values: list[float | None] = []
    current: float | None = None
    for index, tr in enumerate(true_ranges):
        if index + 1 < period:
            values.append(None)
            continue
        if current is None:
            current = sum(true_ranges[index + 1 - period:index + 1]) / period
        else:
            current = (current * (period - 1) + tr) / period
        values.append(current)
    return values


def spread_pct(quote: UsQuote | None) -> float | None:
    if quote is None or quote.bid is None or quote.ask is None or quote.bid <= 0 or quote.ask <= 0:
        return None
    mid = (quote.bid + quote.ask) / 2
    if mid <= 0:
        return None
    return (quote.ask - quote.bid) / mid * 100


def estimate_trade_value(candles: list[UsCandle]) -> float:
    return sum(((c.high + c.low + c.close) / 3) * c.volume for c in candles)


def rvol(candidate: CandidateSnapshot) -> float | None:
    if not candidate.same_time_avg_volume or candidate.same_time_avg_volume <= 0:
        return None
    return candidate.cumulative_volume / candidate.same_time_avg_volume


def evaluate_common_liquidity(
    candidate: CandidateSnapshot,
    candles: list[UsCandle],
    now: datetime,
    settings: StrategySettings,
) -> list[CriterionResult]:
    quote_spread = spread_pct(candidate.quote)
    trade_value = candidate.trade_value if candidate.trade_value is not None else estimate_trade_value(candles)
    current_rvol = rvol(candidate)
    data_age = None
    if candidate.quote and candidate.quote.updated_at:
        data_age = (now.astimezone(ET) - candidate.quote.updated_at.astimezone(ET)).total_seconds()
    return [
        _criterion("common_stock", candidate.is_common_stock, None, "일반주식 여부"),
        _criterion(
            "leveraged_inverse_filter",
            settings.include_leveraged_inverse_etf or not candidate.is_leveraged_or_inverse_etf,
            None,
            "레버리지/인버스 ETF 제외",
        ),
        _criterion("price_range", settings.price_min <= candidate.price <= settings.price_max, f"{candidate.price:.4f}", "현재가 10~300달러"),
        _criterion("trade_value", trade_value >= settings.min_trade_value, f"{trade_value:.0f}", "당일 누적 거래대금 2,000만 달러 이상"),
        _criterion("rvol", current_rvol is not None and current_rvol >= settings.min_rvol, _fmt(current_rvol), "동일 시간대 RVOL 1.5 이상"),
        _criterion("bid_ask_present", quote_spread is not None, _fmt(quote_spread), "매수/매도 1호가 존재"),
        _criterion("spread", quote_spread is not None and quote_spread <= settings.max_spread_pct, _fmt(quote_spread), "스프레드율 0.15% 이하"),
        _criterion(
            "fresh_quote",
            data_age is not None and data_age <= settings.max_data_age_seconds,
            _fmt(data_age),
            "신규 진입 직전 데이터 최신성",
        ),
    ]


def evaluate_5m_trend_pullback(
    candidate: CandidateSnapshot,
    candles: list[UsCandle],
    market_context: MarketContext,
    runtime: StrategyRuntimeState,
    settings: StrategySettings | None = None,
    now: datetime | None = None,
) -> StrategyDecision:
    settings = settings or StrategySettings()
    current_time = (now or datetime.now(ET)).astimezone(ET)
    normalized = normalize_candles(candles)
    criteria = evaluate_common_liquidity(candidate, normalized, current_time, settings)
    closes = [c.close for c in normalized]
    vols = [c.volume for c in normalized]
    ema9, ema20, ema50 = ema(closes, 9), ema(closes, 20), ema(closes, 50)
    vwaps, atr14 = vwap(normalized), atr(normalized, 14)
    latest = normalized[-1] if normalized else None
    latest_ema9, latest_ema20, latest_ema50 = _last(ema9), _last(ema20), _last(ema50)
    latest_vwap, latest_atr = _last(vwaps), _last(atr14)
    wave = _find_5m_wave(normalized)
    pullback = _find_pullback_after_wave(normalized, wave)
    market_ok = _market_etf_filter(candidate.exchange, market_context)
    criteria.extend([
        _criterion("session", _between_et(current_time, time(9, 45), time(14, 30)), current_time.strftime("%H:%M"), "정규장 09:45~14:30 ET"),
        _criterion("change_rate", 1.5 <= candidate.change_rate <= 8.0, f"{candidate.change_rate:.2f}", "당일 등락률 +1.5~+8%"),
        _criterion("above_open", candidate.price > candidate.open_price, f"{candidate.price:.4f}/{candidate.open_price:.4f}", "현재가 > 당일 시가"),
        _criterion("near_high", candidate.price >= candidate.day_high * 0.95, f"{candidate.price:.4f}/{candidate.day_high:.4f}", "현재가가 당일 고가의 95% 이상"),
        _criterion("volume_vs_5d", candidate.avg_volume_5d is not None and candidate.cumulative_volume >= candidate.avg_volume_5d * 1.5, _fmt(candidate.avg_volume_5d), "최근 거래량 5일 평균 대비 150% 이상"),
        _criterion("close_above_vwap", latest is not None and latest_vwap is not None and latest.close > latest_vwap, _fmt(latest_vwap), "5분봉 종가 > VWAP"),
        _criterion("ema_stack", _all_present(latest_ema9, latest_ema20, latest_ema50) and latest_ema9 > latest_ema20 > latest_ema50, f"{_fmt(latest_ema9)}/{_fmt(latest_ema20)}/{_fmt(latest_ema50)}", "EMA(9) > EMA(20) > EMA(50)"),
        _criterion("market_etf", market_ok, None, "NASDAQ=QQQ, NYSE=SPY 시장 필터"),
        _criterion("impulse_wave", wave is not None, _wave_value(wave), "최근 3~6봉 상승 파동"),
        _criterion("pullback_zone", pullback is not None, _pullback_value(pullback), "2~4봉 눌림과 30~60% 되돌림"),
    ])
    if latest and pullback and wave and latest_ema9 is not None and latest_atr is not None:
        previous_high = normalized[-2].high if len(normalized) >= 2 else latest.high
        pullback_avg_vol = pullback["avg_volume"]
        trigger_ok = (
            latest.close > previous_high
            and latest.close > latest_ema9
            and latest.volume > pullback_avg_vol * 1.2
        )
        stop_price = float(pullback["low"]) - 0.1 * latest_atr
        entry_price = _limit_buy_price(candidate.quote, latest.close)
        stop_pct = (entry_price - stop_price) / entry_price * 100 if entry_price > 0 else 999
    else:
        trigger_ok = False
        stop_price = None
        entry_price = None
        stop_pct = 999
    criteria.append(_criterion("buy_trigger", trigger_ok, _fmt(entry_price), "반전봉 확정과 거래량 재증가"))
    criteria.append(_criterion("stop_width", entry_price is not None and stop_price is not None and stop_pct <= 1.2, _fmt(stop_pct), "진입가-손절가 거리 1.2% 이하"))
    return _decision(
        strategy_id=STRATEGY_5M_TREND_PULLBACK,
        candidate=candidate,
        criteria=criteria,
        entry_price=entry_price,
        stop_price=stop_price,
        atr_value=latest_atr,
        runtime=runtime,
        settings=settings,
        target_r_multiples=(1.0, 2.0),
    )


def evaluate_1m_volume_breakout(
    candidate: CandidateSnapshot,
    candles: list[UsCandle],
    runtime: StrategyRuntimeState,
    settings: StrategySettings | None = None,
    now: datetime | None = None,
) -> StrategyDecision:
    settings = settings or StrategySettings()
    current_time = (now or datetime.now(ET)).astimezone(ET)
    normalized = normalize_candles(candles)
    criteria = evaluate_common_liquidity(candidate, normalized, current_time, settings)
    closes = [c.close for c in normalized]
    ema9, ema20 = ema(closes, 9), ema(closes, 20)
    vwaps, atr14 = vwap(normalized), atr(normalized, 14)
    latest = normalized[-1] if normalized else None
    latest_ema9, latest_ema20 = _last(ema9), _last(ema20)
    latest_vwap, latest_atr = _last(vwaps), _last(atr14)
    prior_5_high = max((c.high for c in normalized[-6:-1]), default=None)
    prior_20_median_volume = median([c.volume for c in normalized[-21:-1]]) if len(normalized) >= 21 else None
    body_ratio, upper_wick_ratio = _body_and_upper_wick_ratio(latest)
    previous_return = _previous_candle_return(normalized)
    trigger = prior_5_high
    limit_price = _limit_buy_price(candidate.quote, latest.close if latest else candidate.price)
    stop_reference = min((c.low for c in normalized[-6:-1]), default=None)
    stop_by_atr = (limit_price - 0.6 * latest_atr) if latest_atr is not None else None
    stop_price = max(stop_reference or 0, stop_by_atr or 0) or None
    stop_pct = (limit_price - stop_price) / limit_price * 100 if stop_price and limit_price > 0 else 999
    volume_growth = None
    if candidate.avg_volume_5d and candidate.avg_volume_5d > 0:
        volume_growth = candidate.cumulative_volume / candidate.avg_volume_5d * 100
    criteria.extend([
        _criterion("session", _between_et(current_time, time(9, 35), time(11, 30)), current_time.strftime("%H:%M"), "정규장 09:35~11:30 ET"),
        _criterion("change_rate", 2.0 <= candidate.change_rate <= 10.0, f"{candidate.change_rate:.2f}", "당일 등락률 +2~+10%"),
        _criterion("above_open", candidate.price > candidate.open_price, f"{candidate.price:.4f}/{candidate.open_price:.4f}", "현재가 > 당일 시가"),
        _criterion("near_high", candidate.price >= candidate.day_high * 0.98, f"{candidate.price:.4f}/{candidate.day_high:.4f}", "현재가가 당일 고가의 98% 이상"),
        _criterion("volume_1m", candidate.cumulative_volume >= 1_000_000, str(candidate.cumulative_volume), "당일 거래량 100만 주 이상"),
        _criterion("volume_growth_200", volume_growth is not None and volume_growth >= 200, _fmt(volume_growth), "거래량 증가율 200% 이상"),
        _criterion("close_above_vwap", latest is not None and latest_vwap is not None and latest.close > latest_vwap, _fmt(latest_vwap), "1분봉 종가 > VWAP"),
        _criterion("ema_stack", _all_present(latest_ema9, latest_ema20) and latest_ema9 > latest_ema20, f"{_fmt(latest_ema9)}/{_fmt(latest_ema20)}", "EMA(9) > EMA(20)"),
        _criterion("breakout", latest is not None and trigger is not None and latest.close > trigger, _fmt(trigger), "직전 5개 확정봉 최고가 돌파"),
        _criterion("volume_breakout", latest is not None and prior_20_median_volume is not None and latest.volume >= prior_20_median_volume * 1.8, _fmt(prior_20_median_volume), "현재 봉 거래량 >= 20봉 중앙값 x1.8"),
        _criterion("body_ratio", body_ratio is not None and body_ratio >= 0.55, _fmt(body_ratio), "봉 몸통/전체 길이 55% 이상"),
        _criterion("upper_wick", upper_wick_ratio is not None and upper_wick_ratio <= 0.30, _fmt(upper_wick_ratio), "윗꼬리/전체 길이 30% 이하"),
        _criterion("vwap_extension", latest_vwap is not None and limit_price <= latest_vwap * 1.015, _fmt(limit_price), "예정가가 VWAP보다 1.5% 이상 높지 않음"),
        _criterion("no_chase", previous_return is not None and previous_return < 2.0, _fmt(previous_return), "직전 1분봉 2% 이상 급등 추격 금지"),
        _criterion("limit_with_atr", trigger is not None and latest_atr is not None and limit_price <= trigger + 0.1 * latest_atr, _fmt(limit_price), "매수 가능 가격 <= trigger + 0.1 ATR"),
        _criterion("stop_width", stop_pct <= 0.8, _fmt(stop_pct), "실제 손절폭 0.8% 이하"),
    ])
    return _decision(
        strategy_id=STRATEGY_1M_VOLUME_BREAKOUT,
        candidate=candidate,
        criteria=criteria,
        entry_price=limit_price,
        stop_price=stop_price,
        atr_value=latest_atr,
        runtime=runtime,
        settings=settings,
        target_r_multiples=(1.0, 1.5),
    )


def calculate_order_quantity(account_equity: float, entry_price: float, stop_price: float, settings: StrategySettings) -> int:
    if entry_price <= 0 or stop_price <= 0 or entry_price <= stop_price:
        return 0
    risk_budget = account_equity * settings.risk_per_trade_pct
    risk_per_share = entry_price - stop_price
    risk_qty = floor(risk_budget / risk_per_share)
    notional_qty = floor((account_equity * settings.max_position_notional_pct) / entry_price)
    return max(0, min(risk_qty, notional_qty))


def _decision(
    *,
    strategy_id: str,
    candidate: CandidateSnapshot,
    criteria: list[CriterionResult],
    entry_price: float | None,
    stop_price: float | None,
    atr_value: float | None,
    runtime: StrategyRuntimeState,
    settings: StrategySettings,
    target_r_multiples: tuple[float, float],
) -> StrategyDecision:
    blockers = [item.key for item in criteria if not item.passed]
    blockers.extend(_runtime_blockers(candidate, runtime, settings))
    qty = calculate_order_quantity(runtime.account_equity, entry_price or 0, stop_price or 0, settings)
    if qty <= 0:
        blockers.append("quantity_zero")
    risk = (entry_price - stop_price) if entry_price and stop_price else None
    target_1 = entry_price + risk * target_r_multiples[0] if entry_price and risk else None
    target_2 = entry_price + risk * target_r_multiples[1] if entry_price and risk else None
    ready = not blockers and entry_price is not None and stop_price is not None and qty > 0
    return StrategyDecision(
        strategy_id=strategy_id,
        symbol=candidate.symbol,
        exchange=candidate.exchange,
        ready=ready,
        entry_price=entry_price,
        stop_price=stop_price,
        quantity=qty,
        risk_per_share=risk,
        target_1=target_1,
        target_2=target_2,
        force_exit_at_et=settings.force_flat_time_et,
        criteria=criteria,
        blocked_reasons=_dedupe(blockers),
        metadata={"atr14": atr_value or 0.0},
    )


def _runtime_blockers(candidate: CandidateSnapshot, runtime: StrategyRuntimeState, settings: StrategySettings) -> list[str]:
    blockers: list[str] = []
    if runtime.open_positions >= settings.max_open_positions:
        blockers.append("max_open_positions")
    if runtime.daily_loss >= runtime.account_equity * settings.daily_max_loss_pct:
        blockers.append("daily_loss_limit")
    if runtime.consecutive_losses >= settings.max_consecutive_losses:
        blockers.append("consecutive_loss_limit")
    if runtime.symbol_trades_today.get(candidate.symbol, 0) >= settings.max_same_symbol_trades_per_day:
        blockers.append("same_symbol_daily_limit")
    if candidate.symbol in runtime.has_open_order_symbols:
        blockers.append("open_order_exists")
    if candidate.symbol in runtime.has_position_symbols:
        blockers.append("position_exists")
    return blockers


def _find_5m_wave(candles: list[UsCandle]) -> dict[str, float] | None:
    if len(candles) < 26:
        return None
    baseline = median([c.volume for c in candles[-26:-6]])
    for size in range(6, 2, -1):
        window = candles[-(size + 4):-4]
        if len(window) != size:
            continue
        low = min(c.low for c in window)
        high = max(c.high for c in window)
        start = window[0].open
        gain_pct = (high - start) / start * 100 if start > 0 else 0
        avg_volume = sum(c.volume for c in window) / len(window)
        if gain_pct >= 1.2 and baseline > 0 and avg_volume >= baseline * 1.5:
            return {"low": low, "high": high, "gain_pct": gain_pct, "avg_volume": avg_volume}
    return None


def _find_pullback_after_wave(candles: list[UsCandle], wave: dict[str, float] | None) -> dict[str, float] | None:
    if wave is None or len(candles) < 6:
        return None
    wave_range = wave["high"] - wave["low"]
    if wave_range <= 0:
        return None
    for size in range(4, 1, -1):
        pullback = candles[-(size + 1):-1]
        if len(pullback) != size:
            continue
        low = min(c.low for c in pullback)
        retrace = (wave["high"] - low) / wave_range * 100
        avg_volume = sum(c.volume for c in pullback) / len(pullback)
        lower_low_count = sum(1 for left, right in zip(pullback, pullback[1:]) if right.low < left.low)
        if 30 <= retrace <= 60 and avg_volume <= wave["avg_volume"] * 0.70 and lower_low_count < len(pullback) - 1:
            return {"low": low, "retrace": retrace, "avg_volume": avg_volume}
    return None


def _market_etf_filter(exchange: str, context: MarketContext) -> bool:
    candles = context.qqq_candles if exchange == "ND" else context.spy_candles if exchange == "NY" else []
    if len(candles) < 20:
        return True
    normalized = normalize_candles(candles)
    closes = [c.close for c in normalized]
    e9, e20, vwaps = _last(ema(closes, 9)), _last(ema(closes, 20)), _last(vwap(normalized))
    latest = normalized[-1]
    return _all_present(e9, e20, vwaps) and latest.close > vwaps and e9 > e20


def _limit_buy_price(quote: UsQuote | None, reference: float) -> float:
    if quote and quote.ask and quote.ask > 0:
        return float(quote.ask)
    return round(reference, 4)


def _body_and_upper_wick_ratio(candle: UsCandle | None) -> tuple[float | None, float | None]:
    if candle is None:
        return None, None
    full = candle.high - candle.low
    if full <= 0:
        return None, None
    body = abs(candle.close - candle.open)
    upper = candle.high - max(candle.open, candle.close)
    return body / full, upper / full


def _previous_candle_return(candles: list[UsCandle]) -> float | None:
    if len(candles) < 2:
        return None
    previous = candles[-2]
    if previous.open <= 0:
        return None
    return (previous.close - previous.open) / previous.open * 100


def _criterion(key: str, passed: bool, value: str | None, reason: str) -> CriterionResult:
    return CriterionResult(key=key, passed=bool(passed), value=value, reason=reason)


def _last(values: list[float | None]) -> float | None:
    return values[-1] if values else None


def _all_present(*values: float | None) -> bool:
    return all(value is not None for value in values)


def _between_et(dt: datetime, start: time, end: time) -> bool:
    current = dt.astimezone(ET).time()
    return start <= current <= end


def _fmt(value: float | int | None) -> str | None:
    if value is None:
        return None
    return f"{float(value):.4f}"


def _wave_value(wave: dict[str, float] | None) -> str | None:
    if wave is None:
        return None
    return f"gain={wave['gain_pct']:.2f}%,avgVol={wave['avg_volume']:.0f}"


def _pullback_value(pullback: dict[str, float] | None) -> str | None:
    if pullback is None:
        return None
    return f"retrace={pullback['retrace']:.2f}%,avgVol={pullback['avg_volume']:.0f}"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
