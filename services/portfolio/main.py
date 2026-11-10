"""S6 Portfolio: holdings and watchlist per user, valued at the latest close."""
from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from stockplatform import db
from stockplatform.events import HOLDING_CHANGED, WATCHLIST_CHANGED
from stockplatform.prices import symbol_exists
from stockplatform.service import create_service, render_page

PAGE = """
<div class='card'><div class='controls'>
 <div><label>User</label><input id='u' value='demo' style='width:100px' onchange='load()'></div>
 <div><label>Symbol</label><input id='s' value='AAPL' size='7'></div>
 <div><label>Quantity</label><input id='q' type='number' value='10' style='width:90px'></div>
 <div><label>Average cost</label><input id='c' type='number' value='150' style='width:110px'></div>
 <button onclick='add()'>Add holding</button><button class='ghost' onclick='watch()'>Add to watchlist</button></div><p class='err' id='e'></p></div>
<div class='stats' id='stats'></div>
<div class='card'><h3>Allocation</h3><div id='alloc'></div></div>
<div class='card'><h3>Holdings</h3><table><thead><tr><th>Symbol</th><th class='num'>Quantity</th><th class='num'>Avg cost</th><th class='num'>Last</th>
 <th class='num'>Value</th><th class='num'>Profit and loss</th><th class='num'>Weight</th><th></th></tr></thead><tbody id='t'></tbody></table></div>
<div class='card'><h3>Watchlist</h3><div id='w'></div></div>
"""
SCRIPT = """
const U=()=>$('#u').value.trim()||'demo';
async function call(url,method,body){const r=await fetch(url,{method,headers:{'content-type':'application/json'},body:body?JSON.stringify(body):undefined});
 if(!r.ok){const j=await r.json();setError(typeof j.detail==='string'?j.detail:'Check the values and try again');return false}setError();return true}
async function add(){if(await call('/api/holdings','POST',{user_id:U(),symbol:$('#s').value,quantity:+$('#q').value,avg_cost:+$('#c').value}))load()}
async function watch(){if(await call(`/api/watchlist/${$('#s').value}?user_id=${U()}`,'PUT'))load()}
async function drop(s){await call(`/api/holdings/${s}?user_id=${U()}`,'DELETE');load()}
async function unwatch(s){await call(`/api/watchlist/${s}?user_id=${U()}`,'DELETE');load()}
async function load(){const j=await (await fetch(`/api/portfolio?user_id=${U()}`)).json(),cost=j.positions.reduce((a,p)=>a+p.quantity*p.avg_cost,0);
 $('#stats').innerHTML=stat('Total value',fmt(j.total_value),j.positions.length+' positions')+stat('Profit and loss',(j.total_pnl>=0?'+':'')+fmt(j.total_pnl),cost?signed(j.total_pnl/cost)+' on cost':'',tone(j.total_pnl))+stat('Invested',fmt(cost));
 donut($('#alloc'),j.positions.map(p=>({label:p.symbol,value:p.value})));
 $('#t').innerHTML=j.positions.length?j.positions.map(p=>`<tr><td><b>${p.symbol}</b></td><td class="num">${p.quantity}</td><td class="num">${fmt(p.avg_cost)}</td><td class="num">${fmt(p.last_price)}</td>
  <td class="num">${fmt(p.value)}</td><td class="num ${tone(p.pnl)}">${p.pnl>=0?'+':''}${fmt(p.pnl)} (${signed(p.pnl_pct)})</td><td class="num">${pct(p.weight,1)}</td>
  <td><button class="ghost" onclick="drop('${p.symbol}')">Remove</button></td></tr>`).join(''):'<tr><td colspan="8" class="empty">No holdings yet. Add one above.</td></tr>';
 const w=(await (await fetch(`/api/watchlist?user_id=${U()}`)).json()).symbols;
 $('#w').innerHTML=w.length?w.map(s=>`<span class="badge purple" style="margin:0 8px 8px 0;font-size:14px;padding:5px 12px">${s} <a href="#" style="color:inherit;text-decoration:none" onclick="unwatch('${s}');return false">&times;</a></span>`).join(''):'<span class="muted">Nothing watched yet.</span>'}
load();
"""


class Holding(BaseModel):
    user_id: str = Field(default="demo", min_length=1, max_length=64)
    symbol: str
    quantity: float = Field(gt=0)
    avg_cost: float = Field(ge=0)


def create_app(**kwargs):
    app = create_service("portfolio", "Portfolio", "Track holdings and a watchlist and see profit and loss.",
                         tags=["portfolio", "holdings", "watchlist", "profit"], **kwargs)
    broker = app.state.broker

    @app.get("/", include_in_schema=False)
    def page():
        return render_page("Portfolio", PAGE, SCRIPT, "Holdings, watchlist and profit and loss")

    @app.post("/api/holdings", status_code=201)
    def add_holding(h: Holding):
        symbol = h.symbol.upper()
        if not symbol_exists(symbol):
            raise HTTPException(404, f"unknown symbol {symbol}")
        with db.connection() as conn:
            row = conn.execute("SELECT id, quantity, avg_cost FROM holdings WHERE user_id=%s AND symbol=%s FOR UPDATE",
                               (h.user_id, symbol)).fetchone()
            if row:  # buying more of the same symbol: keep one row with a weighted average cost
                qty = float(row["quantity"]) + h.quantity
                cost = (float(row["quantity"]) * float(row["avg_cost"]) + h.quantity * h.avg_cost) / qty
                conn.execute("UPDATE holdings SET quantity=%s, avg_cost=%s WHERE id=%s", (qty, cost, row["id"]))
            else:
                qty, cost = h.quantity, h.avg_cost
                conn.execute("INSERT INTO holdings (user_id, symbol, quantity, avg_cost) VALUES (%s,%s,%s,%s)",
                             (h.user_id, symbol, qty, cost))
        broker.publish(HOLDING_CHANGED, {"user_id": h.user_id, "symbol": symbol, "action": "added"}, "portfolio")
        return {"user_id": h.user_id, "symbol": symbol, "quantity": qty, "avg_cost": round(cost, 6)}

    @app.delete("/api/holdings/{symbol}", status_code=204)
    def remove_holding(symbol: str, user_id: str = "demo"):
        symbol = symbol.upper()
        if not db.execute("DELETE FROM holdings WHERE user_id=%s AND symbol=%s", (user_id, symbol)):
            raise HTTPException(404, "no such holding")
        broker.publish(HOLDING_CHANGED, {"user_id": user_id, "symbol": symbol, "action": "removed"}, "portfolio")

    @app.get("/api/portfolio")
    def portfolio(user_id: str = "demo"):
        rows = db.query(
            "SELECT h.symbol, h.quantity, h.avg_cost, (SELECT close FROM prices p WHERE p.symbol = h.symbol "
            "ORDER BY date DESC LIMIT 1) AS last FROM holdings h WHERE h.user_id=%s ORDER BY h.symbol", (user_id,))
        positions = []
        for r in rows:
            qty, cost, last = float(r["quantity"]), float(r["avg_cost"]), float(r["last"] or 0)
            positions.append({"symbol": r["symbol"], "quantity": qty, "avg_cost": cost, "last_price": last,
                              "value": qty * last, "pnl": qty * (last - cost),
                              "pnl_pct": (last / cost - 1) if cost else 0.0})
        total = sum(p["value"] for p in positions)
        for p in positions:
            p["weight"] = p["value"] / total if total else 0.0
        return {"user_id": user_id, "positions": positions, "total_value": total,
                "total_pnl": sum(p["pnl"] for p in positions)}

    @app.get("/api/watchlist")
    def watchlist(user_id: str = "demo"):
        return {"user_id": user_id, "symbols": [r["symbol"] for r in db.query(
            "SELECT symbol FROM watchlist WHERE user_id=%s ORDER BY symbol", (user_id,))]}

    @app.put("/api/watchlist/{symbol}", status_code=204)
    def watch(symbol: str, user_id: str = "demo"):
        symbol = symbol.upper()
        if not symbol_exists(symbol):
            raise HTTPException(404, f"unknown symbol {symbol}")
        if db.execute("INSERT INTO watchlist (user_id, symbol) VALUES (%s,%s) ON CONFLICT DO NOTHING", (user_id, symbol)):
            broker.publish(WATCHLIST_CHANGED, {"user_id": user_id, "symbol": symbol, "action": "added"}, "portfolio")

    @app.delete("/api/watchlist/{symbol}", status_code=204)
    def unwatch(symbol: str, user_id: str = "demo"):
        symbol = symbol.upper()
        if db.execute("DELETE FROM watchlist WHERE user_id=%s AND symbol=%s", (user_id, symbol)):
            broker.publish(WATCHLIST_CHANGED, {"user_id": user_id, "symbol": symbol, "action": "removed"}, "portfolio")

    return app


app = create_app()
