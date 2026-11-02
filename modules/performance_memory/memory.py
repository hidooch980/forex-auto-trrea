"""Auditable closed-trade outcome memory and chronological walk-forward reports.

This module measures agent forecasts against subsequently closed outcomes. It
never trains on future observations and never changes live decision weights.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Iterable


class PerformanceMemory:
    def __init__(self, database: str | Path):
        if str(database) == ":memory:":
            raise ValueError("performance memory requires persistent storage")
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS trade_outcomes(
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    closed_at INTEGER NOT NULL,
                    realized_return_pct REAL NOT NULL,
                    recorded_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_forecasts(
                    trade_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    stance TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    as_of INTEGER NOT NULL,
                    PRIMARY KEY(trade_id,agent_id),
                    FOREIGN KEY(trade_id) REFERENCES trade_outcomes(trade_id)
                );
                CREATE INDEX IF NOT EXISTS idx_outcomes_closed ON trade_outcomes(closed_at);
            """)
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def record_closed_trade(self, trade_id: str, symbol: str, closed_at: int,
                            realized_return_pct: float, forecasts: Iterable[dict],
                            *, recorded_at: int | None = None):
        now = int(datetime.now(timezone.utc).timestamp()) if recorded_at is None else recorded_at
        if not trade_id.strip() or len(trade_id) > 128 or not symbol.strip():
            raise ValueError("trade_id and symbol are required")
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (closed_at, now)):
            raise ValueError("timestamps must be non-negative integers")
        if closed_at > now:
            raise ValueError("cannot record a future-closed trade")
        if isinstance(realized_return_pct, bool) or not isinstance(realized_return_pct, (int,float)) or not isfinite(float(realized_return_pct)):
            raise ValueError("realized_return_pct must be finite")
        rows = list(forecasts)
        if not rows or len(rows) > 30:
            raise ValueError("one to thirty agent forecasts are required")
        seen = set()
        normalized = []
        for row in rows:
            agent = str(row.get("agent_id", "")).strip().lower()
            stance = str(row.get("stance", "")).strip().lower()
            confidence = row.get("confidence")
            as_of = row.get("as_of")
            if not agent or agent in seen or stance not in {"bullish","bearish","neutral"}:
                raise ValueError("invalid or duplicate agent forecast")
            if isinstance(confidence, bool) or not isinstance(confidence, (int,float)) or not isfinite(float(confidence)) or not 0 <= confidence <= 1:
                raise ValueError("forecast confidence must be between zero and one")
            if isinstance(as_of, bool) or not isinstance(as_of, int) or as_of < 0 or as_of > closed_at:
                raise ValueError("forecast timestamp must precede trade close")
            seen.add(agent)
            normalized.append((trade_id, agent, stance, float(confidence), as_of))
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO trade_outcomes VALUES(?,?,?,?,?)",
                (trade_id, symbol.upper(), closed_at, float(realized_return_pct), now),
            )
            db.executemany("INSERT INTO agent_forecasts VALUES(?,?,?,?,?)", normalized)
            db.commit()
        return {"trade_id": trade_id, "forecast_count": len(normalized), "recorded": True}

    @staticmethod
    def _metrics(rows):
        if not rows:
            return {"samples": 0, "hit_rate": None, "brier_score": None, "mean_confidence": None}
        hits = []
        briers = []
        confidences = []
        for row in rows:
            outcome = 1.0 if row["realized_return_pct"] > 0 else 0.0
            predicted = {"bullish": 1.0, "bearish": 0.0, "neutral": 0.5}[row["stance"]]
            hits.append((row["stance"] == "bullish" and outcome == 1.0) or
                        (row["stance"] == "bearish" and outcome == 0.0) or
                        (row["stance"] == "neutral" and row["realized_return_pct"] == 0))
            probability = 0.5 + (predicted - 0.5) * row["confidence"]
            briers.append((probability - outcome) ** 2)
            confidences.append(row["confidence"])
        return {
            "samples": len(rows),
            "hit_rate": round(sum(hits) / len(hits), 6),
            "brier_score": round(sum(briers) / len(briers), 6),
            "mean_confidence": round(sum(confidences) / len(confidences), 6),
        }

    def report(self, *, train_fraction: float = 0.7, min_train: int = 20, min_test: int = 10):
        if not 0.5 <= train_fraction <= 0.9 or min_train < 1 or min_test < 1:
            raise ValueError("invalid walk-forward parameters")
        with closing(self._connect()) as db:
            rows = db.execute("""
                SELECT f.agent_id,f.stance,f.confidence,f.as_of,
                       o.realized_return_pct,o.closed_at,o.trade_id
                FROM agent_forecasts f JOIN trade_outcomes o USING(trade_id)
                ORDER BY o.closed_at ASC,o.trade_id ASC,f.agent_id ASC
            """).fetchall()
        by_agent = {}
        for row in rows:
            by_agent.setdefault(row["agent_id"], []).append(dict(row))
        result = {}
        for agent, samples in by_agent.items():
            split = int(len(samples) * train_fraction)
            train, test = samples[:split], samples[split:]
            eligible = len(train) >= min_train and len(test) >= min_test
            result[agent] = {
                "total_samples": len(samples),
                "train": self._metrics(train),
                "out_of_sample": self._metrics(test),
                "walk_forward_eligible": eligible,
                "weight_change_authorized": False,
            }
        return {
            "method": "chronological expanding-history holdout",
            "train_fraction": train_fraction,
            "agents": result,
            "live_weights_modified": False,
            "warning": "Observational metrics only; not proof of profitability or causal skill.",
        }
