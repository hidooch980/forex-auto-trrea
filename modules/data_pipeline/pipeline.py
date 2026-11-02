"""Persistent, fail-closed data chain and error center for the ERP brain.

Stages are explicit and auditable. This is an orchestration primitive: upstream
connectors still have to supply real, timestamped market and agent evidence.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Mapping


STAGES = ("INGEST", "VALIDATE", "FUSE", "RISK_GATE", "COMPLETE")
TERMINAL = {"COMPLETE", "REJECTED", "FAILED", "QUARANTINED"}
RETRYABLE = {"upstream_timeout", "upstream_unavailable", "rate_limited"}
MAX_ATTEMPTS = 3


class PipelineError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class PersistentPipeline:
    def __init__(self, database: str | Path):
        self.database = Path(database)
        if str(database) == ":memory:":
            raise ValueError("pipeline requires a persistent SQLite file")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def _init_db(self):
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    input_json TEXT NOT NULL,
                    output_json TEXT,
                    error_json TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pipeline_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    level TEXT NOT NULL,
                    code TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES pipeline_runs(run_id)
                );
            """)
            db.commit()

    def _event(self, db, run_id, stage, level, code, detail, now):
        db.execute(
            "INSERT INTO pipeline_events(run_id,stage,level,code,detail,created_at) VALUES(?,?,?,?,?,?)",
            (run_id, stage, level, code, detail[:1000], now),
        )

    def create(self, payload: Mapping[str, Any], idempotency_key: str | None = None, now: int | None = None):
        timestamp = int(time.time()) if now is None else now
        if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
            raise ValueError("timestamp must be a non-negative integer")
        if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
            raise ValueError("invalid idempotency key")
        run_id = str(uuid.uuid4())
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                existing = db.execute(
                    "SELECT run_id FROM pipeline_runs WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if existing:
                    db.commit()
                    return existing["run_id"], False
            db.execute(
                """INSERT INTO pipeline_runs
                (run_id,idempotency_key,status,stage,attempt,input_json,created_at,updated_at)
                VALUES(?,?, 'RUNNING','INGEST',1,?,?,?)""",
                (run_id, idempotency_key, encoded, timestamp, timestamp),
            )
            self._event(db, run_id, "INGEST", "INFO", "pipeline_started", "Input accepted", timestamp)
            db.commit()
        return run_id, True

    def stage(self, run_id: str, stage: str, code: str, detail: str, *, now: int | None = None):
        timestamp = int(time.time()) if now is None else now
        if stage not in STAGES:
            raise ValueError("unknown pipeline stage")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM pipeline_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            if row["status"] != "RUNNING":
                raise PipelineError("run_not_active", "Pipeline run is not active")
            db.execute("UPDATE pipeline_runs SET stage=?,updated_at=? WHERE run_id=?", (stage, timestamp, run_id))
            self._event(db, run_id, stage, "INFO", code, detail, timestamp)
            db.commit()

    def finish(self, run_id: str, output: Mapping[str, Any], *, now: int | None = None):
        timestamp = int(time.time()) if now is None else now
        encoded = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE pipeline_runs SET status='COMPLETE',stage='COMPLETE',output_json=?,updated_at=? WHERE run_id=? AND status='RUNNING'",
                (encoded, timestamp, run_id),
            )
            if db.total_changes == 0:
                raise PipelineError("run_not_active", "Pipeline run is not active")
            self._event(db, run_id, "COMPLETE", "INFO", "pipeline_completed", "Decision chain completed", timestamp)
            db.commit()

    def fail(self, run_id: str, code: str, message: str, *, retryable: bool = False, now: int | None = None):
        timestamp = int(time.time()) if now is None else now
        status = "QUARANTINED" if code in {"invalid_evidence", "schema_violation", "unsafe_input"} else "FAILED"
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE pipeline_runs SET status=?,error_json=?,updated_at=? WHERE run_id=? AND status='RUNNING'",
                (status, json.dumps({"code": code, "message": message[:1000], "retryable": retryable}),
                 timestamp, run_id),
            )
            if db.total_changes == 0:
                raise PipelineError("run_not_active", "Pipeline run is not active")
            self._event(db, run_id, "ERROR", "ERROR", code, message, timestamp)
            db.commit()

    def retry(self, run_id: str, *, now: int | None = None):
        timestamp = int(time.time()) if now is None else now
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM pipeline_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            error = json.loads(row["error_json"] or "{}")
            if row["status"] != "FAILED" or not error.get("retryable") or error.get("code") not in RETRYABLE:
                raise PipelineError("retry_not_allowed", "Only transient upstream failures can be retried")
            if row["attempt"] >= MAX_ATTEMPTS:
                raise PipelineError("retry_limit_reached", "Maximum retry attempts reached")
            db.execute(
                "UPDATE pipeline_runs SET status='RUNNING',stage='INGEST',attempt=attempt+1,error_json=NULL,output_json=NULL,updated_at=? WHERE run_id=?",
                (timestamp, run_id),
            )
            self._event(db, run_id, "INGEST", "WARN", "pipeline_retry", f"Attempt {row['attempt']+1}", timestamp)
            db.commit()
            return json.loads(row["input_json"]), row["attempt"] + 1

    def get(self, run_id: str):
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM pipeline_runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            for key in ("input_json", "output_json", "error_json"):
                result[key.removesuffix("_json")] = json.loads(result.pop(key)) if result.get(key) else None
            result["events"] = [dict(x) for x in db.execute(
                "SELECT stage,level,code,detail,created_at FROM pipeline_events WHERE run_id=? ORDER BY event_id",
                (run_id,),
            ).fetchall()]
            return result

    def health(self):
        with closing(self._connect()) as db:
            rows = db.execute("SELECT status,COUNT(*) count FROM pipeline_runs GROUP BY status").fetchall()
            return {"counts": {row["status"]: row["count"] for row in rows},
                    "retryable_errors": sum(1 for row in db.execute(
                        "SELECT error_json FROM pipeline_runs WHERE status='FAILED'").fetchall()
                        if json.loads(row["error_json"] or "{}").get("retryable")),
                    "quarantined": db.execute("SELECT COUNT(*) FROM pipeline_runs WHERE status='QUARANTINED'").fetchone()[0]}
