"""The full catalog of permission keys a security group can grant, and the default
groups seeded into every new tenant. Replaces the old fixed `UserRole` enum + static
`PERMISSIONS` matrix (auth/rbac.py, now deleted) — permission sets are now per-tenant,
named, and editable (see services/security_group_service.py), not hardcoded roles.

Both channels (the JSON API's `require_permission` and the web UI's
`require_web_permission`) check membership in the same `TenantContext.permissions` set,
resolved fresh from a tenant's SecurityGroup row on every request (auth/deps.py) — so
these keys are the single source of truth for every gated action in the app, read or
write, across both channels."""

PERMISSION_CATALOG: dict[str, str] = {
    "account:read": "View accounts",
    "account:write": "Create accounts",
    "issued_item:read": "View issued items",
    "issued_item:write": "Create/void issued items",
    "stop_payment:read": "View stop payments",
    "stop_payment:write": "Create/cancel stop payments",
    "paid_item:read": "View paid items",
    "paid_item:write": "Submit paid items",
    "check_image:read": "View check images",
    "check_image:write": "Upload/reprocess check images",
    "ach_authorization:read": "View ACH authorizations",
    "ach_authorization:write": "Create/revoke ACH authorizations",
    "ach_transaction:read": "View ACH transactions",
    "ach_transaction:write": "Submit/bulk-load ACH transactions",
    "exception:read": "View exceptions",
    "exception:recommend": "Recommend pay/return decisions",
    "exception:decide": "Finalize pay/return decisions",
    "admin:manage": "Manage ML models and payment networks",
    "user:manage": "Manage users",
    "security_group:manage": "Manage security groups",
    "tenant:manage": "Manage organization branding and settings",
    "audit_log:read": "View the immutable action log",
    "customer:manage": "Manage customers",
}

# Masked out of TenantContext.permissions whenever the active membership is
# customer-scoped (auth/deps.py::decode_and_build_context) — regardless of what the
# assigned security group nominally contains. These are all tenant-wide/bank-staff
# concerns (managing other users, other customers, the tenant's own branding/settings,
# admin ML controls, or the full cross-customer action log); a customer's own staff, or a
# bank employee acting in a customer-scoped context, must never be able to reach them even
# via a misconfigured security group.
CUSTOMER_SCOPE_MASKED_PERMISSIONS: frozenset[str] = frozenset(
    {"user:manage", "security_group:manage", "tenant:manage", "customer:manage", "admin:manage", "audit_log:read"}
)

_ALL = list(PERMISSION_CATALOG)

# audit_log:read is deliberately excluded from the general read-permission bucket below —
# every other *:read key lands in Preparer/Approver/Viewer by default (they already see
# the underlying business records), but "who did what, when" is a more sensitive,
# cross-cutting view than any single resource's own data and defaults to Admin-only,
# same posture as the *:manage permissions. A tenant can still grant it to a custom group.
_READS = [key for key in _ALL if key.endswith(":read") and key != "audit_log:read"]

# Default groups seeded into every new tenant (provisioning_service.py, tests'
# TenantFactory) — chosen to exactly reproduce the old Admin/Preparer/Approver/Viewer
# role behavior, so nothing changes out of the box.
DEFAULT_SECURITY_GROUPS: dict[str, list[str]] = {
    "Admin": _ALL,
    "Preparer": [
        "account:read",
        "issued_item:read", "issued_item:write",
        "stop_payment:read", "stop_payment:write",
        "paid_item:read", "paid_item:write",
        "check_image:read", "check_image:write",
        "ach_authorization:read", "ach_authorization:write",
        "ach_transaction:read", "ach_transaction:write",
        "exception:read", "exception:recommend",
    ],
    "Approver": [*_READS, "exception:decide"],
    "Viewer": [*_READS],
}
