# PosPay

Multi-tenant positive pay platform (checks + ACH today, extensible to other payment
networks — see `networks/`) with pluggable OCR and an ML-assisted exception review
feedback loop.

This README covers local setup and deployment only. For architecture (data model, the
network-adapter pattern, matching engine rules, ML pipeline design), see the project's
architecture plan. For the JSON API (`/api/v1/*` — endpoints, auth, permissions,
schemas), see [API.md](API.md). For implementing a new bank or a new customer —
prerequisites and step-by-step setup, also available as an in-app guided checklist at
`/ui/wizard/bank` and `/ui/customers/{id}/wizard` — see [RUNBOOK.md](RUNBOOK.md).

## Quickstart

**One-click (SQLite, zero manual setup)**: double-click `run_pospay.command` (macOS —
opens Terminal.app and runs it there). On first run it creates a virtual environment,
installs everything, runs migrations, prompts you to create an organization + admin
login, then starts the server and opens your browser to it. Every re-run after that just
starts the server — safe to run any number of times. On Linux/Windows (no `.command`
double-click support yet), run the same script directly:

```bash
python3 scripts/launcher.py
```

Everything this creates — the virtual environment, the SQLite database, uploaded check
images, and trained ML models — lives under `.pospay-run/` next to the project, never in
the source tree itself. **To fully reset and leave the checkout exactly as cloned, just
delete that one folder:**

```bash
rm -rf .pospay-run
```

**Manual setup**, if you'd rather control each step yourself (and are fine with `.venv`,
`pospay.db`, `data/`, and `ml_artifacts/` living directly in the project root as
persistent local dev state, rather than one disposable folder):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

alembic upgrade head
uvicorn pospay.main:app --reload
```

Web UI at `http://localhost:8000/ui/login`. JSON API docs at `http://localhost:8000/docs`.
Tesseract (`brew install tesseract` / `apt install tesseract-ocr`) must be on `PATH` for
check-image OCR to work — it's a system binary, not pip-installable; the launcher warns
if it's missing but still runs.

## Running tests

```bash
pytest
```

## Bulk file uploads

Both issued items (`/ui/issued-items/bulk`) and ACH transactions
(`/ui/ach/transactions/bulk`) accept bulk uploads, in addition to the JSON API's
`/bulk` endpoints (which take a pre-built JSON array, not a file):

- **Delimited or Excel** (`bulk_import/tabular.py`): any comma/tab/semicolon/pipe file
  or `.xlsx`/`.xls`, header row required, column names case/spacing-insensitive, any
  order. Delimiter is detected by counting candidates in the header line — deliberately
  not `csv.Sniffer`/pandas' generic auto-detection, which on a short sample can pick the
  most-frequent character in the text itself rather than an actual delimiter.
- **NACHA** (`bulk_import/nacha.py`, ACH only): a standard 94-character fixed-width ACH
  file. **Lenient by design**: extracts batch header fields (company id/name, SEC code,
  effective date) and entry detail fields (DFI account number, amount, individual id,
  transaction code, trace number) needed to create transactions, but does not validate
  file/batch control totals, entry hash, or checksums (record types 1, 7, 8, 9 are
  otherwise ignored) — a malformed file can partially import rather than being rejected
  outright.

Every row/entry carries its own account number (not a single account picked once for the
whole file) — resolved against your existing accounts, so one file can span multiple
accounts. Unmatched account numbers, and any other bad row, are reported individually in
the results page without failing the rest of the file (one DB transaction per row).

Both upload forms have a **"create missing accounts"** checkbox: when checked, any
account number in the file that doesn't already exist is created automatically instead of
failing that row. Delimited/Excel files may include an optional `account_name` column,
used as the new account's name; NACHA files carry no such field, so accounts it creates
are named `Account <number>`. The same new account number appearing in multiple rows of
one file is only created once.

**Every submitted file is saved and signed** (`bulk_import/file_storage.py`,
`bulk_import/signing.py`, `services/bulk_upload_file_service.py`) — issued items, ACH
(tabular and NACHA), and the user bulk upload (see below) all keep the original bytes on
local disk (`POSPAY_BULK_UPLOAD_STORAGE_DIR`, default
`./data/bulk_uploads`, consolidated under `.pospay-run/` by the quickstart launcher) plus
a SHA-256 fingerprint and an HMAC-SHA256 signature computed with a server-held secret
(`POSPAY_FILE_SIGNING_SECRET` — same HS256 pattern already used for JWTs). This is saved
**even when the file is rejected outright** (bad format, no data rows) — a malformed
submission is still evidence of what was actually sent, so it's recorded before parsing
ever runs, with a link to it shown right on the error page. Every results/error page links
to a detail view (`/ui/bulk-uploads/<id>`) that re-verifies the signature against a fresh
read of the file **on every visit** — not a cached flag — so tampering after upload (even
a direct edit of the file on disk) shows up as a mismatch, and the original file can be
downloaded byte-for-byte from there. Gated by the same permission that gated the original
upload (`issued_item:write` / `ach_transaction:write` / `user:manage`).

## Bulk-loading check images

`/ui/check-images/bulk` (gated by **both** `paid_item:write` and `check_image:write` —
stricter than every other bulk import in this app, since this one creates two different
resource types in a single step, unlike the single-image upload above, which only ever
links to a paid item that already exists) accepts two formats. **Both create a new
`paid_item` per check** — running it through the same matching engine as any other
presented item — **and** attach its image in the same step, rather than requiring the
paid item to already exist: a real image cash letter *is* the presentment, not a
follow-up step.

- **ZIP file** (`bulk_import/zip_import.py`): a zip containing exactly one manifest file
  (CSV/TSV/Excel — columns `account_number`, `check_number`, `amount`, `presented_date`,
  `front_image_filename`, optional `back_image_filename`) plus the image files it
  references by filename (matched by basename, case-insensitively, anywhere in the
  archive). Supported image formats: single- or 2-page TIFF, JPG, PNG
  (`bulk_import/images.py`) — a 2-page TIFF is split automatically (page 1 = front, page
  2 = back) unless `back_image_filename` is given explicitly, which always wins.
- **X9.37 image cash letter** (`bulk_import/x937.py`): a real Check 21 cash letter file.
  **Lenient by design**, matching this app's existing NACHA parser's philosophy: supports
  the common ASCII, line-delimited "variable format" variant with embedded TIFF/JPEG
  images in Image View Data (Type 52) records; does not support the alternate
  fixed-length undelimited binary variant, EBCDIC encoding, return/adjustment cash
  letters, credit reconcilement records, or file/cash-letter/bundle control-total
  validation. Account number and check number come from each check detail record's On-Us
  and Auxiliary On-Us MICR fields respectively — a common real-world convention (the
  check's own serial number in Auxiliary On-Us, the payor's account number in On-Us), not
  a standard-mandated split, so a bank whose files use a different layout won't resolve
  correctly here; the ZIP+CSV format above is the explicit-column fallback for that case.

Every incoming image, regardless of source format, is decoded and re-encoded to PNG
before storage (`bulk_import/images.py`) — this is what makes the front/back download
links on a check image's detail page (`/ui/check-images/<id>/front` and `/back`) and
downstream OCR work identically no matter what format the original file arrived in.
Same per-row/per-item transaction isolation as every other bulk importer (one bad check
doesn't roll back the batch), and the same signed-original-file audit trail
(`BulkUploadKind.CHECK_IMAGES`) described above.

## Backing out a bulk upload

Every bulk upload (issued items, ACH transactions, users, accounts, check images) can be
undone from its detail page (`/ui/bulk-uploads/<id>`, "Back out this upload"), reusing
the same signed-file/audit infrastructure described above. This is only possible for
uploads processed **after** this feature shipped — `bulk_upload_created_record` (new)
durably links a `BulkUploadFile` to every row it successfully created, something no
earlier version of this app tracked; an older upload's detail page shows "nothing can be
automatically backed out" instead of the button.

Backing out is **one-way** (matching every other void/cancel/revoke action's own
one-way design — nothing here supports "undo the undo") and, per resource type, either
really reverses what was created or is a record-only annotation, depending on whether
this app has any reversible concept for that resource at all:

- **Issued items**: voided (the same `void_issued_item` a manual void uses) — skipped,
  not an error, if already voided or already paid (voiding a paid item would leave its
  matching paid item in an inconsistent state).
- **Users**: the membership created deactivates (the same `deactivate_membership` the
  manual button uses) — skipped if already inactive. Only memberships created directly
  by the bulk file are tracked; one confirmed later via the separate cross-tenant
  confirmation step is a deliberate, independent admin action and isn't automatically
  backed out (it can still be deactivated individually, same as any other membership).
- **Accounts / ACH transactions**: **record-only.** Neither has any deactivation or
  reversal concept in this app at all (no `Account.is_active`, no `AchTransaction`
  status field) — backing these out marks the tracking record and logs an audit entry,
  without inventing new account-lifecycle or ACH-reversal behavior that wasn't asked
  for.
- **Check images**: the hardest case, since a bulk check-image row's real object is the
  `paid_item` it created (see above), which can have already changed *other* rows.
  Reversing it flips a matched `PaidItem.settlement_status` to a new `REVERSED` value
  (excluded from duplicate-payment detection, same as `RETURNED`); if it had flipped a
  linked issued item to `PAID`, that reverts to `OUTSTANDING` — but only if nothing else
  changed that issued item's status since (left alone and noted otherwise). If it had
  spawned an exception in the review queue that's still `OPEN`/`PENDING_APPROVAL`, that
  exception is auto-withdrawn (new `ExceptionStatus.WITHDRAWN` — shown in the exceptions
  queue, and rejected by the recommend/decide routes with a clear message rather than
  the generic "already decided" one); one that's already been paid/returned/escalated by
  a human is left untouched and noted, never silently overridden.

Requires the same permission that gated the original upload
(`issued_item:write`/`ach_transaction:write`/`user:manage`/`account:write`), plus, for
check images specifically, **both** `paid_item:write` and `check_image:write` — matching
that upload route's own stricter dual-permission gate, since backing one out can touch
both resource types.

## Users, security groups, and cross-tenant access

Access control is a set of per-tenant **security groups** (`auth/permissions.py`,
`services/security_group_service.py`), not a fixed role enum — each group is a named,
editable set of permission keys drawn from a single catalog covering every action in the
app (read/write per resource, plus `exception:recommend`/`exception:decide`,
`admin:manage`, `user:manage`, `security_group:manage`). Every new tenant is seeded with 4
default groups reproducing the old fixed roles — **Admin** (everything), **Preparer**
(read/write except deciding exceptions or managing users/groups/admin), **Approver**
(read-only plus `exception:decide`), **Viewer** (read-only) — fully editable from there
via `/ui/security-groups`. Permissions are resolved from the database on **every
request** (`auth/deps.py::decode_and_build_context`), not baked into the JWT, so editing a
group's permissions — or deactivating a user — takes effect on the very next request, not
after the token expires.

**Users** (`/ui/users`) can be added one at a time or via CSV bulk upload
(`/ui/users/bulk`, columns: `email`, `security_group`, `password`), reusing the same
`bulk_import/` infrastructure as issued items/ACH. A `User` is a **global login identity**
(email is unique platform-wide, not per-tenant) with zero or more `TenantMembership` rows,
each pointing at one tenant and one security group there — this is what makes **cross-tenant
access** possible: the same person, same password, can hold membership (with a different
security group) in more than one tenant. Login still takes an organization slug + email +
password exactly as before; once logged in, **"Switch organization"** in the nav
re-mints tokens for any other tenant you're an active member of, with no re-entry of
password or WebAuthn (see below).

Adding a user by an email that already belongs to an identity in a *different* tenant
never attaches it silently — both the single-add form and the bulk CSV surface an explicit
confirmation step ("grant this existing user access to this organization?") before a
membership is created, and that confirmation re-resolves the identity by email
server-side rather than trusting anything the client posted.

WebAuthn credentials are still registered **per tenant-membership**, not once for the
whole identity — a user with memberships in two tenants currently registers a security key
separately in each. Unifying that to one identity-wide credential set is a reasonable
fast-follow, deliberately out of scope for the cross-tenant-membership work.

## Querying and exporting users (access recertification)

`GET /api/v1/users` (gated by `user:manage`) returns the same data `/ui/users` shows —
one row per `TenantMembership` (email, security group, customer scope or "bank-wide",
active/deactivated status, when the membership was created, and `last_login_at`) — built
by reusing `user_service.list_tenant_users` directly, so the API and the web page can
never drift apart. A user with several memberships in one tenant (bank-wide plus
per-customer scopes) correctly appears once per membership, matching how access is
actually granted; this is meant for an access-review/recertification process that needs
to answer "who has access to what, and have they actually used it."

`User.last_login_at` is now actually populated — it existed as a column before this but
nothing ever set it. It's stamped at the moment a login *completes* (password-only, or
after WebAuthn MFA finishes), on both the web and API channels; token refresh and
"switch organization" don't count as a fresh login and don't touch it.

The same list can be exported straight from `/ui/users` as **CSV** or **JSON**
(`/ui/users/export.csv` / `.json`, same permission, same underlying data — no separate
filtering, it exports exactly what the page shows).

## Customers: segregating a tenant's own business clients

A `Tenant` is the bank; a `Customer` (`/ui/customers`, gated by a dedicated
`customer:manage` permission) is one of the bank's own business clients within that
tenant — e.g. "Acme Corp," a company whose accounts and check/ACH activity the bank
processes. Customers are optional: accounts created without one are "house" accounts,
visible only to tenant-wide staff exactly as before this feature existed, so an existing
installation with no customers behaves identically to today.

**One mechanism serves two use cases.** `TenantMembership` gains an optional
`customer_id`: `NULL` is today's exact behavior (tenant-wide staff, sees everything in the
tenant), and a real value scopes that membership's security group to just that one
customer's data. The same field expresses both "a bank employee restricted to servicing
specific customers" and "a customer's own employee logging in to see only their own
company's data" — there's no separate portal or permission catalog, just a narrower scope
on an ordinary membership. A person can hold several memberships in the same tenant (one
tenant-wide, plus overrides per customer, or several customer-scoped ones with no
tenant-wide membership at all) —**"Switch organization"** (`/ui/switch-tenant`) doubles as
"switch customer scope," listing every membership and which customer (or "bank-wide") each
is scoped to. Logging in still takes just a slug + email + password; if more than one
membership exists for that tenant, login defaults to the tenant-wide one if present, else
the earliest-created customer membership, and the switcher reaches any other one — a
login-time picker for the (rare) multi-membership case is a reasonable fast-follow,
deliberately out of scope here.

**Segregation is denormalized, not just joined.** `customer_id` is stamped onto `account`
and onto every table that hangs off an account — `issued_item`, `stop_payment`,
`paid_item`, `ach_authorization_rule`, `ach_transaction` — the same way `tenant_id`
already is, always derived server-side from the referenced account at creation time, never
trusted from a request. `repositories/base.py::CustomerScopedRepository` is the
enforcement point: when a session's `customer_id` is set, every read on those six tables
is additionally filtered to it; when it's `None` (tenant-wide), it behaves exactly like
plain tenant scoping. A customer-scoped caller referencing another customer's `account_id`
directly — not just through a filtered dropdown — gets a clean 404, the same
anti-enumeration posture as cross-tenant isolation, because every service that creates a
child record resolves the parent account through this same repository rather than a raw
lookup.

**No new "what" permissions — only "whose."** A security group's permissions
(`Preparer`, `Approver`, etc.) mean the same thing whether a membership is tenant-wide or
customer-scoped; scoping only narrows *whose* data they apply to. One hard-coded exception:
`user:manage`, `security_group:manage`, `tenant:manage`, `customer:manage`,
`admin:manage`, and `audit_log:read` are unconditionally stripped from the resolved
permission set whenever a membership is customer-scoped
(`auth/permissions.py::CUSTOMER_SCOPE_MASKED_PERMISSIONS`, enforced in
`auth/deps.py::decode_and_build_context`) — regardless of what the underlying security
group nominally contains, so even a customer-scoped membership using the full "Admin"
group can never reach tenant-admin surfaces like `/ui/users` or `/ui/audit-log`.

**Bulk loading** extends the existing CSV infrastructure rather than adding a new one:
accounts (`/ui/accounts/bulk`, columns `account_number`, `name`, optional
`customer_number`, optional `ach_debit_block_mode`) and users
(`/ui/users/bulk`, existing columns plus an optional `customer_number`) both resolve a
human-readable customer number to the tenant's internal customer record the same way
issued-item/ACH bulk uploads already resolve account numbers. A customer-scoped uploader
can only ever create rows in their own scope — a `customer_number` column that names a
different customer is rejected, not silently reassigned.

Not yet done, documented as an accepted v1 limitation: Postgres RLS policies on the six
customer-scoped tables enforce `tenant_id` only, not `customer_id` — the repository layer
above is the primary, tested enforcement point, same posture as tenant isolation's own RLS
today.

## Per-tenant branding

Each tenant can customize a logo, favicon, accent color, and display name from
`/ui/settings` (gated by a dedicated `tenant:manage` permission, not folded into
`admin:manage`, so a security group can be scoped to branding alone). Uploaded images are
stored on local disk under `POSPAY_TENANT_ASSET_STORAGE_DIR` (default
`./data/tenant_assets`, consolidated under `.pospay-run/` by the quickstart launcher, same
as check-image storage) — the DB only ever stores the path and content-type, never the
blob. The accent color reuses the single `--accent` CSS custom property `app.css` already
threads through every button/link/nav highlight, applied via a small inline `<style>`
override, so no CSS rewrite was needed.

Branding shows throughout the logged-in app shell (nav logo/name, page titles, browser-tab
favicon, accent color) **and** on the login page itself — via a tenant slug in the URL
(`/ui/login/<slug>`), not Host-header/subdomain routing. A slug-based login link needs no
DNS or reverse-proxy infrastructure and works identically locally and in production,
unlike a subdomain-per-tenant approach, which this project deliberately doesn't build
toward given its local-first, one-click-launcher design. An unknown or inactive slug falls
back to the plain generic login form rather than an error. Logo/favicon bytes are served
by two public (unauthenticated) routes keyed by slug, `/ui/branding/<slug>/logo` and
`/ui/branding/<slug>/favicon` — a company logo isn't sensitive, and the login page needs to
show it before any session exists, so both the pre-auth login page and the authenticated
app shell hit the exact same serving routes.

## Immutable action log

Every state-changing action — through **either** the web UI or the JSON API — is recorded
to a per-tenant, tamper-evident action log (`/ui/audit-log`, gated by a dedicated
`audit_log:read` permission that's Admin-only by default, unlike every other `*:read`
permission, since "who did what" is more sensitive than any single resource's own data).
Covers create/void/cancel/revoke/upload/recommend/decide across issued items, stop
payments, paid items, check images, ACH authorizations/transactions, exceptions/decisions,
accounts, users, security groups, and tenant settings — one entry per successfully-created
row for bulk uploads too, not one entry for the file as a whole (the file itself already
has its own signed audit record — see "Bulk file uploads" above).

Entries form a **hash chain**, not independent per-row signatures: each entry's
`entry_hash` is an HMAC-SHA256 (`POSPAY_AUDIT_LOG_SIGNING_SECRET`, a dedicated secret,
distinct from every other signing secret in this app) over its own fields plus the
*previous* entry's hash. A chain — not independent signatures — is what's needed here,
because the real threat to an action log is deletion or reordering, not just editing one
row: an independent per-row signature can't detect a row being deleted outright, but a
broken chain link can. `services/audit_log_service.py::verify_chain` (surfaced as "Verify
chain" on the audit log page) walks every entry for a tenant and recomputes each hash from
scratch — proof nothing has been edited, deleted, or reordered since it was written, not a
cached flag. This is tamper-**evidence**, not OS-level tamper-*prevention* (no DB
triggers/grants are revoked) — the same posture as bulk-upload file signing.

Logging calls live in the route handlers (both `web/routers/*.py` and `api/v1/*.py`),
right after the mutating service call succeeds and before that request's `db.commit()` —
so the audit entry and the business change commit together atomically, and every route
already has the actor/tenant/channel it needs without any shared service function having
to take on a new required parameter.

## Authentication

Username + password (bcrypt-hashed) issuing JWTs (`api/v1/auth.py`), with an optional
FIDO2/WebAuthn second factor (`api/v1/webauthn.py`, `auth/webauthn_service.py`):

- `POST /auth/webauthn/register/options` + `/register/verify` — register a security key
  (authenticated with a normal access token)
- `GET /auth/webauthn/credentials`, `DELETE /auth/webauthn/credentials/{id}` — manage
  registered keys
- Once a user has at least one registered key, `POST /auth/login` no longer returns real
  tokens after the password check — it returns `mfa_required: true` and a short-lived
  `mfa_token` (5 min, carries no permissions) instead. That token authenticates
  `POST /auth/webauthn/login/options` + `/login/verify`, which — once the assertion
  verifies — issue the real access/refresh token pair.
- Users with no registered key log in exactly as before (`mfa_required: false`); this is
  additive, not a breaking change for existing accounts.

WebAuthn requires a real browser to drive `navigator.credentials.create()/get()` — there's
no backend-only way to test the full ceremony against an actual authenticator. The test
suite (`tests/test_auth/webauthn_helpers.py`) instead hand-constructs cryptographically
valid registration/authentication responses (COSE-encoded EC key, CBOR attestation/
authenticator data, DER ECDSA signature) to exercise the real server-side verification
path without a browser. `webauthn_rp_id`/`webauthn_origin` default to `localhost` /
`http://localhost:8000` — set both to your real domain before deploying, or every
registered credential will fail verification against the wrong origin.

For the full set of `/api/v1/*` endpoints (issued items, stop payments, paid items,
check images, ACH, exceptions/decisions, admin, users), the permission each one requires,
and request/response schemas, see [API.md](API.md).

## Postgres

```bash
pip install -e ".[dev,postgres]"
docker compose up -d postgres
POSPAY_DATABASE_URL=postgresql+psycopg://pospay:pospay@localhost:5432/pospay alembic upgrade head
```

Or bring up the whole stack (app + Postgres) with `docker compose up --build`.

**Row-Level Security**: on Postgres, migrations enable RLS (`FORCE ROW LEVEL SECURITY`)
on the single-tenant operational tables (`account`, `issued_item`, `stop_payment`,
`check_image`, `paid_item`, `ach_authorization_rule`, `ach_transaction`,
`security_group`, `tenant_membership`, `bulk_upload_file`, `audit_log_entry`) as
defense-in-depth alongside the primary
tenant-isolation mechanism (the repository-layer filter in `repositories/base.py`, which
is what's actually under test in `tests/test_api/test_cross_tenant_isolation.py`).
`exception_item`/`decision` (the ML pipeline reads across all tenants by design, see
`ml/train.py`) and `user` (a global login identity with no single-tenant row-ownership
story — see "Users, security groups, and cross-tenant access" above) are deliberately
excluded. This RLS migration has been schema-compile-verified against the Postgres
dialect but **not yet exercised against a live Postgres instance** in development (no
Docker/Postgres available in the environment this was built in) — test it thoroughly,
including the cross-tenant suite against a real Postgres backend, before relying on it in
production.

## MSSQL

Requires the Microsoft ODBC Driver (17 or 18) installed at the OS level — not available
via pip alone (see Microsoft's docs for your platform). Also requires a running SQL
Server instance; a Linux container (`mcr.microsoft.com/mssql/server`) is the easiest way
to get one for local dev.

```bash
pip install -e ".[dev,mssql]"
POSPAY_DATABASE_URL="mssql+pyodbc://pospay:<password>@localhost:1433/pospay?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes" alembic upgrade head
```

Known friction points, not yet exercised against a live instance in this build:
- `UNIQUEIDENTIFIER` type mapping for UUID primary/foreign keys — SQLAlchemy's generic
  `Uuid` type should handle this, but hasn't been verified against real MSSQL here.
- The Postgres RLS migration is a no-op on MSSQL (dialect-gated) — MSSQL deployments rely
  solely on the repository-layer filter for tenant isolation, same as SQLite.
- Alembic's autogenerate has known rough edges on MSSQL around identity columns and
  server-side defaults; review generated migrations before applying against MSSQL.

## Web UI

Server-rendered (FastAPI + Jinja2, no Node/build step) under `/ui/*`, covering every
resource: accounts, issued items, stop payments, paid items, check images (upload +
OCR status), ACH authorizations/transactions, the exceptions review queue
(recommend/decide), admin ML screens, users/security groups, per-tenant branding
settings, the immutable action log, and WebAuthn security-key management.

It's a second presentation layer over the same `services/`/`auth/` code the JSON API
uses (`web/routers/*.py` call service functions directly — never the JSON API over
HTTP), authenticated via cookies instead of a bearer token: `web/deps.py::get_web_context`
reads an `access_token` cookie, `auth/deps.py::get_current_context` reads the
`Authorization` header — the two channels never read each other's credential. Moving to
cookies reintroduces CSRF risk the header-based API doesn't have, so every `/ui/*` POST
is guarded by a double-submit cookie token (`web/security.py`); UI gating checks the same
`ctx.permissions` set (resolved from the caller's security group) the API enforces,
exposed to templates as a `can(ctx, permission)` Jinja global — hiding a button is
cosmetic, the POST route's own permission check is what actually enforces it.

## Architecture at a glance

- `db/` — engine/session factory (one code path for all three backends), tenant context
- `domain/` — SQLAlchemy models (import `pospay.domain` to register every mapper — see
  its `__init__.py` docstring for why this matters)
- `networks/` — the pluggable per-payment-network layer (`check/`, `ach/`); each
  implements `networks.base.NetworkAdapter` and self-registers via
  `networks.registry.register_adapter()`. Adding a new network (e.g. RTP) means adding a
  new `networks/<code>/` package plus one import in `main.py` — no changes to
  `exception_item`, `decision`, `ml/`, or the `/exceptions` API.
- `ocr/` — pluggable OCR (`OCRProvider` protocol; Tesseract is the default, cloud
  providers are stubbed behind optional extras)
- `ml/` — model training/scoring, one model per network, fed by human pay/return
  decisions (`decision.features_json`)
- `api/v1/` — FastAPI routers; `exceptions.py`/`decisions.py` are network-agnostic
- `workers/` — the ML retrain job, runnable via an opt-in in-process APScheduler
  (`POSPAY_ENABLE_ML_SCHEDULER=true`) or an external cron/k8s CronJob calling
  `workers.tasks.retrain_job()`
- `web/` — the server-rendered UI (see "Web UI" above); `templates/` and `static/` live
  inside the package so they ship with it wherever it's installed
- `scripts/launcher.py` — the one-click local setup/run script (stdlib-only until it
  re-execs itself under a freshly-created venv's own interpreter); `run_pospay.command`
  is the macOS double-click wrapper around it

## License

Copyright (C) 2026 Chaffed

PosPay is free software: you can redistribute it and/or modify it under the terms of the
GNU Affero General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version.

This means that if you run a modified version of PosPay as a network service, you must
make the modified source available to that service's users — see [LICENSE](LICENSE) for
the full text.
