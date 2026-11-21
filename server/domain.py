import json

from fastapi import HTTPException

from . import providers
from .db import now, pack, uid


def fail(status, message):
    raise HTTPException(status, message)


def public_user(row):
    return {key: row[key] for key in ("id", "email", "name", "role", "created_at")}


def modes():
    return {
        "images": providers.model_mode("portrait"),
        "models": providers.model_mode("model"),
        "payments": providers.payment_mode(),
    }


def pet_view(db, row):
    result = dict(row)
    result.pop("archived", None)
    result["photos"] = [
        {
            **p,
            "url": "/api/media/photo/" + p["id"],
            "original_url": "/api/media/original/" + p["id"],
        }
        for p in db.all(
            "SELECT id,name,created_at FROM photos WHERE pet_id=? AND archived=0 ORDER BY created_at",
            (row["id"],),
        )
    ]
    return result


def work_view(db, row):
    obj = {**row, "kind": "portrait", "photo_ids": json.loads(row["photo_ids"])}
    obj.pop("request_key", None)
    obj["candidates"] = [
        {**c, "preview_url": "/api/media/preview/" + c["id"]}
        for c in db.all(
            "SELECT id,created_at FROM candidates WHERE work_id=? ORDER BY created_at,id",
            (row["id"],),
        )
    ]
    obj["error"] = latest_error(db, row["id"])
    return obj


def latest_error(db, target):
    job = db.one(
        "SELECT error FROM jobs WHERE target_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
        (target,),
    )
    return job["error"] if job else ""


def order_view(db, row):
    hidden = {
        "request_key",
        "payment_ref",
        "checkout_id",
        "checkout_url",
        "refund_ref",
        "preview_key",
        "stl_key",
    }
    result = {k: v for k, v in row.items() if k not in hidden}
    result.update(
        photo_ids=json.loads(row["photo_ids"]),
        owner_confirmed=bool(row["owner_confirmed"]),
        quality_checked=bool(row["quality_checked"]),
        preview_url=None,
        downloads=[],
        error=latest_error(db, row["id"]),
    )
    if row["kind"] == "portrait":
        result["preview_url"] = "/api/media/preview/" + row["candidate_id"]
    elif row["preview_key"] and row["payment_status"] == "paid":
        result["preview_url"] = "/api/media/model-preview/" + row["id"]
    if row["delivery_status"] == "delivered" and row["payment_status"] == "paid":
        kinds = (
            [("高清肖像.jpg", "portrait")]
            if row["kind"] == "portrait"
            else [("彩色模型.glb", "glb"), ("打印模型.stl", "stl")]
        )
        result["downloads"] = [{"name": n, "url": f"/api/media/{k}/{row['id']}"} for n, k in kinds]
    return result


def owned(db, table, ident, user):
    if table not in {"pets", "works", "orders", "samples"}:
        raise ValueError("unknown table")
    row = db.one(f"SELECT * FROM {table} WHERE id=? AND user_id=?", (ident, user["id"]))
    if not row or row.get("archived"):
        fail(404, "没有找到这条记录")
    if (
        table in {"works", "orders"}
        and db.one("SELECT archived FROM pets WHERE id=?", (row["pet_id"],))["archived"]
    ):
        fail(404, "档案已移除")
    return row


def photos_for(db, pet_id, ids):
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 10
        or any(not isinstance(v, str) for v in ids)
    ):
        fail(422, "请选择 1 至 10 张照片")
    if len(set(ids)) != len(ids):
        fail(422, "请去掉重复的照片")
    keys = []
    for ident in ids:
        row = db.one(
            "SELECT key FROM photos WHERE id=? AND pet_id=? AND archived=0", (ident, pet_id)
        )
        if not row:
            fail(422, "所选照片不属于该档案")
        keys.append(row["key"])
    return keys


def add_job(db, target, kind, payload):
    db.execute(
        "INSERT INTO jobs(id,target_id,kind,payload,status,created_at,provider_mode,request_count) VALUES(?,?,?,?,?,?,?,?)",
        (
            uid("job"),
            target,
            kind,
            pack(payload),
            "queued",
            now(),
            providers.model_mode(kind),
            payload["count"],
        ),
    )


def model_job(db, order, pet, feedback=""):
    if order["candidate_id"]:
        item = db.one("SELECT key FROM candidates WHERE id=?", (order["candidate_id"],))
        keys = [item["key"]] if item else []
    else:
        keys = [
            db.one("SELECT key FROM photos WHERE id=? AND pet_id=?", (ident, pet["id"]))["key"]
            for ident in json.loads(order["photo_ids"])
        ]
    if not keys:
        fail(409, "缺少已选的建模素材")
    prompt = "为这只宠物制作立体模型。请保留宠物的外形特征：" + pet["traits"]
    if feedback:
        prompt += "。主人提出了修改：" + feedback
    add_job(db, order["id"], "model", {"keys": keys, "style": "", "prompt": prompt, "count": 1})


def apply_paid(db, row, payment_ref):
    if row["payment_status"] != "unpaid":
        return
    if row["kind"] == "portrait":
        db.execute(
            "UPDATE orders SET payment_status='paid',payment_ref=?,generation_status='ready',delivery_status='delivered' WHERE id=?",
            (payment_ref, row["id"]),
        )
    else:
        db.execute(
            "UPDATE orders SET payment_status='paid',payment_ref=?,generation_status='queued' WHERE id=?",
            (payment_ref, row["id"]),
        )
        model_job(db, row, db.one("SELECT * FROM pets WHERE id=?", (row["pet_id"],)))


def finish_model_if_ready(db, ident):
    db.execute(
        """UPDATE orders SET delivery_status='delivered' WHERE id=? AND kind='model' AND payment_status='paid'
                  AND generation_status='ready' AND owner_confirmed=1 AND quality_checked=1
                  AND preview_key<>'' AND stl_key<>''""",
        (ident,),
    )


def portrait_prompt(pet, style, feedback=""):
    return f"参考图均为同一只宠物。保持第一张的姿态、脸型、耳形、眼睛颜色、左右花纹。主人记录：{pet['traits']}。画风：{style['prompt']}。修改要求：{feedback or '无'}。只输出作品，不添加文字。"
