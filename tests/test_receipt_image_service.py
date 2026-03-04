"""Unit tests for receipt_image_service: get_images, create_images, get_first."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import services.receipt_image_service  # ensure module loaded before patching

_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000001")
_NOW = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_img(
    id_="aaaaaaaa-0000-0000-0000-000000000001",
    img_number=1,
    mime_type="image/jpeg",
    size_bytes=2048,
    s3_bucket="my-bucket",
    s3_key="receipts/img.jpg",
):
    img = MagicMock()
    img.id = id_
    img.img_number = img_number
    img.mime_type = mime_type
    img.size_bytes = size_bytes
    img.s3_bucket = s3_bucket
    img.s3_key = s3_key
    img.created_at = _NOW
    img.updated_at = _NOW
    return img


def _make_upload(content_type="image/jpeg", file_size=1024):
    upload = MagicMock()
    upload.content_type = content_type
    upload.file.tell.side_effect = [0, file_size]
    return upload


# ---------------------------------------------------------------------------
# get_images
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_images_empty():
    """Returns empty list when receipt has no images."""
    session = AsyncMock()
    with (
        patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", AsyncMock(return_value=[])),
    ):
        from services.receipt_image_service import get_images
        result = await get_images(session, receipt_id=_RECEIPT_ID)
    assert result == []


@pytest.mark.asyncio
async def test_get_images_single():
    """Returns list with one dict containing all expected fields."""
    session = AsyncMock()
    img = _make_img()
    with (
        patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", AsyncMock(return_value=[img])),
        patch("services.receipt_image_service.presign_url", return_value="https://s3.example.com/img.jpg"),
    ):
        from services.receipt_image_service import get_images
        result = await get_images(session, receipt_id=_RECEIPT_ID)

    assert len(result) == 1
    item = result[0]
    assert item["id"] == str(img.id)
    assert item["img_number"] == img.img_number
    assert item["mime_type"] == "image/jpeg"
    assert item["size_bytes"] == 2048
    assert item["s3_bucket"] == "my-bucket"
    assert item["s3_key"] == "receipts/img.jpg"
    assert item["url"] == "https://s3.example.com/img.jpg"
    assert item["created_at"] == _NOW
    assert item["updated_at"] == _NOW


@pytest.mark.asyncio
async def test_get_images_multiple():
    """Returns a dict per image, in the order returned by the repo."""
    session = AsyncMock()
    imgs = [_make_img(id_=f"img-{i}", img_number=i) for i in range(3)]
    with (
        patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", AsyncMock(return_value=imgs)),
        patch("services.receipt_image_service.presign_url", return_value="https://url"),
    ):
        from services.receipt_image_service import get_images
        result = await get_images(session, receipt_id=_RECEIPT_ID)

    assert len(result) == 3


@pytest.mark.asyncio
async def test_get_images_calls_presign_url_per_image():
    """presign_url is called once per image with correct bucket and key."""
    session = AsyncMock()
    img = _make_img(s3_bucket="bucket-A", s3_key="path/file.jpg")
    mock_presign = MagicMock(return_value="https://signed")
    with (
        patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", AsyncMock(return_value=[img])),
        patch("services.receipt_image_service.presign_url", mock_presign),
    ):
        from services.receipt_image_service import get_images
        await get_images(session, receipt_id=_RECEIPT_ID)

    mock_presign.assert_called_once_with("bucket-A", "path/file.jpg")


# ---------------------------------------------------------------------------
# get_first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_first_no_images_returns_none():
    """Returns None when the receipt has no images."""
    session = AsyncMock()
    with patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", AsyncMock(return_value=[])):
        from services.receipt_image_service import get_first
        result = await get_first(session, receipt_id=_RECEIPT_ID)
    assert result is None


@pytest.mark.asyncio
async def test_get_first_happy_path():
    """Returns dict with id, mime_type, size_bytes, and presigned url."""
    session = AsyncMock()
    img = _make_img(mime_type="image/png", size_bytes=512)
    with (
        patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", AsyncMock(return_value=[img])),
        patch("services.receipt_image_service.presign_url", return_value="https://signed-url"),
    ):
        from services.receipt_image_service import get_first
        result = await get_first(session, receipt_id=_RECEIPT_ID)

    assert result is not None
    assert result["id"] == str(img.id)
    assert result["mime_type"] == "image/png"
    assert result["size_bytes"] == 512
    assert result["url"] == "https://signed-url"


@pytest.mark.asyncio
async def test_get_first_calls_repo_with_limit_1():
    """Passes limit=1, offset=0 to the repo to fetch only the first image."""
    session = AsyncMock()
    img = _make_img()
    mock_get = AsyncMock(return_value=[img])
    with (
        patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", mock_get),
        patch("services.receipt_image_service.presign_url", return_value="https://url"),
    ):
        from services.receipt_image_service import get_first
        await get_first(session, receipt_id=_RECEIPT_ID)

    mock_get.assert_called_once_with(session, _RECEIPT_ID, limit=1, offset=0)


# ---------------------------------------------------------------------------
# create_images
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_images_empty_returns_empty_list():
    """Returns [] immediately when no images are provided."""
    session = AsyncMock()
    from services.receipt_image_service import create_images
    result = await create_images(session, uploader_nit="900", receipt_id=_RECEIPT_ID, images=[])
    assert result == []


@pytest.mark.asyncio
async def test_create_images_calls_upload_for_each_file():
    """upload_image is called once per UploadFile."""
    session = AsyncMock()
    uploads = [_make_upload(), _make_upload()]
    mock_upload = AsyncMock(return_value=("bucket", "key/img.jpg"))
    img = _make_img()
    with (
        patch("services.receipt_image_service.upload_image", mock_upload),
        patch("services.receipt_image_service.receipt_image_repo.create", AsyncMock()),
        patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", AsyncMock(return_value=[img, img])),
        patch("services.receipt_image_service.presign_url", return_value="https://url"),
    ):
        from services.receipt_image_service import create_images
        await create_images(session, uploader_nit="900", receipt_id=_RECEIPT_ID, images=uploads)

    assert mock_upload.call_count == 2


@pytest.mark.asyncio
async def test_create_images_creates_repo_row_for_each_file():
    """receipt_image_repo.create is called once per uploaded file."""
    session = AsyncMock()
    uploads = [_make_upload(), _make_upload()]
    mock_create = AsyncMock()
    img = _make_img()
    with (
        patch("services.receipt_image_service.upload_image", AsyncMock(return_value=("bucket", "key"))),
        patch("services.receipt_image_service.receipt_image_repo.create", mock_create),
        patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", AsyncMock(return_value=[img, img])),
        patch("services.receipt_image_service.presign_url", return_value="https://url"),
    ):
        from services.receipt_image_service import create_images
        await create_images(session, uploader_nit="900", receipt_id=_RECEIPT_ID, images=uploads)

    assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_create_images_returns_get_images_result():
    """Returns whatever get_images returns after uploading."""
    session = AsyncMock()
    uploads = [_make_upload()]
    img = _make_img()
    expected = [{"id": str(img.id), "url": "https://url", "mime_type": "image/jpeg",
                 "size_bytes": 2048, "img_number": 1, "s3_bucket": "my-bucket",
                 "s3_key": "receipts/img.jpg", "created_at": _NOW, "updated_at": _NOW}]
    with (
        patch("services.receipt_image_service.upload_image", AsyncMock(return_value=("bucket", "key"))),
        patch("services.receipt_image_service.receipt_image_repo.create", AsyncMock()),
        patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", AsyncMock(return_value=[img])),
        patch("services.receipt_image_service.presign_url", return_value="https://url"),
    ):
        from services.receipt_image_service import create_images
        result = await create_images(session, uploader_nit="900", receipt_id=_RECEIPT_ID, images=uploads)

    assert len(result) == 1
    assert result[0]["id"] == str(img.id)


@pytest.mark.asyncio
async def test_create_images_passes_mime_and_bucket_key_to_repo():
    """repo.create receives mime_type, s3_bucket, s3_key from upload."""
    session = AsyncMock()
    upload = _make_upload(content_type="image/png", file_size=512)
    mock_create = AsyncMock()
    img = _make_img()
    with (
        patch("services.receipt_image_service.upload_image", AsyncMock(return_value=("test-bucket", "test/key.png"))),
        patch("services.receipt_image_service.receipt_image_repo.create", mock_create),
        patch("services.receipt_image_service.receipt_image_repo.get_by_receipt", AsyncMock(return_value=[img])),
        patch("services.receipt_image_service.presign_url", return_value="https://url"),
    ):
        from services.receipt_image_service import create_images
        await create_images(session, uploader_nit="900", receipt_id=_RECEIPT_ID, images=[upload])

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["s3_bucket"] == "test-bucket"
    assert call_kwargs["s3_key"] == "test/key.png"
    assert call_kwargs["mime_type"] == "image/png"
    assert call_kwargs["receipt_id"] == _RECEIPT_ID
