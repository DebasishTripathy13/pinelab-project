import logging
import json
from typing import List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("sentinelpay.security.policy")

@dataclass
class PolicyResult:
    score: float = 0.0
    violations: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

class PolicyEngine:
    async def check(self, tx: dict, wallet: dict) -> PolicyResult:
        result = PolicyResult()
        amount = float(tx.get("amount", 0))

        # 1. Balance check
        if wallet.get("balance", 0) < amount:
            result.violations.append("insufficient_balance")
            result.reasons.append(f"Insufficient balance: need {amount}, have {wallet['balance']}")

        # 2. Single transaction limit
        spend_limit = wallet.get("spend_limit", 500)
        if amount > spend_limit:
            result.violations.append("exceeds_single_limit")
            result.reasons.append(f"Exceeds single transaction limit of {spend_limit}")

        # 3. Weekly spend check
        weekly_spent = wallet.get("current_weekly_spend", 0) or 0
        weekly_limit = wallet.get("weekly_limit", 2000)
        if weekly_spent + amount > weekly_limit:
            result.violations.append("exceeds_weekly_limit")
            result.reasons.append(f"Would exceed weekly limit: spent {weekly_spent} + {amount} > {weekly_limit}")

        # 4. Frozen check
        if wallet.get("is_frozen"):
            result.violations.append("wallet_frozen")
            result.reasons.append("Wallet is frozen")

        # 5. Category restrictions
        blocked_cats = json.loads(wallet.get("blocked_categories", "[]")) if isinstance(wallet.get("blocked_categories"), str) else wallet.get("blocked_categories", [])
        tx_category = tx.get("category", "")
        if tx_category and tx_category in blocked_cats:
            result.violations.append("blocked_category")
            result.reasons.append(f"Category '{tx_category}' is blocked")

        # 6. Time restrictions
        allowed_hours = wallet.get("allowed_hours", '{"start": 0, "end": 24}')
        if isinstance(allowed_hours, str):
            try:
                allowed_hours = json.loads(allowed_hours)
            except json.JSONDecodeError:
                allowed_hours = {"start": 0, "end": 24}

        current_hour = datetime.now().hour
        start_hour = allowed_hours.get("start", 0)
        end_hour = allowed_hours.get("end", 24)
        if not (start_hour <= current_hour < end_hour):
            result.violations.append("outside_allowed_hours")
            result.reasons.append(f"Outside allowed hours ({start_hour}:00 - {end_hour}:00)")

        # Calculate score based on violations
        result.score = min(len(result.violations) * 0.3, 1.0)

        if not result.reasons:
            result.reasons.append("All policies passed")

        return result
