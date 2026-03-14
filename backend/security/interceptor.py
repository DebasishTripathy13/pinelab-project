import logging
import asyncio
import uuid
import json
from typing import Dict
from dataclasses import dataclass, field, asdict
from .merchant_check import MerchantChecker, MerchantResult
from .ml_engine import MLEngine, BehaviorResult
from .policy_engine import PolicyEngine, PolicyResult

logger = logging.getLogger("sentinelpay.security")

@dataclass
class InterceptResult:
    action: str = "APPROVE"  # APPROVE, HUMAN_REVIEW, BLOCK
    total_score: float = 0.0
    merchant_result: dict = field(default_factory=dict)
    behavior_result: dict = field(default_factory=dict)
    policy_result: dict = field(default_factory=dict)
    all_reasons: list = field(default_factory=list)
    trigger_death_switch: bool = False

class Interceptor:
    def __init__(self):
        self.merchant_checker = MerchantChecker()
        self.ml_engine = MLEngine()
        self.policy_engine = PolicyEngine()

    async def intercept(self, payment_request: dict, wallet: dict, history: list) -> InterceptResult:
        """
        Run all 3 security checks in parallel and aggregate results.
        """
        logger.info(f"Intercepting payment: {payment_request.get('amount')} to {payment_request.get('merchant')}")

        # Run all checks in parallel
        merchant_result, behavior_result, policy_result = await asyncio.gather(
            self.merchant_checker.check(
                payment_request.get("merchant", ""),
                payment_request.get("merchant_domain", "")
            ),
            self.ml_engine.analyze(payment_request, history),
            self.policy_engine.check(payment_request, wallet)
        )

        # Aggregate score: merchant 40%, behavior 40%, policy 20%
        total_score = (
            merchant_result.score * 0.4 +
            behavior_result.score * 0.4 +
            policy_result.score * 0.2
        )

        # Collect all reasons
        all_reasons = []
        all_reasons.extend(merchant_result.reasons)
        all_reasons.extend(behavior_result.reasons)
        all_reasons.extend(policy_result.reasons)

        # Decision thresholds
        result = InterceptResult(
            total_score=round(total_score, 3),
            merchant_result={
                "score": merchant_result.score,
                "is_trusted": merchant_result.is_trusted,
                "reasons": merchant_result.reasons
            },
            behavior_result={
                "score": behavior_result.score,
                "confidence": behavior_result.confidence,
                "reasons": behavior_result.reasons
            },
            policy_result={
                "score": policy_result.score,
                "violations": policy_result.violations,
                "reasons": policy_result.reasons
            },
            all_reasons=all_reasons
        )

        # Hard blocks: policy violations that are absolute
        if "wallet_frozen" in policy_result.violations:
            result.action = "BLOCK"
            result.trigger_death_switch = False
            return result

        if "insufficient_balance" in policy_result.violations:
            result.action = "BLOCK"
            return result

        # Score-based decision
        if total_score < 0.3:
            result.action = "APPROVE"
        elif total_score < 0.7:
            result.action = "HUMAN_REVIEW"
        else:
            result.action = "BLOCK"
            if total_score > 0.9:
                result.trigger_death_switch = True

        logger.info(f"Intercept decision: {result.action} (score: {total_score:.3f})")
        return result
