from pospay.domain.user import UserRole

# Fixed permission matrix in code rather than dynamic role/permission tables — the roles
# in a positive-pay maker/checker workflow are a small, well-known set (admin, preparer,
# approver, viewer); a dynamic RBAC engine would be premature complexity for v1.
PERMISSIONS: dict[str, set[UserRole]] = {
    "issued_item:write": {UserRole.ADMIN, UserRole.PREPARER},
    "issued_item:read": {UserRole.ADMIN, UserRole.PREPARER, UserRole.APPROVER, UserRole.VIEWER},
    "stop_payment:write": {UserRole.ADMIN, UserRole.PREPARER},
    "paid_item:write": {UserRole.ADMIN, UserRole.PREPARER},
    "ach_authorization:write": {UserRole.ADMIN, UserRole.PREPARER},
    "ach_transaction:write": {UserRole.ADMIN, UserRole.PREPARER},
    "exception:recommend": {UserRole.ADMIN, UserRole.PREPARER},
    "exception:decide": {UserRole.ADMIN, UserRole.APPROVER},
    "exception:read": {UserRole.ADMIN, UserRole.PREPARER, UserRole.APPROVER, UserRole.VIEWER},
    "admin:manage": {UserRole.ADMIN},
    "account:write": {UserRole.ADMIN},
}


def role_has_permission(role: UserRole, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, set())
