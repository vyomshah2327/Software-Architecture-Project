"""S5 Fund Builder: back-test a custom basket and get simple suggestions by sector."""
from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from stockplatform import analytics, db
from stockplatform.cache import TTLCache
from stockplatform.prices import load_aligned, symbol_exists
from stockplatform.service import create_service, render_page

PAGE = """
<div class='card'><h2>Fund builder</h2>
<label>Symbols with optional weights, for example AAPL:50,MSFT:30,JNJ:20</label>
<input id='basket' value='AAPL:50,MSFT:30,JNJ:20' size='40'>
<label>Amount</label><input id='amt' type='number' value='10000'>
<label>Trading days</label><input id='days' type='number' value='252'>
<button onclick='go()'>Back-test</button></div>
<div class='card'><svg id='c' width='100%' height='160' viewBox='0 0 600 160' preserveAspectRatio='none'></svg>
<table id='t'></table><p class='err' id='e'></p></div>
"""
SCRIPT = """
async function go(){const w={};document.getElementById('basket').value.split(',').forEach(p=>{const [s,x]=p.trim().split(':');if(s)w[s.toUpperCase()]=x?parseFloat(x):1});
 const r=await fetch('/api/backtest',{method:'POST',headers:{'content-type':'application/json'},
  body:JSON.stringify({symbols:Object.keys(w),weights:w,amount:+document.getElementById('amt').value,days:+document.getElementById('days').value})});
 const j=await r.json();if(!r.ok){document.getElementById('e').textContent=JSON.stringify(j.detail);return}document.getElementById('e').textContent='';
 const v=j.values,mn=Math.min(...v),mx=Math.max(...v),pc=x=>(x*100).toFixed(2)+'%';
 document.getElementById('c').innerHTML='<polyline fill="none" stroke="#4f2683" stroke-width="2" points="'+v.map((y,i)=>`${i*600/Math.max(1,v.length-1)},${150-(y-mn)/(mx-mn||1)*140}`).join(' ')+'"/>';
 document.getElementById('t').innerHTML=`<tr><th>Final value</th><td>${j.final_value.toFixed(2)}</td></tr><tr><th>Total return</th><td>${pc(j.total_return)}</td></tr>
 <tr><th>Volatility</th><td>${pc(j.volatility)}</td></tr><tr><th>Max drawdown</th><td>${pc(j.max_drawdown)}</td></tr>`;}
go();
"""


class Basket(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=20)
    weights: dict[str, float] | None = None
    amount: float = Field(default=10000, gt=0)
    days: int = Field(default=252, ge=30, le=2000)


def create_app(**kwargs):
    cache = TTLCache(ttl=300)
    app = create_service(
        "fund-builder", "Fund Builder", "Back-test a basket of companies and see suggested baskets by sector.",
        tags=["fund", "basket", "backtest", "allocation"], subscriptions=["market.data.updated"],
        on_event=lambda e: cache.clear(), **kwargs)

    @app.get("/", include_in_schema=False)
    def page():
        return render_page("Fund Builder", PAGE, SCRIPT)

    @app.post("/api/backtest")
    def backtest(b: Basket):
        symbols = [s.upper() for s in b.symbols]
        if len(set(symbols)) != len(symbols):
            raise HTTPException(422, "each symbol can appear only once")
        for s in symbols:
            if not symbol_exists(s):
                raise HTTPException(404, f"unknown symbol {s}")
        weights = {s: 1.0 for s in symbols}
        if b.weights:
            given = {k.upper(): v for k, v in b.weights.items()}
            if set(given) != set(symbols) or any(v < 0 for v in given.values()):
                raise HTTPException(422, "weights must cover exactly the chosen symbols and not be negative")
            weights = given
        dates, series = load_aligned(symbols, b.days)
        if len(dates) < 30:
            raise HTTPException(404, "not enough shared price history for this basket")
        try:
            result = analytics.backtest(series, weights, b.amount)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        total = sum(weights.values())
        return {**result, "dates": [d.isoformat() for d in dates],
                "weights": {s: round(w / total, 6) for s, w in weights.items()}}

    @app.get("/api/suggest")
    def suggest(sector: str = Query(min_length=1), count: int = Query(default=5, ge=1, le=10)):
        """The best one year performers in a sector, equally weighted."""
        def work():
            names = [r["symbol"] for r in db.query("SELECT symbol FROM companies WHERE lower(sector) = lower(%s)", (sector,))]
            if not names:
                raise HTTPException(404, f"no companies in sector {sector}")
            dates, series = load_aligned(names, 252)
            ranked = sorted(((analytics.total_return(v), s) for s, v in series.items() if len(v) > 1), reverse=True)
            picks = [s for _, s in ranked[:count]]
            return {"sector": sector, "symbols": picks, "weights": {s: round(1 / len(picks), 6) for s in picks},
                    "one_year_return": {s: r for r, s in ranked[:count]}}
        return cache.get_or_compute(("suggest", sector.lower(), count), work)

    @app.get("/api/sectors")
    def sectors():
        return [r["sector"] for r in db.query("SELECT DISTINCT sector FROM companies WHERE sector IS NOT NULL ORDER BY 1")]

    return app


app = create_app()
