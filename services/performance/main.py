"""S2 Performance: total and annualised return over a period, and side by side comparison."""
from datetime import date

from fastapi import HTTPException, Query

from stockplatform import analytics
from stockplatform.cache import TTLCache
from stockplatform.prices import load_series, symbol_exists
from stockplatform.service import create_service, render_page

PERIODS = {"1m": 21, "3m": 63, "6m": 126, "1y": 252, "max": 5000}

PAGE = """
<div class='card'><div class='controls'>
 <div><label>Symbols, comma separated</label><input id='syms' value='AAPL,MSFT,JPM,XOM,SPY' size='34'></div>
 <div><label>Period</label><select id='per'><option value='1m'>1 month</option><option value='3m'>3 months</option><option value='6m'>6 months</option>
  <option value='1y' selected>1 year</option><option value='ytd'>Year to date</option><option value='max'>All history</option></select></div>
 <button onclick='go()'>Compare</button></div><p class='err' id='e'></p></div>
<div class='stats' id='stats'></div>
<div class='card'><h3>Total return</h3><div id='bars'></div></div>
<div class='card'><h3>Details</h3><table><thead><tr><th>Symbol</th><th>From</th><th>To</th><th class='num'>Total</th><th class='num'>Annualised</th>
 <th class='num'>Best day</th><th class='num'>Worst day</th></tr></thead><tbody id='t'></tbody></table></div>
"""
SCRIPT = """
async function go(){const r=await fetch(`/api/compare?symbols=${$('#syms').value}&period=${$('#per').value}`),j=await r.json();
 if(!r.ok){setError(typeof j.detail==='string'?j.detail:'Check the symbols and try again');return}setError();
 const res=[...j.results].sort((a,b)=>b.total_return-a.total_return),best=res[0],worst=res[res.length-1];
 $('#stats').innerHTML=stat('Best performer',best.symbol,signed(best.total_return),'good')+stat('Weakest performer',worst.symbol,signed(worst.total_return),tone(worst.total_return))
  +stat('Spread',pct(best.total_return-worst.total_return),'between best and weakest');
 barChart($('#bars'),res.map(x=>x.symbol),res.map(x=>x.total_return),{format:v=>signed(v)});
 $('#t').innerHTML=res.map(x=>`<tr><td><b>${x.symbol}</b></td><td>${x.start}</td><td>${x.end}</td><td class="num ${tone(x.total_return)}">${signed(x.total_return)}</td>
  <td class="num ${tone(x.annualized_return)}">${signed(x.annualized_return)}</td><td class="num good">${signed(x.best_day)}</td><td class="num bad">${signed(x.worst_day)}</td></tr>`).join('')}
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
        return render_page("Performance", PAGE, SCRIPT, "Compare returns over any period")

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
