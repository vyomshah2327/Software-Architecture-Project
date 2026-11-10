"""S2 Performance: total and annualised return over a period, and side by side comparison."""
from datetime import date

from fastapi import HTTPException, Query

from stockplatform import analytics
from stockplatform.cache import TTLCache
from stockplatform.prices import load_series, symbol_exists
from stockplatform.service import create_service, render_page

PERIODS = {"1m": 21, "3m": 63, "6m": 126, "1y": 252, "max": 5000}

PAGE = """
<div class='card'><h2>Performance</h2>
<label>Symbols (comma separated)</label><input id='syms' value='AAPL,MSFT,SPY' size='30'>
<label>Period</label><select id='per'><option>1m</option><option>3m</option><option>6m</option>
<option selected>1y</option><option>ytd</option><option>max</option></select>
<button onclick='go()'>Compare</button></div>
<div class='card'><table id='t'></table><p class='err' id='e'></p></div>
"""
SCRIPT = """
async function go(){const s=document.getElementById('syms').value,p=document.getElementById('per').value;
 const r=await fetch(`/api/compare?symbols=${s}&period=${p}`);const j=await r.json();
 if(!r.ok){document.getElementById('e').textContent=j.detail;return}document.getElementById('e').textContent='';
 const pc=x=>(x*100).toFixed(2)+'%';
 document.getElementById('t').innerHTML='<tr><th>Symbol</th><th>Total return</th><th>Annualised</th><th>Best day</th><th>Worst day</th></tr>'+
 j.results.map(x=>`<tr><td>${x.symbol}</td><td>${pc(x.total_return)}</td><td>${pc(x.annualized_return)}</td><td>${pc(x.best_day)}</td><td>${pc(x.worst_day)}</td></tr>`).join('');}
go();
"""


def window(series, period: str):
    if period == "ytd":
        start = date(date.today().year, 1, 1)
        inside = [p for p in series if p[0] >= start]
        return inside if len(inside) > 1 else series[-2:]
    return series[-(PERIODS[period] + 1):]


def create_app(**kwargs):
    cache = TTLCache(ttl=300)
    app = create_service(
        "performance", "Performance", "Total and annualised return for a company over a chosen period.",
        tags=["performance", "returns", "compare"], subscriptions=["market.data.updated"],
        on_event=lambda e: cache.clear(), **kwargs)

    def compute(symbol: str, period: str) -> dict:
        symbol = symbol.upper()
        if period not in PERIODS and period != "ytd":
            raise HTTPException(422, f"period must be one of {sorted(PERIODS) + ['ytd']}")
        if not symbol_exists(symbol):
            raise HTTPException(404, f"unknown symbol {symbol}")

        def work():
            series = window(load_series(symbol, 5000), period)
            if len(series) < 2:
                raise HTTPException(404, f"not enough prices for {symbol}")
            closes = [c for _, c in series]
            rets = analytics.daily_returns(closes)
            return {"symbol": symbol, "period": period, "start": series[0][0].isoformat(),
                    "end": series[-1][0].isoformat(), "total_return": analytics.total_return(closes),
                    "annualized_return": analytics.annualized_return(closes),
                    "best_day": max(rets), "worst_day": min(rets)}
        return cache.get_or_compute((symbol, period), work)

    @app.get("/", include_in_schema=False)
    def page():
        return render_page("Performance", PAGE, SCRIPT)

    @app.get("/api/performance/{symbol}")
    def performance(symbol: str, period: str = "1y"):
        return compute(symbol, period)

    @app.get("/api/compare")
    def compare(symbols: str = Query(min_length=1), period: str = "1y"):
        names = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if not 1 <= len(names) <= 10:
            raise HTTPException(422, "give between 1 and 10 symbols")
        return {"period": period, "results": [compute(s, period) for s in names]}

    return app


app = create_app()
