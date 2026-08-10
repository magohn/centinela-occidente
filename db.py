"""
CENTINELA OCCIDENTE — Capa de Persistencia SQLite
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id    TEXT,
            actor        TEXT NOT NULL,
            categoria    TEXT,
            platform     TEXT NOT NULL,
            text         TEXT,
            url          TEXT,
            likes        INTEGER DEFAULT 0,
            comments     INTEGER DEFAULT 0,
            shares       INTEGER DEFAULT 0,
            collected_at TEXT NOT NULL,
            notified     INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id    TEXT,
            actor        TEXT NOT NULL,
            categoria    TEXT,
            title        TEXT,
            text         TEXT,
            url          TEXT,
            published_at TEXT,
            collected_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id      INTEGER,
            actor        TEXT,
            platform     TEXT,
            keyword      TEXT,
            text         TEXT,
            url          TEXT,
            level        TEXT DEFAULT 'ALTO',
            created_at   TEXT NOT NULL,
            notified     INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def post_exists(source_id: str) -> bool:
    if not source_id:
        return False
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM posts WHERE source_id=?", (source_id,)).fetchone()
    conn.close()
    return row is not None


def save_post(source_id, actor, categoria, platform, text, url, likes=0, comments=0, shares=0):
    if source_id and post_exists(source_id):
        return False
    conn = get_conn()
    conn.execute("""
        INSERT INTO posts (source_id, actor, categoria, platform, text, url, likes, comments, shares, collected_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (source_id, actor, categoria, platform, text, url, likes, comments, shares,
          datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return True


def news_exists(source_id: str) -> bool:
    if not source_id:
        return False
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM news WHERE source_id=?", (source_id,)).fetchone()
    conn.close()
    return row is not None


def save_news(source_id, actor, categoria, title, text, url, published_at=None):
    if source_id and news_exists(source_id):
        return False
    conn = get_conn()
    conn.execute("""
        INSERT INTO news (source_id, actor, categoria, title, text, url, published_at, collected_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (source_id, actor, categoria, title, text, url, published_at,
          datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return True


def save_alert(post_id, actor, platform, keyword, text, url, level="ALTO"):
    conn = get_conn()
    conn.execute("""
        INSERT INTO alerts (post_id, actor, platform, keyword, text, url, level, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (post_id, actor, platform, keyword, text, url, level,
          datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()


def get_pending_alerts():
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM alerts WHERE notified=0 ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_alerts_notified():
    conn = get_conn()
    conn.execute("UPDATE alerts SET notified=1 WHERE notified=0")
    conn.commit()
    conn.close()


def get_today_posts():
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM posts WHERE collected_at >= ? ORDER BY collected_at DESC
    """, (since,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_news():
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM news WHERE collected_at >= ? ORDER BY collected_at DESC
    """, (since,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
