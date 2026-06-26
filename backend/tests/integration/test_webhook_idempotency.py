"""Stripe can redeliver the same ``checkout.session.completed`` event, so the
unique index on ``processed_events.event_id`` must credit exactly once — proven
here against a real Mongo (mongomock's unique-index behavior diverges).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class _FakeStripeModule:
    """Just enough of the stripe SDK surface for webhook() to work."""

    class Webhook:
        @staticmethod
        def construct_event(body, sig, secret):
            # We aren't testing signature verification here; trust the caller.
            import json as _json

            return _json.loads(body)


def test_duplicate_event_credits_once(client, registered_user, mongo_db, monkeypatch):
    user_id = registered_user["user_id"]
    # Stripe + webhook secret need to look configured for the route to run.
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")

    from routes.v1 import billing as billing_mod

    monkeypatch.setattr(billing_mod, "_stripe", lambda: _FakeStripeModule)

    event = {
        "id": "evt_1_abc",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "metadata": {"user_id": user_id, "plan": "starter"},
                "client_reference_id": user_id,
            }
        },
    }
    import json
    body = json.dumps(event)

    starting = mongo_db.users.find_one({"_id": _as_object_id(user_id)})["credits"]

    # Deliver the same event twice.
    r1 = client.post("/api/v1/billing/webhook", data=body, content_type="application/json")
    r2 = client.post("/api/v1/billing/webhook", data=body, content_type="application/json")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.get_json().get("duplicate") is True

    ending = mongo_db.users.find_one({"_id": _as_object_id(user_id)})["credits"]
    assert ending - starting == 500  # "starter" plan grants exactly 500 credits


def _as_object_id(maybe_id: str):
    from bson import ObjectId

    try:
        return ObjectId(maybe_id)
    except Exception:
        return maybe_id
