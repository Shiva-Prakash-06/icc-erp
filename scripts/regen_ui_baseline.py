"""Regenerate tests/ui_contract/baseline.json's url_map route_count/sha256
after a route change. Run: python scripts/regen_ui_baseline.py
"""
import hashlib
import json
from pathlib import Path

from app import create_app

app = create_app()
rows = []
for rule in app.url_map.iter_rules():
    methods = sorted(set(rule.methods) - {"HEAD", "OPTIONS"})
    rows.append([rule.endpoint, rule.rule, methods])
rows.sort()
payload = json.dumps(rows, ensure_ascii=True, separators=(",", ":"))
digest = hashlib.sha256(payload.encode()).hexdigest()

path = Path(__file__).resolve().parents[1] / "tests" / "ui_contract" / "baseline.json"
data = json.loads(path.read_text())
data["url_map"]["route_count"] = len(rows)
data["url_map"]["sha256"] = digest
path.write_text(json.dumps(data, indent=2) + "\n")
print(f"route_count={len(rows)} sha256={digest}")
