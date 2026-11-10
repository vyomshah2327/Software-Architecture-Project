"""S1 Price History: daily prices for one company over a date range."""
from datetime import date

from fastapi import HTTPException, Query

from stockplatform import db
from stockplatform.cache import TTLCache
from stockplatform.prices import symbol_exists
from stockplatform.service import create_service, render_page

PAGE = """
<div class='card'><div class='controls'>
 <div><label>Company</label><select id='sym' onchange='load()'></select></div>
 <div><label>Range</label><select id='days' onchange='load()'><option value='30'>1 month</option><option value='60' selected>3 months</option>
  <option value='125'>6 months</option><option value='250'>1 year</option></select></div>
</div><p class='err' id='e'></p></div>
<div class='stats' id='stats'></div>
<div class='card'><h3>Closing price</h3><div id='chart'></div></div>
<div class='card'><h3>Latest trading days</h3><table><thead><tr><th>Date</th><th class='num'>Open</th><th class='num'>High</th><th class='num'>Low</th>
 <th class='num'>Close</th><th class='num'>Change</th><th class='num'>Volume</th></tr></thead><tbody id='t'></tbody></table></div>
"""
SCRIPT = """
async function init(){const c=await (await fetch('/api/companies')).json();
 $('#sym').innerHTML=c.map(x=>`<option value="${x.symbol}">${x.symbol}  ${x.name}</option>`).join('');
 const p=new URLSearchParams(location.search).get('symbol');if(p)$('#sym').value=p.toUpperCase();load()}
async function load(){loading($('#chart'));
 const r=await fetch(`/api/prices/${$('#sym').value}?limit=${$('#days').value}`),rows=await r.json();
 if(!r.ok){setError(rows.detail);return}setError();
 const cl=rows.map(x=>x.close),ch=cl[cl.length-1]/cl[0]-1;
 $('#stats').innerHTML=stat('Last close',fmt(cl[cl.length-1]),rows[rows.length-1].date)+stat('Change',signed(ch),`over ${rows.length} trading days`,tone(ch))
  +stat('Period high',fmt(Math.max(...rows.map(x=>x.high))))+stat('Period low',fmt(Math.min(...rows.map(x=>x.low))));
 lineChart($('#chart'),rows.map(x=>x.date),[{name:'Close',values:cl}]);
 $('#t').innerHTML=rows.slice(-12).reverse().map((x,i,a)=>{const prev=rows[rows.length-1-i-1],d=prev?x.close/prev.close-1:0;
  return `<tr><td>${x.date}</td><td class="num">${fmt(x.open)}</td><td class="num">${fmt(x.high)}</td><td class="num">${fmt(x.low)}</td><td class="num">${fmt(x.close)}</td>
  <td class="num ${tone(d)}">${signed(d)}</td><td class="num">${Number(x.volume).toLocaleString()}</td></tr>`}).join('')}
init();
"""


def create_app(**kwargs):
    cache = TTLCache(ttl=300)
    app = create_service(
        "price-history", "Price History", "Daily open, high, low, close and volume for a company.",
        tags=["price", "history", "quotes"], subscriptions=["market.data.updated"],
        on_event=lambda e: cache.clear(), **kwargs)

    @app.get("/", include_in_schema=False)
    def page():
        return render_page("Price History", PAGE, SCRIPT, "Daily open, high, low, close and volume")

    @app.get("/api/companies")
    def companies():
        return cache.get_or_compute("companies", lambda: db.query(
            "SELECT symbol, name, sector FROM companies ORDER BY symbol"))

    @app.get("/api/prices/{symbol}")
    def prices(symbol: str, start: date | None = None, end: date | None = None,
               limit: int = Query(default=100, ge=1, le=5000)):
        symbol = symbol.upper()
        if not symbol_exists(symbol):
            raise HTTPException(404, f"unknown symbol {symbol}")
        rows = db.query(
            "SELECT date, open, high, low, close, adjusted_close, volume FROM prices WHERE symbol = %s "
            "AND (%s::date IS NULL OR date >= %s) AND (%s::date IS NULL OR date <= %s) "
            "ORDER BY date DESC LIMIT %s", (symbol, start, start, end, end, limit))
        return [{**r, "date": r["date"].isoformat(), **{k: float(r[k]) for k in
                 ("open", "high", "low", "close", "adjusted_close")}} for r in reversed(rows)]

    @app.get("/api/latest/{symbol}")
    def latest(symbol: str):
        rows = prices(symbol, None, None, 2)
        if not rows:
            raise HTTPException(404, "no prices")
        last = rows[-1]
        change = (last["close"] / rows[-2]["close"] - 1) if len(rows) > 1 else 0.0
        return {"symbol": symbol.upper(), "date": last["date"], "close": last["close"], "change": round(change, 6)}

    return app


app = create_app()
