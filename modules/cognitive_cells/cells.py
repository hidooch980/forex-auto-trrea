"""Cellular learning and measurable market-stress analysis.

Each cell is an isolated specialist memory. Outcomes update Beta evidence;
weights remain neutral until enough observations and are bounded. This is
not neural-network training and does not infer a human's private emotions.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Mapping


CELLS = ("technical", "institutional", "news", "macro", "smart_money", "strategy")


@dataclass(frozen=True)
class MarketAffect:
    state: str
    stress_score: float
    flags: tuple[str, ...]
    human_emotion_inference: bool = False


def analyze_market_affect(*, volatility_pct: float, spread_ratio: float,
                          drawdown_pct: float, consecutive_losses: int,
                          agent_disagreement: float, data_quality_score: float) -> MarketAffect:
    values = (volatility_pct, spread_ratio, drawdown_pct, agent_disagreement, data_quality_score)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(float(v)) for v in values):
        raise ValueError("market affect inputs must be finite numbers")
    if any(v < 0 for v in values) or not 0 <= agent_disagreement <= 1 or not 0 <= data_quality_score <= 1:
        raise ValueError("market affect inputs outside valid range")
    if isinstance(consecutive_losses, bool) or not isinstance(consecutive_losses, int) or consecutive_losses < 0:
        raise ValueError("consecutive_losses must be a non-negative integer")

    components = {
        "volatility": min(volatility_pct / 3.0, 1.0),
        "spread": min(spread_ratio / 3.0, 1.0),
        "drawdown": min(drawdown_pct / 5.0, 1.0),
        "loss_streak": min(consecutive_losses / 4.0, 1.0),
        "agent_disagreement": agent_disagreement,
        "data_quality": 1.0 - data_quality_score,
    }
    score = round(sum(components.values()) / len(components), 4)
    flags = tuple(name for name, value in components.items() if value >= 0.75)
    state = "extreme" if score >= 0.8 else "stressed" if score >= 0.6 else "uncertain" if score >= 0.35 else "calm"
    return MarketAffect(state, score, flags)


class CellularLearning:
    def __init__(self, database: str | Path, *, min_samples: int = 30):
        if str(database) == ":memory:":
            raise ValueError("cellular learning requires persistent storage")
        if isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 1:
            raise ValueError("min_samples must be a positive integer")
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.min_samples = min_samples
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("""CREATE TABLE IF NOT EXISTS cells(
                cell_id TEXT PRIMARY KEY,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                neutral INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0
            )""")
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def observe(self, cell_id: str, outcome: str, *, closed_at: int):
        cell = cell_id.strip().lower()
        if cell not in CELLS:
            raise ValueError("unknown learning cell")
        if outcome not in {"win", "loss", "neutral"}:
            raise ValueError("outcome must be win, loss or neutral")
        if isinstance(closed_at, bool) or not isinstance(closed_at, int) or closed_at < 0:
            raise ValueError("closed_at must be a non-negative integer")
        column = {"win": "wins", "loss": "losses", "neutral": "neutral"}[outcome]
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO cells(cell_id) VALUES(?)", (cell,))
            db.execute(f"UPDATE cells SET {column}={column}+1, updated_at=? WHERE cell_id=?", (closed_at, cell))
            db.commit()
        return self.cell(cell)

    def cell(self, cell_id: str):
        cell = cell_id.strip().lower()
        if cell not in CELLS:
            raise ValueError("unknown learning cell")
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM cells WHERE cell_id=?", (cell,)).fetchone()
        wins, losses, neutral = (row["wins"], row["losses"], row["neutral"]) if row else (0, 0, 0)
        samples = wins + losses
        # Beta(1,1) posterior mean. Neutral outcomes are excluded from win/loss evidence.
        posterior = (wins + 1) / (samples + 2)
        eligible = samples >= self.min_samples
        # Bounded reliability multiplier, neutral until minimum sample count.
        multiplier = min(1.25, max(0.75, 0.75 + posterior)) if eligible else 1.0
        return {
            "cell_id": cell, "wins": wins, "losses": losses, "neutral": neutral,
            "directional_samples": samples, "posterior_win_probability": round(posterior, 4),
            "eligible_for_shadow_weighting": eligible,
            "shadow_reliability_multiplier": round(multiplier, 4),
            "live_weight_change_authorized": False,
        }

    def snapshot(self):
        return {
            "cells": {cell: self.cell(cell) for cell in CELLS},
            "minimum_directional_samples": self.min_samples,
            "mode": "shadow_only",
            "live_weight_change_authorized": False,
        }
