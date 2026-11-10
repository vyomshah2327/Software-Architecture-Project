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
<div class='card'><div class='controls'>
 <div><label>User</label><input id='u' value='demo' style='width:100px' onchange='load()'></div>
 <div><label>Symbol</label><input id='s' value='AAPL' size='7'></div>
 <div><label>Alert me when price is</label><select id='d'><option>above</option><option>below</option></select></div>
 <div><label>Price</label><input id='th' type='number' value='200' step='0.01' style='width:110px'></div>
 <button onclick='add()'>Create alert</button><button class='ghost' onclick='check()'>Check now</button></div><p class='err' id='e'></p></div>
<div class='stats' id='stats'></div>
<div class='card'><h3>Alert rules</h3><table><thead><tr><th>Symbol</th><th>Condition</th><th>Status</th><th></th></tr></thead><tbody id='r'></tbody></table></div>
<div class='card'><h3>Alerts that fired</h3><div id='a'></div></div>
<div class='card'><h3>Watchlist monitor</h3><table><thead><tr><th>Symbol</th><th class='num'>Last</th><th class='num'>Day change</th></tr></thead><tbody id='m'></tbody></table></div>
"""
SCRIPT = """
const U=()=>$('#u').value.trim()||'demo';
async function add(){const r=await fetch('/api/rules',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({user_id:U(),symbol:$('#s').value,direction:$('#d').value,threshold:+$('#th').value})});
 setError(r.ok?'':'Check the symbol and price');load()}
async function check(){await fetch('/api/evaluate',{method:'POST'});load()}
async function del(id){await fetch('/api/rules/'+id,{method:'DELETE'});load()}
const badge=s=>s==='triggered'?'<span class="badge red">Triggered</span>':s==='clear'?'<span class="badge green">Watching</span>':'<span class="badge grey">Not checked yet</span>';
async function load(){const q='?user_id='+U(),rules=await (await fetch('/api/rules'+q)).json(),al=await (await fetch('/api/alerts'+q)).json(),mon=await (await fetch('/api/monitor'+q)).json();
 $('#stats').innerHTML=stat('Active rules',rules.length)+stat('Triggered now',rules.filter(x=>x.last_state==='triggered').length,'',rules.some(x=>x.last_state==='triggered')?'bad':'')+stat('Alerts fired',al.length,'most recent 50');
 $('#r').innerHTML=rules.length?rules.map(x=>`<tr><td><b>${x.symbol}</b></td><td>price ${x.direction} ${fmt(x.threshold)}</td><td>${badge(x.last_state)}</td><td class="num"><button class="ghost" onclick="del(${x.id})">Delete</button></td></tr>`).join(''):'<tr><td colspan="4" class="empty">No rules yet. Create one above.</td></tr>';
 $('#a').innerHTML=al.length?al.map(x=>`<div style="display:flex;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line)"><span class="badge red">ALERT</span><b>${x.symbol}</b> at ${fmt(x.price)}<span class="muted" style="margin-left:auto">${x.triggered_at.replace('T',' ')}</span></div>`).join(''):'<div class="empty">Nothing has fired yet.</div>';
 $('#m').innerHTML=mon.length?mon.map(x=>`<tr><td><b>${x.symbol}</b></td><td class="num">${fmt(x.close)}</td><td class="num ${tone(x.change)}">${signed(x.change)}</td></tr>`).join(''):'<tr><td colspan="3" class="empty">Add symbols to your watchlist in the Portfolio tool.</td></tr>'}
load();setInterval(load,10000);
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
        return render_page("Alerts and Monitor", PAGE, SCRIPT, "Price alerts and a watchlist monitor")

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
