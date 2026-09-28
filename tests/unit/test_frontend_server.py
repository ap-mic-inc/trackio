from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from trackio.frontend_server import FrontendMiddleware, _render_index_html

_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8" />
<link rel="icon" type="image/png" href="/static/trackio/trackio_logo_light.png" />
<script type="module" crossorigin src="/assets/index-abc123.js"></script>
<link rel="stylesheet" crossorigin href="/assets/index-abc123.css">
</head><body><div id="app"></div></body></html>
"""


def _write_html(tmp_path: Path) -> Path:
    path = tmp_path / "index.html"
    path.write_text(_HTML, encoding="utf-8")
    return path


def test_render_index_html_no_root_path_leaves_absolute_refs(tmp_path):
    out = _render_index_html(_write_html(tmp_path))
    assert 'src="/assets/index-abc123.js"' in out
    assert 'href="/assets/index-abc123.css"' in out
    assert 'href="/static/trackio/trackio_logo_light.png"' in out
    assert "window.__trackio_base" not in out


def test_render_index_html_with_root_path_prefixes_refs(tmp_path):
    out = _render_index_html(_write_html(tmp_path), root_path="/dashboard")
    assert 'src="/dashboard/assets/index-abc123.js"' in out
    assert 'href="/dashboard/assets/index-abc123.css"' in out
    assert 'href="/dashboard/static/trackio/trackio_logo_light.png"' in out
    assert 'window.__trackio_base = "/dashboard";' in out


def test_render_index_html_live_reload_endpoint_is_prefixed(tmp_path):
    out = _render_index_html(_write_html(tmp_path), root_path="/dashboard")
    assert '"/dashboard/__trackio/frontend_version"' in out


def test_render_index_html_live_reload_endpoint_unprefixed_by_default(tmp_path):
    out = _render_index_html(_write_html(tmp_path))
    assert '"/__trackio/frontend_version"' in out


def _client_with_middleware(tmp_path: Path) -> TestClient:
    index_html_path = _write_html(tmp_path)

    async def file_handler(request):
        return PlainTextResponse("file-endpoint")

    app = Starlette(routes=[Route("/file", file_handler, methods=["GET"])])
    app.add_middleware(
        FrontendMiddleware,
        frontend_root=tmp_path,
        index_html_path=index_html_path,
    )
    return TestClient(app)


def test_files_page_serves_spa_index(tmp_path):
    client = _client_with_middleware(tmp_path)
    response = client.get("/files?project=demo")
    assert response.status_code == 200
    assert '<div id="app">' in response.text


def test_file_endpoint_reaches_backend_route(tmp_path):
    client = _client_with_middleware(tmp_path)
    response = client.get("/file?path=media/image.png")
    assert response.status_code == 200
    assert response.text == "file-endpoint"
