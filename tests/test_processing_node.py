import os
import threading
import unittest
from unittest.mock import patch

from server.processing_node import Node


class NodePolling(unittest.TestCase):
    def test_empty_claims_back_off_with_jitter_and_work_resets_the_delay(self):
        stop = threading.Event()
        task = {"job_id": "model-1", "epoch": 1}
        replies = [{"task": None}] * 5 + [{"task": task}, {"task": None}]
        with patch.dict(
            os.environ,
            {
                "PET_NODE_TOKEN": "test-token",
                "PET_NODE_ID": "test-node",
                "PET_NODE_POLL_SECONDS": "0.35",
                "PET_NODE_MAX_IDLE_POLL_SECONDS": "2",
            },
        ):
            node = Node(stop)

        def stop_after_last_reply(_delay):
            if claim.call_count == len(replies):
                stop.set()

        with (
            patch.object(node, "json", side_effect=replies) as claim,
            patch.object(node, "process") as process,
            patch.object(node, "probe"),
            patch.object(node, "heartbeat"),
            patch.object(node, "maintain"),
            patch.object(stop, "wait", side_effect=stop_after_last_reply) as wait,
            patch(
                "server.processing_node.random.uniform", side_effect=lambda low, high: low
            ) as jitter,
        ):
            node.run()

        process.assert_called_once_with(task)
        self.assertEqual(claim.call_count, len(replies))
        bounds = [call.args for call in jitter.call_args_list]
        self.assertEqual([high for _, high in bounds], [0.35, 0.7, 1.4, 2, 2, 0.35])
        self.assertEqual(
            [round(low, 2) for low, _ in bounds], [0.35, 0.56, 1.12, 1.6, 1.6, 0.35]
        )
        self.assertEqual([call.args[0] for call in wait.call_args_list], [low for low, _ in bounds])
