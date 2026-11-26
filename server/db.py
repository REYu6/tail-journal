"""Persistence for local SQLite or an optional PostgreSQL deployment."""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def uid(prefix):
    return prefix + "_" + uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def pack(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 260000)
    return salt + "." + value.hex()


def valid_password(password, hashed):
    return hmac.compare_digest(hashed, password_hash(password, hashed.partition(".")[0]))


class DB:
    def __init__(self, conn, postgres):
        self.conn, self.postgres = conn, postgres

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace("?", "%s") if self.postgres else sql, tuple(params))

    def one(self, sql, params=()):
        row = self.execute(sql, params).fetchone()
        return dict(row) if row is not None else None

    def all(self, sql, params=()):
        return [dict(row) for row in self.execute(sql, params).fetchall()]


@contextmanager
def database(write=False):
    url = os.getenv("DATABASE_URL", "")
    pg = url.startswith(("postgresql://", "postgres://"))
    if pg:
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=8)
    else:
        if url:
            raise RuntimeError("DATABASE_URL must be a PostgreSQL URL; unset for SQLite")
        directory = Path(os.getenv("PET_DATA_DIR", "data")).resolve()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        conn = sqlite3.connect(directory / "pet-studio.sqlite3", timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
    try:
        if write:
            if pg:
                conn.execute("SELECT pg_advisory_xact_lock(164838509)")
            else:
                conn.execute("BEGIN IMMEDIATE")
        yield DB(conn, pg)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT NOT NULL UNIQUE,name TEXT NOT NULL,role TEXT NOT NULL,passwd TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(ip TEXT NOT NULL,stamp DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS attempts_key ON attempts(ip,stamp);
CREATE TABLE IF NOT EXISTS pets(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,species TEXT NOT NULL,traits TEXT NOT NULL,story TEXT NOT NULL,occasion TEXT NOT NULL,created_at TEXT NOT NULL,archived INTEGER DEFAULT 0 NOT NULL);
CREATE TABLE IF NOT EXISTS photos(id TEXT PRIMARY KEY,pet_id TEXT NOT NULL REFERENCES pets(id),key TEXT NOT NULL,name TEXT NOT NULL,created_at TEXT NOT NULL,archived INTEGER DEFAULT 0 NOT NULL);
CREATE TABLE IF NOT EXISTS works(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,pet_id TEXT NOT NULL REFERENCES pets(id),style_id TEXT NOT NULL,title TEXT NOT NULL,status TEXT NOT NULL,photo_ids TEXT NOT NULL,revision_count INTEGER DEFAULT 0 NOT NULL,feedback TEXT NOT NULL DEFAULT '',request_key TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(user_id,request_key));
CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,work_id TEXT NOT NULL REFERENCES works(id),key TEXT NOT NULL,preview_key TEXT NOT NULL,source_key TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,pet_id TEXT NOT NULL REFERENCES pets(id),kind TEXT NOT NULL,amount INTEGER NOT NULL,candidate_id TEXT,photo_ids TEXT NOT NULL,request_key TEXT NOT NULL,payment_status TEXT NOT NULL,generation_status TEXT NOT NULL,delivery_status TEXT NOT NULL,owner_confirmed INTEGER NOT NULL DEFAULT 0,quality_checked INTEGER NOT NULL DEFAULT 0,revision_count INTEGER NOT NULL DEFAULT 0,feedback TEXT NOT NULL DEFAULT '',preview_key TEXT NOT NULL DEFAULT '',stl_key TEXT NOT NULL DEFAULT '',payment_ref TEXT NOT NULL DEFAULT '',checkout_url TEXT NOT NULL DEFAULT '',checkout_id TEXT NOT NULL DEFAULT '',refund_ref TEXT NOT NULL DEFAULT '',support TEXT NOT NULL DEFAULT '',support_reply TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,UNIQUE(user_id,request_key));
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,target_id TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,external_id TEXT NOT NULL DEFAULT '',outputs TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',stage TEXT NOT NULL DEFAULT 'submit',lease DOUBLE PRECISION NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS jobs_target ON jobs(target_id);
CREATE INDEX IF NOT EXISTS jobs_due ON jobs(status,lease);
CREATE TABLE IF NOT EXISTS processing_nodes(
    node_id TEXT PRIMARY KEY,capabilities TEXT NOT NULL,last_seen DOUBLE PRECISION NOT NULL,
    read_mbps DOUBLE PRECISION NOT NULL,write_mbps DOUBLE PRECISION NOT NULL,compute_s DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS processing_tasks(
    job_id TEXT PRIMARY KEY REFERENCES jobs(id),target_id TEXT NOT NULL REFERENCES orders(id),
    glb_key TEXT NOT NULL,stl_key TEXT NOT NULL,input_bytes BIGINT NOT NULL,status TEXT NOT NULL,
    node_id TEXT NOT NULL DEFAULT '',epoch INTEGER NOT NULL DEFAULT 0,lease DOUBLE PRECISION NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,policy TEXT NOT NULL DEFAULT '',estimate_s DOUBLE PRECISION NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',created DOUBLE PRECISION NOT NULL,started DOUBLE PRECISION,finished DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS processing_tasks_due ON processing_tasks(status,created);
CREATE TABLE IF NOT EXISTS processing_events(
    id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES processing_tasks(job_id),
    node_id TEXT NOT NULL,epoch INTEGER NOT NULL,event TEXT NOT NULL,at DOUBLE PRECISION NOT NULL,detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS processing_events_time ON processing_events(at);
CREATE TABLE IF NOT EXISTS payment_events(id TEXT PRIMARY KEY,order_id TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS samples(id TEXT PRIMARY KEY,order_id TEXT NOT NULL UNIQUE,user_id TEXT NOT NULL,specs TEXT NOT NULL,status TEXT NOT NULL,quote INTEGER,note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS channels(id TEXT PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,commission INTEGER NOT NULL,acquisition_cost INTEGER NOT NULL DEFAULT 0,labor_cost INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proof_views(user_id TEXT PRIMARY KEY REFERENCES users(id),first_seen_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settlements(id TEXT PRIMARY KEY,channel_id TEXT NOT NULL REFERENCES channels(id),amount INTEGER NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS referrals(user_id TEXT PRIMARY KEY REFERENCES users(id),channel_id TEXT NOT NULL REFERENCES channels(id));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
"""
DEFAULT_STYLES = [
    {
        "id": "watercolor",
        "name": "温柔水彩",
        "prompt": "以柔和水彩手绘宠物肖像，纸张肌理、细腻晕染，突出眼神和面部特征。",
        "active": True,
        "version": 1,
    },
    {
        "id": "cartoon",
        "name": "绘本插画",
        "prompt": "以温暖绘本插画描绘这只宠物，使用柔和配色和清晰自然的线条。",
        "active": True,
        "version": 1,
    },
    {
        "id": "clay",
        "name": "黏土手办",
        "prompt": "以手作黏土摆件风格呈现宠物全身，体积圆润、神态自然。",
        "active": True,
        "version": 1,
    },
]


def initialize():
    if not os.getenv("DATABASE_URL"):
        root = Path(os.getenv("PET_DATA_DIR", "data"))
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with sqlite3.connect(root / "pet-studio.sqlite3") as conn:
            conn.execute("pragma journal_mode=WAL")
    with database(True) as db:
        for statement in SCHEMA.split(";"):
            if statement.strip():
                db.execute(statement)
        # Additive migrations also allow users to retain data across upgrades.
        columns = {
            "orders": {
                "support_reply": "TEXT NOT NULL DEFAULT ''",
                "supplement_note": "TEXT NOT NULL DEFAULT ''",
                "payment_channel": "TEXT NOT NULL DEFAULT 'demo'",
                "checkout_creating": "INTEGER NOT NULL DEFAULT 0",
                "commission": "INTEGER NOT NULL DEFAULT 0",
            },
            "photos": {"original_key": "TEXT NOT NULL DEFAULT ''"},
            "candidates": {"source_key": "TEXT NOT NULL DEFAULT ''"},
            "jobs": {
                "provider_mode": "TEXT NOT NULL DEFAULT 'demo'",
                "request_count": "INTEGER NOT NULL DEFAULT 1",
            },
            "works": {"style_version": "INTEGER NOT NULL DEFAULT 1"},
        }
        for table, fields in columns.items():
            if db.postgres:
                existing = {
                    r["column_name"]
                    for r in db.all(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?",
                        (table,),
                    )
                }
            else:
                existing = {r["name"] for r in db.all(f"PRAGMA table_info({table})")}
            for col, spec in fields.items():
                if col not in existing:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {spec}")
        for key, val in (
            ("unit_costs", {"portrait_image_cny": 0.10, "model_usd": 1.20, "usd_cny": 7.0}),
            ("styles", DEFAULT_STYLES),
            ("prices", {"portrait": 2990, "model": 9900}),
            ("daily_limit", 6),
            ("processing_policy", "adaptive"),
            ("processing_rr_cursor", ""),
        ):
            db.execute(
                "INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO NOTHING", (key, pack(val))
            )
        email, password = (
            os.getenv("PET_ADMIN_EMAIL", "").strip().lower(),
            os.getenv("PET_ADMIN_PASSWORD", ""),
        )
        if email and password and not db.one("SELECT id FROM users WHERE email=?", (email,)):
            if len(password) < 12:
                raise RuntimeError("PET_ADMIN_PASSWORD must be at least 12 characters")
            db.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,?)",
                (uid("user"), email, "平台管理员", "admin", password_hash(password), now()),
            )


def setting(db, key):
    return json.loads(db.one("SELECT value FROM settings WHERE key=?", (key,))["value"])


def log(db, actor, action, target="", note=""):
    db.execute(
        "INSERT INTO audit VALUES(?,?,?,?,?,?)",
        (uid("log"), actor, action, target, str(note)[:1200], now()),
    )
