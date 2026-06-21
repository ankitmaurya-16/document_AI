"""Stripe Checkout (test mode): create session + webhook that grants credits.

If the ``stripe`` SDK or secret key isn't configured, endpoints return 503 so
the UI can fall back to a disabled state.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated

from flask import Blueprint, jsonify, request
from pydantic import StringConstraints

from errors import AppError, ValidationError
from extensions import limiter
from logging_config import get_logger
from rag.auth import require_auth
from rag.database import get_database, get_user_by_id, update_user_credits
from resilience import with_retry
from schemas import _StrictModel, parse_json
from settings import get_settings

# Stripe SDK errors that are safe to retry (network blips, 5xx).
try:
    from stripe.error import APIConnectionError as _StripeConn  # type: ignore
    from stripe.error import APIError as _StripeAPI  # type: ignore
    from stripe.error import RateLimitError as _StripeRate  # type: ignore
    _STRIPE_RETRY_TYPES = (_StripeConn, _StripeAPI, _StripeRate)
except ImportError:
    _STRIPE_RETRY_TYPES = (Exception,)

bp = Blueprint("billing", __name__)
log = get_logger("routes.billing")


# Map of UI plan ids → (Stripe price env var name, credit grant on success).
# Students: fill in these env vars with Stripe test-mode price IDs.
PLANS = {
    "starter": {"env": "STRIPE_PRICE_STARTER", "credits": 500, "usd": 5},
    "pro": {"env": "STRIPE_PRICE_PRO", "credits": 2500, "usd": 20},
}


def _stripe():
    """Return the stripe module configured with the secret key, or None."""
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        return None
    try:
        import stripe  # type: ignore
    except ImportError:
        log.warning("stripe.missing_dependency", hint="pip install stripe")
        return None
    stripe.api_key = key
    return stripe


@with_retry("stripe", exception_types=_STRIPE_RETRY_TYPES)
def _create_checkout_session(stripe, **kwargs):
    return stripe.checkout.Session.create(**kwargs)


def _ensure_processed_events_index(db) -> None:
    """Unique index on event_id + 30-day TTL on receivedAt (idempotent)."""
    try:
        db.processed_events.create_index("event_id", unique=True)
        db.processed_events.create_index("receivedAt", expireAfterSeconds=60 * 60 * 24 * 30)
    except Exception as e:
        log.warning("stripe.processed_events_index_failed", error=str(e))


class CheckoutIn(_StrictModel):
    plan: Annotated[str, StringConstraints(min_length=1, max_length=32)]


@bp.get("/plans")
@limiter.limit(lambda: get_settings().rate_limit_default)
def list_plans():
    """Return the public plan metadata the UI renders."""
    return jsonify({
        "plans": [
            {
                "_id": pid,
                "name": pid.capitalize(),
                "price": p["usd"],
                "credits": p["credits"],
                "features": [
                    f"{p['credits']} credits",
                    "All document formats",
                    "Hybrid retrieval",
                ] + (["Priority latency"] if pid == "pro" else []),
            }
            for pid, p in PLANS.items()
        ]
    }), 200


@bp.post("/create-checkout-session")
@limiter.limit(lambda: get_settings().rate_limit_default)
@require_auth
def create_checkout_session():
    payload = parse_json(CheckoutIn, request)
    plan = PLANS.get(payload.plan)
    if not plan:
        raise ValidationError(f"Unknown plan: {payload.plan}")

    stripe = _stripe()
    if stripe is None:
        # TODO(prod): configure STRIPE_SECRET_KEY to enable Checkout.
        raise AppError(
            "Billing not configured (missing STRIPE_SECRET_KEY)",
            code="billing_unconfigured",
            http_status=503,
        )

    price_id = os.getenv(plan["env"])
    if not price_id:
        raise AppError(
            f"Plan {payload.plan!r} missing {plan['env']}",
            code="billing_misconfigured",
            http_status=503,
        )

    frontend = os.getenv("FRONTEND_URL", "http://localhost:5173")
    try:
        session = _create_checkout_session(
            stripe,
            mode="payment",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{frontend}/credits?status=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{frontend}/credits?status=cancel",
            client_reference_id=request.user_id,
            metadata={"user_id": request.user_id, "plan": payload.plan},
        )
    except Exception as e:  # stripe.error.StripeError + network
        log.exception("stripe.checkout_failed", error=str(e))
        raise AppError("Stripe checkout failed", code="stripe_error", http_status=502)

    log.info("stripe.checkout_created", user_id=request.user_id, plan=payload.plan)
    return jsonify({"url": session.url, "sessionId": session.id}), 200


@bp.post("/webhook")
def webhook():
    """Stripe webhook: verify signature, grant credits on checkout.session.completed."""
    stripe = _stripe()
    if stripe is None:
        return jsonify({"error": "billing_unconfigured"}), 503

    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        log.error("stripe.webhook_secret_missing")
        return jsonify({"error": "webhook_misconfigured"}), 503

    sig_header = request.headers.get("Stripe-Signature", "")
    body = request.get_data(as_text=True)
    try:
        event = stripe.Webhook.construct_event(body, sig_header, secret)
    except Exception as e:
        log.warning("stripe.webhook_bad_signature", error=str(e))
        return jsonify({"error": "invalid_signature"}), 400

    # Idempotency: Stripe retries failed deliveries, so the same event can land
    # multiple times. Insert before processing — a duplicate insert means we've
    # already credited this event and can return 200 immediately.
    from pymongo.errors import DuplicateKeyError

    db = get_database()
    _ensure_processed_events_index(db)
    event_id = event.get("id")
    try:
        db.processed_events.insert_one({
            "event_id": event_id,
            "type": event.get("type"),
            "receivedAt": datetime.utcnow(),
        })
    except DuplicateKeyError:
        log.info("stripe.webhook_duplicate_ignored", event_id=event_id)
        return jsonify({"received": True, "duplicate": True}), 200

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = (session.get("metadata") or {}).get("user_id") or session.get("client_reference_id")
        plan_key = (session.get("metadata") or {}).get("plan")
        plan = PLANS.get(plan_key)
        if user_id and plan:
            user = get_user_by_id(user_id)
            current = (user or {}).get("credits", 0)
            update_user_credits(user_id, current + plan["credits"])
            log.info("stripe.credits_granted", user_id=user_id, added=plan["credits"], event_id=event_id)
        else:
            log.warning("stripe.webhook_missing_context", session_id=session.get("id"))

    return jsonify({"received": True}), 200
