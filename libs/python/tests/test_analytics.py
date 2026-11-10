import math

import pytest

from stockplatform import analytics as a
from stockplatform.cache import TTLCache


def test_returns_and_totals():
    assert a.daily_returns([100, 110, 99]) == pytest.approx([0.1, -0.1])
    assert a.total_return([100, 150]) == pytest.approx(0.5)
    assert a.total_return([100]) == 0.0


def test_annualized_return_doubling_in_one_year():
    closes = [100.0] + [100.0] * (a.TRADING_DAYS - 1) + [200.0]
    assert a.annualized_return(closes) == pytest.approx(1.0, rel=1e-6)


def test_volatility_zero_for_flat_and_scaled_for_noise():
    assert a.volatility([0.01] * 10) == pytest.approx(0.0, abs=1e-12)
    assert a.volatility([0.01, -0.01] * 10) == pytest.approx(0.0102597 * math.sqrt(252), rel=1e-3)


def test_max_drawdown():
    assert a.max_drawdown([100, 120, 60, 90]) == pytest.approx(-0.5)
    assert a.max_drawdown([1, 2, 3]) == 0.0


def test_var_is_positive_loss():
    rets = [-0.05] + [0.01] * 99
    assert a.value_at_risk(rets, 0.95) >= 0
    assert a.value_at_risk([0.01, 0.02]) == 0.0


def test_beta_and_correlation():
    bench = [0.01, -0.02, 0.015, 0.0, -0.01]
    assert a.beta([2 * x for x in bench], bench) == pytest.approx(2.0)
    assert a.correlation(bench, [-x for x in bench]) == pytest.approx(-1.0)
    assert a.correlation(bench, bench) == pytest.approx(1.0)
    assert a.correlation([1, 1, 1], [1, 2, 3]) == 0.0


def test_correlation_matrix_is_symmetric_with_unit_diagonal():
    m = a.correlation_matrix({"A": [1, 2, 3, 4, 6], "B": [2, 1, 4, 3, 5], "C": [5, 4, 3, 2, 0]})
    assert m["A"]["A"] == 1.0 and m["A"]["B"] == m["B"]["A"] and m["A"]["C"] == pytest.approx(-1.0)


def test_sma_and_ema():
    assert a.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    e = a.ema([1, 2, 3, 4, 5], 3)
    assert e[:2] == [None, None] and e[2] == pytest.approx(2.0) and e[3] == pytest.approx(3.0)


def test_rsi_extremes_and_range():
    up = a.rsi([float(i) for i in range(1, 40)])
    assert up[-1] == 100.0 and up[13] is None
    down = a.rsi([float(i) for i in range(40, 1, -1)])
    assert down[-1] == pytest.approx(0.0)
    mixed = [x for x in a.rsi([10, 11, 10, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16, 18]) if x is not None]
    assert all(0 <= x <= 100 for x in mixed)


def test_macd_lengths_and_histogram():
    vals = [float(i % 7 + i * 0.3) for i in range(80)]
    m = a.macd(vals)
    assert len(m["macd"]) == len(m["signal"]) == len(m["histogram"]) == 80
    last = len(vals) - 1
    assert m["histogram"][last] == pytest.approx(m["macd"][last] - m["signal"][last])


def test_backtest_equal_weights():
    r = a.backtest({"A": [10, 20], "B": [10, 10]}, {"A": 1, "B": 1}, 1000)
    assert r["final_value"] == pytest.approx(1500) and r["total_return"] == pytest.approx(0.5)
    with pytest.raises(ValueError):
        a.backtest({"A": [1, 2]}, {"A": 0}, 100)


def test_sharpe_flat_is_zero():
    assert a.sharpe([0.01] * 5) == 0.0


def test_cache_hits_expires_and_clears():
    c, calls = TTLCache(ttl=60), []
    f = lambda: calls.append(1) or len(calls)
    assert c.get_or_compute("k", f) == 1 and c.get_or_compute("k", f) == 1
    c.clear()
    assert c.get_or_compute("k", f) == 2
    expired = TTLCache(ttl=0)
    expired.get_or_compute("k", f)
    assert expired.get_or_compute("k", f) == 4
