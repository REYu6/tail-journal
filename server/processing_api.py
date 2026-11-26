"""Private data and control plane for the post-processing workers."""

import hmac
import os
import time
from typing import Annotated, Literal

import numpy as np
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import scheduler, storage
from .db import database
from .mesh_files import inspect_stl

MIB = 1024 * 1024
MAX_MODEL_BYTES = 200 * MIB
PROBE_BYTES = 128 * 1024
NodeID = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")]
Epoch = Annotated[int, Field(ge=1)]
Rate = Annotated[float, Field(gt=0, le=1_000_000, allow_inf_nan=False)]


def machine_access(authorization: Annotated[str | None, Header()] = None):
    token = os.getenv("PET_NODE_TOKEN", "")
    if (
        not token
        or not authorization
        or not hmac.compare_digest(authorization.encode(), ("Bearer " + token).encode())
    ):
        raise HTTPException(401, "工作节点凭据无效")


router = APIRouter(prefix="/api/processing", dependencies=[Depends(machine_access)])


class Node(BaseModel):
    node_id: NodeID


class Heartbeat(Node):
    capabilities: list[Literal["model"]] = Field(
        default_factory=lambda: ["model"], max_length=1
    )
    read_mbps: Rate | None = None  # Effective throughput in MiB/s.
    write_mbps: Rate | None = None
    compute_s: Annotated[float, Field(gt=0, le=86400, allow_inf_nan=False)] | None = (
        None
    )
    job_id: str | None = Field(default=None, max_length=100)
    epoch: Epoch | None = None


class Failure(Node):
    epoch: Epoch
    reason: str = Field(min_length=1, max_length=300)


@router.post("/heartbeat")
def heartbeat(body: Heartbeat):
    if (body.job_id is None) != (body.epoch is None):
        raise HTTPException(422, "续租时须提供任务及版本")
    return scheduler.heartbeat(**body.model_dump())


@router.post("/claim")
def claim(body: Node):
    job = scheduler.claim(body.node_id)
    if not job:
        return {"task": None}
    return {
        "task": {
            "job_id": job["job_id"],
            "epoch": job["epoch"],
            "has_stl": bool(job["stl_key"]),
            "input_bytes": job["input_bytes"],
            "lease_seconds": job["lease_seconds"],
        }
    }


@router.get("/tasks/{job_id}/source/{kind}")
def source(job_id: str, kind: str, node_id: NodeID, epoch: Epoch):
    job = scheduler.validate(node_id, job_id, epoch)
    if kind not in {"glb", "stl"} or not job[kind + "_key"]:
        raise HTTPException(404, "任务没有该文件")
    mime = "model/gltf-binary" if kind == "glb" else "model/stl"
    return Response(storage.read(job[kind + "_key"]), media_type=mime)


async def read_limited(request, limit):
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise HTTPException(413, "文件超过大小限制")
        data.extend(chunk)
    return bytes(data)


def valid_mesh(data):
    # Binary STL has an exact structural length. ASCII STL needs a parser.
    if len(data) >= 84:
        faces = int.from_bytes(data[80:84], "little")
        if 0 < faces <= 1_000_000 and len(data) == 84 + 50 * faces:
            vertices = np.ndarray(
                (faces, 3, 3), dtype="<f4", buffer=data, offset=96, strides=(50, 12, 4)
            )
            return bool(
                np.isfinite(vertices).all()
                and np.all(vertices.max(axis=(0, 1)) > vertices.min(axis=(0, 1)))
            )
    return data.lstrip()[:5].lower() == b"solid" and inspect_stl(data)["faces"] > 0


def publish(job_id, node_id, epoch, data):
    scheduler.validate(node_id, job_id, epoch)
    if not valid_mesh(data):
        raise HTTPException(422, "请提交有效的 STL 文件")
    started_write = time.monotonic()
    key = storage.put(data, "stl")
    storage_seconds = time.monotonic() - started_write
    try:
        scheduler.complete(node_id, job_id, epoch, key)
    except HTTPException:
        # A stale lease is a definitive rejection. A database transport error
        # can instead arrive after commit: preserve the blob in that case.
        storage.remove(key)
        raise
    return storage_seconds


@router.put("/tasks/{job_id}/result")
async def result(job_id: str, node_id: NodeID, epoch: Epoch, request: Request):
    await run_in_threadpool(scheduler.validate, node_id, job_id, epoch)
    data = await read_limited(request, MAX_MODEL_BYTES)
    # Time excluded from upload throughput includes mesh checks and the final commit.
    after_upload = time.monotonic()
    storage_seconds = await run_in_threadpool(publish, job_id, node_id, epoch, data)
    return {
        "ok": True,
        "finalize_seconds": time.monotonic() - after_upload - storage_seconds,
    }


@router.post("/tasks/{job_id}/fail")
def report_error(job_id: str, body: Failure):
    scheduler.fail(body.node_id, job_id, body.epoch, body.reason)
    return {"ok": True}


def read_probe():
    # Reuse one private, fixed-size object per deployment so cold and idle nodes
    # can measure the same read path as a model even before they have received one.
    name = "processing_probe_blob"
    with database() as db:
        row = db.one("SELECT value FROM settings WHERE key=?", (name,))
    if not row:
        with database(True) as db:
            row = db.one("SELECT value FROM settings WHERE key=?", (name,))
            if not row:
                key = storage.put(bytes(PROBE_BYTES), "glb")
                db.execute("INSERT INTO settings(key,value) VALUES(?,?)", (name, key))
                row = {"value": key}
    return Response(storage.read(row["value"]), media_type="application/octet-stream")


@router.get("/probe")
def probe_download():
    return read_probe()


@router.put("/probe")
async def probe_upload(request: Request):
    data = await read_limited(request, PROBE_BYTES)
    if len(data) != PROBE_BYTES:
        raise HTTPException(422, "链路探测块大小无效")
    key = await run_in_threadpool(storage.put, data, "glb")
    started_cleanup = time.monotonic()
    await run_in_threadpool(storage.remove, key)
    return {"ok": True, "finalize_seconds": time.monotonic() - started_cleanup}
