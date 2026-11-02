"""Multi-account registry for FTMO CFD, Futures and Free Trial profiles.

This stores user-entered account metadata only. It never stores trading passwords,
API secrets, or connects to FTMO/MT5.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("FTMO_ACCOUNTS_DB", "data/ftmo_accounts.sqlite3"))

PRODUCTS = {
    "cfd_1_step": {"label": "FTMO Challenge 1-Step", "phases": ["challenge", "funded"], "account_types": ["standard", "swing"]},
    "cfd_2_step": {"label": "FTMO Challenge 2-Step", "phases": ["challenge", "verification", "funded"], "account_types": ["standard", "swing"]},
    "cfd_instant": {"label": "FTMO Instant", "phases": ["instant"], "account_types": ["standard"]},
    "futures": {"label": "FTMO Futures", "phases": ["evaluation", "sim_funded"], "account_types": ["growth", "classic"]},
    "free_trial": {"label": "FTMO Free Trial", "phases": ["trial"], "account_types": ["standard", "swing"]},
}
PLATFORMS = {"mt4", "mt5", "ctrader", "tradingview", "other"}
CURRENCIES = {"USD", "EUR", "GBP", "CHF", "CZK", "CAD", "AUD"}


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS ftmo_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        label TEXT NOT NULL,
        account_number TEXT,
        product TEXT NOT NULL,
        phase TEXT NOT NULL,
        account_type TEXT NOT NULL,
        platform TEXT NOT NULL,
        initial_capital REAL NOT NULL,
        currency TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, account_number)
    )""")
    con.commit()
    return con


def _validate(payload: dict[str, Any]) -> dict[str, Any]:
    product = str(payload.get("product", ""))
    if product not in PRODUCTS:
        raise ValueError("Unsupported FTMO product.")
    spec = PRODUCTS[product]
    phase = str(payload.get("phase", ""))
    account_type = str(payload.get("account_type", ""))
    platform = str(payload.get("platform", "mt5"))
    currency = str(payload.get("currency", "USD")).upper()
    if phase not in spec["phases"]:
        raise ValueError("The selected phase is not available for this product.")
    if account_type not in spec["account_types"]:
        raise ValueError("The selected account type is not available for this product.")
    if platform not in PLATFORMS:
        raise ValueError("Unsupported trading platform.")
    if currency not in CURRENCIES:
        raise ValueError("Unsupported account currency.")
    try:
        capital = float(payload.get("initial_capital"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Initial capital must be a positive number.") from exc
    if not 0 < capital <= 100_000_000:
        raise ValueError("Initial capital must be between 0 and 100,000,000.")
    label = str(payload.get("label", "")).strip()
    if not label or len(label) > 80:
        raise ValueError("Account label is required and must be at most 80 characters.")
    account_number = str(payload.get("account_number") or "").strip() or None
    if account_number and len(account_number) > 80:
        raise ValueError("Account number must be at most 80 characters.")
    return {
        "label": label, "account_number": account_number, "product": product,
        "phase": phase, "account_type": account_type, "platform": platform,
        "initial_capital": capital, "currency": currency,
    }


def list_accounts(user_id: int) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            "SELECT * FROM ftmo_accounts WHERE user_id=? ORDER BY active DESC, id DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_account(user_id: int, payload: dict[str, Any]) -> dict:
    item = _validate(payload)
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO ftmo_accounts
            (user_id,label,account_number,product,phase,account_type,platform,initial_capital,currency)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (user_id, item["label"], item["account_number"], item["product"], item["phase"],
             item["account_type"], item["platform"], item["initial_capital"], item["currency"]),
        )
        row = con.execute("SELECT * FROM ftmo_accounts WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


def update_account(user_id: int, account_id: int, payload: dict[str, Any]) -> dict | None:
    item = _validate(payload)
    with _connect() as con:
        cur = con.execute(
            """UPDATE ftmo_accounts SET label=?,account_number=?,product=?,phase=?,account_type=?,
            platform=?,initial_capital=?,currency=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND user_id=?""",
            (item["label"], item["account_number"], item["product"], item["phase"],
             item["account_type"], item["platform"], item["initial_capital"], item["currency"],
             account_id, user_id),
        )
        if not cur.rowcount:
            return None
        row = con.execute("SELECT * FROM ftmo_accounts WHERE id=? AND user_id=?", (account_id, user_id)).fetchone()
    return dict(row)


def set_account_active(user_id: int, account_id: int, active: bool) -> bool:
    with _connect() as con:
        cur = con.execute(
            "UPDATE ftmo_accounts SET active=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
            (1 if active else 0, account_id, user_id),
        )
    return bool(cur.rowcount)
