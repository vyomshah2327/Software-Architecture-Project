"""S7 Correlation: how closely the daily returns of several companies move together."""
from fastapi import HTTPException, Query

from stockplatform import analytics
from stockplatform.cache import TTLCache
from stockplatform.prices import load_aligned, symbol_exists
from stockplatform.service import create_service, render_page

PAGE = """
<div class='card'><h2>Correlation</h2>
<label>Symbols (comma separated, 2 to 12)</label><input id='syms' value='AAPL,MSFT,XOM,JPM,SPY' size='40'>
<label>Trading days</label><input id='days' type='number' value='252' min='30' max='2000'>
<button onclick='go()'>Calculate</button></div>
<div class='card'><table id='t'></table><p class='err' id='e'></p></div>
"""
SCRIPT = """
async function go(){const r=await fetch(`/api/correlation?symbols=${document.getElementById('syms').value}&days=${document.getElementById('days').value}`);
 const j=await r.json();if(!r.ok){document.getElementById('e').textContent=j.detail;return}document.getElementById('e').textContent='';
 const n=Object.keys(j.matrix),col=v=>`rgba(79,38,131,${Math.abs(v).toFixed(2)})`;
 document.getElementById('t').innerHTML='<tr><th></th>'+n.map(x=>`<th>${x}</th>`).join('')+'</tr>'+
 n.map(a=>`<tr><th>${a}</th>`+n.map(b=>`<td style="background:${col(j.matrix[a][b])};color:${Math.abs(j.matrix[a][b])>.5?'#fff':'#000'}">${j.matrix[a][b].toFixed(2)}</td>`).join('')+'</tr>').join('');}
go();
"""


def create_app(**kwargs):
    cache = TTLCache(ttl=300)
    app = create_service(
        "correlation", "Correlation", "Correlation matrix of daily returns for a group of companies.",
        tags=["correlation", "diversification", "matrix"], subscriptions=["market.data.updated"],
        on_event=lambda e: cache.clear(), **kwargs)

    @app.get("/", include_in_schema=False)
    def page():
        return render_page("Correlation", PAGE, SCRIPT)

    @app.get("/api/correlation")
    def correlation(symbols: str = Query(min_length=1), days: int = Query(default=252, ge=30, le=2000)):
        names = list(dict.fromkeys(s.strip().upper() for s in symbols.split(",") if s.strip()))
        if not 2 <= len(names) <= 12:
            raise HTTPException(422, "give between 2 and 12 different symbols")
        for s in names:
            if not symbol_exists(s):
                raise HTTPException(404, f"unknown symbol {s}")

        def work():
            dates, series = load_aligned(names, days + 1)
            if len(dates) < 31:
                raise HTTPException(404, "not enough shared price history")
            rets = {s: analytics.daily_returns(v) for s, v in series.items()}
            return {"days": len(dates) - 1, "matrix": analytics.correlation_matrix(rets)}
        return cache.get_or_compute((tuple(names), days), work)

    return app


app = create_app()
