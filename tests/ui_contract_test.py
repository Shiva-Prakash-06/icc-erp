"""Regression gates for the presentation-only Aurora migration."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

from app import create_app


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"
UI_OUTPUT = ROOT / "app" / "static" / "ui"
BASELINE = Path(__file__).with_name("ui_contract") / "baseline.json"
ICONS_CSS = ROOT / "app" / "static" / "css" / "icons.css"


def _template_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in TEMPLATES.rglob("*.html"))


def test_every_template_icon_class_has_a_mask_mapping():
    """G-05: an unmapped `ph-*` class renders as a solid square placeholder.

    Every icon class referenced by any template must have a corresponding
    `--oia-icon` mapping in icons.css (kept in sync by
    scripts/build-icon-assets.mjs).
    """
    mapped = set(re.findall(r"\.(ph-[a-z0-9-]+)\s*\{", ICONS_CSS.read_text(encoding="utf-8")))
    used = set()
    for path in TEMPLATES.rglob("*.html"):
        source = path.read_text(encoding="utf-8")
        for class_attr in re.findall(r'class="([^"]*)"', source):
            classes = class_attr.split()
            if "ph" in classes:
                used.update(cls for cls in classes if cls.startswith("ph-"))

    unmapped = sorted(used - mapped)
    assert not unmapped, f"Unmapped icon classes render as solid squares: {unmapped}"


def test_every_jinja_template_compiles():
    app = create_app()
    with app.app_context():
        for template_name in app.jinja_env.list_templates():
            app.jinja_env.get_template(template_name)


def test_flask_route_contract_matches_frozen_baseline():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    app = create_app()
    rows = []
    for rule in app.url_map.iter_rules():
        methods = sorted(set(rule.methods) - {"HEAD", "OPTIONS"})
        rows.append([rule.endpoint, rule.rule, methods])
    rows.sort()

    payload = json.dumps(rows, ensure_ascii=True, separators=(",", ":"))
    assert len(rows) == baseline["url_map"]["route_count"]
    assert hashlib.sha256(payload.encode()).hexdigest() == baseline["url_map"]["sha256"]


def test_frozen_form_names_remain_in_server_templates():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    source = _template_source()
    for form in baseline["forms"].values():
        for name in form["names"]:
            assert re.search(rf'name=["\']{re.escape(name)}["\']', source), name


def test_legacy_presentation_contract_is_absent():
    source = _template_source()
    banned_fragments = (
        "data-bs-",
        "card-control",
        "form-input-oia",
        "form-label-oia",
        "form-group-oia",
        "btn-oia",
        "table-oia",
        "badge-oia",
        "tabs-control",
        "tab-link",
        "bootstrap-icons",
        "vendor/bootstrap",
    )
    for fragment in banned_fragments:
        assert fragment not in source

    assert not re.search(r"\sstyle\s*=", source, re.IGNORECASE)
    assert not re.search(r"\son(?:click|change|submit)\s*=", source, re.IGNORECASE)
    assert not re.search(r'class="[^"]*(?:^|\s)bi(?:\s|-)"', source)


def test_motion_islands_stay_inside_budget():
    manifest = json.loads((UI_OUTPUT / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["frontend/src/entries/aurora.tsx"]
    command = manifest["frontend/src/islands/command-palette.ts"]

    entry_size = len(gzip.compress((UI_OUTPUT / entry["file"]).read_bytes()))
    command_size = len(gzip.compress((UI_OUTPUT / command["file"]).read_bytes()))

    assert entry_size <= 45 * 1024
    assert command_size <= 35 * 1024
