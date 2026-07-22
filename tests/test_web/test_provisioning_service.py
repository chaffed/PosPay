from pospay.auth.security import verify_password
from pospay.domain.user import UserRole
from pospay.services.provisioning_service import create_tenant_with_admin


def test_create_tenant_with_admin(db_session):
    identity = create_tenant_with_admin(
        db_session,
        tenant_name="Acme Bank",
        tenant_slug="acme-bank",
        admin_email="admin@acme.example.com",
        admin_password="hunter2-hunter2",
    )
    db_session.commit()

    assert identity.tenant.slug == "acme-bank"
    assert identity.admin_user.role == UserRole.ADMIN
    assert identity.admin_user.tenant_id == identity.tenant.id
    assert verify_password("hunter2-hunter2", identity.admin_user.hashed_password)
