"""Guards for the installable-PWA contract.

Every one of these assertions corresponds to something that was actually broken:
the manifest shipped with no icons array at all, the repository contained no
raster image of any size, and the service worker was served from /static/ so its
scope could never include an application page. Lighthouse dropped its PWA
category, so nothing else checks this.
"""

import json
import os

os.environ["TESTING"] = "true"

import pytest

from app import create_app
from app.database import db


def _make(csrf=False):
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = csrf
    # Rendering any page runs the shell context processors, which query
    # reference tables; an empty schema is enough for them.
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    return app, app.test_client(), ctx


@pytest.fixture
def client():
    app, test_client, ctx = _make()
    yield test_client
    db.session.remove()
    db.drop_all()
    ctx.pop()


def test_manifest_is_served_from_the_origin_root_with_installable_icons(client):
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/manifest+json")
    manifest = json.loads(response.data)

    assert manifest["scope"] == "/"
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"

    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert "192x192" in sizes, "Android requires a 192px icon to offer install"
    assert "512x512" in sizes, "Android requires a 512px icon to offer install"
    purposes = {p for icon in manifest["icons"] for p in icon.get("purpose", "any").split()}
    assert "maskable" in purposes, "without a maskable icon Android letterboxes the icon"

    # The manifest colours must match the blueprint ground, not the dark theme
    # they were left on after the redesign.
    assert manifest["theme_color"] == "#f2f2f3"
    assert manifest["background_color"] == "#f2f2f3"

    # Every referenced icon must actually exist and be a real PNG.
    for icon in manifest["icons"]:
        asset = client.get(icon["src"])
        assert asset.status_code == 200, icon["src"]
        assert asset.data[:8] == b"\x89PNG\r\n\x1a\n", f"{icon['src']} is not a PNG"


def test_service_worker_is_served_from_root_so_its_scope_covers_the_app(client):
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/javascript")
    body = response.data.decode()
    # A cached authenticated page would outlive a logout.
    assert "/api/" not in body.split("fetch(request)")[0] or "navigate" in body
    assert "'/offline'" in body or '"/offline"' in body


def test_shell_endpoints_do_not_require_a_session(client):
    """An installed app fetches these before any login has happened."""
    for path in ("/manifest.webmanifest", "/sw.js", "/favicon.ico", "/offline"):
        assert client.get(path).status_code == 200, path


def test_login_page_declares_the_install_metadata(client):
    html = client.get("/login").data.decode()
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert 'rel="apple-touch-icon"' in html, "iOS falls back to a screenshot without this"
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html
    assert "viewport-fit=cover" in html, "safe-area insets are 0 without this"


def test_login_form_carries_a_server_rendered_csrf_token():
    """The token used to be injected by JavaScript only, so a blocked or failed
    app.js made signing in impossible."""
    app, test_client, ctx = _make(csrf=True)
    try:
        html = test_client.get("/login").data.decode()
        assert 'name="csrf_token"' in html
    finally:
        db.session.remove(); db.drop_all(); ctx.pop()


def test_chart_library_is_not_shipped_to_pages_without_a_chart(client):
    """206 KB, render-blocking, previously on every page including login."""
    assert "chart.umd.min.js" not in client.get("/login").data.decode()
