"""
AI Companion — Crypto Auto-Swap Service
=======================================
Converts received crypto (e.g. BTC) to a stablecoin value (USDC).

IMPORTANT — honesty note:
    This module does NOT execute real on-exchange trades. Doing so safely
    requires authenticated exchange API integration (ccxt/Coinbase/Kraken),
    order handling, slippage controls and reconciliation, none of which are
    implemented here. To avoid misrepresenting a financial action, every result
    is explicitly marked ``executed: False`` and ``status: "simulated"``.

    What IS real: the conversion uses a *live* spot price fetched from a public
    price API when the network is available, falling back to a clearly-flagged
    static estimate otherwise.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# Fallback estimates used only when the live price lookup fails (clearly flagged
# via ``live_rate: False`` in the response so callers never mistake it for real).
_FALLBACK_RATES = {
    "BTC": 60000.0,
    "ETH": 3000.0,
    "USDC": 1.0,
    "USDT": 1.0,
}


async def _fetch_live_rate(crypto_currency: str) -> tuple[float, bool]:
    """Return ``(rate_in_usd, is_live)`` for the given asset.

    Uses Coinbase's public spot-price endpoint (no auth required). On any
    failure it returns the static fallback estimate with ``is_live=False``.
    """
    symbol = crypto_currency.upper()
    if symbol in ("USDC", "USDT", "USD"):
        return 1.0, True
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"https://api.coinbase.com/v2/prices/{symbol}-USD/spot"
            )
            resp.raise_for_status()
            amount = float(resp.json()["data"]["amount"])
            return amount, True
    except Exception as exc:  # network/parse error -> honest fallback
        logger.warning(
            "Live price lookup for %s failed (%s); using static estimate.",
            symbol,
            exc,
        )
        return _FALLBACK_RATES.get(symbol, 1.0), False


async def swap_crypto_to_stablecoin(
    crypto_amount: float,
    crypto_currency: str = "BTC",
    target_currency: str = "USDC",
) -> dict[str, Any]:
    """Compute the stablecoin value of a crypto amount.

    NOTE: This is a simulation — no funds are moved. The returned dict always
    has ``executed: False`` and ``status: "simulated"``.
    """
    settings = get_settings()
    rate, is_live = await _fetch_live_rate(crypto_currency)
    usd_value = crypto_amount * rate
    stablecoin_amount = usd_value  # 1 USDC ≈ 1 USD

    # If exchange credentials are present, be explicit that real trading is not
    # wired up — do NOT pretend a trade happened.
    exchange_configured = bool(settings.EXCHANGE_API_KEY and settings.EXCHANGE_API_SECRET)
    if exchange_configured:
        logger.warning(
            "EXCHANGE_API_KEY is set but real exchange trading is not implemented; "
            "returning a simulated swap. Implement a ccxt client to enable live trades."
        )

    logger.info(
        "Simulated swap (no real trade): %s %s -> %s %s (rate=%s, live_rate=%s)",
        crypto_amount, crypto_currency, stablecoin_amount, target_currency, rate, is_live,
    )

    return {
        "status": "simulated",
        "executed": False,
        "provider": "none",
        "tx_id": None,
        "rate": rate,
        "live_rate": is_live,
        "swapped_amount": crypto_amount,
        "received_amount": stablecoin_amount,
        "currency": target_currency,
        "note": (
            "Simulation only — no funds were moved. Configure a real exchange "
            "integration to enable live swaps."
        ),
    }