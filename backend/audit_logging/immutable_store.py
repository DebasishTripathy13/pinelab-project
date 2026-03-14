import os
import json
import logging
import sqlite3

logger = logging.getLogger("sentinelpay.logging.immutable")

IMMUTABLE_DB_PATH = os.getenv("IMMUTABLE_DB_PATH", "immutable_audit.db")

def _get_connection():
    conn = sqlite3.connect(IMMUTABLE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_immutable_store():
    conn = _get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            hash TEXT NOT NULL UNIQUE
        )
    """)

    # Triggers block UPDATE and DELETE
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS block_update
        BEFORE UPDATE ON audit_log
        BEGIN SELECT RAISE(ABORT, 'audit log is immutable'); END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS block_delete
        BEFORE DELETE ON audit_log
        BEGIN SELECT RAISE(ABORT, 'audit log is immutable'); END
    """)

    conn.commit()
    conn.close()
    logger.info(f"Immutable store initialized at {IMMUTABLE_DB_PATH}")

async def write_log(entry: dict):
    conn = _get_connection()
    try:
        conn.execute("""
            INSERT INTO audit_log (timestamp, event_type, payload, prev_hash, hash)
            VALUES (?, ?, ?, ?, ?)
        """, (
            entry["timestamp"],
            entry["event_type"],
            json.dumps(entry["payload"]),
            entry["previous_hash"],
            entry["hash"]
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Immutable store write failed: {e}")
        raise
    finally:
        conn.close()

async def load_all() -> list:
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, event_type, payload, prev_hash, hash FROM audit_log ORDER BY seq ASC")
    rows = cursor.fetchall()
    conn.close()

    return [{
        "timestamp": r["timestamp"],
        "event_type": r["event_type"],
        "payload": json.loads(r["payload"]),
        "previous_hash": r["prev_hash"],
        "hash": r["hash"]
    } for r in rows]
