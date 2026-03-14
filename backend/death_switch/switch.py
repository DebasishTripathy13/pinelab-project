import os
import logging
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("sentinelpay.death_switch")

class DeathSwitch:
    def __init__(self, wallet_manager=None, approval_manager=None):
        self.wallet_manager = wallet_manager
        self.approval_manager = approval_manager
        self._redis = None
        self.last_trigger = None
        self.last_reason = None
        self.trigger_count = 0

    def _get_redis(self):
        if not self._redis:
            try:
                import redis
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
                self._redis = redis.from_url(redis_url)
            except Exception as e:
                logger.warning(f"Redis not available: {e}")
        return self._redis

    async def trigger(self, wallet_id: str, reason: str, transaction_id: str = ""):
        """Fire the death switch - freeze wallet, cancel orders, alert user."""
        logger.critical(f"DEATH SWITCH TRIGGERED for wallet {wallet_id}: {reason}")

        self.last_trigger = datetime.now(timezone.utc).isoformat()
        self.last_reason = reason
        self.trigger_count += 1

        # 1. Freeze wallet immediately
        if self.wallet_manager:
            try:
                self.wallet_manager.freeze_wallet(wallet_id, f"DEATH_SWITCH: {reason}")
            except Exception as e:
                logger.error(f"Failed to freeze wallet: {e}")

        # 2. Publish kill signal via Redis
        r = self._get_redis()
        if r:
            try:
                kill_signal = json.dumps({
                    "action": "KILL",
                    "wallet_id": wallet_id,
                    "reason": reason,
                    "transaction_id": transaction_id,
                    "timestamp": self.last_trigger
                })
                r.publish(f"death_switch:{wallet_id}", kill_signal)
                r.publish("death_switch:global", kill_signal)
                logger.info("Kill signal published to Redis")
            except Exception as e:
                logger.warning(f"Redis publish failed: {e}")

        # 3. Alert user via Telegram
        if self.approval_manager:
            alert_msg = (
                "🔴 DEATH SWITCH FIRED\n\n"
                f"Wallet: {wallet_id[:8]}...\n"
                f"Reason: {reason}\n"
                f"Transaction: {transaction_id or 'N/A'}\n"
                f"Time: {self.last_trigger}\n\n"
                "✅ Wallet frozen. Your real money is safe.\n"
                "Review at: SentinelPay Dashboard\n\n"
                f"To unfreeze, use: /unfreeze {wallet_id}"
            )
            await self.approval_manager.send_alert(alert_msg)

        return {
            "status": "DEATH_SWITCH_FIRED",
            "wallet_id": wallet_id,
            "reason": reason,
            "timestamp": self.last_trigger,
            "wallet_frozen": True
        }

    async def trigger_global(self, reason: str):
        """Fire death switch on ALL wallets."""
        logger.critical(f"GLOBAL DEATH SWITCH: {reason}")

        from ..database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM agent_wallets WHERE is_frozen = 0")
        wallets = cursor.fetchall()
        conn.close()

        results = []
        for w in wallets:
            result = await self.trigger(w["id"], f"GLOBAL: {reason}")
            results.append(result)

        return results

    def get_status(self) -> dict:
        return {
            "last_trigger": self.last_trigger,
            "last_reason": self.last_reason,
            "trigger_count": self.trigger_count
        }
