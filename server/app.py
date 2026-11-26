import hashlib
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import Depends, FastAPI, Request, Response, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import Field

from .commerce import router as commerce_router
from .administration import router as admin_router
from .processing_api import router as processing_router
from .access import COOKIE, Body, Revision, authenticated, current, session
from . import storage, worker
from .db import database, initialize, log, now, pack, password_hash, setting, uid, valid_password
from .domain import (
    add_job,
    fail,
    modes,
    order_view,
    owned,
    pet_view,
    photos_for,
    portrait_prompt,
    public_user,
    work_view,
)


@asynccontextmanager
async def lifespan(app):
    initialize()
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,), daemon=True, name="pet-jobs")
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=3)


app = FastAPI(title="宠物纪念工作室", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def same_origin(request, call_next):
    if request.method not in {"HEAD", "GET", "OPTIONS"} and request.headers.get("origin"):
        origin = urlparse(request.headers["origin"]).netloc
        public_host = urlparse(os.environ.get("PET_PUBLIC_URL", "")).netloc
        if not origin or origin not in {request.headers.get("host"), public_host}:
            return JSONResponse({"detail": "请从本站页面提交请求"}, status_code=403)
    length = request.headers.get("content-length", "0")
    if not length.isascii() or not length.isdigit() or len(length) > 20:
        return JSONResponse({"detail": "无效请求"}, status_code=400)
    model_result = request.method == "PUT" and re.fullmatch(
        r"/api/processing/tasks/[^/]+/result", request.url.path
    )
    if model_result and int(length) > 200 * 1024 * 1024:
        return JSONResponse({"detail": "模型结果超过 200 MiB"}, status_code=413)
    if not model_result and request.url.path.startswith("/api/") and int(length) > 12 * 1024 * 1024:
        return JSONResponse({"detail": "请使用小于 10 MB 的照片"}, status_code=413)
    result = await call_next(request)
    if request.url.path.startswith("/api/"):
        result.headers["Cache-Control"] = "private, no-store"
        result.headers["X-Content-Type-Options"] = "nosniff"
    return result


class Credentials(Body):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class Register(Credentials):
    name: str = Field(min_length=1, max_length=60)


def check_attempt(request):
    ip = request.client.host if request.client else "local"
    with database(True) as db:
        threshold = time.time() - 600
        db.execute("DELETE FROM attempts WHERE stamp<?", (threshold,))
        if (
            db.one("SELECT count(*) AS n FROM attempts WHERE ip=? AND stamp>=?", (ip, threshold))[
                "n"
            ]
            >= 60
        ):
            fail(429, "尝试次数较多，请稍后再试")
        db.execute("INSERT INTO attempts VALUES(?,?)", (ip, time.time()))


@app.post("/api/auth/register")
def register(body: Register, request: Request, response: Response):
    check_attempt(request)
    email = body.email.lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(body.password) < 8:
        fail(422, "请输入有效邮箱，密码至少 8 位")
    with database(True) as db:
        if db.one("SELECT id FROM users WHERE email=?", (email,)):
            fail(409, "邮箱已注册，请登录")
        ident = uid("user")
        db.execute(
            "INSERT INTO users VALUES(?,?,?,?,?,?)",
            (ident, email, body.name, "owner", password_hash(body.password), now()),
        )
        channel = db.one(
            "SELECT id FROM channels WHERE code=?", (request.cookies.get("pet_ref", "")[:50],)
        )
        if channel:
            db.execute("INSERT INTO referrals VALUES(?,?)", (ident, channel["id"]))
        session(db, ident, response)
        return public_user(db.one("SELECT * FROM users WHERE id=?", (ident,)))


@app.post("/api/auth/login")
def login(body: Credentials, request: Request, response: Response):
    check_attempt(request)
    with database(True) as db:
        user = db.one("SELECT * FROM users WHERE email=?", (body.email.lower(),))
        if not user or not valid_password(body.password, user["passwd"]):
            fail(401, "邮箱或密码不正确")
        session(db, user["id"], response)
        return public_user(user)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    with database(True) as db:
        db.execute(
            "DELETE FROM sessions WHERE token=?",
            (hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest(),),
        )
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/health")
def health():
    with database() as db:
        db.one("SELECT 1 AS ok")
    return {"status": "ok"}


@app.get("/api/state")
def state(user=Depends(current)):
    with database() as db:
        value = {
            "user": public_user(user) if user else None,
            "mode": modes(),
            "prices": setting(db, "prices"),
            "styles": [
                {k: v for k, v in s.items() if k != "prompt"}
                for s in setting(db, "styles")
                if s["active"]
            ],
            "pets": [],
            "works": [],
            "orders": [],
            "samples": [],
        }
        if user:
            owner = (user["id"],)
            value["pets"] = [
                pet_view(db, p)
                for p in db.all(
                    "SELECT * FROM pets WHERE user_id=? AND archived=0 ORDER BY created_at DESC",
                    owner,
                )
            ]
            value["works"] = [
                work_view(db, w)
                for w in db.all(
                    "SELECT w.* FROM works w JOIN pets p ON p.id=w.pet_id WHERE w.user_id=? AND p.archived=0 ORDER BY w.created_at DESC",
                    owner,
                )
            ]
            value["orders"] = [
                order_view(db, o)
                for o in db.all(
                    "SELECT o.* FROM orders o JOIN pets p ON p.id=o.pet_id WHERE o.user_id=? AND p.archived=0 ORDER BY o.created_at DESC",
                    owner,
                )
            ]
            value["samples"] = db.all(
                "SELECT * FROM samples WHERE user_id=? ORDER BY created_at DESC", owner
            )
        return value


class Pet(Body):
    name: str = Field(min_length=1, max_length=60)
    species: str = Field(min_length=1, max_length=40)
    traits: str = Field(default="", max_length=1400)
    story: str = Field(default="", max_length=5000)
    occasion: str = Field(default="", max_length=80)


class PetEdit(Body):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    species: str | None = Field(default=None, min_length=1, max_length=40)
    traits: str | None = Field(default=None, max_length=1400)
    story: str | None = Field(default=None, max_length=5000)
    occasion: str | None = Field(default=None, max_length=80)


@app.post("/api/pets")
def create_pet(b: Pet, user=Depends(authenticated)):
    with database(True) as db:
        if (
            db.one("SELECT count(*) AS n FROM pets WHERE user_id=? AND archived=0", (user["id"],))[
                "n"
            ]
            >= 100
        ):
            fail(429, "档案数量已达到上限")
        ident = uid("pet")
        db.execute(
            "INSERT INTO pets(id,user_id,name,species,traits,story,occasion,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (ident, user["id"], b.name, b.species, b.traits, b.story, b.occasion, now()),
        )
        return pet_view(db, owned(db, "pets", ident, user))


@app.patch("/api/pets/{ident}")
def edit_pet(ident: str, b: PetEdit, user=Depends(authenticated)):
    with database(True) as db:
        owned(db, "pets", ident, user)
        for k, v in b.model_dump(exclude_none=True).items():
            db.execute(f"UPDATE pets SET {k}=? WHERE id=?", (v, ident))
        return pet_view(db, owned(db, "pets", ident, user))


@app.delete("/api/pets/{ident}")
def delete_pet(ident: str, user=Depends(authenticated)):
    with database(True) as db:
        owned(db, "pets", ident, user)
        active = db.one(
            """SELECT id FROM orders WHERE pet_id=? AND (payment_status='refunding'
                      OR (payment_status='paid' AND delivery_status<>'delivered') OR (payment_status='unpaid' AND (checkout_url<>'' OR checkout_creating=1)))""",
            (ident,),
        )
        if active:
            fail(409, "档案中还有处理中订单，完成后可以移除")
        db.execute("UPDATE pets SET archived=1 WHERE id=?", (ident,))
        db.execute(
            "UPDATE orders SET payment_status='cancelled',delivery_status='cancelled' WHERE pet_id=? AND payment_status='unpaid'",
            (ident,),
        )
        return {"ok": True}


@app.post("/api/pets/{ident}/photos")
def upload(ident: str, file: UploadFile = File(...), user=Depends(authenticated)):
    with database() as db:
        owned(db, "pets", ident, user)
    data = file.file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        fail(413, "照片不能超过 10 MB")
    try:
        image = storage.normalize_photo(data)
    except Exception:
        fail(422, "无法读取这张照片，请使用 JPG、PNG 或 WebP")
    with database(True) as db:
        owned(db, "pets", ident, user)
        if (
            db.one("SELECT count(*) AS n FROM photos WHERE pet_id=? AND archived=0", (ident,))["n"]
            >= 30
        ):
            fail(429, "每份档案最多保存 30 张照片")
        photo = uid("photo")
        key = storage.put(image, "jpg")
        # Model inputs are small, orientation-corrected files stripped of EXIF.
        # Owners can separately retrieve the exact bytes they entrusted to the archive.
        ext = (
            "png" if data.startswith(b"\x89PNG") else "webp" if data.startswith(b"RIFF") else "jpg"
        )
        original = storage.put(data, ext)
        name = Path(file.filename or "宠物照片.jpg").name[:140]
        created = now()
        db.execute(
            "INSERT INTO photos(id,pet_id,key,name,created_at,original_key) VALUES(?,?,?,?,?,?)",
            (photo, ident, key, name, created, original),
        )
        return {
            "id": photo,
            "url": "/api/media/photo/" + photo,
            "original_url": "/api/media/original/" + photo,
            "name": name,
            "created_at": created,
        }


@app.delete("/api/pets/{ident}/photos/{photo_id}")
def remove_photo(ident: str, photo_id: str, user=Depends(authenticated)):
    with database(True) as db:
        owned(db, "pets", ident, user)
        if not db.one(
            "SELECT id FROM photos WHERE id=? AND pet_id=? AND archived=0", (photo_id, ident)
        ):
            fail(404, "找不到照片")
        db.execute("UPDATE photos SET archived=1 WHERE id=?", (photo_id,))
        return {"ok": True}


class Work(Body):
    pet_id: str
    style_id: str
    photo_ids: list[str] = Field(min_length=1, max_length=10)
    request_key: str | None = Field(default=None, max_length=120)


@app.post("/api/works")
def create_work(b: Work, user=Depends(authenticated)):
    with database(True) as db:
        pet = owned(db, "pets", b.pet_id, user)
        if b.request_key:
            old = db.one(
                "SELECT * FROM works WHERE user_id=? AND request_key=?", (user["id"], b.request_key)
            )
            if old:
                if (old["pet_id"], old["style_id"], old["photo_ids"]) != (
                    b.pet_id,
                    b.style_id,
                    pack(b.photo_ids),
                ):
                    fail(409, "请求号已经用于其他作品")
                return work_view(db, old)
        keys = photos_for(db, b.pet_id, b.photo_ids)
        style = next(
            (s for s in setting(db, "styles") if s["id"] == b.style_id and s["active"]), None
        )
        if not style:
            fail(422, "所选画风暂未开放")
        old = db.one(
            "SELECT * FROM works WHERE user_id=? AND pet_id=? AND style_id=? AND photo_ids=? AND status IN ('queued','running')",
            (user["id"], b.pet_id, b.style_id, pack(b.photo_ids)),
        )
        if old:
            return work_view(db, old)
        if db.one(
            "SELECT count(*) AS n FROM works WHERE user_id=? AND created_at>=?",
            (user["id"], now()[:10]),
        )["n"] >= setting(db, "daily_limit"):
            fail(429, "今日预览额度已用完，已有作品可以继续挑选")
        ident = uid("work")
        db.execute(
            "INSERT INTO works(id,user_id,pet_id,style_id,title,status,photo_ids,request_key,created_at) VALUES(?,?,?,?,?,'queued',?,?,?)",
            (
                ident,
                user["id"],
                b.pet_id,
                b.style_id,
                pet["name"] + " · " + style["name"],
                pack(b.photo_ids),
                b.request_key or uid("request"),
                now(),
            ),
        )
        db.execute("UPDATE works SET style_version=? WHERE id=?", (style.get("version", 1), ident))
        add_job(
            db,
            ident,
            "portrait",
            {"keys": keys, "prompt": portrait_prompt(pet, style), "style": style["id"], "count": 2},
        )
        return work_view(db, owned(db, "works", ident, user))


@app.post("/api/works/{ident}/revise")
def revise_work(ident: str, b: Revision, user=Depends(authenticated)):
    import json

    with database(True) as db:
        w = owned(db, "works", ident, user)
        if w["status"] != "ready" or w["revision_count"] >= 1:
            fail(409, "作品尚未就绪或本次修改机会已使用")
        job = db.one(
            "SELECT payload FROM jobs WHERE target_id=? ORDER BY created_at LIMIT 1", (ident,)
        )
        payload = json.loads(job["payload"])
        payload.update(prompt=payload["prompt"] + " 请依照主人的反馈调整：" + b.feedback, count=1)
        add_job(db, ident, "portrait", payload)
        db.execute(
            "UPDATE works SET revision_count=revision_count+1,feedback=?,status='queued' WHERE id=?",
            (b.feedback, ident),
        )
        return work_view(db, owned(db, "works", ident, user))


app.include_router(commerce_router)
app.include_router(admin_router)
app.include_router(processing_router)


@app.get("/api/media/{kind}/{ident}")
def media(kind: str, ident: str, request: Request, user=Depends(authenticated)):
    staff_access = user["role"] in {"admin", "operator"}
    with database(staff_access) as db:
        if kind in {"photo", "original"}:
            row = db.one(
                """SELECT f.key,f.original_key,f.name,p.user_id FROM photos f JOIN pets p ON p.id=f.pet_id
                          WHERE f.id=? AND p.archived=0 AND f.archived=0""",
                (ident,),
            )
            mime, name = "image/jpeg", "photo.jpg"
            if kind == "original" and row and row["original_key"]:
                row["key"] = row["original_key"]
                ext = row["key"].rsplit(".", 1)[-1]
                mime = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[ext]
                name = Path(row["name"]).stem + "." + ext
        elif kind == "preview":
            row = db.one(
                """SELECT c.preview_key AS key,w.user_id FROM candidates c
                          JOIN works w ON w.id=c.work_id JOIN pets p ON p.id=w.pet_id WHERE c.id=? AND p.archived=0""",
                (ident,),
            )
            mime, name = "image/jpeg", "preview.jpg"
        elif kind in {"portrait", "model-preview", "glb", "stl"}:
            o = db.one(
                "SELECT o.* FROM orders o JOIN pets p ON p.id=o.pet_id WHERE o.id=? AND p.archived=0",
                (ident,),
            )
            if (
                not o
                or o["payment_status"] != "paid"
                or (
                    o["delivery_status"] != "delivered"
                    and kind != "model-preview"
                    and not staff_access
                )
            ):
                fail(404, "文件尚未交付")
            if kind == "portrait" and o["kind"] == "portrait":
                key = db.one("SELECT key FROM candidates WHERE id=?", (o["candidate_id"],))["key"]
                mime, name = "image/jpeg", "pet-portrait.jpg"
            elif kind in {"model-preview", "glb", "stl"} and o["kind"] == "model":
                key = o["stl_key"] if kind == "stl" else o["preview_key"]
                mime, name = (
                    ("model/stl", "pet-model.stl")
                    if kind == "stl"
                    else ("model/gltf-binary", "pet-model.glb")
                )
            else:
                fail(404, "找不到文件")
            row = {"key": key, "user_id": o["user_id"]}
        else:
            fail(404, "找不到文件")
        if not row or not row["key"] or (row["user_id"] != user["id"] and not staff_access):
            fail(404, "找不到文件")
        if staff_access and row["user_id"] != user["id"]:
            log(db, user["id"], "private_file_access", ident, kind)
        key = row["key"]
    try:
        data = storage.read(key)
    except Exception:
        if kind in {"portrait", "glb", "stl"}:
            with database(True) as db:
                db.execute(
                    "UPDATE orders SET delivery_status='failed' WHERE id=? AND payment_status='paid' AND delivery_status='delivered'",
                    (ident,),
                )
        fail(503, "文件暂时不可用，请从订单联系运营")
    if kind == "preview" and row["user_id"] == user["id"]:
        with database(True) as db:
            db.execute(
                "INSERT INTO proof_views VALUES(?,?) ON CONFLICT(user_id) DO NOTHING",
                (user["id"], now()),
            )
    disposition = "attachment" if kind in {"original", "portrait", "stl", "glb"} else "inline"
    return Response(
        data,
        media_type=mime,
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(name, safe='')}"},
    )


@app.get("/r/{code}", include_in_schema=False)
def referral(code: str, request: Request):
    with database() as db:
        if not db.one("SELECT id FROM channels WHERE code=?", (code,)):
            fail(404, "找不到这个合作渠道")
    response = RedirectResponse("/", status_code=302)
    if not request.cookies.get("pet_ref"):
        response.set_cookie(
            "pet_ref",
            code,
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            samesite="lax",
            secure=os.getenv("PET_PUBLIC_URL", "").startswith("https://"),
        )
    return response


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path == "api" or path.startswith("api/"):
        fail(404, "找不到这个接口")
    root = Path(
        os.environ.get("PET_WEB_DIR", str(Path(__file__).resolve().parents[1] / "web" / "dist"))
    ).resolve()
    file = (root / path).resolve()
    if file.is_relative_to(root) and file.is_file():
        return FileResponse(file)
    if (root / "index.html").is_file() and "." not in Path(path).name:
        return FileResponse(root / "index.html")
    fail(404, "前端尚未构建或找不到文件")
