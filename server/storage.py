"""Private blobs. Only the application may translate a key into a user's file."""
from __future__ import annotations

import base64
import io
import os
import re
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError


_KEY = re.compile(r"^[0-9a-f]{32}\.(?:jpg|jpeg|png|webp|glb|stl|json)$")
_MIMES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
          "webp": "image/webp", "glb": "model/gltf-binary",
          "stl": "model/stl", "json": "application/json"}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 36_000_000


def _key(key: str) -> str:
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("无效的文件标识")
    return key


def _s3_enabled() -> bool:
    return bool(os.getenv("PET_S3_BUCKET"))


@lru_cache(maxsize=4)
def _s3(endpoint: str, region: str):
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3", endpoint_url=endpoint or None, region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def _s3_client():
    return _s3(os.getenv("PET_S3_ENDPOINT", ""), os.getenv("PET_S3_REGION", "us-east-1"))


def _root() -> Path:
    return Path(os.getenv("PET_DATA_DIR", "data")) / "media"


def put(data: bytes, suffix: str) -> str:
    ext = suffix.lower().lstrip(".")
    key = _key(f"{uuid.uuid4().hex}.{ext}")
    if _s3_enabled():
        _s3_client().put_object(Bucket=os.environ["PET_S3_BUCKET"],
                                Key=f"private/{key}", Body=data, ContentType=_MIMES[ext])
    else:
        root = _root()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as output:
            try:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
                os.replace(output.name, root / key)
            finally:
                Path(output.name).unlink(missing_ok=True)
    return key


def read(key: str) -> bytes:
    _key(key)
    if _s3_enabled():
        obj = _s3_client().get_object(Bucket=os.environ["PET_S3_BUCKET"], Key=f"private/{key}")
        with obj["Body"] as stream:
            return stream.read()
    return (_root() / key).read_bytes()


def size(key: str) -> int:
    _key(key)
    if _s3_enabled():
        result = _s3_client().head_object(Bucket=os.environ["PET_S3_BUCKET"], Key=f"private/{key}")
        return result["ContentLength"]
    return (_root() / key).stat().st_size


def remove(key: str) -> None:
    _key(key)
    if _s3_enabled():
        _s3_client().delete_object(Bucket=os.environ["PET_S3_BUCKET"], Key=f"private/{key}")
    else:
        (_root() / key).unlink(missing_ok=True)


def source_image(key: str) -> str:
    """Provider-only URL; local files never need to be exposed to the internet."""
    _key(key)
    mime = _MIMES[key.rsplit(".", 1)[1]]
    if not mime.startswith("image/"):
        raise ValueError("建模需要图片")
    if _s3_enabled():
        return _s3_client().generate_presigned_url(
            "get_object", Params={"Bucket": os.environ["PET_S3_BUCKET"], "Key": f"private/{key}"},
            ExpiresIn=3600,
        )
    return f"data:{mime};base64," + base64.b64encode(read(key)).decode("ascii")


def open_photo(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ("JPEG", "PNG", "WEBP") or source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("支持 JPEG、PNG 和 WebP，图片最多 3600 万像素")
            if min(source.size) < 32:
                raise ValueError("请上传宽高至少 32 像素的照片")
            source.load()
            fixed = ImageOps.exif_transpose(source)
            if "A" in fixed.getbands() or "transparency" in fixed.info:
                rgba = fixed.convert("RGBA")
                background = Image.new("RGB", fixed.size, (250, 248, 244))
                background.paste(rgba, mask=rgba.getchannel("A"))
                return background
            return fixed.convert("RGB")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("无法读取照片，请使用有效的 JPEG、PNG 或 WebP 图片") from exc


def jpeg(image: Image.Image, quality: int = 90) -> bytes:
    output = io.BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


def normalize_photo(data: bytes) -> bytes:
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("照片大小不能超过 12 MB")
    image = open_photo(data)
    image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
    return jpeg(image, 92)


def preview_image(data: bytes) -> bytes:
    image = open_photo(data)
    image.thumbnail((720, 720), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(overlay)
    size = max(11, min(image.size) // 25)
    font = ImageFont.load_default(size=size)
    for row, y in enumerate(range(size, image.height, size * 7)):
        for x in range(-size * 3 if row % 2 else size, image.width, size * 15):
            draw.text((x, y), "PORTRAIT PREVIEW", font=font,
                      fill=(255, 250, 238, 105), stroke_width=1,
                      stroke_fill=(65, 46, 31, 55))
    return jpeg(Image.alpha_composite(image.convert("RGBA"), overlay), 80)
