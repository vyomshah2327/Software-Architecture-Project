"""S1 Price History: daily prices for one company over a date range."""
from datetime import date

from fastapi import HTTPException, Query

from stockplatform import db
from stockplatform.cache import TTLCache
from stockplatform.prices import symbol_exists
from stockplatform.service import create_service, render_page

PAGE = """
<div class='card'><h2>Price history</h2>
<label>Symbol</label><select id='sym'></select>
<label>Days</label><input id='days' type='number' value='60' min='5' max='2000'>
<button onclick='load()'>Show</button></div>
<div class='card'><svg id='chart' width='100%' height='160' viewBox='0 0 600 160' preserveAspectRatio='none'></svg>
<table id='t'></table></div>
"""
SCRIPT = """
async function init(){const r=await fetch('/api/companies');const c=await r.json();
 document.getElementById('sym').innerHTML=c.map(x=>`<option value="${x.symbol}">${x.symbol} - ${x.name}</option>`).join('');
 const p=new URLSearchParams(location.search).get('symbol'); if(p) document.getElementById('sym').value=p; load();}
async function load(){const s=document.getElementById('sym').value,d=document.getElementById('days').value;
 const r=await fetch(`/api/prices/${s}?limit=${d}`);const rows=await r.json();
 const closes=rows.map(x=>x.close),mn=Math.min(...closes),mx=Math.max(...closes);
 document.getElementById('chart').innerHTML='<polyline fill="none" stroke="#4f2683" stroke-width="2" points="'+
  closes.map((v,i)=>`${i*600/Math.max(1,closes.length-1)},${150-(v-mn)/(mx-mn||1)*140}`).join(' ')+'"/>';
 document.getElementById('t').innerHTML='<tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr>'+
  rows.slice(-15).reverse().map(x=>`<tr><td>${x.date}</td><td>${x.open}</td><td>${x.high}</td><td>${x.low}</td><td>${x.close}</td><td>${x.volume}</td></tr>`).join('');}
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
        return render_page("Price History", PAGE, SCRIPT)

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
