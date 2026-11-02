"""SQLite-backed user accounts and opaque server-side sessions.

Set ADMIN_USERNAME and ADMIN_PASSWORD before first startup to provision the first
administrator. No default credentials are created.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

ROLES = {"admin", "trader", "analyst", "viewer"}
DB_PATH = Path(os.getenv("AUTH_DB_PATH", "data/auth.sqlite3"))
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "28800"))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth() -> None:
    with _connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','trader','analyst','viewer')),
                active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                identity_hash TEXT PRIMARY KEY,
                attempts INTEGER NOT NULL,
                window_started INTEGER NOT NULL,
                blocked_until INTEGER NOT NULL DEFAULT 0
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )
        """)
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        # Bootstrap only when explicitly configured; never overwrite an existing user.
        username = os.getenv("ADMIN_USERNAME", "").strip()
        password = os.getenv("ADMIN_PASSWORD", "")
        if username and password and not db.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone():
            if len(password) < 14:
                raise RuntimeError("ADMIN_PASSWORD must contain at least 14 characters.")
            salt = secrets.token_bytes(16)
            digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
            db.execute(
                "INSERT INTO users(username,password_hash,salt,role,active,created_at) VALUES(?,?,?,?,1,?)",
                (username, digest.hex(), salt.hex(), "admin", int(time.time())),
            )


def _password_digest(password: str, salt_hex: str) -> str:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
        n=2**14, r=8, p=1
    ).hex()


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute(
            "SELECT * FROM users WHERE username = ? AND active = 1",
            (username.strip(),),
        ).fetchone()
        if not row:
            # Perform a dummy scrypt to reduce username enumeration timing.
            _password_digest(password, "00112233445566778899aabbccddeeff")
            return None
        candidate = _password_digest(password, row["salt"])
        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None
        return public_user(row)


def public_user(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"], "username": row["username"],
        "role": row["role"], "active": bool(row["active"]),
    }


def create_session(user_id: int) -> tuple[str, str, int]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    expires = int(time.time()) + SESSION_TTL_SECONDS
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as db:
        db.execute(
            "INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES(?,?,?,?)",
            (token_hash, user_id, csrf, expires),
        )
    return token, csrf, expires


def get_session(token: str | None) -> tuple[dict[str, Any], str] | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as db:
        row = db.execute("""
            SELECT u.*, s.csrf_token, s.expires_at
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at >= ? AND u.active = 1
        """, (token_hash, int(time.time()))).fetchone()
        if not row:
            return None
        return public_user(row), row["csrf_token"]


def revoke_session(token: str | None) -> None:
    if not token:
        return
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as db:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def list_users() -> list[dict[str, Any]]:
    with _connect() as db:
        rows = db.execute(
            "SELECT id,username,role,active FROM users ORDER BY id"
        ).fetchall()
        return [public_user(row) for row in rows]


def add_user(username: str, password: str, role: str) -> dict[str, Any]:
    username = username.strip()
    if not 3 <= len(username) <= 64 or not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Username must be 3-64 letters, digits, '_' or '-'.")
    if role not in ROLES or role == "admin":
        raise ValueError("New accounts may be trader, analyst or viewer. Bootstrap admin separately.")
    if len(password) < 14:
        raise ValueError("Password must contain at least 14 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    try:
        with _connect() as db:
            cur = db.execute(
                "INSERT INTO users(username,password_hash,salt,role,active,created_at) VALUES(?,?,?,?,1,?)",
                (username, digest.hex(), salt.hex(), role, int(time.time())),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError("Username already exists.") from exc
    return {"id": user_id, "username": username, "role": role, "active": True}


def set_user_active(
    user_id: int, active: bool, actor_user_id: int | None = None
) -> bool:
    """Change account status without allowing self-lockout or last-admin removal."""
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        target = db.execute(
            "SELECT id, role, active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target is None:
            return False
        if not active:
            if actor_user_id is not None and actor_user_id == user_id:
                raise ValueError("Administrators cannot deactivate their own account.")
            if target["role"] == "admin" and target["active"]:
                active_admins = db.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
                ).fetchone()[0]
                if active_admins <= 1:
                    raise ValueError("The last active administrator cannot be deactivated.")
        db.execute("UPDATE users SET active = ? WHERE id = ?", (int(active), user_id))
        if not active:
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return True


def login_is_blocked(identity: str, now: int | None = None) -> tuple[bool, int]:
    """Persistent per-identity login throttling; identity is hashed before storage."""
    now = int(time.time()) if now is None else int(now)
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    with _connect() as db:
        row = db.execute(
            "SELECT attempts, window_started, blocked_until FROM login_attempts WHERE identity_hash = ?",
            (key,),
        ).fetchone()
        if row is None:
            return False, 0
        if row["blocked_until"] > now:
            return True, row["blocked_until"] - now
        if now - row["window_started"] >= 300:
            db.execute("DELETE FROM login_attempts WHERE identity_hash = ?", (key,))
        return False, 0


def record_login_failure(identity: str, now: int | None = None) -> None:
    now = int(time.time()) if now is None else int(now)
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT attempts, window_started FROM login_attempts WHERE identity_hash = ?",
            (key,),
        ).fetchone()
        if row is None or now - row["window_started"] >= 300:
            attempts = 1
            started = now
        else:
            attempts = row["attempts"] + 1
            started = row["window_started"]
        blocked_until = now + 900 if attempts >= 8 else 0
        db.execute(
            "INSERT INTO login_attempts(identity_hash,attempts,window_started,blocked_until) "
            "VALUES(?,?,?,?) ON CONFLICT(identity_hash) DO UPDATE SET "
            "attempts=excluded.attempts, window_started=excluded.window_started, "
            "blocked_until=excluded.blocked_until",
            (key, attempts, started, blocked_until),
        )


def clear_login_failures(identity: str) -> None:
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    with _connect() as db:
        db.execute("DELETE FROM login_attempts WHERE identity_hash = ?", (key,))
