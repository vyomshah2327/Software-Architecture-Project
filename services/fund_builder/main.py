"""S5 Fund Builder: back-test a custom basket and get simple suggestions by sector."""
from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from stockplatform import analytics, db
from stockplatform.cache import TTLCache
from stockplatform.prices import load_aligned, symbol_exists
from stockplatform.service import create_service, render_page

PAGE = """
<div class='card'><div class='controls'>
 <div><label>Basket, symbol:weight</label><input id='basket' value='AAPL:40,MSFT:30,JNJ:20,XOM:10' size='38'></div>
 <div><label>Amount</label><input id='amt' type='number' value='10000' style='width:110px'></div>
 <div><label>History</label><select id='days'><option value='125'>6 months</option><option value='252' selected>1 year</option><option value='500'>2 years</option></select></div>
 <button onclick='go()'>Back-test</button></div>
 <div class='controls' style='margin-top:12px'><div><label>Or get an idea from a sector</label><select id='sector'></select></div>
 <button class='ghost' onclick='suggest()'>Suggest a basket</button></div><p class='err' id='e'></p></div>
<div class='stats' id='stats'></div>
<div class='card'><h3>Value of the fund over time</h3><div id='chart'></div></div>
<div class='card'><h3>Allocation</h3><div id='alloc'></div></div>
"""
SCRIPT = """
async function sectors(){const s=await (await fetch('/api/sectors')).json();$('#sector').innerHTML=s.map(x=>`<option>${x}</option>`).join('')}
async function suggest(){const r=await fetch('/api/suggest?count=4&sector='+encodeURIComponent($('#sector').value)),j=await r.json();
 if(!r.ok){setError(j.detail);return}$('#basket').value=j.symbols.map(s=>s+':'+Math.round(j.weights[s]*100)).join(',');go()}
async function go(){loading($('#chart'));const w={};$('#basket').value.split(',').forEach(p=>{const [s,x]=p.trim().split(':');if(s)w[s.toUpperCase()]=x?parseFloat(x):1});
 const r=await fetch('/api/backtest',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({symbols:Object.keys(w),weights:w,amount:+$('#amt').value,days:+$('#days').value})});
 const j=await r.json();if(!r.ok){setError(typeof j.detail==='string'?j.detail:'Check the basket: each symbol once, weights not negative');$('#chart').innerHTML='';return}setError();
 const amt=+$('#amt').value;
 $('#stats').innerHTML=stat('Final value',fmt(j.final_value),'started with '+fmt(amt,0))+stat('Total return',signed(j.total_return),'',tone(j.total_return))
  +stat('Volatility',pct(j.volatility),'annualised')+stat('Max drawdown',pct(j.max_drawdown),'worst fall from a peak','bad');
 lineChart($('#chart'),j.dates.map(d=>d.slice(5)),[{name:'Fund value',values:j.values}]);
 donut($('#alloc'),Object.entries(j.weights).map(([k,v])=>({label:k,value:v})))}
sectors().then(go);
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
        return render_page("Fund Builder", PAGE, SCRIPT, "Back-test a basket of companies")

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
