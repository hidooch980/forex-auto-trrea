from backend import app as app_module


def test_status_is_safe_by_default():
    result = app_module.status()
    assert result["live_trading_enabled"] is False
    assert result["emergency_stop"] is True
    assert result["integrations"]["order_execution"] == "disabled"


def test_emergency_stop_endpoint_latches():
    result = app_module.activate_emergency_stop()
    assert result["ok"] is True
    assert app_module.status()["emergency_stop"] is True


def test_decision_preview_never_authorizes_execution():
    result = app_module.decision_preview(symbol="XAUUSD")
    assert result["execution_allowed"] is False
    assert result["guard_reason"]


def test_dashboard_contains_emergency_control():
    html = app_module.dashboard()
    assert "activateStop" in html
    assert "حالت امن" in html
