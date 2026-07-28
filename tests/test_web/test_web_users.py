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
    # extract the security_group_id rendered into the hidden checkbox value — the value
    # is "email::security_group_id::customer_id", with customer_id blank here (bank-wide)
    import re

    match = re.search(rf'value="({re.escape(confirm_value)}[0-9a-f-]+::)"', resp.text)
    assert match is not None

    confirm_resp = client.post(
        "/ui/users/bulk/confirm", data={"csrf_token": csrf, "confirm": match.group(1)}, follow_redirects=False
    )
    assert confirm_resp.status_code == 200
    assert "1 created" in confirm_resp.text


def test_export_csv_requires_permission(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-users-export-forbidden")
    _login(client, tenant.slug, users["viewer"].email)

    resp = client.get("/ui/users/export.csv", follow_redirects=False)
    assert resp.status_code == 403


def test_export_csv_contains_expected_rows(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-users-export-csv")
    _login(client, tenant.slug, users["admin"].email)

    resp = client.get("/ui/users/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="users.csv"' in resp.headers["content-disposition"]

    import csv
    import io

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert {row["email"] for row in rows} == {u.email for u in users.values()}
    admin_row = next(row for row in rows if row["email"] == users["admin"].email)
    assert admin_row["security_group"] == "Admin"
    assert admin_row["customer"] == "bank-wide"
    assert admin_row["status"] == "active"


def test_export_json_contains_expected_rows(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-users-export-json")
    _login(client, tenant.slug, users["admin"].email)

    resp = client.get("/ui/users/export.json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert 'filename="users.json"' in resp.headers["content-disposition"]

    body = resp.json()
    assert {row["email"] for row in body} == {u.email for u in users.values()}
    admin_row = next(row for row in body if row["email"] == users["admin"].email)
    assert admin_row["security_group"] == "Admin"
    assert admin_row["customer"] == "bank-wide"
    assert admin_row["status"] == "active"


def test_export_reflects_deactivated_status(client, db_session, tenant_factory):
    from pospay.repositories.tenant_membership_repo import TenantMembershipRepository

    tenant, _account, users = tenant_factory.make(slug="web-users-export-deactivated")
    _login(client, tenant.slug, users["admin"].email)
    membership = TenantMembershipRepository(db_session, tenant.id).list(user_id=users["viewer"].id)[0]
    user_service.deactivate_membership(db_session, tenant.id, membership.id)
    db_session.commit()

    body = client.get("/ui/users/export.json").json()
    viewer_row = next(row for row in body if row["email"] == users["viewer"].email)
    assert viewer_row["status"] == "deactivated"


def test_edit_entitlements_page_requires_permission(client, db_session, tenant_factory):
    from pospay.repositories.tenant_membership_repo import TenantMembershipRepository

    tenant, _account, users = tenant_factory.make(slug="web-users-edit-forbidden")
    membership = TenantMembershipRepository(db_session, tenant.id).list(user_id=users["viewer"].id)[0]
    _login(client, tenant.slug, users["viewer"].email)

    resp = client.get(f"/ui/users/{membership.id}/edit", follow_redirects=False)
    assert resp.status_code == 403


def test_edit_entitlements_changes_security_group(client, db_session, tenant_factory):
    from pospay.repositories.tenant_membership_repo import TenantMembershipRepository

    tenant, _account, users = tenant_factory.make(slug="web-users-edit-group")
    csrf = _login(client, tenant.slug, users["admin"].email)
    membership = TenantMembershipRepository(db_session, tenant.id).list(user_id=users["viewer"].id)[0]
    approver_group = security_group_service.get_security_group_by_name(db_session, tenant.id, "Approver")

    edit_form = client.get(f"/ui/users/{membership.id}/edit")
    assert edit_form.status_code == 200
    assert users["viewer"].email in edit_form.text

    resp = client.post(
        f"/ui/users/{membership.id}",
        data={"csrf_token": csrf, "security_group_id": str(approver_group.id), "customer_id": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    list_page = client.get("/ui/users")
    assert "Approver" in list_page.text

    db_session.expire_all()
    updated = TenantMembershipRepository(db_session, tenant.id).get(membership.id)
    assert updated.security_group_id == approver_group.id


def test_edit_entitlements_changes_customer_scope(client, db_session, tenant_factory):
    from pospay.repositories.tenant_membership_repo import TenantMembershipRepository
    from pospay.services import customer_service

    tenant, _account, users = tenant_factory.make(slug="web-users-edit-customer")
    csrf = _login(client, tenant.slug, users["admin"].email)
    customer = customer_service.create_customer(
        db_session, tenant.id, customer_service.CustomerInput(customer_number="C-1", name="Acme Co")
    )
    db_session.commit()
    membership = TenantMembershipRepository(db_session, tenant.id).list(user_id=users["viewer"].id)[0]

    resp = client.post(
        f"/ui/users/{membership.id}",
        data={"csrf_token": csrf, "security_group_id": str(membership.security_group_id), "customer_id": str(customer.id)},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    list_page = client.get("/ui/users")
    assert "Acme Co" in list_page.text


def test_edit_entitlements_shows_error_on_scope_collision(client, db_session, tenant_factory):
    from pospay.repositories.tenant_membership_repo import TenantMembershipRepository
    from pospay.services import customer_service

    tenant, _account, users = tenant_factory.make(slug="web-users-edit-collision")
    csrf = _login(client, tenant.slug, users["admin"].email)
    customer = customer_service.create_customer(
        db_session, tenant.id, customer_service.CustomerInput(customer_number="C-1", name="Acme Co")
    )
    preparer_group = security_group_service.get_security_group_by_name(db_session, tenant.id, "Preparer")
    scoped_user = user_service.create_user_with_membership(
        db_session, tenant.id, email="scoped-collide@example.com", password="hunter2-hunter2",
        security_group_id=preparer_group.id, customer_id=customer.id,
    )
    db_session.commit()
    scoped_membership = TenantMembershipRepository(db_session, tenant.id).list(user_id=scoped_user.id)[0]
    bankwide_membership = TenantMembershipRepository(db_session, tenant.id).list(user_id=users["viewer"].id)[0]
    assert bankwide_membership.customer_id is None

    # try to move the viewer's own bank-wide membership onto the same customer scoped_user already holds --
    # no actual collision there since it's a different user; instead try moving scoped_user's membership
    # to bank-wide while they have no other membership -- to force a real collision, first grant them a
    # second, bank-wide membership too
    user_service.confirm_cross_tenant_membership(
        db_session, tenant.id, email="scoped-collide@example.com", security_group_id=preparer_group.id, customer_id=None
    )
    db_session.commit()

    resp = client.post(
        f"/ui/users/{scoped_membership.id}",
        data={"csrf_token": csrf, "security_group_id": str(preparer_group.id), "customer_id": ""},
    )
    assert resp.status_code == 422
    assert "already has a separate membership" in resp.text


def test_edit_entitlements_404s_for_unknown_membership(client, tenant_factory):
    import uuid

    tenant, _account, users = tenant_factory.make(slug="web-users-edit-404")
    _login(client, tenant.slug, users["admin"].email)

    resp = client.get(f"/ui/users/{uuid.uuid4()}/edit")
    assert resp.status_code == 404


def test_edit_entitlements_404s_for_other_tenants_membership(client, db_session, tenant_factory):
    from pospay.repositories.tenant_membership_repo import TenantMembershipRepository

    tenant_a, _account_a, users_a = tenant_factory.make(slug="web-users-edit-cross-a")
    tenant_b, _account_b, users_b = tenant_factory.make(slug="web-users-edit-cross-b")
    membership_a = TenantMembershipRepository(db_session, tenant_a.id).list(user_id=users_a["viewer"].id)[0]
    _login(client, tenant_b.slug, users_b["admin"].email)

    resp = client.get(f"/ui/users/{membership_a.id}/edit")
    assert resp.status_code == 404
