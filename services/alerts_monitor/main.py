"""S8 Alerts and Monitor: price alert rules, a watchlist monitor, and evaluation after each data load.

An alert fires once when a rule goes from not met to met (edge triggered), so running the check
twice, or handling the same event twice, never produces a duplicate alert.
"""
from fastapi import HTTPException
from pydantic import BaseModel, Field

from stockplatform import db
from stockplatform.events import ALERT_TRIGGERED, Envelope, MARKET_DATA_UPDATED
from stockplatform.prices import symbol_exists
from stockplatform.service import create_service, render_page

PAGE = """
<div class='card'><h2>Alerts and monitor</h2><label>User</label><input id='u' value='demo'>
<label>Symbol</label><input id='s' value='AAPL' size='8'>
<select id='d'><option>above</option><option>below</option></select>
<input id='th' type='number' value='200' step='0.01'><button onclick='add()'>Create alert</button>
<button onclick='check()'>Check now</button><p class='err' id='e'></p></div>
<div class='card'><h3>Rules</h3><table id='r'></table></div>
<div class='card'><h3>Triggered alerts</h3><table id='a'></table></div>
<div class='card'><h3>Watchlist monitor</h3><table id='m'></table></div>
"""
SCRIPT = """
const U=()=>document.getElementById('u').value;
async function add(){const r=await fetch('/api/rules',{method:'POST',headers:{'content-type':'application/json'},
 body:JSON.stringify({user_id:U(),symbol:s.value,direction:d.value,threshold:+th.value})});
 e.textContent=r.ok?'':JSON.stringify((await r.json()).detail);load()}
async function check(){await fetch('/api/evaluate',{method:'POST'});load()}
async function del(id){await fetch('/api/rules/'+id,{method:'DELETE'});load()}
async function load(){const q='?user_id='+U();
 const rules=await (await fetch('/api/rules'+q)).json();
 r.innerHTML='<tr><th>Symbol</th><th>Condition</th><th>State</th><th></th></tr>'+rules.map(x=>`<tr><td>${x.symbol}</td><td>${x.direction} ${x.threshold}</td><td>${x.last_state||'not checked'}</td><td><button onclick="del(${x.id})">Delete</button></td></tr>`).join('');
 const al=await (await fetch('/api/alerts'+q)).json();
 a.innerHTML='<tr><th>When</th><th>Symbol</th><th>Price</th></tr>'+al.map(x=>`<tr><td>${x.triggered_at}</td><td>${x.symbol}</td><td>${x.price}</td></tr>`).join('');
 const mon=await (await fetch('/api/monitor'+q)).json();
 m.innerHTML='<tr><th>Symbol</th><th>Last</th><th>Change</th></tr>'+mon.map(x=>`<tr><td>${x.symbol}</td><td>${x.close}</td><td>${(x.change*100).toFixed(2)}%</td></tr>`).join('');}
load();
"""


class Rule(BaseModel):
    user_id: str = Field(default="demo", min_length=1, max_length=64)
    symbol: str
    direction: str = Field(pattern="^(above|below)$")
    threshold: float = Field(gt=0)


def create_app(**kwargs):
    holder = {}

    def on_event(envelope: Envelope):
        if envelope.type == MARKET_DATA_UPDATED:
            holder["evaluate"](envelope.data.get("symbols"))

    app = create_service("alerts-monitor", "Alerts and Monitor", "Price alerts and a monitor for your watchlist.",
                         tags=["alerts", "monitor", "notifications", "watchlist"],
                         subscriptions=["market.data.updated"], on_event=on_event, **kwargs)
    broker = app.state.broker

    def evaluate(symbols: list[str] | None = None) -> list[dict]:
        """Check active rules against the latest close. Returns the alerts created."""
        rules = db.query(
            "SELECT r.id, r.user_id, r.symbol, r.direction, r.threshold, r.last_state, "
            "(SELECT close FROM prices p WHERE p.symbol = r.symbol ORDER BY date DESC LIMIT 1) AS last "
            "FROM alert_rules r WHERE r.active AND (%s::text[] IS NULL OR r.symbol = ANY(%s))", (symbols, symbols))
        created = []
        for r in rules:
            if r["last"] is None:
                continue
            price, threshold = float(r["last"]), float(r["threshold"])
            met = price > threshold if r["direction"] == "above" else price < threshold
            state = "triggered" if met else "clear"
            if state == r["last_state"]:
                continue
            db.execute("UPDATE alert_rules SET last_state=%s WHERE id=%s", (state, r["id"]))
            if met:
                db.execute("INSERT INTO alerts (rule_id, symbol, price) VALUES (%s,%s,%s)", (r["id"], r["symbol"], price))
                alert = {"rule_id": r["id"], "user_id": r["user_id"], "symbol": r["symbol"], "price": price,
                         "direction": r["direction"], "threshold": threshold}
                created.append(alert)
                broker.publish(ALERT_TRIGGERED, alert, "alerts-monitor")
        return created

    holder["evaluate"] = evaluate
    app.state.evaluate = evaluate

    @app.get("/", include_in_schema=False)
    def page():
        return render_page("Alerts and Monitor", PAGE, SCRIPT)

    @app.post("/api/rules", status_code=201)
    def create_rule(r: Rule):
        symbol = r.symbol.upper()
        if not symbol_exists(symbol):
            raise HTTPException(404, f"unknown symbol {symbol}")
        row = db.query("INSERT INTO alert_rules (user_id, symbol, direction, threshold) VALUES (%s,%s,%s,%s) "
                       "RETURNING id", (r.user_id, symbol, r.direction, r.threshold))[0]
        return {"id": row["id"], "user_id": r.user_id, "symbol": symbol, "direction": r.direction,
                "threshold": r.threshold}

    @app.get("/api/rules")
    def list_rules(user_id: str = "demo"):
        return [{**x, "threshold": float(x["threshold"])} for x in db.query(
            "SELECT id, symbol, direction, threshold, active, last_state FROM alert_rules WHERE user_id=%s "
            "ORDER BY id", (user_id,))]

    @app.delete("/api/rules/{rule_id}", status_code=204)
    def delete_rule(rule_id: int):
        if not db.execute("DELETE FROM alert_rules WHERE id=%s", (rule_id,)):
            raise HTTPException(404, "no such rule")

    @app.get("/api/alerts")
    def alerts(user_id: str = "demo"):
        return [{"id": x["id"], "symbol": x["symbol"], "price": float(x["price"]),
                 "triggered_at": x["triggered_at"].isoformat(timespec="seconds")} for x in db.query(
            "SELECT a.id, a.symbol, a.price, a.triggered_at FROM alerts a JOIN alert_rules r ON r.id = a.rule_id "
            "WHERE r.user_id=%s ORDER BY a.triggered_at DESC LIMIT 50", (user_id,))]

    @app.post("/api/evaluate")
    def run_check():
        return {"created": evaluate()}

    @app.get("/api/monitor")
    def monitor(user_id: str = "demo"):
        out = []
        for w in db.query("SELECT symbol FROM watchlist WHERE user_id=%s ORDER BY symbol", (user_id,)):
            rows = db.query("SELECT close FROM prices WHERE symbol=%s ORDER BY date DESC LIMIT 2", (w["symbol"],))
            if rows:
                last = float(rows[0]["close"])
                prev = float(rows[1]["close"]) if len(rows) > 1 else last
                out.append({"symbol": w["symbol"], "close": last, "change": last / prev - 1 if prev else 0.0})
        return out

    return app


app = create_app()
