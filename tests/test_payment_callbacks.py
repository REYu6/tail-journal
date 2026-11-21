"""A signed Stripe fixture exercises the real webhook without charging or calling Stripe."""

import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.app import app
from server.db import database, now, uid
from server import providers


class PaymentCallbacks(unittest.TestCase):
    def test_expiry_settlement_idempotency_refund_and_late_payment(self):
        secret = "whsec_local_test_fixture"
        with (
            tempfile.TemporaryDirectory() as root,
            patch.dict(
                os.environ,
                {
                    "PET_DATA_DIR": root,
                    "DATABASE_URL": os.environ.get("PET_TEST_DATABASE_URL", ""),
                    "PET_ADMIN_EMAIL": "finance@example.net",
                    "PET_ADMIN_PASSWORD": "finance-test-only-strong",
                    "PET_PAYMENT_MODE": "stripe",
                    "PET_IMAGE_MODE": "demo",
                    "PET_MODEL_MODE": "demo",
                    "PET_PUBLIC_URL": "",
                    "STRIPE_WEBHOOK_SECRET": secret,
                    "PET_S3_BUCKET": "",
                },
            ),
            TestClient(app) as client,
        ):
            admin = TestClient(app)
            self.assertEqual(
                admin.post(
                    "/api/auth/login",
                    json={"email": "finance@example.net", "password": "finance-test-only-strong"},
                ).status_code,
                200,
            )
            channel = admin.post(
                "/api/admin/channels",
                json={"name": "结算渠道", "code": "partner2", "commission": 350},
            ).json()
            client.get("/r/partner2", follow_redirects=False)
            user = client.post(
                "/api/auth/register",
                json={"name": "主人", "email": "one@example.net", "password": "a-long-password"},
            ).json()
            pet = client.post("/api/pets", json={"name": "阿毛", "species": "狗"}).json()
            ident = uid("order")
            with database(True) as db:
                db.execute(
                    "INSERT INTO orders(id,user_id,pet_id,kind,amount,candidate_id,photo_ids,request_key,payment_status,generation_status,delivery_status,checkout_id,checkout_url,created_at,payment_channel) VALUES(?,?,?,'portrait',2990,'fixture','[]',?,'unpaid','ready','pending','cs_first','https://checkout.stripe.com/expired',?,'stripe')",
                    (ident, user["id"], pet["id"], uid("request"), now()),
                )
                db.execute("UPDATE orders SET commission=350 WHERE id=?", (ident,))

            def send(event_id, event_type, data, signature=True):
                raw = json.dumps(
                    {"id": event_id, "type": event_type, "data": {"object": data}}
                ).encode()
                stamp = str(int(time.time()))
                mac = hmac.new(
                    secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256
                ).hexdigest()
                return client.post(
                    "/api/payments/webhook",
                    content=raw,
                    headers={"Stripe-Signature": f"t={stamp},v1={mac if signature else 'bad'}"},
                )

            meta = {"metadata": {"order_id": ident}}
            self.assertEqual(
                send(
                    "evt1",
                    "checkout.session.expired",
                    {**meta, "amount_total": 2990, "id": "cs_first"},
                ).status_code,
                200,
            )
            with database() as db:
                o = db.one("SELECT * FROM orders WHERE id=?", (ident,))
            self.assertEqual(o["checkout_url"], "")
            with (
                patch.dict(os.environ, {"PET_PUBLIC_URL": "https://pet.example.net"}),
                patch.object(
                    providers,
                    "create_checkout",
                    return_value={"url": "https://checkout.stripe.com/new", "id": "cs_new"},
                ) as checkout,
            ):
                res = client.post(f"/api/orders/{ident}/pay")
                self.assertEqual(res.status_code, 200, res.text)
                self.assertEqual(checkout.call_args.kwargs["previous_id"], "cs_first")
            data = {
                **meta,
                "payment_status": "paid",
                "currency": "cny",
                "client_reference_id": ident,
                "amount_total": 2990,
                "payment_intent": "pi_fixture",
            }
            self.assertEqual(
                send("evt2", "checkout.session.completed", data, False).status_code, 400
            )
            self.assertEqual(
                send("evt2", "checkout.session.completed", {**data, "amount_total": 1}).status_code,
                409,
            )
            for _ in range(2):
                self.assertEqual(send("evt2", "checkout.session.completed", data).status_code, 200)
            with database() as db:
                o = db.one("SELECT * FROM orders WHERE id=?", (ident,))
                self.assertEqual(o["delivery_status"], "delivered")
                self.assertEqual(db.one("SELECT COUNT(*) AS n FROM payment_events")["n"], 2)
            endpoint = "/api/admin/channels/" + channel["id"] + "/settle"
            self.assertEqual(
                admin.post(endpoint, json={"note": "线下已汇款，核对凭证 #1"}).json()["amount"], 350
            )
            self.assertEqual(admin.post(endpoint, json={"note": "同笔登记"}).status_code, 409)
            refund = {
                **meta,
                "id": "re_1",
                "payment_intent": "pi_fixture",
                "amount": 2990,
                "status": "pending",
            }
            self.assertEqual(send("evt3", "refund.created", refund).status_code, 200)
            self.assertEqual(
                send("evt4", "refund.updated", {**refund, "status": "succeeded"}).status_code, 200
            )
            self.assertEqual(send("evt5", "checkout.session.completed", data).status_code, 200)
            result = client.get("/api/state").json()["orders"][0]
            self.assertEqual(result["payment_status"], "refunded")
            self.assertFalse(result["downloads"])
            account = next(
                c
                for c in admin.get("/api/admin/state").json()["channels"]
                if c["id"] == channel["id"]
            )
            self.assertEqual(account["commission_due"], 0)
            self.assertEqual(account["commission_credit"], 350)
            admin.close()


if __name__ == "__main__":
    unittest.main()
