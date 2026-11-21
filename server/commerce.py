import os

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from . import providers
from .access import Body, Revision, authenticated
from .db import database, log, now, pack, setting, uid
from .domain import (
    apply_paid,
    fail,
    finish_model_if_ready,
    model_job,
    order_view,
    owned,
    photos_for,
)

router = APIRouter(prefix="/api")


class OrderInput(Body):
    kind: str
    pet_id: str
    candidate_id: str | None = None
    photo_ids: list[str] = Field(default_factory=list, max_length=4)
    accept_inference: bool = False
    request_key: str | None = Field(default=None, max_length=120)


def qualified_candidate(db, candidate, pet_id, owner):
    item = db.one(
        """SELECT c.id FROM candidates c JOIN works w ON c.work_id=w.id
                   WHERE c.id=? AND w.pet_id=? AND w.user_id=?""",
        (candidate, pet_id, owner),
    )
    if not item:
        fail(422, "所选作品不属于该宠物档案")


@router.post("/orders")
def create_order(b: OrderInput, user=Depends(authenticated)):
    if b.kind not in {"model", "portrait"}:
        fail(422, "请选择肖像或 3D 模型")
    with database(True) as db:
        owned(db, "pets", b.pet_id, user)
        if b.request_key:
            prior = db.one(
                "SELECT * FROM orders WHERE user_id=? AND request_key=?",
                (user["id"], b.request_key),
            )
            if prior:
                if (prior["kind"], prior["pet_id"], prior["candidate_id"], prior["photo_ids"]) != (
                    b.kind,
                    b.pet_id,
                    b.candidate_id,
                    pack(b.photo_ids),
                ):
                    fail(409, "请求号已经用于其他订单")
                return order_view(db, prior)
        if b.candidate_id:
            qualified_candidate(db, b.candidate_id, b.pet_id, user["id"])
        if b.kind == "portrait":
            if not b.candidate_id or b.photo_ids:
                fail(422, "请选定一张肖像预览")
            current = db.one(
                """SELECT * FROM orders WHERE user_id=? AND candidate_id=? AND kind='portrait'
                              AND payment_status IN ('unpaid','paid','refunding')""",
                (user["id"], b.candidate_id),
            )
            if current:
                return order_view(db, current)
        else:
            if bool(b.photo_ids) == bool(b.candidate_id):
                fail(422, "请选择原照或已交付肖像作为建模参考")
            if len(b.photo_ids) < 2 and not b.accept_inference:
                fail(422, "请先确认单张照片无法还原未展示的角度")
            if b.photo_ids:
                photos_for(db, b.pet_id, b.photo_ids)
            elif not db.one(
                """SELECT id FROM orders WHERE user_id=? AND candidate_id=? AND kind='portrait'
                                AND payment_status='paid' AND delivery_status='delivered'""",
                (user["id"], b.candidate_id),
            ):
                fail(422, "请先购买选中的肖像，或直接使用原照")
            prior = db.one(
                """SELECT * FROM orders WHERE user_id=? AND pet_id=? AND kind='model'
                            AND COALESCE(candidate_id,'')=? AND photo_ids=? AND payment_status='unpaid'""",
                (user["id"], b.pet_id, b.candidate_id or "", pack(b.photo_ids)),
            )
            if prior:
                return order_view(db, prior)
        ident = uid("order")
        db.execute(
            """INSERT INTO orders(id,user_id,pet_id,kind,amount,candidate_id,photo_ids,request_key,payment_status,generation_status,delivery_status,created_at)
                      VALUES(?,?,?,?,?,?,?,?,'unpaid',?,'pending',?)""",
            (
                ident,
                user["id"],
                b.pet_id,
                b.kind,
                setting(db, "prices")[b.kind],
                b.candidate_id,
                pack(b.photo_ids),
                b.request_key or uid("request"),
                "ready" if b.kind == "portrait" else "pending",
                now(),
            ),
        )
        affiliate = db.one(
            "SELECT c.commission FROM channels c JOIN referrals r ON r.channel_id=c.id WHERE r.user_id=?",
            (user["id"],),
        )
        db.execute(
            "UPDATE orders SET payment_channel=?,commission=? WHERE id=?",
            (providers.payment_mode(), affiliate["commission"] if affiliate else 0, ident),
        )
        return order_view(db, owned(db, "orders", ident, user))


@router.post("/orders/{ident}/pay")
def pay(ident: str, request: Request, user=Depends(authenticated)):
    with database(True) as db:
        o = owned(db, "orders", ident, user)
        if o["payment_status"] == "paid":
            return {"order": order_view(db, o), "demo": providers.payment_mode() == "demo"}
        if o["payment_status"] != "unpaid":
            fail(409, "订单无法支付")
        if o["delivery_status"] == "needs_info":
            fail(409, "请先补充建模照片")
        if o["payment_channel"] != providers.payment_mode():
            fail(409, "订单支付渠道已切换，请联系客服处理")
        if providers.payment_mode() == "demo":
            apply_paid(db, o, "demo_" + ident)
            log(db, user["id"], "demo_payment", ident)
            return {"order": order_view(db, owned(db, "orders", ident, user)), "demo": True}
        if o["checkout_url"]:
            return {"order": order_view(db, o), "checkout_url": o["checkout_url"], "demo": False}
        address = os.environ.get("PET_PUBLIC_URL", "").rstrip("/")
        if not address.startswith("https://"):
            fail(503, "支付服务需要配置 HTTPS 的 PET_PUBLIC_URL")
        # Commit the reservation before calling Stripe. Concurrent callers use
        # the same provider idempotency key; cancellation waits for reconciliation.
        db.execute("UPDATE orders SET checkout_creating=1 WHERE id=?", (ident,))
        previous = o["checkout_id"]
    try:
        data = providers.create_checkout(
            ident,
            o["amount"],
            "宠物纪念肖像" if o["kind"] == "portrait" else "宠物立体模型",
            address + "/orders",
            previous_id=previous,
        )
    except Exception:
        # Stripe may already have accepted the call. Retrying the same order
        # returns its prior session; never create another independent charge.
        fail(502, "支付服务暂不可用，可稍后从原订单继续")
    with database(True) as db:
        o = owned(db, "orders", ident, user)
        if o["payment_status"] == "paid":
            db.execute("UPDATE orders SET checkout_creating=0 WHERE id=?", (ident,))
            return {"order": order_view(db, o), "demo": False}
        if not o["checkout_url"] and o["checkout_id"] == previous:
            db.execute(
                "UPDATE orders SET checkout_id=?,checkout_url=?,checkout_creating=0 WHERE id=?",
                (data["id"], data["url"], ident),
            )
        o = owned(db, "orders", ident, user)
        return {"order": order_view(db, o), "checkout_url": o["checkout_url"], "demo": False}


@router.post("/payments/webhook")
async def webhook(request: Request):
    if providers.payment_mode() == "demo":
        fail(409, "演示环境未启用支付回调")
    try:
        event = providers.verify_payment(
            await request.body(), request.headers.get("Stripe-Signature", "")
        )
    except (ValueError, RuntimeError):
        fail(400, "回调签名或内容无效")
    if not event:
        return {"ok": True}
    with database(True) as db:
        if db.one("SELECT id FROM payment_events WHERE id=?", (event["event_id"],)):
            return {"ok": True}
        row = db.one("SELECT * FROM orders WHERE id=?", (event["order_id"],))
        if not row or row["amount"] != event["amount_fen"]:
            fail(409, "订单金额与回调不符")
        if row["payment_channel"] != "stripe":
            fail(409, "支付渠道不一致")
        if event.get("type") == "checkout_expired":
            if row["checkout_id"] == event["checkout_id"] and row["payment_status"] == "unpaid":
                db.execute("UPDATE orders SET checkout_url='' WHERE id=?", (row["id"],))
            db.execute(
                "INSERT INTO payment_events VALUES(?,?,?)", (event["event_id"], row["id"], now())
            )
            return {"ok": True}
        if event.get("type") == "payment":
            db.execute("UPDATE orders SET checkout_creating=0 WHERE id=?", (row["id"],))
        if row["payment_status"] == "cancelled":
            fail(409, "已撤销订单收款，请人工核对")
        if event.get("type") == "refund":
            from .administration import apply_refund_state

            if row["payment_ref"] != event["payment_ref"] or (
                row["refund_ref"] and row["refund_ref"] != event["refund_id"]
            ):
                fail(409, "退款凭证与原订单不符")
            apply_refund_state(db, row, event["refund_id"], event["refund_status"])
        else:
            if row["payment_ref"] and row["payment_ref"] != event["payment_ref"]:
                fail(409, "需核实重复收款")
            apply_paid(db, row, event["payment_ref"])
        db.execute(
            "INSERT INTO payment_events VALUES(?,?,?)", (event["event_id"], row["id"], now())
        )
        log(db, "payment", event.get("type", "payment") + "_verified", row["id"])
        return {"ok": True}


@router.post("/orders/{ident}/cancel")
def cancel(ident: str, user=Depends(authenticated)):
    with database(True) as db:
        o = owned(db, "orders", ident, user)
        if (
            o["payment_status"] not in {"unpaid", "cancelled"}
            or o["checkout_url"]
            or o["checkout_creating"]
        ):
            fail(409, "订单已进入支付处理，无法取消")
        db.execute(
            "UPDATE orders SET payment_status='cancelled',delivery_status='cancelled' WHERE id=?",
            (ident,),
        )
        return order_view(db, owned(db, "orders", ident, user))


@router.post("/orders/{ident}/confirm")
def confirm(ident: str, user=Depends(authenticated)):
    with database(True) as db:
        o = owned(db, "orders", ident, user)
        if (
            o["kind"] != "model"
            or o["payment_status"] != "paid"
            or o["generation_status"] != "ready"
        ):
            fail(409, "模型尚未就绪")
        db.execute("UPDATE orders SET owner_confirmed=1 WHERE id=?", (ident,))
        finish_model_if_ready(db, ident)
        return order_view(db, owned(db, "orders", ident, user))


@router.post("/orders/{ident}/revise")
def revise(ident: str, b: Revision, user=Depends(authenticated)):
    with database(True) as db:
        o = owned(db, "orders", ident, user)
        if (
            o["kind"] != "model"
            or o["payment_status"] != "paid"
            or o["delivery_status"] != "review"
            or o["owner_confirmed"]
            or o["revision_count"] >= 1
        ):
            fail(409, "此订单暂不可修改，或已经用过修改机会")
        if b.photo_ids:
            photos_for(db, o["pet_id"], b.photo_ids)
            db.execute(
                "UPDATE orders SET photo_ids=?,candidate_id=NULL WHERE id=?",
                (pack(b.photo_ids), ident),
            )
        db.execute(
            """UPDATE orders SET revision_count=revision_count+1,feedback=?,owner_confirmed=0,quality_checked=0,
                      generation_status='queued',delivery_status='pending',preview_key='',stl_key='' WHERE id=?""",
            (b.feedback, ident),
        )
        model_job(
            db, owned(db, "orders", ident, user), owned(db, "pets", o["pet_id"], user), b.feedback
        )
        return order_view(db, owned(db, "orders", ident, user))


class Support(Body):
    message: str = Field(min_length=1, max_length=1500)


@router.post("/orders/{ident}/support")
def ask_support(ident: str, b: Support, user=Depends(authenticated)):
    with database(True) as db:
        owned(db, "orders", ident, user)
        db.execute("UPDATE orders SET support=? WHERE id=?", (b.message, ident))
        log(db, user["id"], "support_requested", ident, b.message)
        return order_view(db, owned(db, "orders", ident, user))


class Sample(Body):
    specs: str = Field(min_length=1, max_length=1500)


@router.post("/orders/{ident}/sample")
def ask_sample(ident: str, b: Sample, user=Depends(authenticated)):
    with database(True) as db:
        o = owned(db, "orders", ident, user)
        if (
            o["kind"] != "model"
            or o["payment_status"] != "paid"
            or o["delivery_status"] != "delivered"
        ):
            fail(409, "请先完成数字模型交付")
        prev = db.one("SELECT * FROM samples WHERE order_id=?", (ident,))
        if prev:
            return prev
        sample_id = uid("sample")
        db.execute(
            "INSERT INTO samples(id,order_id,user_id,specs,status,created_at) VALUES(?,?,?,?,'requested',?)",
            (sample_id, ident, user["id"], b.specs, now()),
        )
        return owned(db, "samples", sample_id, user)


class SampleResponse(Body):
    accept: bool


@router.post("/samples/{ident}/respond")
def sample_response(ident: str, b: SampleResponse, user=Depends(authenticated)):
    with database(True) as db:
        s = owned(db, "samples", ident, user)
        if s["status"] != "quoted":
            fail(409, "暂时没有待确认报价")
        db.execute(
            "UPDATE samples SET status=? WHERE id=?",
            ("accepted" if b.accept else "declined", ident),
        )
        return owned(db, "samples", ident, user)


class Supplement(Body):
    photo_ids: list[str] = Field(min_length=1, max_length=4)
    accept_inference: bool = False


@router.post("/orders/{ident}/supplement")
def supplement(ident: str, b: Supplement, user=Depends(authenticated)):
    with database(True) as db:
        o = owned(db, "orders", ident, user)
        if (
            o["kind"] != "model"
            or o["delivery_status"] != "needs_info"
            or o["payment_status"] not in {"unpaid", "paid"}
        ):
            fail(409, "此订单当前无需补充资料")
        photos_for(db, o["pet_id"], b.photo_ids)
        if len(b.photo_ids) == 1 and not b.accept_inference:
            fail(422, "请先确认缺少角度时的推测补全")
        paid = o["payment_status"] == "paid"
        db.execute(
            """UPDATE orders SET photo_ids=?,candidate_id=NULL,delivery_status='pending',generation_status=?,
                      preview_key='',stl_key='',owner_confirmed=0,quality_checked=0 WHERE id=?""",
            (pack(b.photo_ids), "queued" if paid else "pending", ident),
        )
        if paid:
            model_job(
                db,
                owned(db, "orders", ident, user),
                owned(db, "pets", o["pet_id"], user),
                o["supplement_note"],
            )
        log(db, user["id"], "photos_supplemented", ident)
        return order_view(db, owned(db, "orders", ident, user))
