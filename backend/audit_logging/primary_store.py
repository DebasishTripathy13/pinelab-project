import json
import logging
from ..database import get_db_connection

logger = logging.getLogger("sentinelpay.logging.primary")

async def write_log(entry: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO audit_log (timestamp, event_type, payload, previous_hash, hash)
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
        logger.error(f"Primary store write failed: {e}")
        raise
    finally:
        conn.close()

async def load_all() -> list:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, event_type, payload, previous_hash, hash FROM audit_log ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    entries = []
    for row in rows:
        entries.append({
            "timestamp": row["timestamp"],
            "event_type": row["event_type"],
            "payload": json.loads(row["payload"]),
            "previous_hash": row["previous_hash"],
            "hash": row["hash"]
        })
    return entries

async def get_recent(hours: int = 1) -> list:
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, event_type, payload, previous_hash, hash
        FROM audit_log WHERE timestamp > ? ORDER BY id ASC
    """, (cutoff,))
    rows = cursor.fetchall()
    conn.close()

    return [{
        "timestamp": r["timestamp"],
        "event_type": r["event_type"],
        "payload": json.loads(r["payload"]),
        "previous_hash": r["previous_hash"],
        "hash": r["hash"]
    } for r in rows]

async def get_count() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM audit_log")
    row = cursor.fetchone()
    conn.close()
    return row["cnt"]
