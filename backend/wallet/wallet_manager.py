import logging
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from ..database import get_db_connection

logger = logging.getLogger("sentinelpay.wallet")

class WalletManager:
    def get_wallet(self, wallet_id: str):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM agent_wallets WHERE id = ?", (wallet_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Wallet not found")
        return dict(row)

    def get_wallet_by_user(self, user_id: str):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM agent_wallets WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return dict(row)

    def check_funds(self, wallet_id: str, amount: float):
        wallet = self.get_wallet(wallet_id)
        if wallet["is_frozen"]:
            raise HTTPException(status_code=403, detail="Wallet is frozen")
        if wallet["balance"] < amount:
            raise HTTPException(status_code=400, detail="Insufficient funds")
        if amount > wallet["spend_limit"]:
            raise HTTPException(status_code=400, detail=f"Amount exceeds transaction limit of {wallet['spend_limit']}")
        weekly_spent = wallet.get("current_weekly_spend") or 0
        if weekly_spent + amount > wallet["weekly_limit"]:
            raise HTTPException(status_code=400, detail=f"Amount exceeds weekly limit of {wallet['weekly_limit']}")
        return True

    def deduct_funds(self, wallet_id: str, amount: float):
        self.check_funds(wallet_id, amount)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE agent_wallets
            SET balance = balance - ?,
                current_weekly_spend = COALESCE(current_weekly_spend, 0) + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (amount, amount, wallet_id))
        conn.commit()
        conn.close()
        logger.info(f"Deducted {amount} from wallet {wallet_id}")

    def topup(self, wallet_id: str, amount: float):
        wallet = self.get_wallet(wallet_id)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE agent_wallets
            SET balance = balance + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (amount, wallet_id))
        conn.commit()
        conn.close()
        new_balance = wallet["balance"] + amount
        logger.info(f"Topped up wallet {wallet_id} by {amount}. New balance: {new_balance}")
        return new_balance

    def freeze_wallet(self, wallet_id: str, reason: str = "security_trigger"):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE agent_wallets
            SET is_frozen = 1, frozen_reason = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (reason, wallet_id))
        conn.commit()
        conn.close()
        logger.warning(f"Wallet {wallet_id} frozen: {reason}")

    def unfreeze_wallet(self, wallet_id: str):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE agent_wallets
            SET is_frozen = 0, frozen_reason = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (wallet_id,))
        conn.commit()
        conn.close()
        logger.info(f"Wallet {wallet_id} unfrozen")

    def get_weekly_spend(self, wallet_id: str) -> float:
        wallet = self.get_wallet(wallet_id)
        return wallet.get("current_weekly_spend") or 0.0

    def get_weekly_remaining(self, wallet_id: str) -> float:
        wallet = self.get_wallet(wallet_id)
        spent = wallet.get("current_weekly_spend") or 0.0
        return wallet["weekly_limit"] - spent

    def reset_weekly_spend(self, wallet_id: str):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE agent_wallets SET current_weekly_spend = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?
        """, (wallet_id,))
        conn.commit()
        conn.close()

    def get_transaction_history(self, wallet_id: str, limit: int = 50) -> list:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM transactions
            WHERE wallet_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (wallet_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def record_transaction(self, tx_data: dict):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (id, wallet_id, amount, merchant, merchant_domain, description,
                                     category, status, risk_score, risk_reasons, merchant_score,
                                     behavior_score, policy_score, pine_order_id, triggered_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_data["id"], tx_data["wallet_id"], tx_data["amount"],
            tx_data.get("merchant"), tx_data.get("merchant_domain"),
            tx_data.get("description"), tx_data.get("category"),
            tx_data.get("status", "pending"), tx_data.get("risk_score"),
            json.dumps(tx_data.get("risk_reasons", [])),
            tx_data.get("merchant_score"), tx_data.get("behavior_score"),
            tx_data.get("policy_score"), tx_data.get("pine_order_id"),
            tx_data.get("triggered_by")
        ))
        conn.commit()
        conn.close()

    def update_transaction_status(self, tx_id: str, status: str, pine_order_id: str = None):
        conn = get_db_connection()
        cursor = conn.cursor()
        if pine_order_id:
            cursor.execute("UPDATE transactions SET status = ?, pine_order_id = ? WHERE id = ?",
                          (status, pine_order_id, tx_id))
        else:
            cursor.execute("UPDATE transactions SET status = ? WHERE id = ?", (status, tx_id))
        conn.commit()
        conn.close()
