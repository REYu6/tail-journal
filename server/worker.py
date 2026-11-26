"""Durable model queue; persist provider result before extracting local previews."""

import json
import logging
import os
import time

from . import providers, scheduler, storage
from .mesh_files import stl_from_glb
from .db import database, now, pack, uid

logger = logging.getLogger("pawfolio.jobs")


def target_status(db, job, status):
    if job["kind"] == "portrait":
        db.execute("UPDATE works SET status=? WHERE id=?", (status, job["target_id"]))
    else:
        db.execute(
            "UPDATE orders SET generation_status=? WHERE id=? AND payment_status='paid'",
            (status, job["target_id"]),
        )


def failed(db, job, status, message):
    db.execute("UPDATE jobs SET status=?,error=?,lease=0 WHERE id=?", (status, message, job["id"]))
    target_status(db, job, status)


def claim():
    t = time.time()
    with database(True) as db:
        row = db.one(
            """SELECT * FROM jobs WHERE status IN ('queued','running') AND stage!='postprocess' AND lease<=?
                        ORDER BY created_at,id LIMIT 1""",
            (t,),
        )
        if not row:
            return None
        if row["kind"] == "model":
            order = db.one("SELECT payment_status FROM orders WHERE id=?", (row["target_id"],))
            if order and order["payment_status"] == "refunding":
                db.execute("UPDATE jobs SET lease=? WHERE id=?", (t + 5, row["id"]))
                return None
            if not order or order["payment_status"] != "paid":
                db.execute("UPDATE jobs SET status='stopped' WHERE id=?", (row["id"],))
                return None
        if not row["external_id"] and providers.model_mode(row["kind"]) != row["provider_mode"]:
            failed(db, row, "failed", "供应商模式已切换，请运营核对后恢复工作环境")
            return None
        if row["status"] == "running" and row["stage"] == "submitting" and not row["external_id"]:
            failed(db, row, "uncertain", "供应商受理状态待核实，请联系运营处理。")
            return None
        stage = "submitting" if not row["external_id"] else row["stage"]
        db.execute(
            "UPDATE jobs SET status='running',stage=?,lease=? WHERE id=?",
            (stage, t + 600, row["id"]),
        )
        target_status(db, row, "running")
        return row


def step():
    job = claim()
    if not job:
        return False
    ident = job["id"]
    try:
        if not job["external_id"]:
            p = json.loads(job["payload"])
            external = providers.submit_model(
                job["kind"], p["keys"], p["prompt"], p["style"], p["count"]
            )
            with database(True) as db:
                db.execute(
                    "UPDATE jobs SET external_id=?,stage='poll',attempts=0,lease=0 WHERE id=?",
                    (external, ident),
                )
            return True
        distributed = job["kind"] == "model" and os.getenv("PET_DISTRIBUTED") == "1"
        if job["outputs"]:
            outputs = json.loads(job["outputs"])
        else:
            info = providers.poll_model(job["kind"], job["external_id"], defer_conversion=distributed)
            if info["status"] == "pending":
                with database(True) as db:
                    db.execute(
                        "UPDATE jobs SET attempts=0,lease=? WHERE id=?", (time.time() + 2, ident)
                    )
                return True
            if info["status"] != "succeeded":
                with database(True) as db:
                    failed(db, job, "failed", "生成未成功，请在订单或任务详情联系运营。")
                    db.execute("UPDATE jobs SET stage='rejected' WHERE id=?", (ident,))
                return True
            outputs = info["outputs"]
            with database(True) as db:
                db.execute(
                    "UPDATE jobs SET outputs=?,stage='persist',attempts=0 WHERE id=?",
                    (pack(outputs), ident),
                )
        if job["kind"] == "portrait":
            images = [o["key"] for o in outputs if o["kind"] == "image"]
            if not images:
                raise ValueError("no portrait output")
            # Always deliver the exact normalized image used to create its proof.
            items = []
            for key in images:
                image = storage.normalize_photo(storage.read(key))
                original = storage.put(image, "jpg")
                preview = storage.put(storage.preview_image(image), "jpg")
                items.append((uid("candidate"), job["target_id"], original, preview, key, now()))
            with database(True) as db:
                for item in items:
                    db.execute(
                        "INSERT INTO candidates(id,work_id,key,preview_key,source_key,created_at) VALUES(?,?,?,?,?,?)",
                        item,
                    )
                db.execute("UPDATE works SET status='ready' WHERE id=?", (job["target_id"],))
                db.execute("UPDATE jobs SET status='done',lease=0,error='' WHERE id=?", (ident,))
        else:
            keys = {o["kind"]: o["key"] for o in outputs}
            if not keys.get("glb"):
                raise ValueError("incomplete model")
            if distributed:
                glb = next(o for o in outputs if o["kind"] == "glb")
                size = glb.get("bytes") or storage.size(glb["key"])
                with database(True) as db:
                    scheduler.enqueue(db, ident, job["target_id"], glb["key"], size, keys.get("stl", ""))
                return True
            # A persisted GLB may predate switching back to the local processor.
            if not keys.get("stl"):
                keys["stl"] = storage.put(stl_from_glb(storage.read(keys["glb"])), "stl")
            with database(True) as db:
                db.execute(
                    """UPDATE orders SET generation_status='ready',delivery_status='review',preview_key=?,stl_key=?,
                    owner_confirmed=0,quality_checked=0 WHERE id=? AND payment_status IN ('paid','refunding')""",
                    (keys["glb"], keys["stl"], job["target_id"]),
                )
                db.execute("UPDATE jobs SET status='done',lease=0,error='' WHERE id=?", (ident,))
    except Exception as err:
        # A transport failure at submission can follow a billable acceptance.
        # Never blindly submit the same work a second time.
        logger.warning("Model task %s raised %s", ident, type(err).__name__)
        with database(True) as db:
            if not job["external_id"]:
                failed(db, job, "uncertain", "提交后尚未核实受理结果，需运营核对供应商。")
            elif job["attempts"] >= 5:
                failed(db, job, "failed", "获取或归档结果失败，可从原任务恢复。")
            else:
                db.execute(
                    "UPDATE jobs SET attempts=attempts+1,lease=? WHERE id=?",
                    (time.time() + min(60, 2 ** (job["attempts"] + 1)), ident),
                )
    return True


def run(stop):
    while not stop.is_set():
        try:
            worked = step()
        except Exception:
            logger.exception("Worker iteration failed")
            worked = False
        if not worked:
            stop.wait(0.6)
