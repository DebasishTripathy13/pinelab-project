from datetime import datetime, timezone
from typing import Dict, List

def build_features(tx: dict, history: List[dict]) -> dict:
    """Build feature dict from transaction and history for ML scoring."""
    now = datetime.now(timezone.utc)
    amount = float(tx.get("amount", 0))

    # Time features
    hour_of_day = now.hour
    day_of_week = now.weekday()

    # Velocity
    tx_last_hour = 0
    tx_last_24h = 0
    for h in history:
        try:
            h_time = datetime.fromisoformat(str(h.get("created_at", "")))
            diff = (now - h_time).total_seconds()
            if diff < 3600:
                tx_last_hour += 1
            if diff < 86400:
                tx_last_24h += 1
        except (ValueError, TypeError):
            pass

    # Amount stats
    amounts = [float(h.get("amount", 0)) for h in history if h.get("amount")]
    weekly_avg = sum(amounts[-7:]) / max(len(amounts[-7:]), 1) if amounts else amount
    overall_avg = sum(amounts) / max(len(amounts), 1) if amounts else amount
    amount_vs_weekly_avg = amount / weekly_avg if weekly_avg > 0 else 1.0

    # Merchant
    merchant = tx.get("merchant", "").lower()
    merchant_seen = any(h.get("merchant", "").lower() == merchant for h in history)

    # Time since last
    seconds_since_last = 3600
    if history:
        try:
            last_time = datetime.fromisoformat(str(history[0].get("created_at", "")))
            seconds_since_last = (now - last_time).total_seconds()
        except (ValueError, TypeError):
            pass

    return {
        "amount": amount,
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
        "transactions_last_hour": tx_last_hour,
        "transactions_last_24h": tx_last_24h,
        "amount_vs_weekly_avg": amount_vs_weekly_avg,
        "merchant_seen_before": merchant_seen,
        "seconds_since_last_tx": seconds_since_last,
        "weekly_avg": weekly_avg,
        "overall_avg": overall_avg
    }
