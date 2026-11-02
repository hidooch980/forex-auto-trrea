from types import SimpleNamespace
import secrets

from backend import app as app_module
from backend import auth


def make_request(token, csrf="", method="GET"):
    return SimpleNamespace(
        cookies={"forex_session": token},
        headers={"x-csrf-token": csrf},
        method=method,
    )


def make_user(role):
    user = auth.add_user("test_" + role + "_" + secrets.token_hex(4), "a-long-test-password-2026", role)
    token, csrf, _ = auth.create_session(user["id"])
    return make_request(token, csrf), csrf


def test_status_is_safe_by_default():
    request, _ = make_user("viewer")
    result = app_module.status(request)
    assert result["live_trading_enabled"] is False
    assert result["emergency_stop"] is True
    assert result["integrations"]["order_execution"] == "disabled"


def test_emergency_stop_requires_authorized_role_and_csrf():
    request, _ = make_user("trader")
    request.method = "POST"
    result = app_module.activate_emergency_stop(request)
    assert result["ok"] is True
    assert app_module.status(make_user("viewer")[0])["emergency_stop"] is True


def test_viewer_cannot_activate_emergency_stop():
    request, _ = make_user("viewer")
    request.method = "POST"
    try:
        app_module.activate_emergency_stop(request)
        assert False, "viewer must not have write permission"
    except app_module.HTTPException as exc:
        assert exc.status_code == 403


def test_decision_preview_never_authorizes_execution():
    request, _ = make_user("analyst")
    result = app_module.decision_preview(request=request, symbol="XAUUSD")
    assert result["execution_allowed"] is False
    assert result["guard_reason"]


def test_dashboard_has_login_and_user_management():
    html = app_module.dashboard()
    assert "/api/auth/login" in html
    assert "createUser" in html
    assert "حالت امن" in html


def test_news_feed_does_not_fabricate_live_news():
    request, _ = make_user("viewer")
    result = app_module.news_feed(request)
    assert result["available"] is False
    assert result["feed_status"] == "not_connected"
    assert result["articles"] == []


def test_analytics_overview_is_explicitly_unavailable_without_providers():
    request, _ = make_user("viewer")
    result = app_module.analytics_overview(request)
    assert result["available"] is False
    assert result["market_data_status"] == "not_connected"
    assert result["trade_history_status"] == "not_connected"
    assert result["fear_greed"]["score"] is None
    assert result["market_heatmap"] == []
    assert result["signal_performance"]["win_rate_pct"] is None


def test_dashboard_contains_analytics_page_and_localized_navigation():
    html = app_module.dashboard()
    assert 'id="page-performance"' in html
    assert 'id="fear-greed-score"' in html
    assert 'id="symbol-ranking"' in html
    assert "loadPerformance" in html


def test_public_site_and_pwa_manifest_are_served():
    site = app_module.public_site()
    manifest = app_module.pwa_manifest()
    assert "Forex AI" in site
    assert 'href="/manifest.webmanifest"' in site
    assert 'href="/app"' in site
    assert manifest.media_type == "application/manifest+json"
    assert '"start_url": "/app"' in manifest.body.decode()


def test_pwa_service_worker_does_not_cache_private_api_responses():
    worker = app_module.service_worker()
    source = worker.body.decode()
    assert 'url.pathname.startsWith("/api/")' in source
    assert '"/manifest.webmanifest"' in source
    assert '"/offline"' in source


def test_app_route_contains_installable_pwa_metadata_and_ftmo_management():
    html = app_module.dashboard()
    assert 'rel="manifest"' in html
    assert 'id="install-app"' in html
    assert 'id="page-ftmo"' in html
    assert "saveFtmoAccount" in html


def test_dashboard_has_broker_server_autocomplete():
    html = app_module.dashboard()
    assert 'id="broker-search"' in html
    assert 'id="broker-suggestions"' in html
    assert 'id="broker-environment"' in html
    assert 'id="broker-server-search"' in html
    assert "searchBrokerNames" in html
    assert "loadBrokerServers" in html


def test_broker_directory_api_search_and_user_server_suggestions(tmp_path, monkeypatch):
    from modules.broker_directory import directory
    monkeypatch.setattr(directory, "DB_PATH", tmp_path / "broker-directory.sqlite3")
    request, _ = make_user("trader")
    found = app_module.search_brokers(request, q="pepper")
    assert any(item["name"] == "Pepperstone" for item in found["brokers"])

    request.method = "POST"
    payload = app_module.BrokerServerPayload(
        broker_name="Example Broker", platform="mt5",
        environment="demo", server_name="ExampleBroker-Demo01",
    )
    saved = app_module.add_broker_server(payload, request)
    assert saved["server"]["server_name"] == "ExampleBroker-Demo01"

    request.method = "GET"
    servers = app_module.broker_servers(request, broker="Example Broker", platform="mt5", environment="demo")
    assert [item["server_name"] for item in servers["servers"]] == ["ExampleBroker-Demo01"]


def test_viewer_cannot_add_broker_server(tmp_path, monkeypatch):
    from modules.broker_directory import directory
    monkeypatch.setattr(directory, "DB_PATH", tmp_path / "broker-directory.sqlite3")
    request, _ = make_user("viewer")
    request.method = "POST"
    payload = app_module.BrokerServerPayload(
        broker_name="Example Broker", platform="mt5",
        environment="live", server_name="ExampleBroker-Live01",
    )
    try:
        app_module.add_broker_server(payload, request)
        assert False, "viewer must not be allowed to write broker servers"
    except app_module.HTTPException as exc:
        assert exc.status_code == 403

def test_portfolio_risk_preview_is_authenticated_and_never_executes():
    request, _ = make_user("trader")
    request.method = "POST"
    payload = app_module.PortfolioRiskPreviewPayload(
        equity_usd=10000,
        positions=[
            app_module.RiskPositionPayload(
                market="forex", instrument="EURUSD", side="long",
                notional_usd=1000, stop_risk_usd=50, margin_usd=100,
                liquidity_usd_1pct=50000, spread_bps=2,
            )
        ],
        proposed_order=app_module.RiskTradePayload(
            market="crypto_futures", instrument="BTCUSDT", side="short",
            notional_usd=1000, stop_risk_usd=50, margin_usd=250,
            liquidity_usd_1pct=50000, spread_bps=5,
        ),
    )
    result = app_module.portfolio_risk_preview(payload, request)
    assert result["available"] is True
    assert result["execution_allowed"] is False
    assert result["live_positions_connected"] is False
    assert result["emergency_stop"] is True
    assert "portfolio_emergency_stop" in result["reasons"]
    assert result["metrics"]["total_open_risk_pct"] == 1.0


def test_viewer_cannot_call_portfolio_risk_preview():
    request, _ = make_user("viewer")
    request.method = "POST"
    payload = app_module.PortfolioRiskPreviewPayload(
        equity_usd=10000,
        proposed_order=app_module.RiskTradePayload(
            market="crypto_spot", instrument="BTCUSDT", side="long",
            notional_usd=500, stop_risk_usd=10, margin_usd=0,
            liquidity_usd_1pct=10000, spread_bps=5,
        ),
    )
    try:
        app_module.portfolio_risk_preview(payload, request)
        assert False, "viewer must not call portfolio risk preview"
    except app_module.HTTPException as exc:
        assert exc.status_code == 403
