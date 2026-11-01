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
