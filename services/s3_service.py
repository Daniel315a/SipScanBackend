import os
import asyncio
import mimetypes
from uuid import uuid4
from datetime import datetime
import boto3

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "receipts")
PRESIGN_TTL_SECONDS = int(os.getenv("PRESIGN_TTL_SECONDS", "3600"))

_s3 = None

def _client():
    """Lazily create an S3 client using env credentials/role."""
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=AWS_REGION)
    return _s3

def _guess_ext(filename: str | None, content_type: str | None) -> str:
    ext = ""
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[1].lower()
    if not ext and content_type:
        ext = mimetypes.guess_extension(content_type) or ""
    return ext

def build_key(uploader_nit: str, filename: str | None, content_type: str | None) -> str:
    """Create a hierarchical S3 key: prefix/YYYY/MM/NIT/uuid.ext"""
    now = datetime.utcnow()
    ext = _guess_ext(filename, content_type)
    safe_nit = "".join(ch for ch in (uploader_nit or "") if ch.isalnum() or ch in ("-", "_"))
    return f"{S3_PREFIX}/{now.year:04d}/{now.month:02d}/{safe_nit}/{uuid4().hex}{ext}"

async def upload_image(upload_file, uploader_nit: str) -> tuple[str, str]:
    """
    Upload the received UploadFile to S3 (private). Returns (bucket, key).
    """
    key = build_key(uploader_nit, getattr(upload_file, "filename", None), upload_file.content_type)
    s3 = _client()

    # Ensure file pointer at start
    upload_file.file.seek(0)

    def _do_upload():
        extra = {}
        if upload_file.content_type:
            extra["ContentType"] = upload_file.content_type
        s3.upload_fileobj(upload_file.file, S3_BUCKET, key, ExtraArgs=extra or None)

    # Run blocking boto3 call off the event loop
    await asyncio.to_thread(_do_upload)
    return S3_BUCKET, key

def presign_url(bucket: str, key: str, ttl: int | None = None) -> str:
    """Generate a time-limited URL for GET access."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=int(ttl or PRESIGN_TTL_SECONDS),
    )
