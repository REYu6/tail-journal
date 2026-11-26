"""Exercise assignment, takeover and atomic publication against a real transaction store."""

import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi import HTTPException

from server import scheduler
from server.db import database, initialize, now


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = patch.dict(
            os.environ,
            {
                "PET_DATA_DIR": directory.name,
                "DATABASE_URL": "",
                "PET_ADMIN_EMAIL": "",
                "PET_ADMIN_PASSWORD": "",
                "PET_DISTRIBUTED": "1",
                "PET_TASK_LEASE_SECONDS": "4",
                "PET_NODE_TTL_SECONDS": "3",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        clock = patch("server.scheduler.time.time", return_value=100.0)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        initialize()
        with database(True) as db:
            db.execute(
                "INSERT INTO users VALUES ('owner','a@b','owner','user','hash',?)",
                (now(),),
            )
            db.execute(
                """INSERT INTO pets(id,user_id,name,species,traits,story,occasion,created_at)
                          VALUES ('pet','owner','P','cat','','','',?)""",
                (now(),),
            )

    def seed(self, ident, mib=1):
        with database(True) as db:
            db.execute(
                """INSERT INTO orders(id,user_id,pet_id,kind,amount,photo_ids,request_key,payment_status,
                          generation_status,delivery_status,created_at) VALUES (?,'owner','pet','model',1,'[]',?,
                          'paid','running','pending',?)""",
                (ident, ident, now()),
            )
            db.execute(
                """INSERT INTO jobs(id,target_id,kind,payload,status,stage,external_id,created_at)
                          VALUES(?,?,'model','{}','running','poll','fal:accepted',?)""",
                (ident, ident, now()),
            )
            scheduler.enqueue(db, ident, ident, ident + ".glb", mib * scheduler.MIB)

    def test_fenced_takeover_preserves_cloud_job_and_single_publication(self):
        self.seed("one")
        scheduler.heartbeat("A")
        first = scheduler.claim("A")
        self.assertIsNone(scheduler.claim("A"))
        self.clock.return_value = 103
        self.assertTrue(
            scheduler.heartbeat("A", job_id="one", epoch=first["epoch"])["renewed"]
        )
        self.clock.return_value = 108
        self.assertFalse(
            scheduler.heartbeat("B", job_id="one", epoch=first["epoch"])["renewed"]
        )
        with self.assertRaises(HTTPException):
            scheduler.complete("A", "one", first["epoch"], "stale.stl")
        second = scheduler.claim("B")
        self.assertGreater(second["epoch"], first["epoch"])
        self.assertFalse(
            scheduler.heartbeat("A", job_id="one", epoch=first["epoch"])["renewed"]
        )
        with self.assertRaises(HTTPException):
            scheduler.fail("A", "one", first["epoch"], "旧节点")
        scheduler.complete("B", "one", second["epoch"], "confirmed.stl")
        with self.assertRaises(HTTPException):
            scheduler.complete("B", "one", second["epoch"], "duplicate.stl")
        with database() as db:
            self.assertEqual(
                db.one("SELECT stl_key FROM orders")["stl_key"], "confirmed.stl"
            )
            self.assertEqual(
                db.one("SELECT status,external_id FROM jobs"),
                {"status": "done", "external_id": "fal:accepted"},
            )
        events = scheduler.snapshot()["events"]
        self.assertEqual(sum(e["event"] == "completed" for e in events), 1)
        self.assertEqual(sum(e["event"] == "expired" for e in events), 1)
        self.assertEqual(sum(e["event"] == "takeover" for e in events), 1)

    def test_size_and_measured_bandwidth_change_dispatch(self):
        scheduler.heartbeat("B", read_mbps=20, write_mbps=20, compute_s=4)
        self.seed("first")
        self.assertEqual(scheduler.claim("B")["job_id"], "first")
        scheduler.heartbeat("A", read_mbps=2, write_mbps=2, compute_s=1)
        self.seed("small", 1)
        self.seed("large", 40)
        small = scheduler.claim("A")
        self.assertEqual(small["job_id"], "small")
        tasks = {x["job_id"]: x for x in scheduler.snapshot()["tasks"]}
        self.assertEqual(tasks["large"]["node_id"], "B")
        scheduler.heartbeat("B", read_mbps=0.1, write_mbps=0.1, compute_s=4)
        scheduler.complete("A", "small", small["epoch"], "ready.stl")
        self.assertEqual(scheduler.claim("A")["job_id"], "large")

    def test_competing_claims_and_revoked_order(self):
        self.seed("one")
        scheduler.heartbeat("A")
        with ThreadPoolExecutor(max_workers=2) as pool:
            grants = list(pool.map(scheduler.claim, ["A", "A"]))
        self.assertEqual(sum(bool(g) for g in grants), 1)
        with database(True) as db:
            db.execute(
                "UPDATE orders SET payment_status='refunded',delivery_status='refunded'"
            )
        with self.assertRaises(HTTPException):
            scheduler.complete("A", "one", 1, "refunded.stl")
        self.assertFalse(scheduler.heartbeat("A", job_id="one", epoch=1)["renewed"])
        self.assertIsNone(scheduler.claim("A"))
        self.assertEqual(scheduler.snapshot()["tasks"][0]["status"], "stopped")

    def test_finite_retries_and_operator_recovery(self):
        self.seed("one")
        scheduler.heartbeat("A")
        for epoch in range(1, scheduler.MAX_FAILURES + 1):
            grant = scheduler.claim("A")
            self.assertEqual(grant["epoch"], epoch)
            scheduler.fail("A", "one", epoch, "读取异常")
        self.assertIsNone(scheduler.claim("A"))
        with database(True) as db:
            self.assertTrue(scheduler.retry(db, "one"))
        grant = scheduler.claim("A")
        self.assertGreater(grant["epoch"], scheduler.MAX_FAILURES)
        self.assertEqual(grant["glb_key"], "one.glb")

    def test_round_robin_and_shortest_queue_balance(self):
        scheduler.heartbeat("A")
        scheduler.heartbeat("B")
        for policy in ("round_robin", "shortest_queue"):
            scheduler.set_policy(policy)
            self.seed(policy + "-1")
            self.seed(policy + "-2")
            assigned = [scheduler.claim("A"), scheduler.claim("B")]
            self.assertEqual(len({g["job_id"] for g in assigned}), 2)
            for who, grant in zip(("A", "B"), assigned):
                scheduler.complete(who, grant["job_id"], grant["epoch"], "done.stl")

    def test_node_capability_and_idempotent_dispatch(self):
        scheduler.heartbeat("A")
        self.seed("a")
        self.seed("b")
        self.assertEqual(scheduler.claim("A")["job_id"], "a")
        scheduler.complete("A", "a", 1, "a.stl")
        scheduler.heartbeat("A", capabilities=[])
        self.assertIsNone(scheduler.claim("A"))
        # Duplicate delivery of the provider receipt must neither reopen completed
        # work nor replace the input that a queued task will use after a restart.
        with database(True) as db:
            for ident in ("a", "b"):
                scheduler.enqueue(db, ident, ident, "wrong.glb", 123)
        scheduler.heartbeat("B")
        grant = scheduler.claim("B")
        self.assertEqual((grant["job_id"], grant["glb_key"]), ("b", "b.glb"))
        self.assertEqual(len(scheduler.snapshot()["tasks"]), 2)
