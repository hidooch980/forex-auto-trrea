"""SQLite-backed persistent risk reservations and equity circuit breakers.

Risk values are percentage points of equity (0.10 means 0.10%).
This module records risk state; it never places or modifies broker orders.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path


class RiskStateError(RuntimeError):
    """Invalid state transition or unsafe ledger state."""


class RiskLimitError(RiskStateError):
    """A new reservation would exceed a configured risk limit."""


@dataclass(frozen=True)
class RiskLimits:
    max_total_risk_pct: float = 0.10
    max_engine_risk_pct: float = 0.025
    max_active_per_engine: int = 1
    max_daily_loss_pct: float = 1.0
    max_peak_drawdown_pct: float = 5.0


@dataclass(frozen=True)
class RiskSnapshot:
    active_risk_pct: float
    active_reservations: int
    active_by_engine: dict[str, int]
    daily_loss_pct: float
    peak_drawdown_pct: float
    daily_lock: bool
    drawdown_lock: bool
    updated_at: int | None

    @property
    def locked(self) -> bool:
        return self.daily_lock or self.drawdown_lock


class PersistentRiskLedger:
    """A single-account SQLite ledger with atomic reservation checks."""

    ACTIVE = ("PENDING", "OPEN")

    def __init__(self, db_path: str | Path, limits: RiskLimits = RiskLimits()):
        self.db_path = str(db_path)
        if self.db_path == ":memory:":
            raise ValueError("use a persistent SQLite file; in-memory state is not restart-safe")
        self.limits = limits
        self._validate_limits()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id TEXT PRIMARY KEY,
                    engine TEXT NOT NULL,
                    risk_pct REAL NOT NULL CHECK(risk_pct > 0),
                    status TEXT NOT NULL CHECK(status IN ('PENDING','OPEN','CLOSED','CANCELLED')),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reservations_status
                    ON reservations(status);
                CREATE TABLE IF NOT EXISTS equity_marks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    marked_at INTEGER NOT NULL,
                    utc_day TEXT NOT NULL,
                    equity REAL NOT NULL CHECK(equity > 0),
                    daily_start_equity REAL NOT NULL CHECK(daily_start_equity > 0),
                    high_water_equity REAL NOT NULL CHECK(high_water_equity > 0)
                );
                CREATE INDEX IF NOT EXISTS idx_equity_marks_time
                    ON equity_marks(marked_at DESC, id DESC);
                CREATE TABLE IF NOT EXISTS risk_locks (
                    lock_name TEXT PRIMARY KEY,
                    active INTEGER NOT NULL CHECK(active IN (0,1)),
                    reason TEXT NOT NULL,
                    changed_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS risk_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
            """)

    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def _validate_limits(self):
        vals = (self.limits.max_total_risk_pct, self.limits.max_engine_risk_pct,
                self.limits.max_daily_loss_pct, self.limits.max_peak_drawdown_pct)
        if not all(isinstance(v, (int, float)) and isfinite(float(v)) and v > 0 for v in vals):
            raise ValueError("risk limits must be finite positive numbers")
        if not isinstance(self.limits.max_active_per_engine, int) or self.limits.max_active_per_engine < 1:
            raise ValueError("max_active_per_engine must be a positive integer")
        if self.limits.max_engine_risk_pct > self.limits.max_total_risk_pct:
            raise ValueError("per-engine risk limit cannot exceed total risk limit")

    @staticmethod
    def _now(value: int | None) -> int:
        stamp = int(time.time()) if value is None else value
        if not isinstance(stamp, int) or isinstance(stamp, bool) or stamp < 0:
            raise ValueError("timestamp must be a non-negative integer")
        return stamp

    @staticmethod
    def _audit(db, event: str, reference: str, details: str, now: int):
        db.execute("INSERT INTO risk_audit(event,reference,details,created_at) VALUES(?,?,?,?)",
                   (event, reference, details, now))

    def reserve(self, reservation_id: str, engine: str, risk_pct: float,
                *, status: str = "PENDING", now: int | None = None) -> RiskSnapshot:
        """Atomically reserve risk before submitting an order to an execution adapter."""
        stamp = self._now(now)
        if not reservation_id or not engine:
            raise ValueError("reservation_id and engine are required")
        if not isinstance(risk_pct, (int, float)) or not isfinite(float(risk_pct)) or risk_pct <= 0:
            raise ValueError("risk_pct must be finite and positive")
        if risk_pct > self.limits.max_engine_risk_pct:
            raise RiskLimitError("engine_risk_limit")
        if status not in self.ACTIVE:
            raise ValueError("new reservations must be PENDING or OPEN")

        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            locks = {r["lock_name"] for r in db.execute(
                "SELECT lock_name FROM risk_locks WHERE active=1")}
            if "drawdown" in locks or "daily" in locks:
                raise RiskLimitError("persistent_risk_lock")
            existing = db.execute(
                "SELECT 1 FROM reservations WHERE reservation_id=?", (reservation_id,)).fetchone()
            if existing:
                raise RiskStateError("duplicate_reservation_id")
            rows = db.execute(
                "SELECT engine, risk_pct FROM reservations WHERE status IN ('PENDING','OPEN')"
            ).fetchall()
            total = sum(float(r["risk_pct"]) for r in rows)
            engine_count = sum(1 for r in rows if r["engine"] == engine)
            if total + float(risk_pct) > self.limits.max_total_risk_pct + 1e-12:
                raise RiskLimitError("total_risk_limit")
            if engine_count >= self.limits.max_active_per_engine:
                raise RiskLimitError("engine_position_limit")
            db.execute(
                "INSERT INTO reservations VALUES(?,?,?,?,?,?)",
                (reservation_id, engine, float(risk_pct), status, stamp, stamp))
            self._audit(db, "RESERVE", reservation_id,
                        f"engine={engine};risk_pct={risk_pct};status={status}", stamp)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return self.snapshot(now=stamp)

    def transition(self, reservation_id: str, new_status: str,
                   *, now: int | None = None) -> RiskSnapshot:
        stamp = self._now(now)
        allowed = {"PENDING": {"OPEN", "CANCELLED", "CLOSED"},
                   "OPEN": {"CLOSED"}}
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM reservations WHERE reservation_id=?",
                             (reservation_id,)).fetchone()
            if row is None:
                raise RiskStateError("reservation_not_found")
            old = row["status"]
            if new_status not in allowed.get(old, set()):
                raise RiskStateError(f"invalid_transition:{old}->{new_status}")
            db.execute("UPDATE reservations SET status=?,updated_at=? WHERE reservation_id=?",
                       (new_status, stamp, reservation_id))
            self._audit(db, "TRANSITION", reservation_id, f"{old}->{new_status}", stamp)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return self.snapshot(now=stamp)

    def record_equity(self, equity: float, *, now: int | None = None) -> RiskSnapshot:
        """Persist equity, daily baseline and high-water mark; activate circuit breakers."""
        stamp = self._now(now)
        if not isinstance(equity, (int, float)) or not isfinite(float(equity)) or equity <= 0:
            raise ValueError("equity must be finite and positive")
        day = datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT * FROM equity_marks ORDER BY marked_at DESC,id DESC LIMIT 1"
            ).fetchone()
            if previous and stamp < previous["marked_at"]:
                raise RiskStateError("equity_timestamp_regression")
            new_utc_day = bool(previous and previous["utc_day"] != day)
            daily_start = (float(previous["daily_start_equity"])
                           if previous and not new_utc_day else float(equity))
            high_water = max(float(previous["high_water_equity"]), float(equity)) if previous else float(equity)
            if new_utc_day:
                db.execute("UPDATE risk_locks SET active=0,reason='automatic UTC day rollover',changed_at=? "
                           "WHERE lock_name='daily' AND active=1", (stamp,))
                self._audit(db, "DAILY_LOCK_RESET", day, "new UTC trading day", stamp)
            daily_loss = max(0.0, (daily_start - float(equity)) / daily_start * 100)
            drawdown = max(0.0, (high_water - float(equity)) / high_water * 100)
            db.execute(
                "INSERT INTO equity_marks(marked_at,utc_day,equity,daily_start_equity,high_water_equity) VALUES(?,?,?,?,?)",
                (stamp, day, float(equity), daily_start, high_water))
            if daily_loss >= self.limits.max_daily_loss_pct:
                db.execute("INSERT INTO risk_locks VALUES('daily',1,?,?) "
                           "ON CONFLICT(lock_name) DO UPDATE SET active=1,reason=excluded.reason,changed_at=excluded.changed_at",
                           (f"daily_loss_pct={daily_loss:.6f}", stamp))
            if drawdown >= self.limits.max_peak_drawdown_pct:
                db.execute("INSERT INTO risk_locks VALUES('drawdown',1,?,?) "
                           "ON CONFLICT(lock_name) DO UPDATE SET active=1,reason=excluded.reason,changed_at=excluded.changed_at",
                           (f"peak_drawdown_pct={drawdown:.6f}", stamp))
            self._audit(db, "EQUITY_MARK", day,
                        f"equity={equity};daily_loss_pct={daily_loss:.6f};drawdown_pct={drawdown:.6f}", stamp)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return self.snapshot(now=stamp)

    def unlock(self, lock_name: str, reason: str, *, now: int | None = None) -> RiskSnapshot:
        """Explicit operator override; the reason is retained in the audit trail."""
        if lock_name not in {"daily", "drawdown"} or not reason.strip():
            raise ValueError("valid lock_name and non-empty reason are required")
        stamp = self._now(now)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT active FROM risk_locks WHERE lock_name=?", (lock_name,)).fetchone()
            if row and row["active"]:
                db.execute("UPDATE risk_locks SET active=0,reason=?,changed_at=? WHERE lock_name=?",
                           (reason.strip(), stamp, lock_name))
                self._audit(db, "UNLOCK", lock_name, reason.strip(), stamp)
            db.commit()
        return self.snapshot(now=stamp)

    def snapshot(self, *, now: int | None = None) -> RiskSnapshot:
        stamp = self._now(now)
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT engine,risk_pct FROM reservations WHERE status IN ('PENDING','OPEN')"
            ).fetchall()
            mark = db.execute("SELECT * FROM equity_marks ORDER BY marked_at DESC,id DESC LIMIT 1").fetchone()
            locks = {r["lock_name"]: bool(r["active"]) for r in db.execute(
                "SELECT lock_name,active FROM risk_locks")}
        active_by_engine: dict[str, int] = {}
        for row in rows:
            active_by_engine[row["engine"]] = active_by_engine.get(row["engine"], 0) + 1
        daily_loss = drawdown = 0.0
        updated_at = None
        if mark:
            daily_loss = max(0.0, (mark["daily_start_equity"] - mark["equity"])
                             / mark["daily_start_equity"] * 100)
            drawdown = max(0.0, (mark["high_water_equity"] - mark["equity"])
                           / mark["high_water_equity"] * 100)
            updated_at = int(mark["marked_at"])
        return RiskSnapshot(
            active_risk_pct=sum(float(r["risk_pct"]) for r in rows),
            active_reservations=len(rows),
            active_by_engine=active_by_engine,
            daily_loss_pct=daily_loss,
            peak_drawdown_pct=drawdown,
            daily_lock=locks.get("daily", False),
            drawdown_lock=locks.get("drawdown", False),
            updated_at=updated_at,
        )
