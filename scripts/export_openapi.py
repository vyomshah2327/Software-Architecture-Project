"""Write each service's OpenAPI description to docs/openapi/<name>.json (run from the repo root)."""
import importlib
import json
import pathlib

MODULES = ["price_history", "performance", "volatility_risk", "indicators",
           "fund_builder", "portfolio", "correlation_svc", "alerts_monitor"]
out = pathlib.Path(__file__).parent.parent / "docs" / "openapi"
out.mkdir(parents=True, exist_ok=True)
for m in MODULES:
    app = importlib.import_module(f"{m}.main").app
    (out / f"{app.state.name}.json").write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print("wrote", app.state.name)
