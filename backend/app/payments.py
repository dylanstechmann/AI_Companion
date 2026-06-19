"""
AI Companion — Payments, Credits & Billing Service
===================================================
Supports buying USD-denominated credit packs using:
1. Stripe (Credit/Debit Card, Apple Pay, Google Pay)
2. PayPal
3. BTCPay Server (Bitcoin / Lightning) with auto-stablecoin conversion

Credits are denominated in cents (1 credit = $0.01).
Cost-per-operation is calculated at operation cost + 10% margin.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import get_settings
from app import database
from app.crypto_swap import swap_crypto_to_stablecoin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Credit packs definitions (1 credit = $0.01)
# ---------------------------------------------------------------------------
CREDIT_PACKS = {
    "starter": {"name": "Starter Pack", "price_usd": 5.00, "credits": 500},
    "plus": {"name": "Plus Pack", "price_usd": 20.00, "credits": 2500},
    "pro": {"name": "Pro Pack", "price_usd": 75.00, "credits": 10000},
    "enterprise": {"name": "Enterprise Pack", "price_usd": 300.00, "credits": 50000},
}

# Operational costs (in credits, cost + 10%)
OPERATION_COSTS = {
    "chat_message_flash": 0.05,       # $0.0004 * 1.10 = $0.00044 -> ~0.05 credits
    "chat_message_gpt4": 1.1,         # $0.01 * 1.10 = $0.011 -> 1.1 credits
    "tts_generation": 0.8,            # $0.0075 * 1.10 = $0.00825 -> ~0.8 credits
    "stt_transcription": 0.3,         # $0.003 * 1.10 = $0.0033 -> ~0.3 credits
    "avatar_generation": 4.4,         # $0.04 * 1.10 = $0.044 -> 4.4 credits
    "web_research": 2.2,              # $0.02 * 1.10 = $0.022 -> 2.2 credits
}

# Legacy fallback for backward compatibility
SUBSCRIPTION_PLANS = {
    "free": {"price_sats": 0, "messages_per_day": -1, "features": ["Credits system active"]},
    "basic": {"price_sats": 0, "messages_per_day": -1, "features": ["Credits system active"]},
    "premium": {"price_sats": 0, "messages_per_day": -1, "features": ["Credits system active"]},
}


class PaymentService:
    """Billing facades supporting Stripe, PayPal, and BTCPay Server."""

    def __init__(self) -> None:
        settings = get_settings()
        
        # BTCPay Config
        self.btcpay_url = getattr(settings, "BTCPAY_URL", "").rstrip("/")
        self.btcpay_api_key = getattr(settings, "BTCPAY_API_KEY", "")
        self.btcpay_store_id = getattr(settings, "BTCPAY_STORE_ID", "")
        self.btcpay_webhook_secret = getattr(settings, "BTCPAY_WEBHOOK_SECRET", "")
        
        # Stripe Config
        self.stripe_secret_key = getattr(settings, "STRIPE_SECRET_KEY", "")
        self.stripe_publishable_key = getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")
        self.stripe_webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        
        # PayPal Config
        self.paypal_client_id = getattr(settings, "PAYPAL_CLIENT_ID", "")
        self.paypal_secret = getattr(settings, "PAYPAL_SECRET", "")
        self.paypal_mode = getattr(settings, "PAYPAL_MODE", "sandbox").lower()
        
        # HTTP client
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    # ---- Credit balance & Usage -------------------------------------------

    async def get_user_balance(self, user_id: int) -> int:
        """Return user's credit balance (1 credit = $0.01)."""
        return await database.get_user_credits(user_id)

    async def deduct_usage(self, user_id: int, action: str, multiplier: float = 1.0) -> bool:
        """Deduct operation cost from user's balance and log usage."""
        cost = OPERATION_COSTS.get(action, 0.0) * multiplier
        if cost <= 0.0:
            return True
            
        ok = await database.deduct_user_credits(user_id, cost)
        if not ok:
            logger.info("Insufficient balance for user %s (%s)", user_id, action)
            return False
            
        await database.add_usage_log(user_id, action, cost)
        return True

    # ---- Stripe Integration -----------------------------------------------

    async def create_stripe_checkout(self, user_id: int, pack_id: str, redirect_url: str) -> dict[str, Any]:
        """Create a Stripe checkout session for a credit pack."""
        if pack_id not in CREDIT_PACKS:
            raise ValueError(f"Unknown credit pack: {pack_id}")
            
        pack = CREDIT_PACKS[pack_id]
        price_cents = int(pack["price_usd"] * 100)
        
        if not self.stripe_secret_key:
            # Mock session URL for development
            mock_session_id = f"stripe-mock-{uuid.uuid4().hex[:12]}"
            # Instantly record mock pending payment
            await database.create_payment(user_id, mock_session_id, price_cents)
            return {
                "session_id": mock_session_id,
                "checkout_url": f"{redirect_url}?session_id={mock_session_id}&mock_status=success",
                "mode": "mock",
            }
            
        # Call Stripe API
        stripe_url = "https://api.stripe.com/v1/checkout/sessions"
        headers = {"Authorization": f"Bearer {self.stripe_secret_key}"}
        payload = {
            "success_url": f"{redirect_url}?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": redirect_url,
            "mode": "payment",
            "client_reference_id": str(user_id),
            "metadata[pack]": pack_id,
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][product_data][name]": f"{pack['name']} ({pack['credits']} Credits)",
            "line_items[0][price_data][unit_amount]": str(price_cents),
            "line_items[0][quantity]": "1",
        }
        
        response = await self._client.post(stripe_url, headers=headers, data=payload)
        if response.status_code != 200:
            logger.error("Stripe Checkout creation failed: %s", response.text)
            raise RuntimeError("Failed to create Stripe Checkout session")
            
        data = response.json()
        # Record pending payment
        await database.create_payment(user_id, data["id"], price_cents)
        return {
            "session_id": data["id"],
            "checkout_url": data["url"],
            "mode": "live",
        }

    async def handle_stripe_webhook(self, payload_str: str, signature: str) -> dict[str, Any]:
        """Verify and process Stripe webhook events."""
        if not self.stripe_secret_key:
            return {"processed": False, "error": "Stripe not configured"}
            
        # Verification using pure python is complex, in practice we'd use stripe SDK.
        # As fallback / simplified version, we can fetch the session details directly from Stripe
        # using the session ID in the event payload to verify authenticity! This is highly secure.
        try:
            import json
            event = json.loads(payload_str)
        except Exception:
            return {"processed": False, "error": "Invalid JSON"}
            
        event_type = event.get("type")
        if event_type == "checkout.session.completed":
            session = event.get("data", {}).get("object", {})
            session_id = session.get("id")
            if not session_id:
                return {"processed": False, "error": "Missing session ID"}
                
            # Verify the session by calling Stripe directly (prevents spoofing)
            stripe_url = f"https://api.stripe.com/v1/checkout/sessions/{session_id}"
            headers = {"Authorization": f"Bearer {self.stripe_secret_key}"}
            resp = await self._client.get(stripe_url, headers=headers)
            if resp.status_code != 200:
                return {"processed": False, "error": "Failed to verify session with Stripe"}
                
            verified_session = resp.json()
            if verified_session.get("payment_status") == "paid":
                user_id = int(verified_session.get("client_reference_id"))
                pack_id = verified_session.get("metadata", {}).get("pack")
                pack = CREDIT_PACKS.get(pack_id)
                if pack:
                    # Mark paid
                    await database.update_payment_status(session_id, "paid")
                    await database.add_user_credits(user_id, pack["credits"])
                    logger.info("Stripe: Credited user %s with %d credits", user_id, pack["credits"])
                    return {"processed": True, "user_id": user_id, "credits": pack["credits"]}
                    
        return {"processed": True, "message": "Ignored event type"}

    # ---- PayPal Integration -----------------------------------------------

    async def _get_paypal_token(self) -> str:
        base_url = "https://api-m.paypal.com" if self.paypal_mode == "live" else "https://api-m.sandbox.paypal.com"
        token_url = f"{base_url}/v1/oauth2/token"
        headers = {"Accept": "application/json", "Accept-Language": "en_US"}
        auth = (self.paypal_client_id, self.paypal_secret)
        data = {"grant_type": "client_credentials"}
        
        resp = await self._client.post(token_url, headers=headers, auth=auth, data=data)
        if resp.status_code != 200:
            raise RuntimeError("Failed to get PayPal token")
        return resp.json()["access_token"]

    async def create_paypal_order(self, user_id: int, pack_id: str) -> dict[str, Any]:
        """Create a PayPal order for a credit pack."""
        if pack_id not in CREDIT_PACKS:
            raise ValueError(f"Unknown credit pack: {pack_id}")
            
        pack = CREDIT_PACKS[pack_id]
        price_usd = pack["price_usd"]
        
        if not self.paypal_client_id:
            mock_order_id = f"paypal-mock-{uuid.uuid4().hex[:12]}"
            await database.create_payment(user_id, mock_order_id, int(price_usd * 100))
            return {
                "order_id": mock_order_id,
                "checkout_url": f"https://example.com/paypal-mock-checkout?order_id={mock_order_id}",
                "mode": "mock",
            }
            
        token = await self._get_paypal_token()
        base_url = "https://api-m.paypal.com" if self.paypal_mode == "live" else "https://api-m.sandbox.paypal.com"
        order_url = f"{base_url}/v2/checkout/orders"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": "USD",
                        "value": f"{price_usd:.2f}"
                    },
                    "description": f"{pack['name']} ({pack['credits']} Credits)"
                }
            ],
            "application_context": {
                "return_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel"
            }
        }
        
        resp = await self._client.post(order_url, headers=headers, json=payload)
        if resp.status_code != 201:
            logger.error("PayPal order creation failed: %s", resp.text)
            raise RuntimeError("Failed to create PayPal order")
            
        data = resp.json()
        order_id = data["id"]
        approve_link = next(link["href"] for link in data["links"] if link["rel"] == "approve")
        
        # Record pending payment
        await database.create_payment(user_id, order_id, int(price_usd * 100))
        return {
            "order_id": order_id,
            "checkout_url": approve_link,
            "mode": "live",
        }

    async def capture_paypal_order(self, user_id: int, order_id: str) -> dict[str, Any]:
        """Capture approval PayPal order and credit user's account."""
        if not self.paypal_client_id:
            # Handle mock capture
            payment = await database.get_payment_by_invoice(order_id)
            if payment and payment["status"] == "pending":
                price_cents = payment["amount_sats"] # using sats column as cents
                credits = price_cents # 1 credit = 1 cent
                await database.update_payment_status(order_id, "paid")
                await database.add_user_credits(user_id, credits)
                return {"status": "success", "credits": credits, "mode": "mock"}
            return {"status": "failed", "error": "Invalid mock payment"}
            
        token = await self._get_paypal_token()
        base_url = "https://api-m.paypal.com" if self.paypal_mode == "live" else "https://api-m.sandbox.paypal.com"
        capture_url = f"{base_url}/v2/checkout/orders/{order_id}/capture"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        resp = await self._client.post(capture_url, headers=headers, json={})
        if resp.status_code != 201 and resp.status_code != 200:
            logger.error("PayPal capture failed: %s", resp.text)
            raise RuntimeError("Failed to capture PayPal order")
            
        data = resp.json()
        if data.get("status") == "COMPLETED":
            payment = await database.get_payment_by_invoice(order_id)
            if payment:
                price_cents = payment["amount_sats"]
                credits = price_cents
                await database.update_payment_status(order_id, "paid")
                await database.add_user_credits(user_id, credits)
                logger.info("PayPal: Credited user %s with %d credits", user_id, credits)
                return {"status": "success", "credits": credits, "mode": "live"}
                
        return {"status": "failed", "detail": data.get("status")}

    # ---- BTCPay Server Integration (Crypto) --------------------------------

    async def create_btcpay_invoice(self, user_id: int, pack_id: str, redirect_url: str) -> dict[str, Any]:
        """Create a BTCPay invoice for a credit pack."""
        if pack_id not in CREDIT_PACKS:
            raise ValueError(f"Unknown credit pack: {pack_id}")
            
        pack = CREDIT_PACKS[pack_id]
        price_usd = pack["price_usd"]
        
        if not self.btcpay_url:
            mock_invoice_id = f"btcpay-mock-{uuid.uuid4().hex[:12]}"
            await database.create_payment(user_id, mock_invoice_id, int(price_usd * 100))
            return {
                "invoice_id": mock_invoice_id,
                "payment_url": f"{redirect_url}?invoice_id={mock_invoice_id}&mock_status=success",
                "mode": "mock",
            }
            
        btcpay_invoice_url = f"{self.btcpay_url}/api/v1/stores/{self.btcpay_store_id}/invoices"
        headers = {
            "Authorization": f"token {self.btcpay_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "amount": price_usd,
            "currency": "USD", # BTCPay Server automatically converts USD to BTC amount
            "metadata": {
                "userId": str(user_id),
                "pack": pack_id,
            },
            "checkout": {
                "redirectURL": redirect_url,
            }
        }
        
        resp = await self._client.post(btcpay_invoice_url, headers=headers, json=payload)
        if resp.status_code != 200:
            logger.error("BTCPay Invoice creation failed: %s", resp.text)
            raise RuntimeError("Failed to create BTCPay invoice")
            
        data = resp.json()
        invoice_id = data["id"]
        payment_url = data["checkoutLink"]
        
        # Record pending payment
        await database.create_payment(user_id, invoice_id, int(price_usd * 100))
        return {
            "invoice_id": invoice_id,
            "payment_url": payment_url,
            "mode": "live",
        }

    async def handle_btcpay_webhook(self, payload_str: str, signature: str) -> dict[str, Any]:
        """Verify BTCPay webhook and perform instant crypto-to-USDC swap."""
        # Simple verify
        if self.btcpay_webhook_secret and signature:
            expected = hmac.new(
                self.btcpay_webhook_secret.encode(),
                payload_str.encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, signature):
                logger.warning("BTCPay webhook signature mismatch.")
                return {"processed": False, "error": "invalid signature"}
                
        import json
        try:
            payload = json.loads(payload_str)
        except Exception:
            return {"processed": False, "error": "invalid json"}
            
        event_type = payload.get("type", "")
        if event_type in {"InvoiceSettled", "InvoiceCompleted"}:
            invoice_data = payload.get("invoice", {})
            invoice_id = invoice_data.get("id")
            
            payment = await database.get_payment_by_invoice(invoice_id)
            if payment and payment["status"] == "pending":
                user_id = payment["user_id"]
                price_cents = payment["amount_sats"]
                credits = price_cents
                
                # Retrieve the crypto amount received (in BTC)
                # For demonstration, BTCPay invoices hold the BTC payment rate
                btc_amount = float(invoice_data.get("amount", 0.0))
                
                # Compute stablecoin value (simulation only — no real trade is
                # executed; see crypto_swap.swap_crypto_to_stablecoin docstring).
                swap_details = await swap_crypto_to_stablecoin(btc_amount, "BTC", "USDC")
                logger.info(
                    "Crypto swap (simulated, executed=%s): %s",
                    swap_details.get("executed"), swap_details,
                )
                
                await database.update_payment_status(invoice_id, "paid")
                await database.add_user_credits(user_id, credits)
                logger.info("BTCPay Webhook: Credited user %s with %d credits", user_id, credits)
                return {"processed": True, "user_id": user_id, "credits": credits}
                
        return {"processed": True, "message": "Ignored or already processed"}

    # ---- Legacy methods fallback (mock compatibility) --------------------

    async def check_invoice(self, invoice_id: str) -> dict[str, Any]:
        """Check status of a pending invoice (used for polling)."""
        payment = await database.get_payment_by_invoice(invoice_id)
        if not payment:
            return {"status": "not_found"}
            
        # Background PayPal auto-capture if user approved
        if self.paypal_client_id and payment["status"] == "pending" and not invoice_id.startswith("paypal-mock-") and not invoice_id.startswith("stripe-mock-") and not invoice_id.startswith("btcpay-mock-"):
            if not invoice_id.startswith("cs_") and len(invoice_id) > 10:
                try:
                    token = await self._get_paypal_token()
                    base_url = "https://api-m.paypal.com" if self.paypal_mode == "live" else "https://api-m.sandbox.paypal.com"
                    order_url = f"{base_url}/v2/checkout/orders/{invoice_id}"
                    headers = {"Authorization": f"Bearer {token}"}
                    resp = await self._client.get(order_url, headers=headers)
                    if resp.status_code == 200:
                        order_data = resp.json()
                        paypal_status = order_data.get("status")
                        if paypal_status == "APPROVED":
                            capture_result = await self.capture_paypal_order(payment["user_id"], invoice_id)
                            if capture_result.get("status") == "success":
                                return {"status": "paid", "amount_sats": payment["amount_sats"]}
                        elif paypal_status == "COMPLETED":
                            await database.update_payment_status(invoice_id, "paid")
                            return {"status": "paid", "amount_sats": payment["amount_sats"]}
                except Exception:
                    logger.exception("Failed to auto-capture PayPal order during check")

        # Mock auto-settle for local testing
        if invoice_id.startswith("stripe-mock-") or invoice_id.startswith("paypal-mock-") or invoice_id.startswith("btcpay-mock-"):
            if payment["status"] == "pending":
                user_id = payment["user_id"]
                credits = payment["amount_sats"]
                await database.update_payment_status(invoice_id, "paid")
                await database.add_user_credits(user_id, credits)
                return {"status": "paid", "amount_sats": credits}
                
        return {"status": payment["status"], "amount_sats": payment["amount_sats"]}

    async def get_subscription(self, user_id: int) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "plan": "premium",
            "price_sats": 0,
            "messages_per_day": -1,
            "features": ["Unlimited access (credit based)"],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None,
        }

    async def get_usage_history(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        return await database.get_usage_history(user_id, limit)

    async def get_payment_history(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        return await database.get_payment_history(user_id, limit)


_payment_service: Optional[PaymentService] = None

def get_payment_service() -> PaymentService:
    global _payment_service
    if _payment_service is None:
        _payment_service = PaymentService()
    return _payment_service
