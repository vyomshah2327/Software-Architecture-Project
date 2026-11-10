"""S4 Technical Indicators: SMA, EMA, RSI and MACD series for a company."""
from fastapi import HTTPException, Query

from stockplatform import analytics
from stockplatform.cache import TTLCache
from stockplatform.prices import load_series, symbol_exists
from stockplatform.service import create_service, render_page

NAMES = ("sma", "ema", "rsi", "macd")

PAGE = """
<div class='card'><div class='controls'>
 <div><label>Symbol</label><input id='sym' value='AAPL' size='8'></div>
 <div><label>Indicator</label><select id='ind' onchange='sync()'><option value='sma'>Simple moving average</option><option value='ema'>Exponential moving average</option>
  <option value='rsi'>RSI</option><option value='macd'>MACD</option></select></div>
 <div id='wbox'><label>Window</label><input id='win' type='number' value='20' min='2' max='200' style='width:90px'></div>
 <button onclick='go()'>Calculate</button></div><p class='err' id='e'></p></div>
<div class='stats' id='stats'></div>
<div class='card'><h3 id='ct'>Price</h3><div id='chart'></div></div>
"""
SCRIPT = """
function sync(){const i=$('#ind').value;$('#wbox').style.display=i==='macd'?'none':'';$('#win').value=i==='rsi'?14:20}
async function go(){loading($('#chart'));const i=$('#ind').value;
 const r=await fetch(`/api/indicators/${$('#sym').value.trim()}?name=${i}&window=${$('#win').value}&limit=120`),j=await r.json();
 if(!r.ok){setError(typeof j.detail==='string'?j.detail:'Check the inputs');return}setError();const d=j.dates.map(x=>x.slice(5));
 if(i==='sma'||i==='ema'){const last=j.close[j.close.length-1],v=j.latest,up=last>v;
  $('#stats').innerHTML=stat('Last close',fmt(last))+stat(i.toUpperCase()+' '+j.window,fmt(v))+stat('Price vs average',signed(last/v-1),up?'trading above the average':'trading below the average',tone(last/v-1));
  $('#ct').textContent='Close and '+i.toUpperCase()+' '+j.window;lineChart($('#chart'),d,[{name:'Close',values:j.close},{name:i.toUpperCase()+' '+j.window,values:j.values,color:'#f59e0b'}])}
 else if(i==='rsi'){const v=j.latest,s=v>70?['Overbought','red']:v<30?['Oversold','green']:['Neutral','purple'];
  $('#stats').innerHTML=stat('RSI '+j.window,fmt(v,1),'0 to 100 scale')+`<div class="stat"><div class="k">Reading</div><div class="v"><span class="badge ${s[1]}">${s[0]}</span></div><div class="s">above 70 or below 30 is notable</div></div>`;
  $('#ct').textContent='Relative strength index';lineChart($('#chart'),d,[{name:'RSI',values:j.values,color:'#7c3aed'}],{min:0,max:100,bands:[{y:70,label:'70'},{y:30,label:'30'}],format:v=>fmt(v,0)})}
 else{const l=j.latest,bull=l.macd>l.signal;
  $('#stats').innerHTML=stat('MACD line',fmt(l.macd,3))+stat('Signal line',fmt(l.signal,3))+`<div class="stat"><div class="k">Momentum</div><div class="v"><span class="badge ${bull?'green':'red'}">${bull?'Bullish':'Bearish'}</span></div><div class="s">MACD ${bull?'above':'below'} signal</div></div>`;
  $('#ct').textContent='MACD and signal';lineChart($('#chart'),d,[{name:'MACD',values:j.macd},{name:'Signal',values:j.signal,color:'#f59e0b'}],{format:v=>fmt(v,2)})}}
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
        return render_page("Technical Indicators", PAGE, SCRIPT, "Moving averages, RSI and MACD")

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
