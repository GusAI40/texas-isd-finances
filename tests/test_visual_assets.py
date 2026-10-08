"""Focused contracts for the public visual helper and its explicit route."""
from pathlib import Path

from fastapi.testclient import TestClient

from src.api import app

ROOT = Path(__file__).resolve().parent.parent


def test_visual_helper_exists_and_has_no_external_dependency():
    source = (ROOT / "static" / "visual-components.js").read_text(encoding="utf-8")
    assert "TxisdVisual" in source
    assert "teacherRetention" in source
    assert "renderAccessibleTable" in source
    assert "https://" not in source


def test_visual_helper_has_explicit_asset_route():
    with TestClient(app) as client:
        response = client.get("/static/visual-components.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert "teacherRetention" in response.text


def test_index_loads_helper_before_application_script():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    asset = html.index('/static/visual-components.js')
    app = html.index('function renderOneChild')
    assert asset < app
