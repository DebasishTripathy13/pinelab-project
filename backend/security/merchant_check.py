import os
import logging
import httpx
import json
import time
from typing import Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger("sentinelpay.security.merchant")

TRUSTED_MERCHANTS = [
    "blinkit.com", "bigbasket.com", "swiggy.com", "zomato.com",
    "amazon.in", "flipkart.com", "jiomart.com", "dunzo.com",
    "zepto.com", "instamart.swiggy.com", "myntra.com",
    "nykaa.com", "pharmeasy.in", "1mg.com", "netmeds.com",
    "bookmyshow.com", "makemytrip.com", "uber.com", "ola.com"
]

@dataclass
class MerchantResult:
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    is_trusted: bool = False
    domain: str = ""

class MerchantChecker:
    def __init__(self):
        self.vt_api_key = os.getenv("VIRUSTOTAL_API_KEY", "")
        self._cache: Dict[str, dict] = {}
        self._cache_ttl = 86400  # 24 hours

    async def check(self, merchant_name: str, merchant_domain: str = "") -> MerchantResult:
        result = MerchantResult(domain=merchant_domain or merchant_name)

        # Normalize domain
        domain = (merchant_domain or merchant_name).lower().strip()
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]

        # 1. Check trusted allowlist
        for trusted in TRUSTED_MERCHANTS:
            if trusted in domain or domain in trusted:
                result.score = 0.0
                result.is_trusted = True
                result.reasons.append(f"Trusted merchant: {domain}")
                return result

        # 2. Check VirusTotal if key available
        if self.vt_api_key and domain:
            vt_result = await self._check_virustotal(domain)
            if vt_result:
                if vt_result.get("malicious", 0) > 0:
                    result.score = 1.0
                    result.reasons.append(f"VirusTotal: {vt_result['malicious']} engines flagged as malicious")
                    return result
                elif vt_result.get("suspicious", 0) > 0:
                    result.score = 0.6
                    result.reasons.append(f"VirusTotal: {vt_result['suspicious']} engines flagged as suspicious")
                else:
                    result.score = 0.2
                    result.reasons.append("VirusTotal: clean but not in trusted list")

        # 3. Heuristic checks for unknown merchants
        if result.score == 0.0 and not result.is_trusted:
            result.score = 0.3
            result.reasons.append(f"Unknown merchant: {domain} (not in allowlist)")

            # Suspicious TLD check
            suspicious_tlds = [".ru", ".cn", ".tk", ".ml", ".ga", ".cf", ".xyz"]
            if any(domain.endswith(tld) for tld in suspicious_tlds):
                result.score = 0.8
                result.reasons.append(f"Suspicious TLD detected")

            # Very short or very long domains
            base_domain = domain.split(".")[0]
            if len(base_domain) <= 2 or len(base_domain) > 30:
                result.score = min(result.score + 0.2, 1.0)
                result.reasons.append("Unusual domain length")

        return result

    async def _check_virustotal(self, domain: str) -> dict:
        # Check cache first
        cache_key = f"vt:{domain}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if time.time() - cached["time"] < self._cache_ttl:
                return cached["data"]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://www.virustotal.com/api/v3/domains/{domain}",
                    headers={"x-apikey": self.vt_api_key}
                )
                if response.status_code == 200:
                    data = response.json()
                    stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                    result = {
                        "malicious": stats.get("malicious", 0),
                        "suspicious": stats.get("suspicious", 0),
                        "harmless": stats.get("harmless", 0),
                        "undetected": stats.get("undetected", 0)
                    }
                    self._cache[cache_key] = {"data": result, "time": time.time()}
                    return result
                elif response.status_code == 429:
                    logger.warning("VirusTotal rate limit hit")
                    return None
        except Exception as e:
            logger.error(f"VirusTotal check failed: {e}")
        return None
