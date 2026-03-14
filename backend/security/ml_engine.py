import logging
import numpy as np
from typing import Dict, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("sentinelpay.security.ml")

@dataclass
class BehaviorResult:
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    confidence: float = 0.0

class MLEngine:
    def __init__(self):
        self.min_samples = 10

    def extract_features(self, tx: dict, history: list) -> list:
        amount = float(tx.get("amount", 0))
        now = datetime.now()
        hour = now.hour
        day_of_week = now.weekday()

        # Velocity features
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

        # Amount comparison
        if history:
            amounts = [float(h.get("amount", 0)) for h in history if h.get("amount")]
            avg_amount = np.mean(amounts) if amounts else amount
            weekly_amounts = amounts[-7:] if len(amounts) >= 7 else amounts
            weekly_avg = np.mean(weekly_amounts) if weekly_amounts else amount
            amount_vs_avg = amount / avg_amount if avg_amount > 0 else 1.0
        else:
            amount_vs_avg = 1.0
            weekly_avg = amount

        # Merchant familiarity
        merchant = tx.get("merchant", "").lower()
        merchant_seen = any(
            h.get("merchant", "").lower() == merchant for h in history
        )

        # Time since last transaction
        if history:
            try:
                last_time = datetime.fromisoformat(str(history[0].get("created_at", "")))
                seconds_since_last = (now - last_time).total_seconds()
            except (ValueError, TypeError):
                seconds_since_last = 3600
        else:
            seconds_since_last = 3600

        return [
            amount,
            float(hour),
            float(day_of_week),
            float(tx_last_hour),
            float(tx_last_24h),
            float(amount_vs_avg),
            float(merchant_seen),
            float(seconds_since_last)
        ]

    async def analyze(self, tx: dict, history: list) -> BehaviorResult:
        result = BehaviorResult()
        features = self.extract_features(tx, history)

        amount = features[0]
        hour = features[1]
        tx_last_hour = features[3]
        tx_last_24h = features[4]
        amount_vs_avg = features[5]
        merchant_seen = features[6]

        # Rule-based scoring (works from cold start)
        score = 0.0

        # Amount anomaly
        if amount_vs_avg > 5:
            score += 0.4
            result.reasons.append(f"Amount is {amount_vs_avg:.1f}x your average")
        elif amount_vs_avg > 3:
            score += 0.25
            result.reasons.append(f"Amount is {amount_vs_avg:.1f}x your average")
        elif amount_vs_avg > 2:
            score += 0.1
            result.reasons.append(f"Amount is {amount_vs_avg:.1f}x your average")

        # Velocity check
        if tx_last_hour > 5:
            score += 0.3
            result.reasons.append(f"{int(tx_last_hour)} transactions in last hour (high velocity)")
        elif tx_last_hour > 3:
            score += 0.15
            result.reasons.append(f"{int(tx_last_hour)} transactions in last hour")

        if tx_last_24h > 20:
            score += 0.2
            result.reasons.append(f"{int(tx_last_24h)} transactions in last 24h")

        # Time anomaly
        if hour >= 1 and hour <= 5:
            score += 0.2
            result.reasons.append(f"Unusual hour: {int(hour)}:00 (1am-5am)")

        # New merchant
        if not merchant_seen and len(history) > 5:
            score += 0.1
            result.reasons.append("First transaction with this merchant")

        result.score = min(score, 1.0)
        result.confidence = min(len(history) / self.min_samples, 1.0)

        if not result.reasons:
            result.reasons.append("Transaction appears normal")

        return result
