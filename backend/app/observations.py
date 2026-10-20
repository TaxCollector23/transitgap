"""Private-field, text-only community observation storage."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .data_loader import data_dir


def database_path() -> Path:
    configured = os.getenv("TRANSITGAP_OBSERVATIONS_DB")
    if configured:
        return Path(configured)
    # Vercel's function filesystem is read-only and /tmp is instance-local.
    # Production durability requires binding a persistent database path.
    if os.getenv("VERCEL"):
        return Path("/tmp/transitgap/observations.sqlite3")
    return data_dir() / "observations.sqlite3"


def _connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def initialize_observations(path: Path | None = None) -> None:
    with _connect(path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                evidence_status TEXT NOT NULL DEFAULT 'COMMUNITY_REPORTED',
                review_status TEXT NOT NULL DEFAULT 'UNREVIEWED',
                related_feature_id TEXT,
                optional_source_reference TEXT
            )
        """)
        connection.execute("CREATE INDEX IF NOT EXISTS observations_created_at_idx ON observations(created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS observations_location_idx ON observations(latitude, longitude)")


def create_observation(*, latitude: float, longitude: float, category: str, description: str | None,
                       related_feature_id: str | None = None, path: Path | None = None,
                       now: datetime | None = None) -> dict[str, Any]:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    observation_id = str(uuid.uuid4())
    # Values are bound parameters. Description stays plain text; the UI renders
    # it as a text node and never inserts it as HTML.
    with _connect(path) as connection:
        connection.execute("""
            INSERT INTO observations
                (id, latitude, longitude, category, description, created_at, updated_at,
                 evidence_status, review_status, related_feature_id, optional_source_reference)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'COMMUNITY_REPORTED', 'UNREVIEWED', ?, NULL)
        """, (observation_id, latitude, longitude, category, description, timestamp, timestamp,
              related_feature_id))
        row = connection.execute("SELECT * FROM observations WHERE id = ?", (observation_id,)).fetchone()
    return dict(row)


def list_observations(*, west: float | None = None, south: float | None = None,
                      east: float | None = None, north: float | None = None,
                      limit: int = 100, offset: int = 0, path: Path | None = None) -> dict[str, Any]:
    clauses = []
    values: list[Any] = []
    if None not in (west, south, east, north):
        clauses.extend(("longitude >= ?", "longitude <= ?", "latitude >= ?", "latitude <= ?"))
        values.extend((west, east, south, north))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(path) as connection:
        total = connection.execute("SELECT COUNT(*) FROM observations" + where, values).fetchone()[0]
        rows = connection.execute(
            "SELECT * FROM observations" + where + " ORDER BY created_at DESC, id ASC LIMIT ? OFFSET ?",
            (*values, limit, offset),
        ).fetchall()
    return {"count": total, "limit": limit, "offset": offset, "observations": [dict(row) for row in rows],
            "evidence_status_note": "Community reports are unverified claims and are never used to block routes."}


def database_durability() -> str:
    if os.getenv("VERCEL"):
        configured = os.getenv("TRANSITGAP_OBSERVATIONS_DB")
        if not configured or str(Path(configured)).startswith("/tmp/"):
            return "instance-local"
        return "configured-path-unverified"
    return "filesystem-persistent"
