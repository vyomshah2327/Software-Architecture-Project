"""S3 Volatility and Risk: volatility, drawdown, value at risk, beta and Sharpe ratio."""
from fastapi import HTTPException, Query

from stockplatform import analytics
from stockplatform.cache import TTLCache
from stockplatform.prices import load_aligned, symbol_exists
from stockplatform.service import create_service, render_page

BENCHMARK = "SPY"

PAGE = """
<div class='card'><h2>Volatility and risk</h2>
<label>Symbol</label><input id='sym' value='AAPL'>
<label>Trading days</label><input id='days' type='number' value='252' min='30' max='2000'>
<button onclick='go()'>Measure</button></div>
<div class='card'><table id='t'></table><p class='err' id='e'></p></div>
"""
SCRIPT = """
async function go(){const r=await fetch(`/api/risk/${document.getElementById('sym').value}?days=${document.getElementById('days').value}`);
 const j=await r.json();if(!r.ok){document.getElementById('e').textContent=j.detail;return}document.getElementById('e').textContent='';
 const pc=x=>(x*100).toFixed(2)+'%';
 document.getElementById('t').innerHTML=`<tr><th>Annual volatility</th><td>${pc(j.volatility)}</td></tr>
 <tr><th>Max drawdown</th><td>${pc(j.max_drawdown)}</td></tr><tr><th>1 day VaR (95%)</th><td>${pc(j.var_95)}</td></tr>
 <tr><th>Beta vs ${j.benchmark}</th><td>${j.beta.toFixed(2)}</td></tr><tr><th>Sharpe ratio</th><td>${j.sharpe.toFixed(2)}</td></tr>`;}
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
        return render_page("Volatility and Risk", PAGE, SCRIPT)

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
