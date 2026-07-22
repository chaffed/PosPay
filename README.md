# PosPay

Multi-tenant positive pay platform (checks + ACH today, extensible to other payment
networks — see `networks/`) with pluggable OCR and an ML-assisted exception review
feedback loop.

This README covers local setup and deployment only. For architecture (data model, the
network-adapter pattern, matching engine rules, ML pipeline design), see the project's
architecture plan.

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

**Manual setup**, if you'd rather control each step yourself:

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

## Postgres

```bash
pip install -e ".[dev,postgres]"
docker compose up -d postgres
POSPAY_DATABASE_URL=postgresql+psycopg://pospay:pospay@localhost:5432/pospay alembic upgrade head
```

Or bring up the whole stack (app + Postgres) with `docker compose up --build`.

**Row-Level Security**: on Postgres, migrations enable RLS (`FORCE ROW LEVEL SECURITY`)
on the single-tenant operational tables (`account`, `user`, `issued_item`,
`stop_payment`, `check_image`, `paid_item`, `ach_authorization_rule`,
`ach_transaction`) as defense-in-depth alongside the primary tenant-isolation mechanism
(the repository-layer filter in `repositories/base.py`, which is what's actually under
test in `tests/test_api/test_cross_tenant_isolation.py`). `exception_item` and `decision`
are deliberately excluded — the ML retraining pipeline reads across all tenants by design
(see `ml/train.py`) and a blanket RLS policy there would silently break it. This RLS
migration has been schema-compile-verified against the Postgres dialect but **not yet
exercised against a live Postgres instance** in development (no Docker/Postgres available
in the environment this was built in) — test it thoroughly, including the cross-tenant
suite against a real Postgres backend, before relying on it in production.

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
(recommend/decide), admin ML screens, and WebAuthn security-key management.

It's a second presentation layer over the same `services/`/`auth/` code the JSON API
uses (`web/routers/*.py` call service functions directly — never the JSON API over
HTTP), authenticated via cookies instead of a bearer token: `web/deps.py::get_web_context`
reads an `access_token` cookie, `auth/deps.py::get_current_context` reads the
`Authorization` header — the two channels never read each other's credential. Moving to
cookies reintroduces CSRF risk the header-based API doesn't have, so every `/ui/*` POST
is guarded by a double-submit cookie token (`web/security.py`); role-based UI gating
reuses the exact same permission matrix (`auth/rbac.py`) the API enforces, exposed to
templates as a `can(role, permission)` Jinja global — hiding a button is cosmetic, the
POST route's own permission check is what actually enforces it.

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
