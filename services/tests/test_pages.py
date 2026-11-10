"""Every page's JavaScript must at least parse. A typo there leaves a blank page that no API test would catch."""
import importlib
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from stockplatform.events import InMemoryBroker

MODULES = ["price_history", "performance", "volatility_risk", "indicators",
           "fund_builder", "portfolio", "correlation_svc", "alerts_monitor"]

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


@pytest.mark.parametrize("module", MODULES)
def test_page_scripts_parse(module, tmp_path):
    app = importlib.import_module(f"{module}.main").create_app(broker=InMemoryBroker(), registry=None)
    html = TestClient(app).get("/").text
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert len(scripts) == 2 and all(scripts)
    for i, code in enumerate(scripts):
        path = tmp_path / f"{module}_{i}.js"
        path.write_text(code)
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, f"{module} script {i}: {result.stderr[:400]}"
