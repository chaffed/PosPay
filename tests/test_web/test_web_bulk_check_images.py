# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import io
import zipfile

from PIL import Image

from pospay.bulk_import.x937 import _T10_BUSINESS_DATE, _T25_AMOUNT, _T25_AUX_ON_US, _T25_ON_US, _T25_ROUTING_NUMBER
from tests.conftest import TenantFactory


def _login(client, tenant_slug, email, password=TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    client.post(
        "/ui/login", data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"}
    )
    return csrf


def _make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _two_page_tiff() -> bytes:
    front = Image.new("RGB", (30, 15), "white")
    back = Image.new("RGB", (30, 15), "black")
    buffer = io.BytesIO()
    front.save(buffer, format="TIFF", save_all=True, append_images=[back])
    return buffer.getvalue()


def _single_page_jpeg() -> bytes:
    img = Image.new("RGB", (30, 15), "blue")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


def _fixed_record(record_type: str, fields: dict[slice, str], length: int = 80) -> bytes:
    buf = bytearray(b" " * length)
    buf[0:2] = record_type.encode("ascii")
    for field_slice, value in fields.items():
        encoded = value.encode("ascii")
        buf[field_slice] = encoded.ljust(field_slice.stop - field_slice.start)[: field_slice.stop - field_slice.start]
    return bytes(buf)


def _synthetic_x937_file(*, account_number: str, check_number: str, amount_cents: int, image_bytes: bytes) -> bytes:
    image_header = bytearray(b" " * 116)
    image_header[0:2] = b"52"
    length_field = str(len(image_bytes)).zfill(10).encode("ascii")
    image_record = bytes(image_header) + length_field + image_bytes

    return b"".join(
        [
            _fixed_record("01", {}),
            _fixed_record("10", {_T10_BUSINESS_DATE: "20260115"}),
            _fixed_record(
                "25",
                {
                    _T25_ROUTING_NUMBER: "12345678",
                    _T25_ON_US: account_number,
                    _T25_AUX_ON_US: check_number,
                    _T25_AMOUNT: str(amount_cents).zfill(10),
                },
            ),
            _fixed_record("50", {}, length=200),
            image_record,
            _fixed_record("70", {}),
            _fixed_record("90", {}),
            _fixed_record("99", {}),
        ]
    )


def test_bulk_upload_form_requires_both_permissions(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-checkimg-forbidden")
    _login(client, tenant.slug, users["viewer"].email)

    resp = client.get("/ui/check-images/bulk", follow_redirects=False)
    assert resp.status_code == 403


def test_bulk_upload_zip_creates_paid_items_and_splits_multipage_tiff(client, db_session, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-bulk-checkimg-zip")
    csrf = _login(client, tenant.slug, users["admin"].email)

    manifest = (
        "account_number,check_number,amount,presented_date,front_image_filename\n"
        f"{account.account_number},7001,150.00,2026-01-15,check7001.tif\n"
        f"{account.account_number},7002,25.99,2026-01-16,check7002.jpg\n"
        f"{account.account_number},7003,10.00,2026-01-17,does-not-exist.jpg\n"
    ).encode()
    zip_bytes = _make_zip(
        {
            "manifest.csv": manifest,
            "check7001.tif": _two_page_tiff(),
            "check7002.jpg": _single_page_jpeg(),
        }
    )

    resp = client.post(
        "/ui/check-images/bulk",
        data={"csrf_token": csrf, "format": "zip"},
        files={"upload_file": ("checks.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    assert "2 of 3 succeeded" in resp.text
    assert "was not found in the zip" in resp.text

    paid_items_page = client.get("/ui/paid-items")
    assert "7001" in paid_items_page.text
    assert "7002" in paid_items_page.text
    assert "7003" not in paid_items_page.text

    check_images_page = client.get("/ui/check-images")
    assert check_images_page.status_code == 200
    # OCR ran synchronously in the background task under TestClient
    assert "completed" in check_images_page.text or "failed" in check_images_page.text


def test_bulk_upload_x937_creates_paid_item_with_image(client, db_session, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-bulk-checkimg-x937")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = _synthetic_x937_file(
        account_number=account.account_number, check_number="8001", amount_cents=5000, image_bytes=_single_page_jpeg()
    )

    resp = client.post(
        "/ui/check-images/bulk",
        data={"csrf_token": csrf, "format": "x937"},
        files={"upload_file": ("cashletter.x937", content, "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text
    assert "1 of 1 succeeded" in resp.text

    paid_items_page = client.get("/ui/paid-items")
    assert "8001" in paid_items_page.text


def test_bulk_upload_x937_unknown_account_fails_cleanly(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-checkimg-x937-badacct")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = _synthetic_x937_file(
        account_number="no-such-account", check_number="9001", amount_cents=1000, image_bytes=_single_page_jpeg()
    )

    resp = client.post(
        "/ui/check-images/bulk",
        data={"csrf_token": csrf, "format": "x937"},
        files={"upload_file": ("cashletter.x937", content, "application/octet-stream")},
    )
    assert resp.status_code == 200
    assert "No account found" in resp.text


def test_check_image_download_routes_serve_normalized_png(client, db_session, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-bulk-checkimg-download")
    csrf = _login(client, tenant.slug, users["admin"].email)

    manifest = (
        "account_number,check_number,amount,presented_date,front_image_filename\n"
        f"{account.account_number},6001,42.00,2026-01-15,check6001.tif\n"
    ).encode()
    zip_bytes = _make_zip({"manifest.csv": manifest, "check6001.tif": _two_page_tiff()})

    client.post(
        "/ui/check-images/bulk",
        data={"csrf_token": csrf, "format": "zip"},
        files={"upload_file": ("checks.zip", zip_bytes, "application/zip")},
    )

    from pospay.repositories.check_image_repo import CheckImageRepository

    image = CheckImageRepository(db_session, tenant.id).list()[0]

    front_resp = client.get(f"/ui/check-images/{image.id}/front")
    assert front_resp.status_code == 200
    assert front_resp.headers["content-type"] == "image/png"

    back_resp = client.get(f"/ui/check-images/{image.id}/back")
    assert back_resp.status_code == 200
    assert back_resp.headers["content-type"] == "image/png"
