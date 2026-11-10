"""S6 Portfolio: holdings and watchlist per user, valued at the latest close."""
from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from stockplatform import db
from stockplatform.events import HOLDING_CHANGED, WATCHLIST_CHANGED
from stockplatform.prices import symbol_exists
from stockplatform.service import create_service, render_page

PAGE = """
<div class='card'><h2>My portfolio</h2><label>User</label><input id='u' value='demo'>
<label>Symbol</label><input id='s' value='AAPL' size='8'><label>Quantity</label><input id='q' type='number' value='10'>
<label>Average cost</label><input id='c' type='number' value='150'>
<button onclick='add()'>Add holding</button> <button onclick='watch()'>Watch symbol</button></div>
<div class='card'><table id='t'></table><p id='tot'></p><p class='err' id='e'></p></div>
<div class='card'><h3>Watchlist</h3><div id='w'></div></div>
"""
SCRIPT = """
const U=()=>document.getElementById('u').value,E=m=>document.getElementById('e').textContent=m||'';
async function post(url,body,method='POST'){const r=await fetch(url,{method,headers:{'content-type':'application/json'},body:body?JSON.stringify(body):undefined});
 if(!r.ok){E((await r.json()).detail);return false}E();return true}
async function add(){if(await post('/api/holdings',{user_id:U(),symbol:s.value,quantity:+q.value,avg_cost:+c.value}))load()}
async function watch(){if(await post(`/api/watchlist/${s.value}?user_id=${U()}`,null,'PUT'))load()}
async function drop(sym){await post(`/api/holdings/${sym}?user_id=${U()}`,null,'DELETE');load()}
async function load(){const j=await (await fetch(`/api/portfolio?user_id=${U()}`)).json();const pc=x=>(x*100).toFixed(2)+'%';
 t.innerHTML='<tr><th>Symbol</th><th>Qty</th><th>Avg cost</th><th>Last</th><th>Value</th><th>P&L</th><th>Weight</th><th></th></tr>'+
 j.positions.map(p=>`<tr><td>${p.symbol}</td><td>${p.quantity}</td><td>${p.avg_cost}</td><td>${p.last_price}</td><td>${p.value.toFixed(2)}</td><td>${p.pnl.toFixed(2)} (${pc(p.pnl_pct)})</td><td>${pc(p.weight)}</td><td><button onclick="drop('${p.symbol}')">Remove</button></td></tr>`).join('');
 tot.textContent=`Total value ${j.total_value.toFixed(2)}, profit and loss ${j.total_pnl.toFixed(2)}`;
 w.textContent=(await (await fetch(`/api/watchlist?user_id=${U()}`)).json()).symbols.join(', ')||'Nothing watched yet';}
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
        return render_page("Portfolio", PAGE, SCRIPT)

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
