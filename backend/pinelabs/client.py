import os
import httpx
import logging
import json
from typing import Optional, Dict, Any
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("sentinelpay.pinelabs")

class PineLabsClient:
    def __init__(self):
        self.base_url = os.getenv("PINE_BASE_URL", "https://pluraluat.v2.pinepg.in")
        self.client_id = os.getenv("PINE_CLIENT_ID", "")
        self.client_secret = os.getenv("PINE_CLIENT_SECRET", "")

        self.token = None
        self.token_expiry = 0

        if not self.client_id or not self.client_secret:
            logger.warning("Pine Labs credentials not set. API calls will fail.")

    async def _get_token(self) -> str:
        if self.token and time.time() < self.token_expiry:
            return self.token

        url = f"{self.base_url}/api/auth/v1/token"

        try:
            request_id = str(uuid.uuid4())
            request_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + \
                               datetime.now(timezone.utc).strftime('%f')[:3] + 'Z'

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Request-ID": request_id,
                        "Request-Timestamp": request_timestamp
                    }
                )
                response.raise_for_status()
                data = response.json()
                self.token = data.get("access_token") or data.get("token")

                expires_at_str = data.get("expires_at")
                if expires_at_str:
                    clean_ts = expires_at_str.replace("Z", "+00:00")
                    try:
                        expiry_dt = datetime.fromisoformat(clean_ts)
                        self.token_expiry = expiry_dt.timestamp() - 60
                    except ValueError:
                        self.token_expiry = time.time() + 3500
                else:
                    expires_in = data.get("expires_in", 3600)
                    self.token_expiry = time.time() + expires_in - 60

                logger.info("Pine Labs token acquired successfully")
                return self.token
        except httpx.HTTPStatusError as e:
            logger.error(f"Pine Labs auth failed ({e.response.status_code}): {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to get Pine Labs token: {e}")
            raise

    async def create_order(self, amount: float, merchant_data: Dict, description: str, wallet_id: str) -> Dict:
        token = await self._get_token()

        order_id = f"SP{uuid.uuid4().hex[:12].upper()}"
        request_id = str(uuid.uuid4())
        request_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + \
                           datetime.now(timezone.utc).strftime('%f')[:3] + 'Z'

        payload = {
            "merchant_order_reference": order_id,
            "order_amount": {
                "value": int(amount * 100),
                "currency": "INR"
            },
            "purchase_details": {
                "customer": {
                    "email_id": "agent@sentinelpay.ai",
                    "first_name": "SentinelPay",
                    "last_name": "Agent",
                    "customer_id": wallet_id,
                    "mobile_number": "9999999999",
                    "billing_address": {
                        "address1": "SentinelPay",
                        "city": "Mumbai",
                        "state": "Maharashtra",
                        "pincode": "400001",
                        "country": "India"
                    }
                },
                "merchant_metadata": {
                    "key1": "sentinelpay",
                    "key2": description
                }
            },
            "notes": {
                "wallet_id": wallet_id,
                "system": "SentinelPay",
                "merchant_name": merchant_data.get("name", "unknown")
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/pay/v1/orders",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Request-ID": request_id,
                        "Request-Timestamp": request_timestamp
                    }
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Pine Labs order created: {result}")
                return result
        except httpx.HTTPStatusError as e:
            logger.error(f"Pine Labs create order failed ({e.response.status_code}): {e.response.text}")
            # Return a structured error so caller can handle
            return {
                "id": order_id,
                "status": "FAILED",
                "error": e.response.text,
                "amount": amount
            }
        except Exception as e:
            logger.error(f"Pine Labs order error: {e}")
            return {
                "id": order_id,
                "status": "FAILED",
                "error": str(e),
                "amount": amount
            }

    async def get_order(self, order_id: str) -> Dict:
        token = await self._get_token()
        request_id = str(uuid.uuid4())

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/pay/v1/orders/{order_id}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Request-ID": request_id
                    }
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Get order failed: {e}")
            return {"id": order_id, "status": "UNKNOWN", "error": str(e)}

    async def cancel_order(self, order_id: str) -> Dict:
        token = await self._get_token()
        request_id = str(uuid.uuid4())

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/pay/v1/orders/{order_id}/cancel",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Request-ID": request_id
                    }
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return {"status": "CANCEL_FAILED", "error": str(e)}

    async def create_refund(self, order_id: str, amount: Optional[float] = None) -> Dict:
        token = await self._get_token()
        request_id = str(uuid.uuid4())

        payload = {"merchant_refund_reference": f"REF-{uuid.uuid4().hex[:8]}"}
        if amount:
            payload["refund_amount"] = {"value": int(amount * 100), "currency": "INR"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/pay/v1/orders/{order_id}/refund",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Request-ID": request_id
                    }
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Refund failed: {e}")
            return {"status": "REFUND_FAILED", "error": str(e)}
