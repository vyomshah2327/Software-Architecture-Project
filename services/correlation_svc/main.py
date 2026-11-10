"""S7 Correlation: how closely the daily returns of several companies move together."""
from fastapi import HTTPException, Query

from stockplatform import analytics
from stockplatform.cache import TTLCache
from stockplatform.prices import load_aligned, symbol_exists
from stockplatform.service import create_service, render_page

PAGE = """
<div class='card'><div class='controls'>
 <div><label>Symbols, 2 to 12</label><input id='syms' value='AAPL,MSFT,NVDA,JPM,XOM,JNJ,SPY' size='42'></div>
 <div><label>Window</label><select id='days'><option value='63'>3 months</option><option value='126'>6 months</option><option value='252' selected>1 year</option></select></div>
 <button onclick='go()'>Calculate</button></div><p class='err' id='e'></p></div>
<div class='stats' id='stats'></div>
<div class='card'><h3>Correlation of daily returns</h3><div style='overflow:auto'><table id='t' style='text-align:center'></table></div>
 <div class='legend' style='align-items:center;margin-top:14px'>-1 <span style='display:inline-block;width:220px;height:10px;border-radius:6px;background:linear-gradient(90deg,#f97316,#fff7ed 50%,#ede9fe 50%,#6d28d9)'></span> +1
 <span>Close to +1: move together. Close to -1: move opposite. Near 0: unrelated.</span></div></div>
"""
SCRIPT = """
function color(v){const a=Math.min(1,Math.abs(v));return v>=0?`rgba(109,40,217,${a.toFixed(2)})`:`rgba(249,115,22,${a.toFixed(2)})`}
async function go(){const r=await fetch(`/api/correlation?symbols=${$('#syms').value}&days=${$('#days').value}`),j=await r.json();
 if(!r.ok){setError(typeof j.detail==='string'?j.detail:'Give 2 to 12 different symbols');return}setError();
 const n=Object.keys(j.matrix),pairs=[];n.forEach((a,i)=>n.forEach((b,k)=>{if(k>i)pairs.push([a,b,j.matrix[a][b]])}));pairs.sort((x,y)=>y[2]-x[2]);
 const hi=pairs[0],lo=pairs[pairs.length-1];
 $('#stats').innerHTML=stat('Most alike',hi[0]+' and '+hi[1],'correlation '+fmt(hi[2]))+stat('Least alike',lo[0]+' and '+lo[1],'correlation '+fmt(lo[2]))+stat('Window',j.days+' days','of daily returns');
 $('#t').innerHTML='<tr><th></th>'+n.map(x=>`<th style="text-align:center">${x}</th>`).join('')+'</tr>'+
  n.map(a=>`<tr><th>${a}</th>`+n.map(b=>{const v=j.matrix[a][b];return `<td style="background:${color(v)};color:${Math.abs(v)>.5?'#fff':'inherit'};font-weight:600;border-radius:6px">${v.toFixed(2)}</td>`}).join('')+'</tr>').join('')}
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
        return render_page("Correlation", PAGE, SCRIPT, "How closely companies move together")

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
