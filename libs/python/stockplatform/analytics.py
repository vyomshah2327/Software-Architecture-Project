"""Pure calculations used by the services. No database, no network, easy to test."""
from __future__ import annotations

import math
import statistics

TRADING_DAYS = 252


def daily_returns(closes: list[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]


def total_return(closes: list[float]) -> float:
    if len(closes) < 2 or not closes[0]:
        return 0.0
    return closes[-1] / closes[0] - 1


def annualized_return(closes: list[float]) -> float:
    if len(closes) < 2 or closes[0] <= 0 or closes[-1] <= 0:
        return 0.0
    years = (len(closes) - 1) / TRADING_DAYS
    return (closes[-1] / closes[0]) ** (1 / years) - 1


def volatility(returns: list[float]) -> float:
    """Annualised standard deviation of daily returns."""
    return statistics.stdev(returns) * math.sqrt(TRADING_DAYS) if len(returns) > 1 else 0.0


def max_drawdown(closes: list[float]) -> float:
    """Largest peak to trough fall, as a negative fraction (for example -0.23)."""
    peak, worst = float("-inf"), 0.0
    for c in closes:
        peak = max(peak, c)
        if peak > 0:
            worst = min(worst, c / peak - 1)
    return worst


def value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    """Historical one day VaR as a positive loss fraction."""
    if not returns:
        return 0.0
    ordered = sorted(returns)
    index = max(0, int(math.floor((1 - confidence) * len(ordered))) - 1) if len(ordered) > 20 else 0
    return max(0.0, -ordered[index])


def sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    sd = statistics.stdev(returns)
    if sd == 0:
        return 0.0
    return (statistics.mean(returns) - risk_free / TRADING_DAYS) / sd * math.sqrt(TRADING_DAYS)


def covariance(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    ma, mb = sum(a[:n]) / n, sum(b[:n]) / n
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)


def beta(returns: list[float], benchmark: list[float]) -> float:
    n = min(len(returns), len(benchmark))
    var = statistics.variance(benchmark[:n]) if n > 1 else 0.0
    return covariance(returns[:n], benchmark[:n]) / var if var else 0.0


def correlation(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    sa, sb = statistics.stdev(a[:n]), statistics.stdev(b[:n])
    return covariance(a[:n], b[:n]) / (sa * sb) if sa and sb else 0.0


def correlation_matrix(series: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    names = list(series)
    return {x: {y: (1.0 if x == y else round(correlation(series[x], series[y]), 4)) for y in names} for x in names}


def sma(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        out.append(None if i + 1 < window else sum(values[i + 1 - window:i + 1]) / window)
    return out


def ema(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < window:
        return out
    k = 2 / (window + 1)
    prev = sum(values[:window]) / window
    out[window - 1] = prev
    for i in range(window, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: list[float], window: int = 14) -> list[float | None]:
    """Wilder's relative strength index."""
    out: list[float | None] = [None] * len(values)
    if len(values) <= window:
        return out
    gains = [max(values[i] - values[i - 1], 0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0) for i in range(1, len(values))]
    avg_gain, avg_loss = sum(gains[:window]) / window, sum(losses[:window]) / window

    def value(g, l):
        return 100.0 if l == 0 else 100 - 100 / (1 + g / l)

    out[window] = value(avg_gain, avg_loss)
    for i in range(window + 1, len(values)):
        avg_gain = (avg_gain * (window - 1) + gains[i - 1]) / window
        avg_loss = (avg_loss * (window - 1) + losses[i - 1]) / window
        out[i] = value(avg_gain, avg_loss)
    return out


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, list[float | None]]:
    f, s = ema(values, fast), ema(values, slow)
    line = [None if a is None or b is None else a - b for a, b in zip(f, s)]
    defined = [x for x in line if x is not None]
    sig_def = ema(defined, signal)
    sig: list[float | None] = [None] * (len(line) - len(defined)) + sig_def
    hist = [None if a is None or b is None else a - b for a, b in zip(line, sig)]
    return {"macd": line, "signal": sig, "histogram": hist}


def backtest(closes: dict[str, list[float]], weights: dict[str, float], amount: float) -> dict:
    """Buy once at the start with the given weights and hold. Series must be the same length."""
    total_w = sum(weights.values())
    if total_w <= 0:
        raise ValueError("weights must add up to more than zero")
    n = min(len(v) for v in closes.values())
    shares = {s: amount * (weights[s] / total_w) / closes[s][0] for s in weights}
    values = [sum(shares[s] * closes[s][i] for s in weights) for i in range(n)]
    rets = daily_returns(values)
    return {"values": values, "total_return": total_return(values), "volatility": volatility(rets),
            "max_drawdown": max_drawdown(values), "final_value": values[-1]}
