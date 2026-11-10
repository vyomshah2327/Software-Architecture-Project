"""S4 Technical Indicators: SMA, EMA, RSI and MACD series for a company."""
from fastapi import HTTPException, Query

from stockplatform import analytics
from stockplatform.cache import TTLCache
from stockplatform.prices import load_series, symbol_exists
from stockplatform.service import create_service, render_page

NAMES = ("sma", "ema", "rsi", "macd")

PAGE = """
<div class='card'><h2>Technical indicators</h2>
<label>Symbol</label><input id='sym' value='AAPL'>
<label>Indicator</label><select id='ind'><option>sma</option><option>ema</option><option>rsi</option><option>macd</option></select>
<label>Window</label><input id='win' type='number' value='20' min='2' max='200'>
<button onclick='go()'>Calculate</button></div>
<div class='card'><svg id='c' width='100%' height='160' viewBox='0 0 600 160' preserveAspectRatio='none'></svg>
<p class='err' id='e'></p><pre id='o'></pre></div>
"""
SCRIPT = """
async function go(){const i=document.getElementById('ind').value;
 const r=await fetch(`/api/indicators/${document.getElementById('sym').value}?name=${i}&window=${document.getElementById('win').value}&limit=120`);
 const j=await r.json();if(!r.ok){document.getElementById('e').textContent=j.detail;return}document.getElementById('e').textContent='';
 const s=(i==='macd'?j.macd:j.values).filter(x=>x!==null),mn=Math.min(...s),mx=Math.max(...s);
 document.getElementById('c').innerHTML='<polyline fill="none" stroke="#4f2683" stroke-width="2" points="'+
 s.map((v,k)=>`${k*600/Math.max(1,s.length-1)},${150-(v-mn)/(mx-mn||1)*140}`).join(' ')+'"/>';
 document.getElementById('o').textContent='Latest: '+JSON.stringify(j.latest);}
go();
"""


def create_app(**kwargs):
    cache = TTLCache(ttl=300)
    app = create_service(
        "indicators", "Technical Indicators", "Moving averages, RSI and MACD for a company.",
        tags=["indicators", "sma", "ema", "rsi", "macd", "technical"], subscriptions=["market.data.updated"],
        on_event=lambda e: cache.clear(), **kwargs)

    @app.get("/", include_in_schema=False)
    def page():
        return render_page("Technical Indicators", PAGE, SCRIPT)

    @app.get("/api/indicators/{symbol}")
    def indicators(symbol: str, name: str = "sma", window: int = Query(default=20, ge=2, le=200),
                   limit: int = Query(default=120, ge=1, le=1000)):
        symbol, name = symbol.upper(), name.lower()
        if name not in NAMES:
            raise HTTPException(422, f"name must be one of {list(NAMES)}")
        if not symbol_exists(symbol):
            raise HTTPException(404, f"unknown symbol {symbol}")

        def work():
            series = load_series(symbol, limit + 250)
            if len(series) < 40:
                raise HTTPException(404, f"not enough prices for {symbol}")
            closes = [c for _, c in series]
            dates = [d.isoformat() for d, _ in series]
            if name == "macd":
                m = analytics.macd(closes)
                out = {k: v[-limit:] for k, v in m.items()}
                latest = {k: v[-1] for k, v in out.items()}
            else:
                fn = {"sma": analytics.sma, "ema": analytics.ema, "rsi": analytics.rsi}[name]
                values = fn(closes, window)[-limit:]
                out, latest = {"values": values}, values[-1]
            return {"symbol": symbol, "name": name, "window": window, "dates": dates[-limit:],
                    "close": closes[-limit:], "latest": latest, **out}
        return cache.get_or_compute((symbol, name, window, limit), work)

    return app


app = create_app()
