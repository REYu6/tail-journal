"""A restart between sending a billable job and recording its ID is ambiguous."""

import os
import tempfile
import unittest
from unittest.mock import patch

from server import worker
from server.db import database, initialize, now, pack, uid


class JobRecovery(unittest.TestCase):
    def test_restart_does_not_repeat_billable_submission(self):
        with (
            tempfile.TemporaryDirectory() as root,
            patch.dict(
                os.environ,
                {
                    "PET_DATA_DIR": root,
                    "DATABASE_URL": "",
                    "PET_ADMIN_EMAIL": "",
                    "PET_ADMIN_PASSWORD": "",
                    "PET_IMAGE_MODE": "demo",
                    "PET_MODEL_MODE": "demo",
                    "PET_S3_BUCKET": "",
                },
            ),
        ):
            initialize()
            ident = uid("job")
            with database(True) as db:
                db.execute(
                    "INSERT INTO jobs(id,target_id,kind,payload,status,stage,lease,created_at) VALUES(?,?,?,?,'running','submitting',0,?)",
                    (ident, uid("work"), "portrait", pack({}), now()),
                )
            with patch.object(worker.providers, "submit_model") as submit:
                self.assertFalse(worker.step())
                self.assertFalse(worker.step())
                submit.assert_not_called()
            with database() as db:
                self.assertEqual(
                    db.one("SELECT status FROM jobs WHERE id=?", (ident,))["status"], "uncertain"
                )
