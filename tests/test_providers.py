"""Offline contract tests for the provider boundaries and printable demo files."""
import hashlib
import hmac
import io
import json
import os
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from server import providers, storage
from server.demo_model import demo_mesh
from server.mesh_files import inspect_stl, stl_from_glb


def photo():
    image = Image.new("RGB", (640, 480), "#89a993")
    brush = ImageDraw.Draw(image)
    brush.ellipse((150, 80, 530, 430), fill="#b8784a")
    brush.ellipse((230, 200, 260, 235), fill="#403633")
    return storage.jpeg(image)


class ProviderContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        environment = patch.dict(os.environ, {
            "PET_DATA_DIR": self.temp.name, "PET_S3_BUCKET": "", "PET_IMAGE_MODE": "demo",
            "PET_MODEL_MODE": "demo", "PET_PAYMENT_MODE": "demo",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.photo = photo()
        self.photo_key = storage.put(self.photo, "jpg")

    def test_private_files_and_preview_are_distinct(self):
        with self.assertRaises(ValueError):
            storage.read("../other_user/photo.jpg")
        with self.assertRaises(ValueError):
            storage.normalize_photo(b"not an image")
        task = providers.submit_model("portrait", [self.photo_key], "keep the eyes", "水彩", 2)
        results = providers.poll_model("portrait", task)
        self.assertEqual(len(results["outputs"]), 2)
        first, second = (storage.read(x["key"]) for x in results["outputs"])
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, self.photo)
        self.assertNotEqual(storage.preview_image(first), first)
        self.assertEqual(results, providers.poll_model("portrait", task))

    def test_demo_is_watertight_and_open_mesh_fails(self):
        glb, stl = demo_mesh()
        report = inspect_stl(stl)
        self.assertTrue(report["passed"])
        self.assertGreater(report["faces"], 1000)
        fallback = inspect_stl(stl_from_glb(glb))
        self.assertTrue(fallback["passed"])
        self.assertAlmostEqual(fallback["height_mm"], 80, places=1)
        count = struct.unpack("<I", stl[80:84])[0]
        opened = stl[:80] + struct.pack("<I", count - 1) + stl[84:-50]
        self.assertFalse(inspect_stl(opened)["passed"])

    @patch.dict(os.environ, {"DASHSCOPE_API_KEY":"test-key"})
    def test_dashscope_async_submit_and_retrieve(self):
        os.environ["PET_IMAGE_MODE"] = "live"
        with patch.object(providers, "_json", return_value={"output":{"task_id":"example-id"}}) as call:
            task = providers.submit_model("portrait", [self.photo_key], "preserve patterns", "gouache", 2)
        url, headers, body = call.call_args.args
        self.assertIn("/services/aigc/image-generation/generation", url)
        self.assertEqual(headers["X-DashScope-Async"], "enable")
        self.assertTrue(body["input"]["messages"][0]["content"][0]["image"].startswith("data:image/jpeg"))
        self.assertEqual(body["parameters"]["n"], 2)
        completed = {"output":{"task_status":"SUCCEEDED","choices":[{"message":{"content":[{"image":"https://a.aliyuncs.com/out.jpg"}]}}]}}
        with patch.object(providers, "_json", side_effect=[{"output":{"task_status":"RUNNING"}}, completed]), patch.object(providers, "_download", return_value=self.photo):
            self.assertEqual(providers.poll_model("portrait", task)["status"], "pending")
            final = providers.poll_model("portrait", task)
        self.assertEqual(final["status"], "succeeded")
        self.assertEqual(storage.open_photo(storage.read(final["outputs"][0]["key"])).size, (640, 480))

    @patch.dict(os.environ, {"FAL_KEY":"test-key"})
    def test_fal_multi_and_glb_only_fallback(self):
        os.environ["PET_MODEL_MODE"] = "live"
        with patch.object(providers, "_json", return_value={"request_id":"example-id",
                "response_url":"https://queue.fal.run/fal-ai/meshy/requests/example-id"}) as call:
            task = providers.submit_model("model",[self.photo_key,self.photo_key],"ginger")
        self.assertIn("multi-image-to-3d", call.call_args.args[0])
        self.assertEqual(len(call.call_args.args[2]["image_urls"]), 2)
        with patch.object(providers,"_json",side_effect=[{"status":"COMPLETED"},{"model_glb":{"url":"https://v3.fal.media/mock.glb"}}]), patch.object(providers, "_download",return_value=demo_mesh()[0]):
            files = providers.poll_model("model", task)["outputs"]
        self.assertEqual([item["kind"] for item in files], ["glb","stl"])
        self.assertTrue(inspect_stl(storage.read(files[1]["key"]))["passed"])

    @patch.dict(os.environ, {"PET_PAYMENT_MODE":"stripe","STRIPE_WEBHOOK_SECRET":"secret"})
    def test_webhook_requires_authentic_recent_paid_cny_event(self):
        details = {"client_reference_id":"order_1","metadata":{"order_id":"order_1"},
                   "payment_status":"paid","currency":"cny","amount_total":2990,"payment_intent":"pi_demo"}
        def event(obj, age=0):
            body = json.dumps({"id":"evt_test","type":"checkout.session.completed","data":{"object":obj}}).encode()
            ts = str(int(time.time()) - age)
            signature = hmac.new(b"secret",ts.encode()+b"."+body,hashlib.sha256).hexdigest()
            return body, f"t={ts},v1={signature}"
        payload, sig = event(details)
        result = providers.verify_payment(payload, sig)
        self.assertEqual((result["order_id"],result["amount_fen"]), ("order_1",2990))
        self.assertEqual(providers.verify_payment(*event({**details,"payment_status":"unpaid"})), {})
        self.assertEqual(providers.verify_payment(*event({**details,"currency":"usd"})), {})
        with self.assertRaises(ValueError):
            providers.verify_payment(*event(details, age=900))
        with self.assertRaises(ValueError):
            providers.verify_payment(payload+b" ", sig)

    @patch.dict(os.environ, {"PET_PAYMENT_MODE":"stripe","STRIPE_WEBHOOK_SECRET":"secret"})
    def test_checkout_and_refund_idempotency_and_pending(self):
        with patch.object(providers,"_stripe",return_value={"id":"cs_abc","url":"https://checkout.stripe.com/c/pay/cs_abc"}) as call:
            providers.create_checkout("order_a",9900,"3D", "https://company.example/orders", previous_id="cs_old")
        _, fields, key = call.call_args.args
        self.assertEqual(key,"pet-checkout-order_a-cs_old")
        self.assertEqual(fields["line_items[0][price_data][unit_amount]"], "9900")
        with patch.object(providers,"_stripe",return_value={"status":"pending","id":"re_abc"}):
            with self.assertRaises(providers.PaymentPending) as captured:
                providers.refund_payment("pi_abc",9900,"order_a")
        self.assertEqual(captured.exception.refund_id, "re_abc")

    def test_failed_live_configuration_never_falls_back_to_demo(self):
        with patch.dict(os.environ, {"PET_IMAGE_MODE":"live","DASHSCOPE_API_KEY":""}):
            with self.assertRaises(providers.ProviderError):
                providers.submit_model("portrait", [self.photo_key], "keep the eyes")
        with self.assertRaises(providers.ProviderError):
            providers.refund_payment("pi_real",2990,"order_test")


if __name__ == "__main__":
    unittest.main()
