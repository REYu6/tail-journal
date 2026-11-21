"""Exercise the owner/staff workflow against an isolated database and private blobs."""

import io
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient

from server.app import app
from server.db import database
from server import storage


class BusinessFlow(unittest.TestCase):
    def test_paid_proofs_model_qc_and_customer_privacy(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "PET_DATA_DIR": directory,
                    "DATABASE_URL": os.environ.get("PET_TEST_DATABASE_URL", ""),
                    "PET_ADMIN_EMAIL": "staff@example.org",
                    "PET_ADMIN_PASSWORD": "local-admin-test-secret",
                    "PET_S3_BUCKET": "",
                    "PET_PAYMENT_MODE": "demo",
                    "PET_IMAGE_MODE": "demo",
                    "PET_MODEL_MODE": "demo",
                    "PET_PUBLIC_URL": "",
                },
            ),
            TestClient(app) as owner,
        ):
            admin = TestClient(app)
            stranger = TestClient(app)

            def go(client, path, payload=None, method="post"):
                r = client.request(method, "/api" + path, json=payload)
                self.assertLess(r.status_code, 300, (path, r.text[:500]))
                return r.json()

            def until(key, ident, field, value):
                deadline = time.monotonic() + 14
                while time.monotonic() < deadline:
                    item = next(
                        x for x in go(owner, "/state", method="get")[key] if x["id"] == ident
                    )
                    if item[field] == value:
                        return item
                    time.sleep(0.12)
                self.fail(f"{ident} did not reach {value}: {item}")

            go(
                admin,
                "/auth/login",
                {"email": "staff@example.org", "password": "local-admin-test-secret"},
            )
            ch = go(
                admin,
                "/admin/channels",
                {"code": "store01", "name": "摄影工作室", "commission": 300},
            )
            self.assertEqual(owner.get("/r/store01", follow_redirects=False).status_code, 302)
            go(
                owner,
                "/auth/register",
                {"email": "pet-owner@example.org", "name": "阿黎", "password": "eight-characters"},
            )
            go(
                stranger,
                "/auth/register",
                {"email": "stranger@example.org", "name": "新主人", "password": "eight-characters"},
            )
            self.assertEqual(owner.get("/api/admin/state").status_code, 403)
            p = go(owner, "/pets", {"name": "布丁", "species": "猫", "traits": "右前爪是白的"})
            image = io.BytesIO()
            Image.new("RGB", (640, 520), (180, 140, 118)).save(image, format="JPEG")
            r = owner.post(
                f"/api/pets/{p['id']}/photos",
                files={"file": ("pet.jpg", image.getvalue(), "image/jpeg")},
            )
            self.assertEqual(r.status_code, 200, r.text)
            photo = r.json()
            self.assertEqual(owner.get(photo["original_url"]).content, image.getvalue())
            self.assertEqual(stranger.get(photo["original_url"]).status_code, 404)
            self.assertEqual(stranger.get(photo["url"]).status_code, 404)
            self.assertEqual(
                owner.post(
                    f"/api/pets/{p['id']}/photos",
                    files={"file": ("test.jpg", b"invalid", "image/jpeg")},
                ).status_code,
                422,
            )
            body = {
                "pet_id": p["id"],
                "photo_ids": [photo["id"]],
                "style_id": "watercolor",
                "request_key": "create-proof-1",
            }
            w = go(owner, "/works", body)
            self.assertEqual(go(owner, "/works", body)["id"], w["id"])
            w = until("works", w["id"], "status", "ready")
            self.assertEqual(len(w["candidates"]), 2)
            c = w["candidates"][0]
            preview = owner.get(c["preview_url"]).content
            go(owner, f"/works/{w['id']}/revise", {"feedback": "保留耳尖"})
            w = until("works", w["id"], "status", "ready")
            self.assertEqual(len(w["candidates"]), 3)
            self.assertEqual(
                owner.post(
                    f"/api/works/{w['id']}/revise", json={"feedback": "再做一次"}
                ).status_code,
                409,
            )
            o = go(
                owner, "/orders", {"pet_id": p["id"], "kind": "portrait", "candidate_id": c["id"]}
            )
            self.assertEqual(owner.get("/api/media/portrait/" + o["id"]).status_code, 404)
            paid = go(owner, f"/orders/{o['id']}/pay")["order"]
            self.assertEqual(paid["delivery_status"], "delivered")
            self.assertEqual(
                go(owner, f"/orders/{o['id']}/pay")["order"]["delivery_status"], "delivered"
            )
            original = owner.get(paid["downloads"][0]["url"]).content
            self.assertNotEqual(original, preview)
            self.assertEqual(stranger.get(paid["downloads"][0]["url"]).status_code, 404)
            with database() as db:
                key = db.one("SELECT key FROM candidates WHERE id=?", (c["id"],))["key"]
            storage.remove(key)
            self.assertEqual(owner.get(paid["downloads"][0]["url"]).status_code, 503)
            go(admin, f"/admin/orders/{o['id']}/restore", {"note": "从原任务副本修复"})
            self.assertEqual(owner.get(paid["downloads"][0]["url"]).content, original)
            m = go(
                owner,
                "/orders",
                {
                    "pet_id": p["id"],
                    "kind": "model",
                    "candidate_id": c["id"],
                    "accept_inference": True,
                },
            )
            go(admin, f"/admin/orders/{m['id']}/request-photos", {"note": "请补充一张正脸照"})
            self.assertEqual(owner.post(f"/api/orders/{m['id']}/pay").status_code, 409)
            go(
                owner,
                f"/orders/{m['id']}/supplement",
                {"photo_ids": [photo["id"]], "accept_inference": True},
            )
            go(owner, f"/orders/{m['id']}/pay")
            model = until("orders", m["id"], "delivery_status", "review")
            self.assertTrue(owner.get(model["preview_url"]).content.startswith(b"glTF"))
            self.assertEqual(owner.get("/api/media/stl/" + m["id"]).status_code, 404)
            go(owner, f"/orders/{m['id']}/confirm")
            self.assertEqual(
                go(owner, "/state", method="get")["orders"][0]["delivery_status"], "review"
            )
            delivered = go(admin, f"/admin/orders/{m['id']}/qc", {"note": "已检查模型与切片截面"})
            self.assertEqual(delivered["delivery_status"], "delivered")
            self.assertGreater(len(owner.get(delivered["downloads"][1]["url"]).content), 84)
            sample = go(owner, f"/orders/{m['id']}/sample", {"specs": "8厘米，全彩"})
            go(
                admin,
                f"/admin/samples/{sample['id']}/quote",
                {"quote": 18000, "note": "含运费，实际制作需再次确认"},
            )
            self.assertEqual(
                go(owner, f"/samples/{sample['id']}/respond", {"accept": True})["status"],
                "accepted",
            )
            go(owner, f"/orders/{o['id']}/support", {"message": "需要售后"})
            go(admin, f"/admin/orders/{o['id']}/resolve", {"note": "已与主人沟通"})
            refund = go(admin, f"/admin/orders/{o['id']}/refund", {"note": "客户要求"})
            self.assertEqual(refund["payment_status"], "refunded")
            self.assertEqual(owner.get(paid["downloads"][0]["url"]).status_code, 404)
            dashboard = go(admin, "/admin/state", method="get")
            referred = next(x for x in dashboard["channels"] if x["id"] == ch["id"])
            self.assertEqual(referred["preview_users"], 1)
            self.assertEqual(referred["demo_orders"], 2)
            self.assertEqual(referred["commission_due"], 0)
            self.assertEqual(dashboard["stats"]["revenue"], 0)
            admin.close()
            stranger.close()


if __name__ == "__main__":
    unittest.main()
