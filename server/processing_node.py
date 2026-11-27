"""Run a model processing worker with `python -m server.processing_node`."""

import json
import logging
import math
import os
import random
import re
import signal
import socket
import struct
import threading
import time
from pathlib import Path

import httpx

from .mesh_files import inspect_stl, stl_from_glb

log = logging.getLogger("tail-journal.node")
MIB = 1024 * 1024
CHUNK = 64 * 1024
PROBE_BYTES = 128 * 1024
MAX_MODEL_BYTES = 200 * MIB


def number(value, minimum=0):
    value = float(value)
    if not math.isfinite(value) or value < minimum:
        raise ValueError("数值配置超出范围")
    return value


class Node:
    def __init__(self, stop):
        coordinator = os.getenv("PET_COORDINATOR_URL", "http://127.0.0.1:8000").rstrip(
            "/"
        )
        token = os.environ["PET_NODE_TOKEN"]
        self.name = os.getenv("PET_NODE_ID", socket.gethostname())
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", self.name) or not token:
            raise ValueError("请配置有效的 PET_NODE_ID 和 PET_NODE_TOKEN")
        self.client = httpx.Client(
            base_url=coordinator + "/api/processing/",
            trust_env=False,
            headers={"Authorization": "Bearer " + token},
            timeout=httpx.Timeout(60, connect=8),
        )
        self.stop = stop
        self.lock = threading.Lock()
        self.active = None
        self.lost = threading.Event()
        self.metrics = {}
        self.heartbeat_interval = number(
            os.getenv("PET_NODE_HEARTBEAT_SECONDS", "2"), 0.05
        )
        self.poll_interval = number(os.getenv("PET_NODE_POLL_SECONDS", "0.35"), 0.02)
        self.max_idle_poll_interval = max(
            self.poll_interval,
            number(os.getenv("PET_NODE_MAX_IDLE_POLL_SECONDS", "2"), 0.02),
        )
        self.probe_interval = number(os.getenv("PET_NODE_PROBE_SECONDS", "10"), 0.1)
        self.limit_file = os.getenv("PET_NODE_LIMIT_FILE")
        self.caps = {
            key: number(os.getenv("PET_" + key.upper(), "0"))
            for key in ("read_mib_s", "write_mib_s")
        }
        self.current_caps = self.caps.copy()

    def cap(self, direction):
        key = direction + "_mib_s"
        if self.limit_file:
            try:
                values = json.loads(Path(self.limit_file).read_text())
                self.current_caps[key] = number(values.get(key, self.caps[key]))
            except (OSError, ValueError, TypeError, AttributeError):
                # Keep the last known cap if the experiment rewrites its file
                # between two chunk reads.
                pass
        return self.current_caps[key]

    def measure(self, name, value):
        # Apply the same exponential smoothing to measured task and idle samples.
        with self.lock:
            self.metrics[name] = min(
                999999, 0.65 * value + 0.35 * self.metrics.get(name, value)
            )

    def json(self, path, **body):
        response = self.client.post(path, json={"node_id": self.name, **body})
        response.raise_for_status()
        return response.json()

    def heartbeat(self):
        with self.lock:
            active = self.active
            fields = self.metrics.copy()
            if active:
                fields.update(job_id=active[0], epoch=active[1])
        reply = self.json("heartbeat", capabilities=["model"], **fields)
        self.heartbeat_interval = min(
            self.heartbeat_interval, reply["lease_seconds"] / 3
        )
        if active and not reply["renewed"]:
            with self.lock:
                if active == self.active:
                    self.lost.set()

    def maintain(self):
        while not self.stop.wait(self.heartbeat_interval):
            try:
                self.heartbeat()
            except httpx.HTTPError as exc:
                log.warning("节点心跳未送达：%s", type(exc).__name__)

    def pace(self, size, direction, started):
        rate = self.cap(direction)
        delay = size / (rate * MIB) - (time.monotonic() - started) if rate > 0 else 0
        if delay > 0:
            self.stop.wait(delay)
        if self.stop.is_set() or self.lost.is_set():
            raise InterruptedError("节点已停止或任务已由其他节点接管")

    def sample_window(self, name, window, transferred):
        # A large in-flight file can span several heartbeats. Report changes
        # observed during this transfer before it finishes.
        started, prior_bytes = window
        now = time.monotonic()
        if now - started >= 1.0:
            self.measure(name, (transferred - prior_bytes) / MIB / (now - started))
            return now, transferred
        return window

    def read(self, path, params=None):
        data = bytearray()
        started = time.monotonic()
        previous = started
        window = (started, 0)
        with self.client.stream("GET", path, params=params) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(CHUNK):
                if len(data) + len(chunk) > MAX_MODEL_BYTES:
                    raise ValueError("模型文件超过传输上限")
                self.pace(len(chunk), "read", previous)
                data.extend(chunk)
                window = self.sample_window("read_mbps", window, len(data))
                previous = time.monotonic()
        elapsed = max(time.monotonic() - started, 0.000001)
        self.measure("read_mbps", len(data) / MIB / elapsed)
        return bytes(data)

    def write(self, path, data, params=None):
        def parts():
            previous = time.monotonic()
            window = (previous, 0)
            for offset in range(0, len(data), CHUNK):
                chunk = data[offset : offset + CHUNK]
                self.pace(len(chunk), "write", previous)
                previous = time.monotonic()
                yield chunk
                window = self.sample_window("write_mbps", window, offset + len(chunk))

        started = time.monotonic()
        response = self.client.put(
            path,
            content=parts(),
            params=params,
            headers={
                "Content-Length": str(len(data)),
                "Content-Type": "application/octet-stream",
            },
        )
        response.raise_for_status()
        elapsed = (
            time.monotonic() - started - response.json().get("finalize_seconds", 0)
        )
        self.measure("write_mbps", len(data) / MIB / max(elapsed, 0.000001))

    def probe(self):
        sample = self.read("probe")
        if len(sample) != PROBE_BYTES:
            raise ValueError("链路探测块不完整")
        self.write("probe", sample)
        self.heartbeat()

    def process(self, task):
        job_id, epoch = task["job_id"], task["epoch"]
        with self.lock:
            self.active = (job_id, epoch)
            self.lost.clear()
        log.info("领取 %s v%s", job_id, epoch)
        params = {"node_id": self.name, "epoch": epoch}
        prefix = f"tasks/{job_id}/"
        try:
            glb = self.read(prefix + "source/glb", params)
            if glb[:4] != b"glTF":
                raise ValueError("模型缺少 GLB 文件头")
            existing = (
                self.read(prefix + "source/stl", params) if task["has_stl"] else None
            )
            started = time.monotonic()
            stl = existing if existing is not None else stl_from_glb(glb)
            if inspect_stl(stl)["faces"] <= 0:
                raise ValueError("模型没有有效的 STL 三角网格")
            self.measure("compute_s", time.monotonic() - started)
            self.write(prefix + "result", stl, params)
            log.info("完成 %s v%s", job_id, epoch)
        except InterruptedError:
            log.info("释放 %s v%s", job_id, epoch)
        except (
            ValueError,
            TypeError,
            OSError,
            LookupError,
            ArithmeticError,
            RuntimeError,
            struct.error,
            httpx.HTTPError,
        ) as exc:
            # Malformed third-party geometry may raise parser-specific errors.
            # Reject this job while keeping the node available for other assets.
            log.warning("处理失败 %s v%s：%s", job_id, epoch, type(exc).__name__)
            if not self.stop.is_set() and not self.lost.is_set():
                try:
                    self.json(
                        prefix + "fail",
                        epoch=epoch,
                        reason="工作节点无法处理模型：" + type(exc).__name__,
                    )
                except httpx.HTTPError:
                    # A lost completion ACK may mean the commit already succeeded.
                    # Fenced failure reports cannot reverse this decision.
                    pass
        finally:
            with self.lock:
                self.active = None
                self.lost.clear()

    def run(self):
        heartbeat_thread = threading.Thread(target=self.maintain, daemon=True)
        heartbeat_thread.start()
        probe_due = 0
        poll_delay = self.poll_interval
        try:
            while not self.stop.is_set():
                try:
                    if time.monotonic() >= probe_due:
                        self.probe()
                        probe_due = time.monotonic() + self.probe_interval
                    task = self.json("claim")["task"]
                    if task:
                        poll_delay = self.poll_interval
                        self.process(task)
                        self.heartbeat()
                        continue
                except (httpx.HTTPError, ValueError, OSError) as exc:
                    log.warning("协调服务暂不可用：%s", type(exc).__name__)
                # Jitter spreads idle requests across nodes without exceeding the cap.
                earliest = max(self.poll_interval, poll_delay * 0.8)
                self.stop.wait(random.uniform(earliest, poll_delay))
                poll_delay = min(poll_delay * 2, self.max_idle_poll_interval)
        finally:
            self.stop.set()
            heartbeat_thread.join()
            self.client.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    Node(stop).run()


if __name__ == "__main__":
    main()
