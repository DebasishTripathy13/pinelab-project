import os
import logging
import json
import httpx
from typing import Dict, List
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger("sentinelpay.intelligence.ai_analyst")

class AnalystBackend(Enum):
    GEMINI = "gemini"
    OPENAI = "openai"
    OLLAMA = "ollama"

SYSTEM_PROMPT = """You are a payment security analyst AI embedded in SentinelPay.
You will be given recent transaction log entries from an AI agent's payment activity.
Your job:
1. Hunt for threat patterns — repeated failed attempts, unusual timing, merchant hopping, amount probing
2. Explain any anomalies in plain English
3. Suggest concrete remediation steps (tighten spend cap, add merchant to blocklist, freeze wallet, etc.)
4. Rate overall threat level: LOW / MEDIUM / HIGH / CRITICAL

Be specific. Reference exact transactions by timestamp if possible.
Output as JSON: { "threat_level": "LOW|MEDIUM|HIGH|CRITICAL", "findings": [], "anomalies": [], "remediations": [] }
Return ONLY valid JSON, no markdown."""

class AIAnalyst:
    def __init__(self):
        self.default_backend = AnalystBackend(os.getenv("AI_ANALYST_BACKEND", "gemini"))

    async def analyze_logs(self, entries: list, backend: AnalystBackend = None) -> dict:
        backend = backend or self.default_backend
        sanitized = self._sanitize(entries)

        if not sanitized:
            return {"threat_level": "LOW", "findings": [], "anomalies": [], "remediations": []}

        prompt = f"Analyze these {len(sanitized)} recent SentinelPay log entries:\n\n{json.dumps(sanitized, indent=2)}"

        try:
            if backend == AnalystBackend.GEMINI:
                return await self._gemini(prompt)
            elif backend == AnalystBackend.OPENAI:
                return await self._openai(prompt)
            elif backend == AnalystBackend.OLLAMA:
                return await self._ollama(prompt)
        except Exception as e:
            logger.error(f"AI analysis failed ({backend.value}): {e}")
            return {
                "threat_level": "LOW",
                "findings": [f"Analysis failed: {str(e)}"],
                "anomalies": [],
                "remediations": []
            }

    def analyze_transaction(self, transaction: dict) -> dict:
        """Synchronous single-transaction analysis using rule-based fallback."""
        amount = transaction.get("amount", 0)
        merchant = transaction.get("merchant_name", "unknown")

        risk = 0.0
        reasons = []

        if amount > 5000:
            risk += 0.4
            reasons.append("High value transaction")
        if amount > 2000:
            risk += 0.2
            reasons.append("Above average amount")

        suspicious_keywords = ["casino", "gambling", "crypto", "forex", "loan"]
        desc = (transaction.get("description", "") + " " + merchant).lower()
        for kw in suspicious_keywords:
            if kw in desc:
                risk += 0.3
                reasons.append(f"Suspicious keyword: {kw}")

        return {
            "risk_score": min(risk, 1.0),
            "reasoning": "; ".join(reasons) if reasons else "Transaction appears normal"
        }

    async def _gemini(self, prompt: str) -> dict:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return {"threat_level": "LOW", "findings": ["Gemini API key not configured"], "anomalies": [], "remediations": []}

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(SYSTEM_PROMPT + "\n\n" + prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            raise

    async def _openai(self, prompt: str) -> dict:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return {"threat_level": "LOW", "findings": ["OpenAI API key not configured"], "anomalies": [], "remediations": []}

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            raise

    async def _ollama(self, prompt: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post("http://localhost:11434/api/generate", json={
                    "model": "llama3.1",
                    "prompt": SYSTEM_PROMPT + "\n\n" + prompt,
                    "stream": False,
                    "format": "json"
                })
                data = response.json()
                text = data.get("response", "{}")
                return json.loads(text)
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise

    def _sanitize(self, entries: list) -> list:
        safe = []
        for e in entries:
            s = e.copy()
            if "payload" in s and isinstance(s["payload"], dict):
                s["payload"] = {k: v for k, v in s["payload"].items()
                               if k not in ["wallet_id", "user_id", "pine_order_id"]}
            safe.append(s)
        return safe

    async def save_analysis(self, findings: dict):
        from ..database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ai_analyses (timestamp, threat_level, findings, anomalies, remediations, backend, entry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            findings.get("threat_level", "LOW"),
            json.dumps(findings.get("findings", [])),
            json.dumps(findings.get("anomalies", [])),
            json.dumps(findings.get("remediations", [])),
            self.default_backend.value,
            0
        ))
        conn.commit()
        conn.close()

    async def get_latest_analysis(self) -> dict:
        from ..database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_analyses ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "timestamp": row["timestamp"],
            "threat_level": row["threat_level"],
            "findings": json.loads(row["findings"]),
            "anomalies": json.loads(row["anomalies"]),
            "remediations": json.loads(row["remediations"]),
            "backend": row["backend"]
        }
