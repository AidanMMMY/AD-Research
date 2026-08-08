"""SPA fallback 测试（功能可用性审计 2026-08-08）。

此前 uvicorn 直接服务时深层路由（/login、/dashboard 等）直达/刷新返回
404 —— 生产靠 nginx try_files 兜底，后端直连端口会断。修复后：
  - 非 API 深层路径 404 → 回退 index.html（前端 router 渲染）；
  - API 路径 404 仍返回 JSON；
  - 带扩展名的静态资源 404 仍返回 404。
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.skipif(
    not (__import__("pathlib").Path(__file__).parents[2] / "web" / "dist" / "index.html").exists(),
    reason="web/dist 未构建，跳过 SPA 测试",
)
class TestSpaFallback:
    def test_deep_route_returns_index_html(self):
        r = client.get("/login")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert '<div id="root">' in r.text

    def test_arbitrary_spa_path_returns_index_html(self):
        r = client.get("/some/deep/route/123")
        assert r.status_code == 200
        assert '<div id="root">' in r.text

    def test_api_404_stays_json(self):
        r = client.get("/api/v1/definitely-not-an-endpoint")
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/json")
        assert "detail" in r.json()

    def test_health_still_json(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] in ("ok", "degraded")

    def test_missing_asset_returns_404(self):
        r = client.get("/assets/definitely-missing-12345.js")
        assert r.status_code == 404
