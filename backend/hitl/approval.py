import os
import logging
import asyncio
import uuid
import json
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger("sentinelpay.hitl")

class ApprovalManager:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.pending_approvals: Dict[str, dict] = {}
        self.timeout_seconds = 300  # 5 minutes
        self._bot = None

    def _get_bot(self):
        if not self._bot and self.bot_token:
            try:
                from telegram import Bot
                self._bot = Bot(token=self.bot_token)
            except Exception as e:
                logger.error(f"Failed to create Telegram bot: {e}")
        return self._bot

    async def request_approval(self, payment_context: Dict, transaction_id: str = "") -> dict:
        approval_id = str(uuid.uuid4())

        self.pending_approvals[approval_id] = {
            "context": payment_context,
            "transaction_id": transaction_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        message = (
            "⚠️ SentinelPay — Payment Review Required\n\n"
            f"Agent: {payment_context.get('triggered_by', 'Unknown')}\n"
            f"Merchant: {payment_context.get('merchant', 'Unknown')}\n"
            f"Domain: {payment_context.get('merchant_domain', 'N/A')}\n"
            f"Amount: ₹{payment_context.get('amount', 0)}\n"
            f"Description: {payment_context.get('description', 'N/A')}\n\n"
            f"Risk Score: {payment_context.get('risk_score', 'N/A')}\n"
            f"Reasons: {', '.join(payment_context.get('reasons', ['N/A']))}\n\n"
            f"Approval ID: {approval_id}\n"
            f"Auto-kill in 5 minutes if no response.\n\n"
            f"Reply with:\n"
            f"/approve {approval_id}\n"
            f"/kill {approval_id}"
        )

        # Try sending via Telegram
        await self._send_telegram(message)

        logger.info(f"Approval request {approval_id} created for tx {transaction_id}")

        return {
            "approval_id": approval_id,
            "status": "pending",
            "message": message
        }

    async def _send_telegram(self, message: str):
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram not configured, approval logged only")
            return False

        try:
            import httpx
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                })
                if response.status_code == 200:
                    logger.info("Telegram notification sent")
                    return True
                else:
                    logger.error(f"Telegram send failed: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

    async def send_alert(self, message: str):
        """Send a generic alert message to Telegram."""
        await self._send_telegram(message)

    def resolve_approval(self, approval_id: str, action: str, resolved_by: str = "user") -> bool:
        if approval_id in self.pending_approvals:
            self.pending_approvals[approval_id]["status"] = action
            self.pending_approvals[approval_id]["resolved_at"] = datetime.now(timezone.utc).isoformat()
            self.pending_approvals[approval_id]["resolved_by"] = resolved_by
            logger.info(f"Approval {approval_id} resolved: {action} by {resolved_by}")
            return True
        return False

    def get_approval_status(self, approval_id: str) -> Optional[dict]:
        return self.pending_approvals.get(approval_id)

    async def wait_for_approval(self, approval_id: str, timeout: int = None) -> str:
        """Wait for approval with timeout. Returns 'approved', 'killed', or 'timeout'."""
        timeout = timeout or self.timeout_seconds
        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < timeout:
            status = self.pending_approvals.get(approval_id, {}).get("status", "pending")
            if status in ("approved", "killed"):
                return status
            await asyncio.sleep(1)

        # Timeout - auto kill
        self.pending_approvals[approval_id]["status"] = "timeout_killed"
        logger.warning(f"Approval {approval_id} timed out after {timeout}s - auto-killed")
        return "timeout"

    def get_pending_count(self) -> int:
        return sum(1 for a in self.pending_approvals.values() if a["status"] == "pending")
