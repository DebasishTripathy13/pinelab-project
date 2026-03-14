import os
import uuid
import json
import asyncio
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List

from .database import get_db_connection, init_db
from .pinelabs.client import PineLabsClient
from .wallet.wallet_manager import WalletManager
from .security.interceptor import Interceptor
from .hitl.approval import ApprovalManager
from .death_switch.switch import DeathSwitch
from .intelligence.spend_intel import SpendIntelligence
from .intelligence.ai_analyst import AIAnalyst

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinelpay")

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Init audit logging
    try:
        from .audit_logging.logger import init_logging
        await init_logging()
    except Exception as e:
        logger.warning(f"Audit logging init failed (non-fatal): {e}")
    logger.info("SentinelPay started")
    yield
    logger.info("SentinelPay shutting down")

app = FastAPI(title="SentinelPay API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Services ---
pine_client = PineLabsClient()
wallet_mgr = WalletManager()
interceptor = Interceptor()
approval_mgr = ApprovalManager()
death_switch = DeathSwitch(wallet_manager=wallet_mgr, approval_manager=approval_mgr)
spend_intel = SpendIntelligence()
ai_analyst = AIAnalyst()

AGENT_TOKEN = os.getenv("SENTINELPAY_AGENT_TOKEN", "sp_agent_demo_token_2026")

# --- Models ---
class WalletCreate(BaseModel):
    user_id: str
    initial_balance: float = 0.0
    spend_limit: float = 500.0
    weekly_limit: float = 2000.0

class WalletTopup(BaseModel):
    amount: float

class PaymentRequest(BaseModel):
    amount: float
    merchant: str
    merchant_domain: str = ""
    description: str = ""
    items: Optional[List[str]] = None
    agent_id: str = "unknown"
    category: str = ""

class ApprovalAction(BaseModel):
    approval_id: str
    action: str  # "approved" or "killed"

# --- Auth helper ---
def verify_agent_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization.replace("Bearer ", "")
    if token != AGENT_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid agent token")
    return token

# --- Root ---
@app.get("/")
def root():
    return {
        "status": "active",
        "system": "SentinelPay",
        "version": "1.0.0",
        "pine_labs": "connected" if pine_client.client_id else "not_configured"
    }

# ============ WALLET ENDPOINTS ============

@app.post("/wallets/")
def create_wallet(wallet: WalletCreate):
    wallet_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO agent_wallets (id, user_id, balance, spend_limit, weekly_limit)
           VALUES (?, ?, ?, ?, ?)""",
        (wallet_id, wallet.user_id, wallet.initial_balance,
         wallet.spend_limit, wallet.weekly_limit)
    )
    conn.commit()
    conn.close()
    return {
        "id": wallet_id,
        "user_id": wallet.user_id,
        "balance": wallet.initial_balance,
        "spend_limit": wallet.spend_limit,
        "weekly_limit": wallet.weekly_limit,
        "is_frozen": False
    }

@app.get("/wallets/{wallet_id}")
def get_wallet(wallet_id: str):
    wallet = wallet_mgr.get_wallet(wallet_id)
    return {
        "id": wallet["id"],
        "user_id": wallet["user_id"],
        "balance": wallet["balance"],
        "spend_limit": wallet["spend_limit"],
        "weekly_limit": wallet["weekly_limit"],
        "current_weekly_spend": wallet.get("current_weekly_spend", 0),
        "weekly_remaining": wallet["weekly_limit"] - (wallet.get("current_weekly_spend") or 0),
        "is_frozen": bool(wallet["is_frozen"]),
        "frozen_reason": wallet.get("frozen_reason"),
        "low_balance_threshold": wallet.get("low_balance_threshold", 200)
    }

@app.get("/wallet/balance")
def get_wallet_balance(authorization: str = Header(None)):
    # For agent use - returns first wallet
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agent_wallets LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No wallet found")
    wallet = dict(row)
    return {
        "balance": wallet["balance"],
        "spend_limit": wallet["spend_limit"],
        "weekly_remaining": wallet["weekly_limit"] - (wallet.get("current_weekly_spend") or 0),
        "is_frozen": bool(wallet["is_frozen"])
    }

@app.post("/wallet/topup/{wallet_id}")
def topup_wallet(wallet_id: str, topup: WalletTopup):
    if topup.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    new_balance = wallet_mgr.topup(wallet_id, topup.amount)
    # Log event
    _log_event_sync("WALLET_TOPUP", {
        "wallet_id": wallet_id,
        "amount": topup.amount,
        "new_balance": new_balance
    })
    return {"status": "success", "new_balance": new_balance, "topped_up": topup.amount}

@app.post("/wallet/freeze/{wallet_id}")
async def freeze_wallet(wallet_id: str):
    wallet_mgr.freeze_wallet(wallet_id, "manual_freeze")
    _log_event_sync("WALLET_FROZEN", {"wallet_id": wallet_id, "reason": "manual"})
    return {"status": "frozen", "wallet_id": wallet_id}

@app.post("/wallet/unfreeze/{wallet_id}")
def unfreeze_wallet(wallet_id: str):
    wallet_mgr.unfreeze_wallet(wallet_id)
    _log_event_sync("WALLET_UNFROZEN", {"wallet_id": wallet_id})
    return {"status": "active", "wallet_id": wallet_id}

# ============ PAYMENT ENDPOINT ============

@app.post("/payment/request")
async def process_payment(payment: PaymentRequest, background_tasks: BackgroundTasks):
    logger.info(f"Payment request: ₹{payment.amount} to {payment.merchant}")

    # Find wallet (use first available for now)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agent_wallets LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="No wallet configured")

    wallet = dict(row)
    wallet_id = wallet["id"]

    # Create transaction record
    tx_id = str(uuid.uuid4())
    history = wallet_mgr.get_transaction_history(wallet_id, limit=50)

    # Run security intercept
    intercept_result = await interceptor.intercept(
        {
            "amount": payment.amount,
            "merchant": payment.merchant,
            "merchant_domain": payment.merchant_domain,
            "description": payment.description,
            "category": payment.category,
            "triggered_by": payment.agent_id
        },
        wallet,
        history
    )

    # Log the payment request
    _log_event_sync("PAYMENT_REQUEST", {
        "tx_id": tx_id,
        "amount": payment.amount,
        "merchant": payment.merchant,
        "merchant_domain": payment.merchant_domain,
        "agent_id": payment.agent_id,
        "risk_score": intercept_result.total_score
    })

    # Record transaction
    wallet_mgr.record_transaction({
        "id": tx_id,
        "wallet_id": wallet_id,
        "amount": payment.amount,
        "merchant": payment.merchant,
        "merchant_domain": payment.merchant_domain,
        "description": payment.description,
        "category": payment.category,
        "status": "pending",
        "risk_score": intercept_result.total_score,
        "risk_reasons": intercept_result.all_reasons,
        "merchant_score": intercept_result.merchant_result.get("score", 0),
        "behavior_score": intercept_result.behavior_result.get("score", 0),
        "policy_score": intercept_result.policy_result.get("score", 0),
        "triggered_by": payment.agent_id
    })

    # Decision routing
    if intercept_result.action == "APPROVE":
        return await _execute_payment(tx_id, wallet_id, payment, intercept_result)

    elif intercept_result.action == "HUMAN_REVIEW":
        # Send for human approval
        approval = await approval_mgr.request_approval(
            {
                "amount": payment.amount,
                "merchant": payment.merchant,
                "merchant_domain": payment.merchant_domain,
                "description": payment.description,
                "triggered_by": payment.agent_id,
                "risk_score": f"{intercept_result.total_score:.2f}",
                "reasons": intercept_result.all_reasons[:5]
            },
            transaction_id=tx_id
        )
        wallet_mgr.update_transaction_status(tx_id, "pending_human")
        _log_event_sync("HITL_SENT", {
            "tx_id": tx_id,
            "approval_id": approval["approval_id"],
            "risk_score": intercept_result.total_score
        })

        return {
            "status": "PENDING_HUMAN",
            "transaction_id": tx_id,
            "approval_id": approval["approval_id"],
            "risk_score": intercept_result.total_score,
            "reasons": intercept_result.all_reasons,
            "message": "Payment requires human approval. Check Telegram."
        }

    else:  # BLOCK
        wallet_mgr.update_transaction_status(tx_id, "blocked")
        _log_event_sync("BLOCKED", {
            "tx_id": tx_id,
            "risk_score": intercept_result.total_score,
            "reasons": intercept_result.all_reasons
        })

        if intercept_result.trigger_death_switch:
            background_tasks.add_task(
                death_switch.trigger, wallet_id,
                f"High risk payment blocked (score: {intercept_result.total_score:.2f})",
                tx_id
            )

        return {
            "status": "BLOCKED",
            "transaction_id": tx_id,
            "risk_score": intercept_result.total_score,
            "reasons": intercept_result.all_reasons,
            "death_switch": intercept_result.trigger_death_switch,
            "reason": "; ".join(intercept_result.all_reasons[:3])
        }

# Legacy endpoint compatibility
@app.post("/pay")
async def pay_legacy(payment_data: dict, background_tasks: BackgroundTasks):
    payment = PaymentRequest(
        amount=payment_data.get("amount", 0),
        merchant=payment_data.get("merchant_name", ""),
        merchant_domain=payment_data.get("merchant_domain", ""),
        description=payment_data.get("description", ""),
        agent_id=payment_data.get("agent_id", "legacy"),
    )
    return await process_payment(payment, background_tasks)

async def _execute_payment(tx_id: str, wallet_id: str, payment: PaymentRequest, intercept_result):
    """Execute an approved payment through Pine Labs."""
    try:
        wallet_mgr.deduct_funds(wallet_id, payment.amount)
    except HTTPException as e:
        wallet_mgr.update_transaction_status(tx_id, "failed")
        raise e

    try:
        order = await pine_client.create_order(
            amount=payment.amount,
            merchant_data={"name": payment.merchant},
            description=payment.description,
            wallet_id=wallet_id
        )

        order_id = order.get("id") or order.get("order_id") or order.get("merchant_order_reference", tx_id)
        status = order.get("status", "CREATED")

        wallet_mgr.update_transaction_status(tx_id, "approved", pine_order_id=str(order_id))

        _log_event_sync("APPROVED", {
            "tx_id": tx_id,
            "order_id": str(order_id),
            "risk_score": intercept_result.total_score,
            "amount": payment.amount,
            "merchant": payment.merchant
        })

        # Learn from safe transaction
        try:
            from .ml.feature_engineering import build_features
            from .ml.adaptive_learner import AdaptiveAnomalyDetector
            history = wallet_mgr.get_transaction_history(wallet_id)
            features = build_features({"amount": payment.amount, "merchant": payment.merchant}, history)
            detector = AdaptiveAnomalyDetector(wallet_id)
            detector.learn(features, was_safe=True)
        except Exception as e:
            logger.warning(f"ML learning failed (non-fatal): {e}")

        return {
            "status": "APPROVED",
            "transaction_id": tx_id,
            "order_id": str(order_id),
            "order_status": status,
            "amount": payment.amount,
            "merchant": payment.merchant,
            "risk_score": intercept_result.total_score
        }
    except Exception as e:
        wallet_mgr.update_transaction_status(tx_id, "failed")
        logger.error(f"Pine Labs order failed: {e}")
        return {
            "status": "APPROVED",
            "transaction_id": tx_id,
            "order_id": "pine_labs_unavailable",
            "amount": payment.amount,
            "merchant": payment.merchant,
            "risk_score": intercept_result.total_score,
            "note": "Payment approved but Pine Labs order creation failed. Funds deducted."
        }

# ============ HITL ENDPOINTS ============

@app.post("/hitl/approve")
async def handle_approval(action: ApprovalAction, background_tasks: BackgroundTasks):
    approval = approval_mgr.get_approval_status(action.approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    if approval["status"] != "pending":
        return {"status": approval["status"], "message": "Already resolved"}

    approval_mgr.resolve_approval(action.approval_id, action.action)
    tx_id = approval.get("transaction_id", "")

    if action.action == "approved":
        _log_event_sync("HITL_APPROVED", {"approval_id": action.approval_id, "tx_id": tx_id})

        # Execute the payment
        ctx = approval.get("context", {})
        wallet_id = None
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT wallet_id FROM transactions WHERE id = ?", (tx_id,))
        row = cursor.fetchone()
        if row:
            wallet_id = row["wallet_id"]
        conn.close()

        if wallet_id:
            payment = PaymentRequest(
                amount=ctx.get("amount", 0),
                merchant=ctx.get("merchant", ""),
                merchant_domain=ctx.get("merchant_domain", ""),
                description=ctx.get("description", ""),
                agent_id=ctx.get("triggered_by", "hitl_approved")
            )
            from .security.interceptor import InterceptResult
            dummy_result = InterceptResult(action="APPROVE", total_score=0.0)
            return await _execute_payment(tx_id, wallet_id, payment, dummy_result)

        return {"status": "approved", "approval_id": action.approval_id}

    else:  # killed
        _log_event_sync("HITL_KILLED", {"approval_id": action.approval_id, "tx_id": tx_id})
        wallet_mgr.update_transaction_status(tx_id, "killed")

        # Get wallet and trigger death switch
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT wallet_id FROM transactions WHERE id = ?", (tx_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            background_tasks.add_task(
                death_switch.trigger, row["wallet_id"],
                "Human rejected payment", tx_id
            )

        return {"status": "killed", "approval_id": action.approval_id}

@app.get("/hitl/pending")
def get_pending_approvals():
    pending = {k: v for k, v in approval_mgr.pending_approvals.items() if v["status"] == "pending"}
    return {"pending": pending, "count": len(pending)}

# ============ DEATH SWITCH ============

@app.post("/death-switch/trigger/{wallet_id}")
async def trigger_death_switch(wallet_id: str, reason: str = "manual_trigger"):
    result = await death_switch.trigger(wallet_id, reason)
    return result

@app.get("/death-switch/status")
def get_death_switch_status():
    return death_switch.get_status()

# ============ TRANSACTIONS ============

@app.get("/transactions/{wallet_id}")
def get_transactions(wallet_id: str, limit: int = 50):
    txs = wallet_mgr.get_transaction_history(wallet_id, limit)
    for tx in txs:
        if isinstance(tx.get("risk_reasons"), str):
            try:
                tx["risk_reasons"] = json.loads(tx["risk_reasons"])
            except json.JSONDecodeError:
                pass
    return {"transactions": txs, "count": len(txs)}

@app.get("/transactions")
def get_all_transactions(limit: int = 50):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for tx in rows:
        if isinstance(tx.get("risk_reasons"), str):
            try:
                tx["risk_reasons"] = json.loads(tx["risk_reasons"])
            except json.JSONDecodeError:
                pass
    return {"transactions": rows, "count": len(rows)}

# ============ INTELLIGENCE ============

@app.get("/intelligence/{wallet_id}")
async def get_spend_intelligence(wallet_id: str):
    return await spend_intel.get_summary(wallet_id)

@app.get("/intelligence/ai/latest")
async def get_latest_ai_analysis():
    result = await ai_analyst.get_latest_analysis()
    if not result:
        return {"message": "No AI analysis available yet"}
    return result

@app.post("/intelligence/ai/run")
async def run_ai_analysis():
    try:
        from .audit_logging import primary_store
        entries = await primary_store.get_recent(hours=24)
        if not entries:
            return {"message": "No recent log entries to analyze"}
        findings = await ai_analyst.analyze_logs(entries)
        await ai_analyst.save_analysis(findings)
        return findings
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return {"threat_level": "LOW", "findings": [f"Analysis error: {str(e)}"], "anomalies": [], "remediations": []}

# ============ AUDIT LOG ============

@app.get("/audit/logs")
async def get_audit_logs(limit: int = 100):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    entries = []
    for r in rows:
        entries.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "event_type": r["event_type"],
            "payload": json.loads(r["payload"]) if r["payload"] else {},
            "previous_hash": r["previous_hash"],
            "hash": r["hash"]
        })
    return {"entries": entries, "count": len(entries)}

@app.get("/audit/verify")
async def verify_audit_chain():
    try:
        from .audit_logging.verifier import verify_integrity
        result = await verify_integrity()
        if result.get("tampered"):
            await approval_mgr.send_alert(
                "🚨 CRITICAL: Audit log tampering detected! All wallets may be frozen."
            )
        return result
    except Exception as e:
        return {"error": str(e), "tampered": None}

# ============ DEMO ENDPOINTS ============

@app.post("/demo/seed")
def seed_demo_data():
    """Create a demo wallet with balance for testing."""
    wallet_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if demo wallet exists
    cursor.execute("SELECT id FROM agent_wallets WHERE user_id = 'demo_user'")
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return {"message": "Demo wallet already exists", "wallet_id": existing["id"]}

    cursor.execute(
        """INSERT INTO agent_wallets (id, user_id, balance, spend_limit, weekly_limit)
           VALUES (?, 'demo_user', 5000.0, 2000.0, 10000.0)""",
        (wallet_id,)
    )
    conn.commit()
    conn.close()
    return {"message": "Demo data seeded", "wallet_id": wallet_id, "balance": 5000.0}

@app.post("/demo/simulate-suspicious")
async def simulate_suspicious(background_tasks: BackgroundTasks):
    """Simulate a suspicious payment for demo purposes."""
    payment = PaymentRequest(
        amount=4999.0,
        merchant="unknown-store-3am.ru",
        merchant_domain="unknown-store-3am.ru",
        description="Expensive electronics at 3am",
        agent_id="demo_agent"
    )
    return await process_payment(payment, background_tasks)

# ============ HELPER ============

def _log_event_sync(event_type: str, payload: dict):
    """Fire-and-forget audit log (best effort)."""
    try:
        import asyncio
        from .audit_logging.logger import log_event
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(log_event(event_type, payload))
        else:
            asyncio.run(log_event(event_type, payload))
    except Exception as e:
        logger.warning(f"Audit log failed (non-fatal): {e}")
