"""Run the scheduling experiments over loopback HTTP with two isolated worker processes."""

import argparse
import hashlib
import json
import math
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import trimesh

from server import scheduler, storage
from server.db import database, initialize, now
from server.mesh_files import stl_from_glb

ROOT = Path(__file__).resolve().parents[1]
MESHES = {"small": "sample-cat.glb", "large": "studio-corgi.glb"}
BATCH = ("large", "small", "large", "small", "small", "large", "large", "small")
INTERVAL = 0.18
WORKERS = ("worker-a", "worker-b")


@dataclass(frozen=True)
class Mesh:
    key: str
    size: int
    stl: bytes


def wait_for(check, description, timeout=40):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = check()
        if result:
            return result
        time.sleep(0.05)
    raise RuntimeError(f"等待超时：{description}")


def set_limit(path, read_rate, write_rate):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"read_mib_s": read_rate, "write_mib_s": write_rate}))
    temp.replace(path)


def stop_process(process):
    if process.poll() is None:
        if hasattr(signal, "SIGCONT"):
            process.send_signal(signal.SIGCONT)
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class Cluster:
    def __init__(self, directory, url, token):
        self.directory = directory
        self.url = url
        self.token = token
        self.meshes = {}
        self.processes = {}
        self.sequence = 0

    def spawn(self, stack, name, args, env):
        output = stack.enter_context((self.directory / f"{name}.log").open("w"))
        process = subprocess.Popen(
            [sys.executable, "-m", *args],
            cwd=ROOT,
            env={**os.environ, **env},
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        self.processes[name] = process
        stack.callback(stop_process, process)

    def check_processes(self):
        for name, process in self.processes.items():
            if process.poll() is not None:
                raise RuntimeError(
                    f"{name} exited: "
                    + (self.directory / f"{name}.log").read_text()[-1800:]
                )

    def snapshot(self):
        self.check_processes()
        return scheduler.snapshot()

    def tasks(self):
        return {t["job_id"]: t for t in self.snapshot()["tasks"]}

    def add(self, size):
        mesh = self.meshes[size]
        self.sequence += 1
        ident = f"lab-{self.sequence:03d}-{size}"
        with database(True) as db:
            db.execute(
                """INSERT INTO orders(id,user_id,pet_id,kind,amount,photo_ids,request_key,
                payment_status,generation_status,delivery_status,created_at)
                VALUES(?,'owner','pet','model',0,'[]',?,'paid','running','pending',?)""",
                (ident, ident, now()),
            )
            db.execute(
                """INSERT INTO jobs(id,target_id,kind,payload,status,stage,external_id,created_at)
                VALUES(?,?,'model','{}','processing','postprocess','lab:completed',?)""",
                (ident, ident, now()),
            )
            scheduler.enqueue(db, ident, ident, mesh.key, mesh.size)
        return ident

    def completed(self, ids):
        def check():
            tasks = self.tasks()
            found = [tasks.get(ident, {}) for ident in ids]
            if any(t.get("status") in {"failed", "stopped"} for t in found):
                raise RuntimeError(f"任务失败：{found}")
            return (
                found
                if all(t.get("finished") and t.get("status") == "done" for t in found)
                else None
            )

        return wait_for(check, f"任务完成 {ids}", timeout=120)

    def verify_order(self, ident):
        size = ident.rsplit("-", 1)[1]
        mesh = self.meshes[size]
        with database() as db:
            row = db.one(
                "SELECT generation_status,preview_key,stl_key FROM orders WHERE id=?",
                (ident,),
            )
        if row["generation_status"] != "ready" or row["preview_key"] != mesh.key:
            raise RuntimeError(f"订单交付未正确关联：{ident}")
        output = storage.read(row["stl_key"])
        if output != mesh.stl:
            raise RuntimeError(f"STL 与顺序执行的转换结果不一致：{ident}")
        return row["stl_key"]

    def rates(self):
        return {
            n["node_id"]: n["read_mbps"]
            for n in self.snapshot()["nodes"]
            if n["online"]
        }


@contextmanager
def cluster(policy, limits):
    with (
        tempfile.TemporaryDirectory(prefix="tail-network-lab-") as tmp,
        ExitStack() as stack,
    ):
        directory = Path(tmp)
        token = secrets.token_urlsafe(32)
        isolated = {
            "PET_DATA_DIR": str(directory / "data"),
            "DATABASE_URL": "",
            "PET_S3_BUCKET": "",
            "PET_ADMIN_EMAIL": "",
            "PET_ADMIN_PASSWORD": "",
            "PET_MODEL_MODE": "demo",
            "PET_IMAGE_MODE": "demo",
            "PET_PAYMENT_MODE": "demo",
            "PET_DISTRIBUTED": "1",
            "PET_NODE_TOKEN": token,
            "PET_TASK_LEASE_SECONDS": "3",
            "PET_NODE_TTL_SECONDS": "2",
            "PET_NODE_HEARTBEAT_SECONDS": "0.3",
            "PET_NODE_POLL_SECONDS": "0.08",
            "PET_NODE_PROBE_SECONDS": "0.9",
            "PET_COOKIE_SECURE": "false",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
        }
        stack.enter_context(patch.dict(os.environ, isolated))
        initialize()
        scheduler.set_policy(policy)
        with database(True) as db:
            db.execute(
                "INSERT INTO users VALUES ('owner','owner@lab.invalid','课设','owner','',?)",
                (now(),),
            )
            db.execute(
                """INSERT INTO pets(id,user_id,name,species,traits,story,occasion,created_at)
                VALUES ('pet','owner','演示宠物','cat','','','',?)""",
                (now(),),
            )
        # Reserve an ephemeral port before spawn and pass the actual socket to uvicorn.
        listener = stack.enter_context(socket.socket())
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        lab = Cluster(directory, url, token)
        for size, filename in MESHES.items():
            data = (ROOT / "web" / "public" / "media" / filename).read_bytes()
            lab.meshes[size] = Mesh(
                storage.put(data, "glb"), len(data), stl_from_glb(data)
            )
        output = stack.enter_context((directory / "coordinator.log").open("w"))
        fd = listener.fileno()
        coordinator = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "server.app:app",
                "--fd",
                str(fd),
                "--no-access-log",
            ],
            pass_fds=(fd,),
            cwd=ROOT,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        lab.processes["coordinator"] = coordinator
        stack.callback(stop_process, coordinator)

        def healthy():
            lab.check_processes()
            try:
                with urllib.request.urlopen(
                    url + "/api/health", timeout=0.5
                ) as response:
                    return response.status == 200
            except (OSError, TimeoutError):
                return False

        wait_for(healthy, "协调器启动")
        listener.close()
        for name, (read_rate, write_rate) in zip(WORKERS, limits, strict=True):
            path = directory / f"{name}.json"
            set_limit(path, read_rate, write_rate)
            lab.spawn(
                stack,
                name,
                ["server.processing_node"],
                {
                    "PET_COORDINATOR_URL": url,
                    "PET_NODE_ID": name,
                    "PET_NODE_LIMIT_FILE": str(path),
                },
            )
        wait_for(lambda: set(lab.rates()) == set(WORKERS), "两台工作节点上线")
        yield lab


def batch(policy):
    with cluster(policy, ((1, 2), (6, 12))) as lab:
        wait_for(
            lambda: lab.rates()["worker-b"] > lab.rates()["worker-a"] * 2,
            "初始链路采样",
        )
        t0 = time.monotonic()
        ids = []
        for i, size in enumerate(BATCH):
            time.sleep(max(0, t0 + i * INTERVAL - time.monotonic()))
            ids.append(lab.add(size))
        tasks = lab.completed(ids)
        for task in tasks:
            lab.verify_order(task["job_id"])
        durations = sorted(t["finished"] - t["created"] for t in tasks)
        return {
            "policy": policy,
            "jobs": len(tasks),
            "batch_s": round(
                max(t["finished"] for t in tasks) - min(t["created"] for t in tasks), 3
            ),
            "p95_s": round(durations[math.ceil(len(tasks) * 0.95) - 1], 3),
            "assignments": [t["node_id"] for t in tasks],
        }


def network_change():
    with cluster("adaptive", ((2, 8), (8, 16))) as lab:

        def rates_match(fast):
            rates = lab.rates()
            a, b = (rates[n] for n in WORKERS)
            if fast and b > a * 1.45 or not fast and b < a * 0.75:
                return {n: round(r, 3) for n, r in rates.items()}
            return None

        phases = []
        for phase, rate in (("initial", 8), ("limited", 0.7), ("restored", 8)):
            if phase != "initial":
                # Apply the link change while this independent transfer is still owned.
                marker = lab.add("large")
                wait_for(
                    lambda marker=marker: (
                        lab.tasks()[marker].get("status") == "running"
                    ),
                    "切换限速时有任务执行",
                )
            started = time.monotonic()
            change_wall_time = time.time()
            set_limit(lab.directory / "worker-b.json", rate, 16 if rate > 1 else 1.5)
            if phase != "initial":
                lab.completed([marker])
            observed = wait_for(
                lambda fast=rate > 1: rates_match(fast),
                f"{phase}：有效吞吐更新",
                timeout=70,
            )
            elapsed = time.monotonic() - started
            # One outstanding job at a time isolates link preference from queue pressure.
            decisions = {}
            for size in ("small", "large"):
                task = lab.completed([lab.add(size)])[0]
                lab.verify_order(task["job_id"])
                decisions[size] = task["node_id"]
            phases.append(
                {
                    "phase": phase,
                    "B_read_cap_mib_s": rate,
                    "observed_mib_s": observed,
                    "observed_after_s": round(elapsed, 3),
                    "large_claim_after_s": round(task["started"] - change_wall_time, 3),
                    "decisions": decisions,
                }
            )
        initial, limited, restored = (phase["decisions"]["large"] for phase in phases)
        if initial == limited or initial != restored:
            raise RuntimeError(f"大模型分配未随链路切换并恢复：{phases}")
        return phases


def failover():
    with cluster("adaptive", ((1.5, 3), (3, 6))) as lab:
        ident = lab.add("large")

        def running():
            row = lab.tasks()[ident]
            return row if row["status"] == "running" else None

        first = wait_for(running, "首个节点领取任务")
        dead, old_epoch = first["node_id"], first["epoch"]
        old = lab.processes[dead]
        old.send_signal(signal.SIGSTOP)
        started = time.monotonic()
        try:

            def reclaimed():
                row = lab.tasks()[ident]
                return (
                    row
                    if row["node_id"] != dead
                    and row["epoch"] > old_epoch
                    and row["status"] in {"running", "done"}
                    else None
                )

            second = wait_for(reclaimed, "另一节点接管")
            recovery = time.monotonic() - started
            old.send_signal(signal.SIGCONT)
            # Replay a stale, structurally valid small STL while the new node is working.
            # A short body lets the HTTP client read the rejection on the wire even if
            # the server rejects the headers before it reads any upload bytes.
            request = urllib.request.Request(
                f"{lab.url}/api/processing/tasks/{ident}/result?node_id={dead}&epoch={old_epoch}",
                data=trimesh.creation.box().export(file_type="stl"),
                method="PUT",
                headers={
                    "Authorization": f"Bearer {lab.token}",
                    "Content-Type": "model/stl",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    status = response.status
            except urllib.error.HTTPError as exc:
                status = exc.code
            if status != 409:
                raise RuntimeError(f"过期节点写回没有被拒绝：HTTP {status}")
            final = lab.completed([ident])[0]
            lab.verify_order(ident)
            published = [
                e
                for e in lab.snapshot()["events"]
                if e["job_id"] == ident and e["event"] == "completed"
            ]
            if len(published) != 1 or published[0]["epoch"] != second["epoch"]:
                raise RuntimeError(f"订单有效发布记录异常：{published}")
            return {
                "completed_events": len(published),
                "original": dead,
                "original_epoch": old_epoch,
                "successor": second["node_id"],
                "successor_epoch": final["epoch"],
                "recovery_s": round(recovery, 3),
                "stale_put_status": status,
                "verified_stl_sha256": hashlib.sha256(
                    lab.meshes["large"].stl
                ).hexdigest(),
            }
        finally:
            old.send_signal(signal.SIGCONT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", choices=["all", "batch", "network", "failover"], default="all"
    )
    parser.add_argument("--output", type=Path, help="write JSON measurements")
    parser.add_argument(
        "--repeats", type=int, default=1, help="rounds per batch policy"
    )
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    measurements = {}
    if args.scenario in {"all", "batch"}:
        measurements["batch"] = []
        for _ in range(args.repeats):
            for policy in ("round_robin", "shortest_queue", "adaptive"):
                result = batch(policy)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                measurements["batch"].append(result)
    if args.scenario in {"all", "network"}:
        measurements["network"] = network_change()
        print(json.dumps(measurements["network"], ensure_ascii=False), flush=True)
    if args.scenario in {"all", "failover"}:
        measurements["failover"] = failover()
        print(json.dumps(measurements["failover"], ensure_ascii=False), flush=True)
    if args.output:
        args.output.write_text(
            json.dumps(measurements, indent=2, ensure_ascii=False) + "\n"
        )


if __name__ == "__main__":
    main()
