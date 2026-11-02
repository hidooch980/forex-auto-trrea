from backend import auth


def test_bootstrap_admin_password_hash_and_session(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "auth.sqlite3")
    monkeypatch.setenv("ADMIN_USERNAME", "root_admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "A-very-long-admin-password-2026")
    auth.init_auth()

    admin = auth.authenticate("root_admin", "A-very-long-admin-password-2026")
    assert admin is not None
    assert admin["role"] == "admin"
    assert auth.authenticate("root_admin", "wrong-password") is None

    token, csrf, expires = auth.create_session(admin["id"])
    session = auth.get_session(token)
    assert session is not None
    assert session[0]["username"] == "root_admin"
    assert session[1] == csrf
    assert expires > 0

    auth.revoke_session(token)
    assert auth.get_session(token) is None


def test_user_deactivation_revokes_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "auth.sqlite3")
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    auth.init_auth()

    user = auth.add_user("viewer_test", "a-very-long-user-password", "viewer")
    token, _, _ = auth.create_session(user["id"])
    assert auth.get_session(token) is not None

    assert auth.set_user_active(user["id"], False)
    assert auth.get_session(token) is None



def test_admin_cannot_deactivate_self_or_last_active_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "auth.sqlite3")
    monkeypatch.setenv("ADMIN_USERNAME", "root_admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "A-very-long-admin-password-2026")
    auth.init_auth()
    admin = auth.authenticate("root_admin", "A-very-long-admin-password-2026")

    try:
        auth.set_user_active(admin["id"], False, actor_user_id=admin["id"])
        assert False, "an admin must not deactivate their own account"
    except ValueError as exc:
        assert "own account" in str(exc)

    try:
        auth.set_user_active(admin["id"], False, actor_user_id=999)
        assert False, "the last active admin must not be deactivated"
    except ValueError as exc:
        assert "last active administrator" in str(exc)

    assert auth.authenticate("root_admin", "A-very-long-admin-password-2026") is not None

def test_login_throttle_persists_and_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "auth.sqlite3")
    auth.init_auth()
    identity = "127.0.0.1|trader"
    assert auth.login_is_blocked(identity, now=1000) == (False, 0)
    for _ in range(8):
        auth.record_login_failure(identity, now=1000)
    blocked, retry = auth.login_is_blocked(identity, now=1000)
    assert blocked is True
    assert retry == 900
    assert auth.login_is_blocked(identity, now=1900) == (False, 0)


def test_successful_login_clears_throttle_state(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "auth.sqlite3")
    auth.init_auth()
    identity = "127.0.0.1|trader"
    for index in range(7):
        auth.record_login_failure(identity, now=2000 + index)
    auth.clear_login_failures(identity)
    assert auth.login_is_blocked(identity, now=2008) == (False, 0)
