import logging
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from ..database import get_db_connection

logger = logging.getLogger("sentinelpay.intelligence.spend")

class SpendIntelligence:
    async def analyze(self, wallet_id: str) -> List[Dict]:
        insights = []

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get last 30 days of transactions
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        cursor.execute("""
            SELECT * FROM transactions
            WHERE wallet_id = ? AND created_at > ? AND status = 'approved'
            ORDER BY created_at DESC
        """, (wallet_id, cutoff))
        transactions = [dict(r) for r in cursor.fetchall()]
        conn.close()

        if not transactions:
            insights.append({
                "type": "no_data",
                "message": "No recent transactions to analyze",
                "severity": "info"
            })
            return insights

        # 1. Recurring payment detection
        merchant_counts = {}
        merchant_amounts = {}
        for tx in transactions:
            m = tx.get("merchant", "unknown")
            merchant_counts[m] = merchant_counts.get(m, 0) + 1
            if m not in merchant_amounts:
                merchant_amounts[m] = []
            merchant_amounts[m].append(float(tx.get("amount", 0)))

        for merchant, count in merchant_counts.items():
            if count >= 3:
                avg = sum(merchant_amounts[merchant]) / len(merchant_amounts[merchant])
                insights.append({
                    "type": "recurring_payment",
                    "message": f"Recurring payments to {merchant}: {count} times, avg ₹{avg:.0f}",
                    "merchant": merchant,
                    "count": count,
                    "avg_amount": avg,
                    "severity": "info"
                })

        # 2. Price anomaly detection
        for merchant, amounts in merchant_amounts.items():
            if len(amounts) >= 2:
                avg = sum(amounts) / len(amounts)
                last = amounts[0]
                if last > avg * 1.3 and last > 100:
                    insights.append({
                        "type": "price_increase",
                        "message": f"{merchant} charged ₹{last:.0f} last time. Your average is ₹{avg:.0f}",
                        "merchant": merchant,
                        "last_amount": last,
                        "avg_amount": avg,
                        "severity": "warning",
                        "action": "compare_alternatives"
                    })

        # 3. Budget forecast
        total_spent = sum(float(tx.get("amount", 0)) for tx in transactions)
        days_in_period = 30
        if transactions:
            try:
                ts = str(transactions[-1].get("created_at", ""))
                oldest = datetime.fromisoformat(ts.replace("Z", "+00:00")) if "T" in ts else datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                days_in_period = max(1, (datetime.now(timezone.utc) - oldest).days)
            except (ValueError, TypeError):
                days_in_period = 1
        daily_rate = total_spent / max(days_in_period, 1)
        projected_monthly = daily_rate * 30

        insights.append({
            "type": "budget_forecast",
            "message": f"At current rate, projected monthly spend: ₹{projected_monthly:.0f}",
            "daily_rate": daily_rate,
            "projected_monthly": projected_monthly,
            "total_last_30d": total_spent,
            "severity": "info"
        })

        # 4. Category breakdown
        categories = {}
        for tx in transactions:
            cat = tx.get("category", "uncategorized")
            categories[cat] = categories.get(cat, 0) + float(tx.get("amount", 0))

        if categories:
            top_category = max(categories, key=categories.get)
            insights.append({
                "type": "category_breakdown",
                "message": f"Top spending category: {top_category} (₹{categories[top_category]:.0f})",
                "categories": categories,
                "severity": "info"
            })

        # 5. Spending velocity alert
        def _parse_ts(ts_str):
            try:
                ts = str(ts_str)
                if "T" in ts:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                return datetime.now(timezone.utc)
        last_7d = [tx for tx in transactions if (datetime.now(timezone.utc) - _parse_ts(tx.get("created_at", ""))).days <= 7]
        if len(last_7d) > 10:
            insights.append({
                "type": "high_velocity",
                "message": f"{len(last_7d)} transactions in last 7 days - above normal",
                "count": len(last_7d),
                "severity": "warning"
            })

        return insights

    async def get_summary(self, wallet_id: str) -> dict:
        insights = await self.analyze(wallet_id)
        return {
            "wallet_id": wallet_id,
            "insights": insights,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "actionable_count": sum(1 for i in insights if i.get("severity") == "warning")
        }
