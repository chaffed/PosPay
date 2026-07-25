from pospay.services import security_group_service, user_service
from tests.conftest import TenantFactory


def _login(client, tenant_slug, email, password=TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    client.post(
        "/ui/login", data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"}
    )
    return csrf


def test_users_page_requires_permission(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-users-forbidden")
    _login(client, tenant.slug, users["viewer"].email)

    resp = client.get("/ui/users", follow_redirects=False)
    assert resp.status_code == 403


def test_add_brand_new_user(client, db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-users-add-new")
    csrf = _login(client, tenant.slug, users["admin"].email)
    group = security_group_service.get_security_group_by_name(db_session, tenant.id, "Preparer")

    resp = client.post(
        "/ui/users",
        data={"csrf_token": csrf, "email": "newperson@example.com", "password": "hunter2-hunter2", "security_group_id": str(group.id)},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/ui/users")

    list_page = client.get("/ui/users")
    assert "newperson@example.com" in list_page.text
    assert "Preparer" in list_page.text


def test_add_existing_email_from_other_tenant_requires_confirmation(client, db_session, tenant_factory):
    tenant_a, _account_a, users_a = tenant_factory.make(slug="web-users-cross-a")
    tenant_b, _account_b, users_b = tenant_factory.make(slug="web-users-cross-b")
    csrf = _login(client, tenant_b.slug, users_b["admin"].email)
    group_b = security_group_service.get_security_group_by_name(db_session, tenant_b.id, "Viewer")

    resp = client.post(
        "/ui/users",
        data={"csrf_token": csrf, "email": users_a["preparer"].email, "password": "", "security_group_id": str(group_b.id)},
    )
    assert resp.status_code == 200
    assert "Confirm access" in resp.text

    # not yet granted — still only a member of tenant_a
    pending_memberships = user_service.list_memberships_for_user(db_session, users_a["preparer"].id)
    assert {m.tenant.id for m in pending_memberships} == {tenant_a.id}

    # now confirm it
    confirm_resp = client.post(
        "/ui/users/confirm",
        data={"csrf_token": csrf, "email": users_a["preparer"].email, "security_group_id": str(group_b.id)},
        follow_redirects=False,
    )
    assert confirm_resp.status_code == 303
    memberships = user_service.list_memberships_for_user(db_session, users_a["preparer"].id)
    assert {m.tenant.id for m in memberships} == {tenant_a.id, tenant_b.id}


def test_deactivate_and_reactivate_user(client, db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-users-deactivate")
    csrf = _login(client, tenant.slug, users["admin"].email)
    from pospay.repositories.tenant_membership_repo import TenantMembershipRepository

    membership = TenantMembershipRepository(db_session, tenant.id).list(user_id=users["viewer"].id)[0]

    resp = client.post(f"/ui/users/{membership.id}/deactivate", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303

    list_page = client.get("/ui/users")
    assert "deactivated" in list_page.text

    resp = client.post(f"/ui/users/{membership.id}/reactivate", data={"csrf_token": csrf}, follow_redirects=False)
    assert resp.status_code == 303


def test_bulk_upload_users_csv(client, db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-users-bulk-csv")
    tenant_other, _account_other, users_other = tenant_factory.make(slug="web-users-bulk-csv-other")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        "email,security_group,password\n"
        "bulknew@example.com,Preparer,hunter2-hunter2\n"
        f"{users_other['viewer'].email},Viewer,\n"
    ).encode()

    resp = client.post(
        "/ui/users/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("users.csv", content, "text/csv")},
    )
    assert resp.status_code == 200
    assert "1 created" in resp.text
    assert "1 need" in resp.text

    confirm_value = f"{users_other['viewer'].email}::"
    # extract the security_group_id rendered into the hidden checkbox value
    import re

    match = re.search(rf'value="({re.escape(confirm_value)}[0-9a-f-]+)"', resp.text)
    assert match is not None

    confirm_resp = client.post(
        "/ui/users/bulk/confirm", data={"csrf_token": csrf, "confirm": match.group(1)}, follow_redirects=False
    )
    assert confirm_resp.status_code == 200
    assert "1 created" in confirm_resp.text
