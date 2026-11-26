"""One paid demo order crosses the actual owner, operator and worker HTTP boundaries."""

import io
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from server import worker
from server.app import app
from server.db import database, initialize
from server.mesh_files import inspect_stl
from server.processing_node import Node


class DistributedOrder(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = patch.dict(
            os.environ,
            {
                "PET_DATA_DIR": directory.name,
                "DATABASE_URL": "",
                "PET_S3_BUCKET": "",
                "PET_MODEL_MODE": "demo",
                "PET_IMAGE_MODE": "demo",
                "PET_PAYMENT_MODE": "demo",
                "PET_PUBLIC_URL": "",
                "PET_COOKIE_SECURE": "",
                "PET_DISTRIBUTED": "1",
                "PET_NODE_TOKEN": "course-test-token",
                "PET_NODE_ID": "printer-a",
                "PET_READ_MIB_S": "0",
                "PET_WRITE_MIB_S": "0",
                "PET_NODE_LIMIT_FILE": "",
                "PET_ADMIN_EMAIL": "studio@example.org",
                "PET_ADMIN_PASSWORD": "local-admin-test-secret",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        # Drive the ordinary worker one stage at a time, without a background polling race.
        initialize()
        self.owner = self.client()
        self.staff = self.client()
        self.operator = self.client()
        self.submit(
            self.owner,
            "/api/auth/register",
            {"name": "阿麦", "email": "owner@example.org", "password": "owner-pass"},
        )
        self.submit(
            self.staff,
            "/api/auth/login",
            {"email": "studio@example.org", "password": "local-admin-test-secret"},
        )
        account = self.submit(
            self.operator,
            "/api/auth/register",
            {
                "name": "测试运营",
                "email": "operator@example.org",
                "password": "operator-pass",
            },
        )
        self.submit(
            self.staff, f"/api/admin/users/{account['id']}/role", {"role": "operator"}
        )

    def client(self, **kwargs):
        client = TestClient(app, **kwargs)
        self.addCleanup(client.close)
        return client

    def submit(self, client, path, payload=None):
        response = client.post(path, json=payload)
        self.assertEqual(response.status_code, 200, response.text[:500])
        return response.json()

    def test_private_scheduler_and_controlled_policy_changes(self):
        url = "/api/admin/scheduler"
        policy = {"policy": "shortest_queue"}
        anonymous = self.client()
        self.assertEqual(anonymous.get(url).status_code, 401)
        self.assertEqual(self.owner.get(url).status_code, 403)
        self.assertEqual(self.owner.post(url + "/policy", json=policy).status_code, 403)
        self.assertEqual(self.operator.get(url).status_code, 200)
        self.assertEqual(
            self.operator.post(url + "/policy", json=policy).status_code, 403
        )
        self.assertEqual(self.submit(self.staff, url + "/policy", policy), policy)
        self.assertEqual(self.operator.get(url).json()["policy"], "shortest_queue")
        self.assertEqual(
            self.staff.post(
                "/api/processing/claim", json={"node_id": "printer-a"}
            ).status_code,
            401,
        )

    def test_model_order_from_payment_through_printable_delivery(self):
        pet = self.submit(self.owner, "/api/pets", {"name": "麦芽", "species": "猫"})
        image = io.BytesIO()
        Image.new("RGB", (120, 100), "tan").save(image, "JPEG")
        photo = self.owner.post(
            f"/api/pets/{pet['id']}/photos",
            files={"file": ("cat.jpg", image.getvalue(), "image/jpeg")},
        )
        self.assertEqual(photo.status_code, 200)
        order = self.submit(
            self.owner,
            "/api/orders",
            {
                "pet_id": pet["id"],
                "kind": "model",
                "photo_ids": [photo.json()["id"]],
                "accept_inference": True,
            },
        )
        ident = order["id"]
        self.assertTrue(self.submit(self.owner, f"/api/orders/{ident}/pay")["demo"])
        self.assertTrue(worker.step())
        with database() as db:
            job = db.one(
                "SELECT id,external_id,stage FROM jobs WHERE target_id=?", (ident,)
            )
        self.assertTrue(job["external_id"].startswith("demo:"))
        self.assertEqual(job["stage"], "poll")
        self.assertTrue(worker.step())
        self.assertFalse(worker.step())

        # Run the same command-line worker methods and its measurement / task protocol
        # against an in-process HTTP transport. Only the network transport is replaced.
        node = Node(threading.Event())
        node.client.close()
        node.client = self.client(
            base_url="http://testserver/api/processing/",
            headers={"Authorization": "Bearer course-test-token"},
        )
        node.probe()
        task = node.json("claim")["task"]
        self.assertEqual(task["job_id"], job["id"])
        self.assertFalse(task["has_stl"])
        node.process(task)
        node.heartbeat()
        self.assertIsNone(node.json("claim")["task"])
        self.assertEqual(set(node.metrics), {"read_mbps", "write_mbps", "compute_s"})
        with database() as db:
            self.assertEqual(
                db.one("SELECT external_id,status FROM jobs WHERE id=?", (job["id"],)),
                {
                    "external_id": job["external_id"],
                    "status": "done",
                },
            )
        review = self.owner.get("/api/state").json()["orders"][0]
        self.assertEqual(review["delivery_status"], "review")
        self.assertTrue(
            self.owner.get(review["preview_url"]).content.startswith(b"glTF")
        )
        self.assertEqual(self.owner.get(f"/api/media/stl/{ident}").status_code, 404)
        self.submit(self.owner, f"/api/orders/{ident}/confirm")
        delivered = self.submit(
            self.operator, f"/api/admin/orders/{ident}/qc", {"note": "已复核截面"}
        )
        self.assertEqual(delivered["delivery_status"], "delivered")
        stl = self.owner.get(f"/api/media/stl/{ident}")
        self.assertEqual(stl.status_code, 200)
        self.assertTrue(inspect_stl(stl.content)["passed"])
        history = self.staff.get("/api/admin/scheduler").json()
        self.assertEqual(history["tasks"][0]["status"], "done")
        self.assertEqual(sum(e["event"] == "completed" for e in history["events"]), 1)
