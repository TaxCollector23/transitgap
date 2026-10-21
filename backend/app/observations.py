"""Parameterized PostgreSQL production storage and local SQLite adapter.

Reports are immutable claims until authenticated review. Routing reads only
active reviewed effects with explicit edge association and an expiry date.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import uuid
from typing import Any
from .data_loader import data_dir


def database_path() -> Path:
    if configured := os.getenv("TRANSITGAP_OBSERVATIONS_DB"):
        return Path(configured)
    if os.getenv("VERCEL") or os.getenv("RENDER"):
        return Path("/tmp/transitgap/observations.sqlite3")
    return data_dir()/"observations.sqlite3"

class _Connection:
    def __init__(self, connection, postgres):
        self.connection, self.postgres = connection, postgres
    def execute(self, query, params=()):
        return self.connection.execute(query.replace("?", "%s") if self.postgres else query, params)

@contextmanager
def _connect(path=None):
    postgres = bool(os.getenv("DATABASE_URL")) and path is None
    if postgres:
        import psycopg
        from psycopg.rows import dict_row
        connection = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, connect_timeout=8)
    else:
        target=path or database_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        connection=sqlite3.connect(str(target),timeout=10)
        connection.row_factory=sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield _Connection(connection, postgres)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_observations(path=None):
    with _connect(path) as connection:
        if connection.postgres:
            connection.execute("SELECT pg_advisory_xact_lock(85439121)")
        sql=(Path(__file__).parent/"migrations/001_observations.sql").read_text()
        for statement in sql.split(";"):
            if statement.strip():connection.execute(statement)
        if connection.postgres:
            columns={r["column_name"] for r in connection.execute("SELECT column_name FROM information_schema.columns WHERE table_name='observations' AND table_schema=current_schema()").fetchall()}
        else:
            columns={r["name"] for r in connection.execute("PRAGMA table_info(observations)").fetchall()}
        for name, declaration in {"source":"TEXT NOT NULL DEFAULT 'community'", "edge_reference":"TEXT", "routing_effect":"TEXT NOT NULL DEFAULT 'none'", "effective_until":"TEXT", "affected_profiles":"TEXT NOT NULL DEFAULT '[]'"}.items():
            if name not in columns:connection.execute(f"ALTER TABLE observations ADD COLUMN {name} {declaration}")
        if connection.postgres:
            review_columns={r["column_name"] for r in connection.execute("SELECT column_name FROM information_schema.columns WHERE table_name='observation_reviews' AND table_schema=current_schema()").fetchall()}
        else:
            review_columns={r["name"] for r in connection.execute("PRAGMA table_info(observation_reviews)").fetchall()}
        if "affected_profiles" not in review_columns:connection.execute("ALTER TABLE observation_reviews ADD COLUMN affected_profiles TEXT NOT NULL DEFAULT '[]'")
        connection.execute("UPDATE observations SET review_status='UNVERIFIED' WHERE review_status='UNREVIEWED'")
        connection.execute("INSERT INTO observation_schema_migrations(version,applied_at) VALUES (?,?) ON CONFLICT(version) DO NOTHING",("001",datetime.now(timezone.utc).isoformat()))


def create_observation(*,latitude,longitude,category,description,related_feature_id=None,path=None,now=None):
    timestamp=(now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    identity=str(uuid.uuid4())
    with _connect(path) as c:
        c.execute("""INSERT INTO observations(id,latitude,longitude,category,description,created_at,updated_at,evidence_status,review_status,related_feature_id,source)
         VALUES (?,?,?,?,?,?,?,'COMMUNITY_REPORTED','UNVERIFIED',?,'community')""",(identity,latitude,longitude,category,description,timestamp,timestamp,related_feature_id))
        return dict(c.execute("SELECT * FROM observations WHERE id=?",(identity,)).fetchone())


def list_observations(*,west=None,south=None,east=None,north=None,limit=100,offset=0,path=None,include_inactive=False):
    clauses=[]; params=[]
    if None not in (west,south,east,north):
        clauses.extend(("longitude>=?","longitude<=?","latitude>=?","latitude<=?"));params.extend((west,east,south,north))
    if not include_inactive:clauses.append("review_status NOT IN ('REJECTED','OUTDATED')")
    where=" WHERE "+" AND ".join(clauses) if clauses else ""
    with _connect(path) as c:
        total=c.execute("SELECT COUNT(*) AS total FROM observations"+where,params).fetchone()["total"]
        rows=c.execute("SELECT * FROM observations"+where+" ORDER BY created_at DESC,id ASC LIMIT ? OFFSET ?",(*params,limit,offset)).fetchall()
    return {"count":total,"limit":limit,"offset":offset,"observations":[dict(r) for r in rows],"evidence_status_note":"Community observations are claims. Unverified observations do not change routes; only explicitly reviewed, edge-linked, unexpired effects can influence routing."}


def observation_detail(identity,path=None):
    with _connect(path) as c:
        row=c.execute("SELECT * FROM observations WHERE id=?",(identity,)).fetchone()
        if row is None:raise LookupError("Report not found")
        history=c.execute("SELECT * FROM observation_reviews WHERE observation_id=? ORDER BY created_at,id",(identity,)).fetchall()
    return {**dict(row),"review_history":[dict(r) for r in history]}


def review_observation(identity,*,status,reviewer,reason,edge_reference=None,routing_effect="none",effective_until=None,affected_profiles=None,path=None):
    timestamp=datetime.now(timezone.utc).isoformat()
    with _connect(path) as c:
        row=c.execute("SELECT * FROM observations WHERE id=?"+(" FOR UPDATE" if c.postgres else ""),(identity,)).fetchone()
        if row is None:raise LookupError("Report not found")
        c.execute("INSERT INTO observation_reviews(id,observation_id,previous_status,status,reviewer,reason,created_at,edge_reference,routing_effect,effective_until,affected_profiles) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(str(uuid.uuid4()),identity,row["review_status"],status,reviewer,reason,timestamp,edge_reference,routing_effect,effective_until,json.dumps(affected_profiles or [])))
        c.execute("UPDATE observations SET review_status=?,updated_at=?,edge_reference=?,routing_effect=?,effective_until=?,affected_profiles=? WHERE id=?",(status,timestamp,edge_reference,routing_effect,effective_until,json.dumps(affected_profiles or []),identity))
    return observation_detail(identity,path)


def active_routing_effects(path=None):
    now=datetime.now(timezone.utc).isoformat()
    with _connect(path) as c:
        rows=c.execute("SELECT id,edge_reference,routing_effect,effective_until,affected_profiles FROM observations WHERE review_status='REVIEWED' AND routing_effect!='none' AND edge_reference IS NOT NULL AND effective_until>?",(now,)).fetchall()
    effects={}
    for row in rows:
        item=dict(row); item["affected_profiles"]=json.loads(item["affected_profiles"])
        previous=effects.get(item["edge_reference"])
        effects[item["edge_reference"]] = {"reports":previous.get("reports",[previous])+[item]} if previous else item
    return effects


def database_durability():
    if os.getenv("DATABASE_URL"):return "postgresql"
    if os.getenv("VERCEL") or os.getenv("RENDER"):return "instance-local"
    return "filesystem-persistent"
