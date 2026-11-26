"""Coordinate the post-inference mesh pipeline. Only the coordinator opens this database."""

import json
import math
import os
import time

from fastapi import HTTPException

from .db import database, pack, setting, uid

POLICIES = ("adaptive", "round_robin", "shortest_queue")
MIB = 1024 * 1024
MAX_FAILURES = 3


def _seconds(name, default):
    value = float(os.getenv(name, str(default)))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _lease_seconds():
    return _seconds("PET_TASK_LEASE_SECONDS", 15)


def _online_cutoff(t):
    return t - _seconds("PET_NODE_TTL_SECONDS", 12)


def _event(db, job, node, epoch, event, detail, t):
    db.execute(
        """INSERT INTO processing_events(id,job_id,node_id,epoch,event,at,detail)
           VALUES(?,?,?,?,?,?,?)""",
        (uid("event"), job, node, epoch, event, t, detail),
    )


def enqueue(db, job_id, target_id, glb_key, input_bytes, stl_key=""):
    """In the same transaction, park the original provider job and retain its immutable input."""
    if input_bytes <= 0:
        raise ValueError("GLB 文件为空")
    t = time.time()
    inserted = db.execute(
        """INSERT INTO processing_tasks(job_id,target_id,glb_key,stl_key,input_bytes,status,created)
           VALUES(?,?,?,?,?,'queued',?) ON CONFLICT(job_id) DO NOTHING""",
        (job_id, target_id, glb_key, stl_key, input_bytes, t),
    ).rowcount
    if inserted:
        db.execute(
            "UPDATE jobs SET stage='postprocess',status='running',lease=0 WHERE id=?",
            (job_id,),
        )
        _event(db, job_id, "", 0, "enqueued", "模型已就绪，等待可用节点", t)


def retry(db, job_id):
    task = db.one(
        "SELECT * FROM processing_tasks WHERE job_id=? AND status='failed'", (job_id,)
    )
    if not task:
        return False
    db.execute(
        """UPDATE processing_tasks SET status='queued',failures=0,node_id='',lease=0,started=NULL,
           finished=NULL,reason='运营恢复',estimate_s=0 WHERE job_id=?""",
        (job_id,),
    )
    db.execute(
        "UPDATE jobs SET status='running',stage='postprocess',lease=0,attempts=0,error='' WHERE id=?",
        (job_id,),
    )
    db.execute(
        "UPDATE orders SET generation_status='running' WHERE id=?", (task["target_id"],)
    )
    _event(
        db,
        job_id,
        "",
        task["epoch"],
        "retry",
        "运营使用原模型文件恢复处理",
        time.time(),
    )
    return True


def heartbeat(
    node_id,
    capabilities=("model",),
    read_mbps=None,
    write_mbps=None,
    compute_s=None,
    job_id=None,
    epoch=None,
):
    """Rates are effective MiB/s; compute_s is processing time for recent mesh work."""
    for metric in (read_mbps, write_mbps, compute_s):
        if metric is not None and (not math.isfinite(metric) or metric <= 0):
            raise HTTPException(422, "节点指标应为正数")
    with database(True) as db:
        t = time.time()
        db.execute(
            """INSERT INTO processing_nodes(node_id,capabilities,last_seen,read_mbps,write_mbps,compute_s)
               VALUES(?,?,?,COALESCE(?,8.0),COALESCE(?,8.0),COALESCE(?,1.0))
               ON CONFLICT(node_id) DO UPDATE SET capabilities=excluded.capabilities,last_seen=excluded.last_seen,
               read_mbps=COALESCE(?,processing_nodes.read_mbps),write_mbps=COALESCE(?,processing_nodes.write_mbps),
               compute_s=COALESCE(?,processing_nodes.compute_s)""",
            (
                node_id,
                pack(sorted(set(capabilities))),
                t,
                read_mbps,
                write_mbps,
                compute_s,
                read_mbps,
                write_mbps,
                compute_s,
            ),
        )
        lease = _lease_seconds()
        renewed = False
        if job_id and epoch:
            renewed = bool(
                db.execute(
                    """UPDATE processing_tasks SET lease=? WHERE job_id=? AND node_id=? AND epoch=?
                   AND status='running' AND lease>? AND EXISTS (SELECT 1 FROM orders
                   WHERE id=processing_tasks.target_id AND payment_status IN ('paid','refunding'))""",
                    (t + lease, job_id, node_id, epoch, t),
                ).rowcount
            )
    return {"lease_seconds": lease, "renewed": renewed}


def _release(db, task, msg, t):
    failures = task["failures"] + 1
    terminal = failures >= MAX_FAILURES
    status = "failed" if terminal else "queued"
    db.execute(
        """UPDATE processing_tasks SET status=?,node_id='',lease=0,failures=?,reason=?,started=NULL,
           finished=? WHERE job_id=?""",
        (status, failures, msg, t if terminal else None, task["job_id"]),
    )
    if terminal:
        db.execute(
            "UPDATE jobs SET status='failed',lease=0,error=? WHERE id=?",
            (msg, task["job_id"]),
        )
        db.execute(
            "UPDATE orders SET generation_status='failed' WHERE id=? AND payment_status IN ('paid','refunding')",
            (task["target_id"],),
        )
    _event(
        db,
        task["job_id"],
        task["node_id"],
        task["epoch"],
        "failed" if terminal else "retry",
        msg,
        t,
    )


def _recover(db, t):
    # Refunded orders stop immediately. A refund still being settled can be reversed.
    stopped = db.all(
        """SELECT p.* FROM processing_tasks p JOIN orders o ON o.id=p.target_id
           WHERE p.status IN ('queued','assigned','running') AND o.payment_status NOT IN ('paid','refunding')"""
    )
    for task in stopped:
        db.execute(
            "UPDATE processing_tasks SET status='stopped',lease=0,finished=? WHERE job_id=?",
            (t, task["job_id"]),
        )
        db.execute(
            "UPDATE jobs SET status='stopped',lease=0 WHERE id=?", (task["job_id"],)
        )
        _event(
            db,
            task["job_id"],
            task["node_id"],
            task["epoch"],
            "stopped",
            "订单已停止制作",
            t,
        )
    for task in db.all(
        "SELECT * FROM processing_tasks WHERE status='running' AND lease<=?", (t,)
    ):
        _event(
            db,
            task["job_id"],
            task["node_id"],
            task["epoch"],
            "expired",
            "节点租约已到期",
            t,
        )
        _release(db, task, "节点租约到期，重新分配", t)


def _service_times(node, size):
    # Approximate output volume by GLB size until a particular model is processed.
    mib = size / MIB
    return mib / node["read_mbps"], node["compute_s"], mib / node["write_mbps"]


def _assign(db, t):
    nodes = {
        row["node_id"]: row
        for row in db.all(
            "SELECT * FROM processing_nodes WHERE last_seen>=? ORDER BY node_id",
            (_online_cutoff(t),),
        )
        if "model" in json.loads(row["capabilities"])
    }
    if not nodes:
        db.execute(
            "UPDATE processing_tasks SET status='queued',node_id='',reason='等待具备模型处理能力的节点' "
            "WHERE status='assigned'"
        )
        return
    policy = setting(db, "processing_policy")
    cursor = setting(db, "processing_rr_cursor") if policy == "round_robin" else ""
    previous_cursor = cursor
    wait = dict.fromkeys(nodes, 0.0)
    counts = dict.fromkeys(nodes, 0)
    for active in db.all(
        "SELECT node_id,input_bytes,started FROM processing_tasks WHERE status='running'"
    ):
        node = active["node_id"]
        if node in nodes:
            duration = sum(_service_times(nodes[node], active["input_bytes"]))
            wait[node] += max(0.01, duration - max(0.0, t - active["started"]))
            counts[node] += 1
    pending = db.all(
        """SELECT p.* FROM processing_tasks p JOIN orders o ON p.target_id=o.id
           WHERE p.status IN ('assigned','queued') AND o.payment_status='paid' ORDER BY p.created,p.job_id"""
    )
    for task in pending:
        size = task["input_bytes"]
        if policy == "round_robin":
            if (
                task["policy"] == policy
                and task["node_id"] in nodes
                and task["status"] == "assigned"
            ):
                chosen = task["node_id"]
            else:
                chosen = next((n for n in nodes if n > cursor), next(iter(nodes)))
                cursor = chosen
        elif policy == "shortest_queue":
            chosen = min(nodes, key=lambda n: (counts[n], n))
        else:
            chosen = min(
                nodes,
                key=lambda n: (
                    wait[n] + sum(_service_times(nodes[n], size)),
                    counts[n],
                    n,
                ),
            )
        read, compute, write = _service_times(nodes[chosen], size)
        service = read + compute + write
        estimate = wait[chosen] + service
        if (
            task["node_id"] != chosen
            or task["status"] == "queued"
            or task["policy"] != policy
        ):
            reason = (
                f"排队 {wait[chosen]:.2f}s，读取 {read:.2f}s，处理 {compute:.2f}s，"
                f"写回 {write:.2f}s，前序任务 {counts[chosen]} 个"
            )
            db.execute(
                """UPDATE processing_tasks SET status='assigned',node_id=?,policy=?,estimate_s=?,reason=?
                   WHERE job_id=?""",
                (chosen, policy, estimate, reason, task["job_id"]),
            )
            _event(db, task["job_id"], chosen, task["epoch"], "assigned", reason, t)
        wait[chosen] += service
        counts[chosen] += 1
    if previous_cursor != cursor:
        db.execute(
            "UPDATE settings SET value=? WHERE key='processing_rr_cursor'",
            (pack(cursor),),
        )


def _grant(task):
    return {
        **{
            key: task[key]
            for key in (
                "job_id",
                "target_id",
                "epoch",
                "glb_key",
                "stl_key",
                "input_bytes",
            )
        },
        "lease_seconds": _lease_seconds(),
    }


def claim(node_id):
    with database(True) as db:
        t = time.time()
        _recover(db, t)
        _assign(db, t)
        task = db.one(
            """SELECT p.* FROM processing_tasks p JOIN orders o ON o.id=p.target_id
               JOIN processing_nodes n ON n.node_id=p.node_id WHERE p.node_id=? AND p.status='assigned'
               AND n.last_seen>=? AND o.payment_status='paid' AND NOT EXISTS (SELECT 1 FROM processing_tasks
               WHERE node_id=p.node_id AND status='running') ORDER BY p.created,p.job_id LIMIT 1""",
            (node_id, _online_cutoff(t)),
        )
        if not task:
            return None
        task["epoch"] += 1
        db.execute(
            "UPDATE processing_tasks SET status='running',epoch=?,lease=?,started=? WHERE job_id=?",
            (task["epoch"], t + _lease_seconds(), t, task["job_id"]),
        )
        _event(
            db, task["job_id"], node_id, task["epoch"], "claimed", "节点已领取任务", t
        )
        if task["epoch"] > 1:
            previous = db.one(
                """SELECT node_id FROM processing_events WHERE job_id=? AND epoch=?
                   AND event='expired' LIMIT 1""",
                (task["job_id"], task["epoch"] - 1),
            )
            if previous and previous["node_id"] != node_id:
                detail = f"{node_id} 接管 {previous['node_id']} 的任务，租约版本 {task['epoch']}"
                _event(
                    db, task["job_id"], node_id, task["epoch"], "takeover", detail, t
                )
        return _grant(task)


def _held(db, node_id, job_id, epoch, t):
    task = db.one(
        """SELECT p.* FROM processing_tasks p JOIN orders o ON o.id=p.target_id
           WHERE p.job_id=? AND p.node_id=? AND p.epoch=? AND p.status='running' AND p.lease>?
           AND o.payment_status IN ('paid','refunding')""",
        (job_id, node_id, epoch, t),
    )
    if not task:
        raise HTTPException(409, "任务租约已失效")
    return task


def validate(node_id, job_id, epoch):
    with database() as db:
        return _grant(_held(db, node_id, job_id, epoch, time.time()))


def complete(node_id, job_id, epoch, stl_key):
    with database(True) as db:
        t = time.time()
        task = _held(db, node_id, job_id, epoch, t)
        outputs = [
            {"kind": "glb", "key": task["glb_key"]},
            {"kind": "stl", "key": stl_key},
        ]
        db.execute(
            """UPDATE orders SET generation_status='ready',delivery_status='review',preview_key=?,stl_key=?,
               owner_confirmed=0,quality_checked=0 WHERE id=?""",
            (task["glb_key"], stl_key, task["target_id"]),
        )
        db.execute(
            "UPDATE jobs SET outputs=?,status='done',lease=0,error='' WHERE id=?",
            (pack(outputs), job_id),
        )
        db.execute(
            "UPDATE processing_tasks SET status='done',lease=0,finished=? WHERE job_id=?",
            (t, job_id),
        )
        _event(db, job_id, node_id, epoch, "completed", "模型已归档，等待看样和质检", t)
    return {"ok": True}


def fail(node_id, job_id, epoch, reason):
    with database(True) as db:
        t = time.time()
        _release(db, _held(db, node_id, job_id, epoch, t), str(reason)[:300], t)
    return {"ok": True}


def set_policy(policy):
    if policy not in POLICIES:
        raise HTTPException(422, "不支持的调度策略")
    with database(True) as db:
        db.execute(
            "UPDATE settings SET value=? WHERE key='processing_policy'", (pack(policy),)
        )
    return {"policy": policy}


def snapshot():
    with database() as db:
        cutoff = _online_cutoff(time.time())
        nodes = db.all(
            """SELECT n.*,(SELECT COUNT(*) FROM processing_tasks p WHERE p.node_id=n.node_id
               AND p.status='assigned') AS queued,(SELECT COUNT(*) FROM processing_tasks p
               WHERE p.node_id=n.node_id AND p.status='running') AS running FROM processing_nodes n ORDER BY node_id"""
        )
        for node in nodes:
            node["online"] = node["last_seen"] >= cutoff
            node["capabilities"] = json.loads(node["capabilities"])
        tasks = db.all(
            """SELECT job_id,target_id,status,node_id,epoch,input_bytes,policy,estimate_s,reason,created,started,finished
               FROM processing_tasks ORDER BY created DESC,job_id DESC LIMIT 100"""
        )
        events = db.all(
            """SELECT job_id,node_id,epoch,event,at,detail FROM processing_events
               ORDER BY at DESC,id DESC LIMIT 150"""
        )
        return {
            "enabled": os.getenv("PET_DISTRIBUTED") == "1",
            "policy": setting(db, "processing_policy"),
            "nodes": nodes,
            "tasks": tasks,
            "events": events,
        }
