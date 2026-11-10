"""S3 Volatility and Risk: volatility, drawdown, value at risk, beta and Sharpe ratio."""
from fastapi import HTTPException, Query

from stockplatform import analytics
from stockplatform.cache import TTLCache
from stockplatform.prices import load_aligned, symbol_exists
from stockplatform.service import create_service, render_page

BENCHMARK = "SPY"

PAGE = """
<div class='card'><div class='controls'>
 <div><label>Symbol</label><input id='sym' value='AAPL' size='8'></div>
 <div><label>Window</label><select id='days'><option value='63'>3 months</option><option value='126'>6 months</option><option value='252' selected>1 year</option><option value='504'>2 years</option></select></div>
 <button onclick='go()'>Measure risk</button></div><p class='err' id='e'></p></div>
<div id='level'></div>
<div class='stats' id='stats'></div>
<div class='card'><h3>How to read these</h3><p class='muted'><b>Volatility</b> is how much the price swings in a year. <b>Max drawdown</b> is the worst fall from a peak.
 <b>Value at risk</b> is the loss that was exceeded on only 5 in 100 days. <b>Beta</b> compares moves with the market: above 1 swings more than SPY.
 <b>Sharpe</b> is return per unit of risk.</p></div>
"""
SCRIPT = """
async function go(){const r=await fetch(`/api/risk/${$('#sym').value.trim()}?days=${$('#days').value}`),j=await r.json();
 if(!r.ok){setError(typeof j.detail==='string'?j.detail:'Check the symbol and window');return}setError();
 const v=j.volatility,lvl=v<.2?['Low','green']:v<.35?['Moderate','purple']:['High','red'];
 $('#level').innerHTML=`<div class="card" style="display:flex;align-items:center;gap:14px"><h2 style="margin:0">${j.symbol}</h2><span class="badge ${lvl[1]}">${lvl[0]} risk</span><span class="muted">based on ${j.days} trading days</span></div>`;
 $('#stats').innerHTML=stat('Annual volatility',pct(v),'how bumpy the ride was')+stat('Max drawdown',pct(j.max_drawdown),'worst peak to trough fall','bad')
  +stat('1 day value at risk',pct(j.var_95),'on 95 of 100 days losses were smaller')+stat('Beta vs '+j.benchmark,fmt(j.beta),j.beta>1?'swings more than the market':'swings less than the market')
  +stat('Sharpe ratio',fmt(j.sharpe),'return per unit of risk',tone(j.sharpe))}
go();
"""


def create_app(**kwargs):
    cache = TTLCache(ttl=300)
    app = create_service(
        "volatility-risk", "Volatility and Risk", "Volatility, drawdown, value at risk, beta and Sharpe ratio.",
        tags=["risk", "volatility", "beta", "drawdown"], subscriptions=["market.data.updated"],
        on_event=lambda e: cache.clear(), **kwargs)

    @app.get("/", include_in_schema=False)
    def page():
        return render_page("Volatility and Risk", PAGE, SCRIPT, "How risky is a company")

    @app.get("/api/risk/{symbol}")
    def risk(symbol: str, days: int = Query(default=252, ge=30, le=2000)):
        symbol = symbol.upper()
        if not symbol_exists(symbol):
            raise HTTPException(404, f"unknown symbol {symbol}")

        def work():
            names = [symbol] if symbol == BENCHMARK else [symbol, BENCHMARK]
            dates, series = load_aligned(names, days + 1)
            closes = series[symbol]
            if len(closes) < 31:
                raise HTTPException(404, f"not enough prices for {symbol}")
            rets = analytics.daily_returns(closes)
            bench = analytics.daily_returns(series[BENCHMARK])
            return {"symbol": symbol, "days": len(rets), "benchmark": BENCHMARK,
                    "volatility": analytics.volatility(rets), "max_drawdown": analytics.max_drawdown(closes),
                    "var_95": analytics.value_at_risk(rets, 0.95), "beta": analytics.beta(rets, bench),
                    "sharpe": analytics.sharpe(rets)}
        return cache.get_or_compute((symbol, days), work)

    return app


app = create_app()
