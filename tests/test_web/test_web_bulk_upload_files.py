# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import re
from pathlib import Path

from pospay.domain.bulk_upload_file import BulkUploadKind
from pospay.repositories.bulk_upload_file_repo import BulkUploadFileRepository
from tests.conftest import TenantFactory


def _login(client, tenant_slug, email, password=TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    client.post(
        "/ui/login", data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"}
    )
    return csrf


def _extract_detail_link(html: str) -> str:
    match = re.search(r'href="(/ui/bulk-uploads/[0-9a-f-]+)"', html)
    assert match is not None, "no /ui/bulk-uploads/... link found on the page"
    return match.group(1)


def test_issued_items_upload_is_recorded_signed_and_downloadable(client, db_session, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="bulk-file-issued-items")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        f"account_number,check_number,amount,payee_name,issue_date\n"
        f"{account.account_number},9001,150.00,Vendor A,2026-01-01\n"
    ).encode()

    resp = client.post(
        "/ui/issued-items/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("items.csv", content, "text/csv")},
    )
    assert resp.status_code == 200
    assert "saved and signed" in resp.text

    detail_link = _extract_detail_link(resp.text)
    detail_resp = client.get(detail_link)
    assert detail_resp.status_code == 200
    assert "signature verified" in detail_resp.text

    download_resp = client.get(f"{detail_link}/download")
    assert download_resp.status_code == 200
    assert download_resp.content == content
    assert "items.csv" in download_resp.headers["content-disposition"]

    record = BulkUploadFileRepository(db_session, tenant.id).list(kind=BulkUploadKind.ISSUED_ITEMS)[0]
    assert record.succeeded_count == 1
    assert record.failed_count == 0


def test_rejected_file_is_still_recorded_and_linked(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="bulk-file-rejected")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/issued-items/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("items.xlsx", b"not a real spreadsheet", "application/octet-stream")},
    )
    assert resp.status_code == 422
    assert "saved and signed" in resp.text

    detail_link = _extract_detail_link(resp.text)
    detail_resp = client.get(detail_link)
    assert detail_resp.status_code == 200
    assert "Rejected before any rows were processed" in detail_resp.text


def test_ach_bulk_upload_is_recorded(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="bulk-file-ach")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        "account_number,originator_id,originator_name,receiver_id,amount,transaction_type,sec_code,trace_number,effective_date\n"
        f"{account.account_number},ORIG1,Payroll Co,,10.00,credit,PPD,T1,2026-01-10\n"
    ).encode()

    resp = client.post(
        "/ui/ach/transactions/bulk",
        data={"csrf_token": csrf, "format": "tabular"},
        files={"upload_file": ("txns.csv", content, "text/csv")},
    )
    assert resp.status_code == 200
    detail_link = _extract_detail_link(resp.text)

    download_resp = client.get(f"{detail_link}/download")
    assert download_resp.content == content


def test_users_bulk_upload_is_recorded(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="bulk-file-users")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = "email,security_group,password\nnewbie@example.com,Preparer,hunter2-hunter2\n".encode()

    resp = client.post(
        "/ui/users/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("users.csv", content, "text/csv")},
    )
    assert resp.status_code == 200
    detail_link = _extract_detail_link(resp.text)

    download_resp = client.get(f"{detail_link}/download")
    assert download_resp.content == content


def test_detail_page_shows_tampered_when_file_altered_on_disk(client, db_session, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="bulk-file-tampered-live")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        f"account_number,check_number,amount,payee_name,issue_date\n"
        f"{account.account_number},9002,150.00,Vendor A,2026-01-01\n"
    ).encode()
    resp = client.post(
        "/ui/issued-items/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("items.csv", content, "text/csv")},
    )
    detail_link = _extract_detail_link(resp.text)

    record = BulkUploadFileRepository(db_session, tenant.id).list(kind=BulkUploadKind.ISSUED_ITEMS)[0]
    path = Path(record.storage_path)
    path.chmod(0o644)
    path.write_bytes(b"tampered content")

    detail_resp = client.get(detail_link)
    assert "SIGNATURE MISMATCH" in detail_resp.text


def test_download_requires_the_upload_kind_permission(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="bulk-file-permission")
    admin_csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        f"account_number,check_number,amount,payee_name,issue_date\n"
        f"{account.account_number},9003,150.00,Vendor A,2026-01-01\n"
    ).encode()
    resp = client.post(
        "/ui/issued-items/bulk",
        data={"csrf_token": admin_csrf},
        files={"upload_file": ("items.csv", content, "text/csv")},
    )
    detail_link = _extract_detail_link(resp.text)

    _login(client, tenant.slug, users["viewer"].email)
    resp = client.get(detail_link, follow_redirects=False)
    assert resp.status_code == 403
    resp = client.get(f"{detail_link}/download", follow_redirects=False)
    assert resp.status_code == 403


def test_detail_and_download_404_for_unknown_upload_id(client, tenant_factory):
    import uuid

    tenant, _account, users = tenant_factory.make(slug="bulk-file-404")
    _login(client, tenant.slug, users["admin"].email)

    resp = client.get(f"/ui/bulk-uploads/{uuid.uuid4()}", follow_redirects=False)
    assert resp.status_code == 404
