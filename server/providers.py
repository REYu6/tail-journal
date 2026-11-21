"""Hosted inference and payments. Keys and unwatermarked files stay server-side."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from . import storage
from .demo_model import demo_mesh
from .mesh_files import inspect_stl, stl_from_glb


class ProviderError(RuntimeError):
    """Safe message for operations; does not include signed URLs or secret headers."""


class PaymentPending(ProviderError):
    def __init__(self, refund_id: str):
        super().__init__("退款已提交，等待支付平台确认")
        self.refund_id = refund_id


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ProviderError(f"未配置 {name}")
    return value


def model_mode(kind: str = "portrait") -> str:
    if kind not in {"portrait", "model"}:
        raise ValueError("未知的生成服务")
    var = "PET_IMAGE_MODE" if kind == "portrait" else "PET_MODEL_MODE"
    value = os.getenv(var, "demo").lower()
    if value not in {"demo", "live"}:
        raise ProviderError(f"{var} 应为 demo 或 live")
    return value


def payment_mode() -> str:
    value = os.getenv("PET_PAYMENT_MODE", "demo").lower()
    if value not in {"demo", "stripe"}:
        raise ProviderError("PET_PAYMENT_MODE 应为 demo 或 stripe")
    return value


def _safe_http_error(exc):
    # The response body can contain original prompts, binary uploads and signed URLs.
    status = exc.code
    return ProviderError(f"服务商请求失败（HTTP {status}）")


def _json(url, headers, body=None, *, form=False):
    data = None
    headers = dict(headers)
    if body is not None:
        data = (urllib.parse.urlencode(body).encode() if form
                else json.dumps(body, ensure_ascii=False).encode())
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=60) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ProviderError("服务商响应过大")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
            return result
    except urllib.error.HTTPError as exc:
        raise _safe_http_error(exc) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError("连接服务商超时或中断，请核查原任务") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProviderError("服务商返回的数据无法解析") from exc


def _allowed(url, domains):
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not any(host == dom or host.endswith("." + dom) for dom in domains)):
        raise ProviderError("供应商文件地址无效")
    return url


def _download(url, domains, limit):
    # Allow only the provider's HTTPS media hosts, including every redirect.
    for _ in range(4):
        _allowed(url, domains)
        try:
            with urllib.request.build_opener(_NoRedirect()).open(url, timeout=90) as res:
                data = res.read(limit + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                url = urllib.parse.urljoin(url, exc.headers["Location"])
                continue
            raise _safe_http_error(exc) from None
        except (urllib.error.URLError, OSError) as exc:
            raise ProviderError("下载生成文件失败，请重新获取原任务的结果") from exc
        if not data or len(data) > limit:
            raise ProviderError("生成文件为空或超出允许大小")
        return data
    raise ProviderError("供应商文件重定向过多")


def _demo_portrait(key, style, prompt, index):
    image = storage.open_photo(storage.read(key))
    image.thumbnail((1540, 1540), Image.Resampling.LANCZOS)
    seed = hashlib.blake2s((style + prompt).encode()).digest()[0]
    # Local image processing preserves features from the actual uploaded photograph.
    smooth = image.filter(ImageFilter.MedianFilter(5 if min(image.size) > 400 else 3))
    smooth = smooth.filter(ImageFilter.SMOOTH_MORE)
    sketch = "铅笔" in style or "pencil" in style
    if sketch:
        edges = ImageOps.invert(smooth.convert("L").filter(ImageFilter.FIND_EDGES))
        base = ImageOps.colorize(ImageChops.multiply(edges, ImageOps.grayscale(image)), "#584b42", "#faf6eb")
        painted = Image.blend(image, base, .67)
    else:
        painterly = smooth.quantize(colors=32 + (seed % 4)*8+index*16).convert("RGB")
        warm = ImageOps.colorize(ImageOps.grayscale(smooth), "#403d40", "#fae4bb")
        painted = Image.blend(painterly, warm, .25 if index == 0 else .13)
        clay = "黏土" in style or "clay" in style
        painted = ImageEnhance.Color(painted).enhance(1.07 if clay else .9)
        painted = ImageEnhance.Contrast(painted).enhance(1.08 if clay else .96)
        painted = Image.blend(painted, Image.new("RGB", painted.size, (252, 247, 233)), .05)
    return storage.jpeg(painted, 93)


def _receipt(provider, detail):
    key = storage.put(json.dumps(detail).encode(), "json")
    return provider + ":" + key


def _receipt_detail(task_id):
    provider, sep, key = task_id.partition(":")
    if not sep:
        raise ValueError("生成任务标识无效")
    return provider, json.loads(storage.read(key))


def _dash_base():
    root = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com").rstrip("/")
    _allowed(root, ("aliyuncs.com",))
    return root


def _fal_headers():
    return {"Authorization": "Key " + _required("FAL_KEY")}


def _dash_headers():
    return {"Authorization": "Bearer " + _required("DASHSCOPE_API_KEY")}


def submit_model(kind: str, image_keys: list[str], prompt: str, style: str = "",
                 count: int = 1, request_key: str | None = None) -> str:
    """A vendor task can run after a timeout. Caller persists the returned ID at once.

    Neither inference provider documents a usable idempotency token; the application
    should reconcile an ambiguous submission instead of submitting a duplicate.
    """
    mode = model_mode(kind)
    if not image_keys or len(image_keys) > (10 if kind == "portrait" else 4):
        raise ValueError("请提供有效数量的参考照片")
    if count not in (1, 2):
        raise ValueError("每次支持一至两张候选图")
    if mode == "demo":
        if kind == "portrait":
            outputs = [{"kind": "image", "key": storage.put(
                _demo_portrait(image_keys[0], style, prompt, i), "jpg")} for i in range(count)]
        else:
            glb, stl = demo_mesh()
            outputs = [{"kind": "glb", "key": storage.put(glb, "glb")},
                       {"kind": "stl", "key": storage.put(stl, "stl")}]
        return _receipt("demo", {"kind": kind, "outputs": outputs})

    photos = [storage.source_image(key) for key in image_keys]
    if kind == "portrait":
        h = _dash_headers()
        h["X-DashScope-Async"] = "enable"
        instruction = f"{style}。{prompt}" if style else prompt
        body = {"model": os.getenv("QWEN_IMAGE_MODEL", "qwen-image-2.1-turbo"),
                "input": {"messages": [{"role": "user", "content":
                    [{"image": image} for image in photos] + [{"text": instruction}]}]},
                "parameters": {"n": count, "size": "1024*1024", "prompt_extend": False}}
        reply = _json(_dash_base()+"/api/v1/services/aigc/image-generation/generation", h, body)
        remote = reply.get("output", {}).get("task_id")
        if not isinstance(remote, str) or not re.fullmatch(r"[\w-]{1,160}", remote):
            raise ProviderError("图片服务未返回可查询的任务编号")
        # Native DashScope task ID survives changes to mode or storage.
        return "dash:" + remote

    multiple = len(photos) > 1
    route = "multi-image-to-3d" if multiple else "image-to-3d"
    body = {"image_urls": photos} if multiple else {"image_url": photos[0]}
    body.update(should_texture=True, symmetry_mode="off")
    if prompt.strip():
        body.update(texture_prompt=prompt[:800], texture_model="meshy-7")
    result = _json("https://queue.fal.run/fal-ai/meshy/v7.1/" + route, _fal_headers(), body)
    remote = result.get("request_id")
    if not isinstance(remote, str) or not re.fullmatch(r"[\w-]{1,160}", remote):
        raise ProviderError("建模服务未返回可查询的任务编号")
    # The queue response supplies the canonical application path. Partners can
    # move an endpoint without changing the route we use to submit new jobs.
    result_url = result.get("response_url")
    if result_url:
        _allowed(result_url, ("queue.fal.run",))
        path = urllib.parse.urlsplit(result_url).path
        if not re.fullmatch(r"(?:/[A-Za-z0-9_.-]+){1,6}/requests/" + re.escape(remote), path):
            raise ProviderError("建模服务返回了无效的任务地址")
        return "fal:" + path
    return "fal:" + remote


def _file_url(value):
    return value.get("url") if isinstance(value, dict) else value


def poll_model(kind: str, task_id: str) -> dict:
    provider, sep, remote = task_id.partition(":")
    if provider == "demo":
        _, job = _receipt_detail(task_id)
        if job["kind"] != kind:
            raise ValueError("生成任务类型不符")
        return {"status":"succeeded", "outputs":job["outputs"]}
    canonical_fal_path = provider == "fal" and re.fullmatch(
        r"(?:/[A-Za-z0-9_.-]+){1,6}/requests/[\w-]{1,160}", remote
    )
    if not sep or not (canonical_fal_path or re.fullmatch(r"[\w-]{1,160}", remote)):
        raise ValueError("生成任务标识无效")

    if provider == "dash" and kind == "portrait":
        reply = _json(_dash_base()+"/api/v1/tasks/"+remote, _dash_headers())
        result = reply.get("output", {})
        state = result.get("task_status")
        if state in ("PENDING","RUNNING"):
            return {"status": "pending"}
        if state != "SUCCEEDED":
            return {"status": "failed", "error": "图片服务任务未完成（" + str(state) + "）"}
        urls = [item["image"] for choice in result.get("choices", [])
                for item in choice.get("message", {}).get("content", []) if item.get("image")]
        if not urls:
            return {"status":"failed", "error":"图片服务没有返回可交付作品"}
        outputs = []
        for url in urls:
            data = _download(url, ("aliyuncs.com",), 32 * 1024 * 1024)
            normalized = storage.jpeg(storage.open_photo(data), 95)
            outputs.append({"kind":"image","key":storage.put(normalized, "jpg")})
        return {"status": "succeeded", "outputs": outputs}

    if provider != "fal" or kind != "model":
        raise ValueError("生成任务类型不符")
    path = remote if canonical_fal_path else "/fal-ai/meshy/requests/" + remote
    root = "https://queue.fal.run" + path
    h = _fal_headers()
    report = _json(root+"/status", h)
    if report.get("status") in ("IN_PROGRESS", "IN_QUEUE"):
        return {"status":"pending"}
    if report.get("status") != "COMPLETED" or report.get("error"):
        return {"status":"failed", "error":"建模服务任务失败"}
    result = _json(root, h)
    models = result.get("model_urls") or {}
    glb = _file_url(result.get("model_glb") or models.get("glb"))
    stl = _file_url(models.get("stl") or result.get("model_stl"))
    if not glb:
        return {"status": "failed", "error": "建模服务未返回 GLB 文件"}
    domains = ("fal.media", "meshy.ai", "meshy.art")
    data = _download(glb, domains, 200 * 1024 * 1024)
    if data[:4] != b"glTF":
        raise ProviderError("建模结果不是有效的 GLB 文件")
    # STL is optional in Meshy's response. A local scene export avoids a second
    # generation charge and gives the reviewer the exact approved geometry.
    printable = _download(stl, domains, 200 * 1024 * 1024) if stl else stl_from_glb(data)
    return {"status": "succeeded", "outputs": [
        {"kind": "glb", "key": storage.put(data, "glb")},
        {"kind": "stl", "key": storage.put(printable, "stl")},
    ]}



def _stripe(resource, body=None, key=None):
    headers = {"Authorization":"Bearer "+_required("STRIPE_SECRET_KEY")}
    if key:
        headers["Idempotency-Key"] = key
    return _json("https://api.stripe.com/v1/"+resource, headers, body, form=True)


def create_checkout(order_id: str, amount_fen: int, title: str, return_url: str, previous_id: str = "") -> dict:
    if payment_mode() != "stripe":
        raise ValueError("演示模式无需创建真实收银台")
    if not 0 < amount_fen or len(order_id) > 128:
        raise ValueError("支付订单无效")
    parsed = urllib.parse.urlsplit(return_url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("支付返回地址无效")
    _required("STRIPE_WEBHOOK_SECRET")  # Never collect funds without a configured callback.
    form = {"mode":"payment","client_reference_id":order_id,"metadata[order_id]":order_id,
            "payment_intent_data[metadata][order_id]":order_id,"line_items[0][quantity]":"1",
            "line_items[0][price_data][unit_amount]":str(amount_fen),
            "line_items[0][price_data][currency]":"cny",
            "line_items[0][price_data][product_data][name]":title[:120],
            "success_url":return_url,"cancel_url":return_url}
    idempotency_key = "pet-checkout-" + order_id + ("-" + previous_id if previous_id else "")
    result = _stripe("checkout/sessions", form, idempotency_key)
    if not result.get("id") or not result.get("url"):
        raise ProviderError("支付平台未返回收银台")
    _allowed(result["url"], ("stripe.com",))
    return {"id": result["id"], "url": result["url"]}


def verify_payment(payload: bytes, signature: str) -> dict:
    """Verify the exact raw HTTP body, then normalize paid and refund events."""
    if payment_mode() != "stripe":
        raise ValueError("未启用真实支付回调")
    parts = [pair.split("=", 1) for pair in signature.split(",") if "=" in pair]
    try:
        timestamp = next(value for key,value in parts if key=="t")
        if abs(int(time.time()) - int(timestamp)) > 300:
            raise ValueError()
    except (ValueError, StopIteration):
        raise ValueError("支付通知时间无效") from None
    expected = hmac.new(_required("STRIPE_WEBHOOK_SECRET").encode(),
                        timestamp.encode()+b"."+payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, val) for key,val in parts if key=="v1"):
        raise ValueError("支付通知签名无效")
    event = json.loads(payload)
    obj = event["data"]["object"]
    name = event["type"]
    if name in ("refund.created", "refund.updated", "refund.failed"):
        return {"type":"refund","order_id":(obj.get("metadata") or {}).get("order_id"),
                "refund_id":obj["id"],"refund_status":obj.get("status"),
                "amount_fen":obj.get("amount"),"payment_ref":obj.get("payment_intent"),"event_id":event["id"]}
    if name in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        return {"type":"checkout_expired", "order_id":(obj.get("metadata") or {}).get("order_id"),
                "checkout_id":obj["id"], "amount_fen":obj.get("amount_total"), "event_id":event["id"]}
    if name not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return {}
    order_id = (obj.get("metadata") or {}).get("order_id")
    if (obj.get("payment_status") != "paid" or obj.get("currency") != "cny"
            or not order_id or order_id != obj.get("client_reference_id")
            or not isinstance(obj.get("amount_total"),int)
            or not isinstance(obj.get("payment_intent"),str)):
        return {}
    return {"type":"payment","order_id":order_id,"amount_fen":obj["amount_total"],
            "payment_ref":obj["payment_intent"],"event_id":event["id"]}


def get_refund_status(refund_id: str) -> str:
    if not re.fullmatch(r"re_[a-zA-Z0-9]+", refund_id):
        raise ValueError("退款编号无效")
    return _stripe("refunds/"+refund_id)["status"]


def refund_payment(payment_ref: str, amount_fen: int, order_id: str) -> str:
    if payment_mode() != "stripe":
        if payment_ref and payment_ref.startswith("pi_"):
            raise ProviderError("真实付款不能按演示退款")
        return "demo-refund-" + order_id
    if not re.fullmatch(r"pi_[a-zA-Z0-9]+", payment_ref or "") or amount_fen <= 0:
        raise ValueError("原支付凭证无效")
    result = _stripe("refunds", {"payment_intent":payment_ref, "amount":str(amount_fen),
                     "metadata[order_id]":order_id}, "pet-refund-"+order_id)
    if result.get("status") in ("pending", "requires_action"):
        raise PaymentPending(result["id"])
    if result.get("status") != "succeeded":
        raise ProviderError("支付平台未完成退款，请核查原退款记录")
    return result["id"]
