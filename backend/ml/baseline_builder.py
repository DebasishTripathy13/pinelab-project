import logging
import json
from datetime import datetime, timezone
from ..database import get_db_connection

logger = logging.getLogger("sentinelpay.ml.baseline")

async def build_baseline(wallet_id: str) -> dict:
    """Build spending baseline from transaction history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM transactions
        WHERE wallet_id = ? AND status = 'approved'
        ORDER BY created_at DESC LIMIT 500
    """, (wallet_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not rows:
        return {
            "wallet_id": wallet_id,
            "transaction_count": 0,
            "avg_amount": 0,
            "max_amount": 0,
            "common_merchants": [],
            "typical_hours": list(range(8, 22)),
            "status": "cold_start"
        }

    amounts = [float(r["amount"]) for r in rows]
    merchants = {}
    hours = {}

    for r in rows:
        m = r.get("merchant", "unknown")
        merchants[m] = merchants.get(m, 0) + 1
        try:
            h = datetime.fromisoformat(str(r["created_at"])).hour
            hours[h] = hours.get(h, 0) + 1
        except (ValueError, TypeError):
            pass

    common_merchants = sorted(merchants.keys(), key=lambda x: merchants[x], reverse=True)[:10]
    typical_hours = sorted(hours.keys(), key=lambda x: hours[x], reverse=True)[:12]

    return {
        "wallet_id": wallet_id,
        "transaction_count": len(rows),
        "avg_amount": sum(amounts) / len(amounts),
        "max_amount": max(amounts),
        "min_amount": min(amounts),
        "std_amount": float(__import__("numpy").std(amounts)) if len(amounts) > 1 else 0,
        "common_merchants": common_merchants,
        "typical_hours": sorted(typical_hours),
        "status": "trained" if len(rows) >= 10 else "learning"
    }
