import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from server import processing_api, storage
from server.db import initialize
from server.demo_model import demo_mesh


class WorkerAPI(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        environment = patch.dict(
            os.environ,
            {
                "PET_NODE_TOKEN": "private-lab-token",
                "PET_DATA_DIR": root.name,
                "PET_S3_BUCKET": "",
                "DATABASE_URL": "",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        app = FastAPI()
        app.include_router(processing_api.router)
        self.http = TestClient(app)
        self.addCleanup(self.http.close)
        self.auth = {"Authorization": "Bearer private-lab-token"}
        self.root = Path(root.name) / "media"
        initialize()

    def test_probes_use_authenticated_storage_path(self):
        path = "/api/processing/probe"
        self.assertEqual(self.http.get(path).status_code, 401)
        sample = self.http.get(path, headers=self.auth)
        self.assertEqual(sample.status_code, 200)
        self.assertEqual(len(sample.content), processing_api.PROBE_BYTES)
        before = list(self.root.iterdir())
        self.assertEqual(
            self.http.put(path, headers=self.auth, content=sample.content).status_code,
            200,
        )
        self.assertEqual(list(self.root.iterdir()), before)
        with patch.dict(os.environ, {"PET_NODE_TOKEN": ""}):
            self.assertEqual(self.http.get(path, headers=self.auth).status_code, 401)

    def test_late_publication_removes_its_private_staged_blob(self):
        glb, stl = demo_mesh()
        glb_key = storage.put(glb, "glb")
        empty = list(self.root.iterdir())
        params = {"node_id": "A", "epoch": 1}
        path = "/api/processing/tasks/job/result"
        with (
            patch.object(
                processing_api.scheduler, "validate", return_value={"glb_key": glb_key}
            ),
            patch.object(
                processing_api.scheduler,
                "complete",
                side_effect=HTTPException(409, "expired"),
            ) as commit,
        ):
            self.assertEqual(
                self.http.put(
                    path, params=params, headers=self.auth, content=b"corrupt"
                ).status_code,
                422,
            )
            self.assertEqual(
                self.http.put(
                    path, params=params, headers=self.auth, content=stl
                ).status_code,
                409,
            )
            self.assertEqual(commit.call_count, 1)
        self.assertEqual(list(self.root.iterdir()), empty)
        self.assertEqual(storage.read(glb_key), glb)

    def test_unauthenticated_and_fenced_sources_never_read_storage(self):
        url = "/api/processing/tasks/job/source/glb?node_id=A&epoch=1"
        with patch.object(storage, "read") as read:
            self.assertEqual(self.http.get(url).status_code, 401)
            with patch.object(
                processing_api.scheduler,
                "validate",
                side_effect=HTTPException(409, "expired"),
            ):
                self.assertEqual(self.http.get(url, headers=self.auth).status_code, 409)
            read.assert_not_called()
