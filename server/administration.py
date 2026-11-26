from fastapi import APIRouter, Depends
from pydantic import Field

from . import providers, scheduler, storage
from .access import Body, admin, staff
from .db import database, log, now, pack, setting, uid
from .domain import fail, finish_model_if_ready, modes, order_view, pet_view, public_user, work_view

router = APIRouter(prefix="/api/admin")


class Note(Body):
    note: str = Field(default="", max_length=1500)
    external_id: str = Field(default="", max_length=250)
    confirm_resubmit: bool = False


class Quote(Body):
    quote: int = Field(gt=0, le=10000000)
    note: str = Field(min_length=1, max_length=1500)


class Style(Body):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    name: str = Field(min_length=1, max_length=40)
    prompt: str = Field(min_length=1, max_length=1400)
    active: bool = True


class Prices(Body):
    portrait: int = Field(gt=0, le=1000000)
    model: int = Field(gt=0, le=1000000)


class UnitCosts(Body):
    portrait_image_cny: float = Field(ge=0, le=10000)
    model_usd: float = Field(ge=0, le=10000)
    usd_cny: float = Field(gt=0, le=100)


class Settings(Body):
    unit_costs: UnitCosts | None = None
    prices: Prices | None = None
    styles: list[Style] | None = Field(default=None, min_length=1, max_length=40)
    daily_limit: int | None = Field(default=None, ge=1, le=100)


class Role(Body):
    role: str


class SchedulingPolicy(Body):
    policy: str = Field(pattern=r"^(adaptive|round_robin|shortest_queue)$")


@router.get("/scheduler")
def scheduler_status(user=Depends(staff)):
    return scheduler.snapshot()


@router.post("/scheduler/policy")
def change_policy(body: SchedulingPolicy, user=Depends(admin)):
    scheduler.set_policy(body.policy)
    with database(True) as db:
        log(db, user["id"], "scheduler_policy", note=body.policy)
    return {"policy": body.policy}


def get_order(db, ident):
    o = db.one("SELECT * FROM orders WHERE id=?", (ident,))
    if not o:
        fail(404, "找不到订单")
    return o


@router.get("/state")
def dashboard(user=Depends(staff)):
    with database() as db:
        users = [public_user(u) for u in db.all("SELECT * FROM users ORDER BY created_at DESC")]
        pets = [
            pet_view(db, p)
            for p in db.all("SELECT * FROM pets WHERE archived=0 ORDER BY created_at DESC")
        ]
        works = [work_view(db, w) for w in db.all("SELECT * FROM works ORDER BY created_at DESC")]
        orders = [
            order_view(db, o) for o in db.all("SELECT * FROM orders ORDER BY created_at DESC")
        ]
        jobs = db.all(
            "SELECT id,target_id,kind,status,stage,external_id,error,provider_mode,request_count,created_at FROM jobs ORDER BY created_at DESC"
        )
        logs = db.all("SELECT * FROM audit ORDER BY created_at DESC LIMIT 250")
        samples = db.all("SELECT * FROM samples ORDER BY created_at DESC")
        # Use settled orders only. A refund is not included in sales totals.
        paid = [o for o in orders if o["payment_status"] == "paid"]
        stats = {
            "users": len(users),
            "pets": len(pets),
            "orders": len(orders),
            "paid_orders": len(paid),
            "revenue": sum(o["amount"] for o in paid if o["payment_channel"] != "demo"),
            "demo_revenue": sum(o["amount"] for o in paid if o["payment_channel"] == "demo"),
            "pending_delivery": sum(o["delivery_status"] != "delivered" for o in paid),
            "failed_jobs": sum(j["status"] in {"failed", "uncertain"} for j in jobs),
            "portrait_jobs": sum(j["kind"] == "portrait" for j in jobs),
            "model_jobs": sum(j["kind"] == "model" for j in jobs),
        }
        return {
            "users": users,
            "pets": pets,
            "works": works,
            "orders": orders,
            "samples": samples,
            "channels": channel_stats(db),
            "unit_costs": setting(db, "unit_costs"),
            "jobs": jobs,
            "audit": logs,
            "stats": stats,
            "prices": setting(db, "prices"),
            "styles": setting(db, "styles"),
            "daily_limit": setting(db, "daily_limit"),
            "mode": modes(),
        }


@router.patch("/settings")
def settings(b: Settings, user=Depends(admin)):
    with database(True) as db:
        if b.styles:
            ids = [s.id for s in b.styles]
            if len(ids) != len(set(ids)):
                fail(422, "画风编号不能重复")
        for k, v in b.model_dump(exclude_none=True).items():
            if k == "styles":
                old = {s["id"]: s for s in setting(db, "styles")}
                for s in v:
                    prev = old.get(s["id"])
                    changed = prev and any(
                        prev[key] != s[key] for key in ("name", "prompt", "active")
                    )
                    s["version"] = (prev.get("version", 1) + int(bool(changed))) if prev else 1
            db.execute("UPDATE settings SET value=? WHERE key=?", (pack(v), k))
            log(db, user["id"], "settings_updated", k)
    return {"ok": True}


@router.post("/users/{ident}/role")
def role(ident: str, b: Role, user=Depends(admin)):
    if b.role not in {"owner", "operator", "admin"}:
        fail(422, "未知角色")
    with database(True) as db:
        target = db.one("SELECT * FROM users WHERE id=?", (ident,))
        if not target:
            fail(404, "找不到用户")
        if target["id"] == user["id"] and b.role != "admin":
            fail(409, "无法移除自己的管理员权限")
        db.execute("UPDATE users SET role=? WHERE id=?", (b.role, ident))
        log(db, user["id"], "role_changed", ident, b.role)
        return public_user(db.one("SELECT * FROM users WHERE id=?", (ident,)))


@router.post("/orders/{ident}/qc")
def qc(ident: str, b: Note, user=Depends(staff)):
    with database(True) as db:
        o = get_order(db, ident)
        if (
            o["payment_status"] != "paid"
            or o["kind"] != "model"
            or o["generation_status"] != "ready"
        ):
            fail(409, "请在模型生成后检查 GLB 和 STL")
        if not b.note:
            fail(422, "请记录切片检查结果")
        try:
            report = providers.inspect_stl(storage.read(o["stl_key"]))
        except Exception:
            fail(422, "无法读取 STL 并完成切片预检")
        if not report["passed"]:
            fail(422, report.get("note", "网格预检未通过，请重新处理模型"))
        db.execute("UPDATE orders SET quality_checked=1 WHERE id=?", (ident,))
        finish_model_if_ready(db, ident)
        log(db, user["id"], "model_qc_passed", ident, b.note + "；" + report.get("note", ""))
        return order_view(db, get_order(db, ident))


def apply_refund_state(db, row, refund_id, status):
    if row["payment_status"] == "refunded":
        return
    if status == "succeeded":
        db.execute(
            "UPDATE orders SET payment_status='refunded',delivery_status='refunded',refund_ref=? WHERE id=?",
            (refund_id, row["id"]),
        )
    elif status in {"pending", "requires_action"}:
        db.execute(
            "UPDATE orders SET payment_status='refunding',refund_ref=? WHERE id=?",
            (refund_id, row["id"]),
        )
    elif status in {"failed", "canceled"}:
        db.execute(
            "UPDATE orders SET payment_status='paid',refund_ref=? WHERE id=?",
            (refund_id, row["id"]),
        )


@router.post("/orders/{ident}/refund")
def refund(ident: str, b: Note, user=Depends(admin)):
    with database(True) as db:
        o = get_order(db, ident)
        if o["payment_status"] == "refunded":
            return order_view(db, o)
        if o["payment_status"] not in {"paid", "refunding"}:
            fail(409, "此订单无法退款")
        try:
            if o["refund_ref"] and not o["refund_ref"].startswith("demo"):
                ref = o["refund_ref"]
                status = providers.get_refund_status(ref)
            else:
                if not b.note:
                    fail(422, "请填写退款原因")
                ref = providers.refund_payment(o["payment_ref"], o["amount"], ident)
                status = "succeeded"
        except providers.PaymentPending as pending:
            ref, status = pending.refund_id, "pending"
        except (ValueError, RuntimeError):
            fail(502, "退款尚未确认，请核对支付平台记录")
        apply_refund_state(db, o, ref, status)
        log(db, user["id"], "refund_" + status, ident, b.note)
        return order_view(db, get_order(db, ident))


def try_restore(db, o):
    if o["payment_status"] != "paid":
        fail(409, "仅可恢复已付款订单")
    if o["kind"] == "portrait":
        item = db.one("SELECT * FROM candidates WHERE id=?", (o["candidate_id"],))
        try:
            storage.read(item["key"])
        except Exception:
            try:
                image = storage.normalize_photo(storage.read(item["source_key"]))
                key = storage.put(image, "jpg")
                db.execute("UPDATE candidates SET key=? WHERE id=?", (key, item["id"]))
            except Exception:
                fail(409, "归档原件暂时不可用，请核实备份或处理退款")
        db.execute("UPDATE orders SET delivery_status='delivered' WHERE id=?", (o["id"],))
    else:
        if o["generation_status"] != "ready":
            fail(409, "请先恢复原建模任务")
        try:
            storage.read(o["preview_key"])
            storage.read(o["stl_key"])
        except Exception:
            fail(409, "缺少模型原件，请核实存储备份或处理退款")
        finish_model_if_ready(db, o["id"])


@router.post("/orders/{ident}/restore")
def restore(ident: str, b: Note, user=Depends(staff)):
    with database(True) as db:
        try_restore(db, get_order(db, ident))
        log(db, user["id"], "delivery_recovered", ident, b.note)
        return order_view(db, get_order(db, ident))


@router.post("/orders/{ident}/resolve")
def resolve(ident: str, b: Note, user=Depends(staff)):
    if not b.note:
        fail(422, "请记录处理结果")
    with database(True) as db:
        get_order(db, ident)
        db.execute("UPDATE orders SET support='',support_reply=? WHERE id=?", (b.note, ident))
        log(db, user["id"], "support_resolved", ident, b.note)
        return order_view(db, get_order(db, ident))


def resume(db, job, b, user):
    if not job or job["status"] not in {"failed", "uncertain"}:
        fail(409, "此任务无需恢复")
    if job["kind"] == "model" and get_order(db, job["target_id"])["payment_status"] != "paid":
        fail(409, "该订单已停止制作")
    if job["stage"] == "postprocess":
        if not scheduler.retry(db, job["id"]):
            fail(409, "任务当前无法重新分配")
        log(db, user["id"], "postprocess_retry", job["id"], b.note)
        return
    external = job["external_id"]
    outputs = job["outputs"]
    if b.external_id:
        if not b.external_id.startswith(("demo:", "dash:", "fal:")):
            fail(422, "请填写有效的供应商任务号")
        external = b.external_id
    elif job["stage"] == "rejected" or not external:
        if user["role"] != "admin" or not b.confirm_resubmit or not b.note:
            fail(409, "请核对供应商，填写原任务号或由管理员明确确认重新生成")
        external, outputs = "", ""
    db.execute(
        """UPDATE jobs SET status='queued',external_id=?,outputs=?,stage=?,lease=0,attempts=0,error='' WHERE id=?""",
        (external, outputs, "poll" if external else "submit", job["id"]),
    )
    table, field = (
        ("works", "status") if job["kind"] == "portrait" else ("orders", "generation_status")
    )
    db.execute(f"UPDATE {table} SET {field}='queued' WHERE id=?", (job["target_id"],))
    log(db, user["id"], "job_reconciled" if external else "model_resubmitted", job["id"], b.note)


@router.post("/jobs/{ident}/retry")
def retry_job(ident: str, b: Note, user=Depends(staff)):
    with database(True) as db:
        resume(db, db.one("SELECT * FROM jobs WHERE id=?", (ident,)), b, user)
        return {"ok": True}


@router.post("/orders/{ident}/retry")
def retry_order(ident: str, b: Note, user=Depends(staff)):
    with database(True) as db:
        resume(
            db,
            db.one(
                "SELECT * FROM jobs WHERE target_id=? ORDER BY created_at DESC LIMIT 1", (ident,)
            ),
            b,
            user,
        )
        return order_view(db, get_order(db, ident))


@router.post("/samples/{ident}/quote")
def quote(ident: str, b: Quote, user=Depends(staff)):
    with database(True) as db:
        sample = db.one("SELECT * FROM samples WHERE id=?", (ident,))
        if not sample:
            fail(404, "找不到打样申请")
        if (
            sample["status"] not in {"requested", "quoted"}
            or get_order(db, sample["order_id"])["payment_status"] != "paid"
        ):
            fail(409, "此申请无法报价")
        db.execute(
            "UPDATE samples SET status='quoted',quote=?,note=? WHERE id=?", (b.quote, b.note, ident)
        )
        log(db, user["id"], "sample_quoted", ident, b.note)
        return db.one("SELECT * FROM samples WHERE id=?", (ident,))


@router.post("/orders/{ident}/request-photos")
def request_photos(ident: str, b: Note, user=Depends(staff)):
    if not b.note:
        fail(422, "请说明需要补拍的具体角度")
    with database(True) as db:
        o = get_order(db, ident)
        if (
            o["kind"] != "model"
            or o["payment_status"] not in {"unpaid", "paid"}
            or (o["payment_status"] == "unpaid" and (o["checkout_url"] or o["checkout_creating"]))
            or o["delivery_status"] == "delivered"
            or o["generation_status"] in {"queued", "running", "uncertain"}
        ):
            fail(409, "当前订单无法请求补图")
        db.execute(
            "UPDATE orders SET delivery_status='needs_info',generation_status='pending',owner_confirmed=0,quality_checked=0,supplement_note=? WHERE id=?",
            (b.note, ident),
        )
        log(db, user["id"], "photos_requested", ident, b.note)
        return order_view(db, get_order(db, ident))


class ChannelData(Body):
    code: str = Field(pattern=r"^[a-zA-Z0-9_-]{2,40}$")
    name: str = Field(min_length=1, max_length=80)
    commission: int = Field(default=0, ge=0, le=10000000)
    acquisition_cost: int = Field(default=0, ge=0, le=1000000000)
    labor_cost: int = Field(default=0, ge=0, le=1000000000)


class ChannelEdit(Body):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    commission: int | None = Field(default=None, ge=0, le=10000000)
    acquisition_cost: int | None = Field(default=None, ge=0, le=1000000000)
    labor_cost: int | None = Field(default=None, ge=0, le=1000000000)


@router.post("/channels")
def add_channel(b: ChannelData, user=Depends(admin)):
    with database(True) as db:
        if db.one("SELECT id FROM channels WHERE code=?", (b.code,)):
            fail(409, "这个渠道编号已存在")
        ident = uid("channel")
        db.execute(
            "INSERT INTO channels VALUES(?,?,?,?,?,?,?)",
            (ident, b.code, b.name, b.commission, b.acquisition_cost, b.labor_cost, now()),
        )
        log(db, user["id"], "channel_created", ident, b.name)
        return db.one("SELECT * FROM channels WHERE id=?", (ident,))


@router.patch("/channels/{ident}")
def edit_channel(ident: str, b: ChannelEdit, user=Depends(admin)):
    with database(True) as db:
        if not db.one("SELECT id FROM channels WHERE id=?", (ident,)):
            fail(404, "找不到渠道")
        for key, value in b.model_dump(exclude_none=True).items():
            db.execute(f"UPDATE channels SET {key}=? WHERE id=?", (value, ident))
        log(db, user["id"], "channel_updated", ident)
        return db.one("SELECT * FROM channels WHERE id=?", (ident,))


def channel_stats(db):
    result = []
    rates = setting(db, "unit_costs")
    referrals = {r["user_id"]: r["channel_id"] for r in db.all("SELECT * FROM referrals")}
    buckets = {c["id"]: c for c in db.all("SELECT * FROM channels ORDER BY created_at DESC")}
    buckets["direct"] = {
        "id": "direct",
        "name": "直接访问",
        "code": "",
        "commission": 0,
        "acquisition_cost": 0,
        "labor_cost": 0,
    }
    for c in buckets.values():
        c.update(
            link=("/r/" + c["code"]) if c["code"] else "/",
            paid_orders=0,
            preview_users=0,
            commission_due=0,
            refund_orders=0,
            revenue=0,
            demo_orders=0,
            estimated_model_cost=0,
        )
    for w in db.all("SELECT DISTINCT w.user_id FROM proof_views w"):
        channel = referrals.get(w["user_id"], "direct")
        buckets[channel]["preview_users"] += 1
    for o in db.all(
        "SELECT user_id,amount,commission,payment_status,delivery_status,payment_channel FROM orders"
    ):
        c = buckets[referrals.get(o["user_id"], "direct")]
        if o["payment_channel"] == "demo":
            if o["payment_status"] in {"paid", "refunding", "refunded"}:
                c["demo_orders"] += 1
            continue
        if o["payment_status"] == "paid":
            c["paid_orders"] += 1
            c["revenue"] += o["amount"]
            if o["delivery_status"] == "delivered":
                c["commission_due"] += o["commission"]
        if o["payment_status"] == "refunded":
            c["refund_orders"] += 1
    jobs = db.all("""SELECT j.kind,j.request_count,COALESCE(w.user_id,o.user_id) AS user_id
                   FROM jobs j LEFT JOIN works w ON j.target_id=w.id LEFT JOIN orders o ON j.target_id=o.id
                   WHERE j.provider_mode<>'demo' AND j.status='done'""")
    for j in jobs:
        c = buckets[referrals.get(j["user_id"], "direct")]
        rate = (
            rates["portrait_image_cny"]
            if j["kind"] == "portrait"
            else rates["model_usd"] * rates["usd_cny"]
        )
        c["estimated_model_cost"] += round(100 * rate * j["request_count"])
    settled = {
        r["channel_id"]: r["total"]
        for r in db.all(
            "SELECT channel_id,SUM(amount) AS total FROM settlements GROUP BY channel_id"
        )
    }
    for c in buckets.values():
        c["commission_accrued"] = c["commission_due"]
        c["commission_settled"] = settled.get(c["id"], 0)
        balance = c["commission_accrued"] - c["commission_settled"]
        c["commission_due"] = max(0, balance)
        c["commission_credit"] = max(0, -balance)
        c["estimated_contribution"] = (
            c["revenue"]
            - c["commission_accrued"]
            - c["estimated_model_cost"]
            - c["acquisition_cost"]
            - c["labor_cost"]
        )
        result.append(c)
    return result


class StylePreview(Body):
    pet_id: str
    photo_ids: list[str] = Field(min_length=1, max_length=10)
    name: str = Field(min_length=1, max_length=40)
    prompt: str = Field(min_length=1, max_length=1400)


@router.post("/styles/preview")
def preview_style(b: StylePreview, user=Depends(admin)):
    from .domain import portrait_prompt
    from .domain import add_job, owned, photos_for

    with database(True) as db:
        pet = owned(db, "pets", b.pet_id, user)
        keys = photos_for(db, b.pet_id, b.photo_ids)
        ident = uid("work")
        db.execute(
            "INSERT INTO works(id,user_id,pet_id,style_id,title,status,photo_ids,request_key,created_at) VALUES(?,?,?,?,?,'queued',?,?,?)",
            (
                ident,
                user["id"],
                b.pet_id,
                "draft",
                b.name + " · 模板试样",
                pack(b.photo_ids),
                uid("request"),
                now(),
            ),
        )
        add_job(
            db,
            ident,
            "portrait",
            {
                "keys": keys,
                "prompt": portrait_prompt(pet, {"prompt": b.prompt}),
                "style": b.name,
                "count": 1,
            },
        )
        log(db, user["id"], "template_preview", ident, b.name)
        return work_view(db, owned(db, "works", ident, user))


@router.post("/channels/{ident}/settle")
def settle_channel(ident: str, b: Note, user=Depends(admin)):
    if not b.note:
        fail(422, "请填写线下结算凭证或备注")
    with database(True) as db:
        if not db.one("SELECT id FROM channels WHERE id=?", (ident,)):
            fail(404, "找不到合作渠道")
        channel = next(c for c in channel_stats(db) if c["id"] == ident)
        if channel["commission_due"] <= 0:
            fail(409, "当前没有未结算佣金")
        entry = uid("settlement")
        db.execute(
            "INSERT INTO settlements VALUES(?,?,?,?,?)",
            (entry, ident, channel["commission_due"], b.note, now()),
        )
        log(
            db, user["id"], "commission_settled", ident, f"{channel['commission_due']} 分，{b.note}"
        )
        return db.one("SELECT * FROM settlements WHERE id=?", (entry,))
