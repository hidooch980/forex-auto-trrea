"""Broker name autocomplete and user-maintained exact server directory.

The built-in list is a discovery index, not a claim that every broker or
server is covered. Exact demo/live server names are user-confirmed because
brokers change server labels and may assign region-specific endpoints.
No passwords, investor passwords, API keys or account credentials are stored.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("BROKER_DIRECTORY_DB", "data/broker_directory.sqlite3"))

# Broker-name discovery catalog only. Exact server names are never fabricated.
BROKERS: tuple[dict[str, Any], ...] = (
    {"name": "Exness", "aliases": ["Exness Group"]},
    {"name": "IC Markets", "aliases": ["International Capital Markets"]},
    {"name": "Pepperstone", "aliases": []},
    {"name": "XM", "aliases": ["XM Global"]},
    {"name": "FXTM", "aliases": ["ForexTime"]},
    {"name": "HFM", "aliases": ["HotForex"]},
    {"name": "Tickmill", "aliases": []},
    {"name": "FP Markets", "aliases": ["First Prudential Markets"]},
    {"name": "Admirals", "aliases": ["Admiral Markets"]},
    {"name": "AvaTrade", "aliases": []},
    {"name": "RoboForex", "aliases": []},
    {"name": "FBS", "aliases": []},
    {"name": "Octa", "aliases": ["OctaFX"]},
    {"name": "Vantage", "aliases": ["Vantage Markets"]},
    {"name": "Fusion Markets", "aliases": []},
    {"name": "Eightcap", "aliases": []},
    {"name": "BlackBull Markets", "aliases": ["BlackBull"]},
    {"name": "Axi", "aliases": ["AxiTrader"]},
    {"name": "FOREX.com", "aliases": []},
    {"name": "OANDA", "aliases": []},
    {"name": "FxPro", "aliases": []},
    {"name": "Darwinex", "aliases": []},
    {"name": "ThinkMarkets", "aliases": []},
    {"name": "Swissquote", "aliases": []},
    {"name": "Dukascopy", "aliases": []},
    {"name": "LiteFinance", "aliases": ["LiteForex"]},
    {"name": "JustMarkets", "aliases": ["JustForex"]},
    {"name": "Deriv", "aliases": []},
    {"name": "VT Markets", "aliases": []},
    {"name": "PU Prime", "aliases": []},
    {"name": "Moneta Markets", "aliases": []},
    {"name": "Blueberry Markets", "aliases": []},
    {"name": "Capital.com", "aliases": []},
    {"name": "CMC Markets", "aliases": []},
    {"name": "IG", "aliases": ["IG Markets"]},
    {"name": "Saxo", "aliases": ["Saxo Bank"]},
    {"name": "Interactive Brokers", "aliases": ["IBKR"]},
    {"name": "FTMO", "aliases": []},
)

def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS broker_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            broker_name TEXT NOT NULL COLLATE NOCASE,
            platform TEXT NOT NULL,
            environment TEXT NOT NULL,
            server_name TEXT NOT NULL COLLATE NOCASE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, broker_name, platform, environment, server_name)
        )
    """)
    con.commit()
    return con

def search_brokers(user_id: int, query: str = "", limit: int = 30) -> list[dict[str, Any]]:
    q = str(query or "").strip().casefold()
    found: dict[str, dict[str, Any]] = {}
    for broker in BROKERS:
        names = [broker["name"], *broker["aliases"]]
        if not q or any(q in name.casefold() for name in names):
            found[broker["name"].casefold()] = {"name": broker["name"], "source": "catalog"}
    with _connect() as con:
        rows = con.execute(
            "SELECT DISTINCT broker_name FROM broker_servers WHERE user_id=? ORDER BY broker_name",
            (user_id,),
        ).fetchall()
    for row in rows:
        name = row["broker_name"]
        if not q or q in name.casefold():
            found.setdefault(name.casefold(), {"name": name, "source": "saved"})
    return sorted(found.values(), key=lambda item: item["name"].casefold())[:max(1, min(int(limit), 50))]

def list_servers(user_id: int, broker_name: str, platform: str = "mt5", environment: str | None = None) -> list[dict[str, Any]]:
    broker = str(broker_name or "").strip()
    if not broker:
        return []
    if platform not in {"mt4", "mt5"}:
        raise ValueError("Only MT4 and MT5 server directories are supported.")
    if environment is not None and environment not in {"demo", "live"}:
        raise ValueError("Environment must be demo or live.")
    sql = "SELECT id, broker_name, platform, environment, server_name FROM broker_servers WHERE user_id=? AND broker_name=? COLLATE NOCASE AND platform=?"
    args: list[Any] = [user_id, broker, platform]
    if environment:
        sql += " AND environment=?"
        args.append(environment)
    sql += " ORDER BY environment, server_name"
    with _connect() as con:
        return [dict(row) for row in con.execute(sql, args).fetchall()]

def save_server(user_id: int, broker_name: str, platform: str, environment: str, server_name: str) -> dict[str, Any]:
    broker = str(broker_name or "").strip()
    server = str(server_name or "").strip()
    if not broker or len(broker) > 100:
        raise ValueError("Broker name is required and must be at most 100 characters.")
    if platform not in {"mt4", "mt5"}:
        raise ValueError("Only MT4 and MT5 server directories are supported.")
    if environment not in {"demo", "live"}:
        raise ValueError("Environment must be demo or live.")
    if not server or len(server) > 160:
        raise ValueError("Exact server name is required and must be at most 160 characters.")
    with _connect() as con:
        con.execute(
            """INSERT OR IGNORE INTO broker_servers
            (user_id, broker_name, platform, environment, server_name)
            VALUES (?, ?, ?, ?, ?)""",
            (user_id, broker, platform, environment, server),
        )
        row = con.execute(
            """SELECT id, broker_name, platform, environment, server_name
            FROM broker_servers WHERE user_id=? AND broker_name=? COLLATE NOCASE
            AND platform=? AND environment=? AND server_name=? COLLATE NOCASE""",
            (user_id, broker, platform, environment, server),
        ).fetchone()
    return dict(row)
