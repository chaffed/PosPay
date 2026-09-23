# PosPay Fix Plan

Source: [EVALUATION.md](EVALUATION.md) (2026-09-22). Finding IDs (S0, F1, U2, …) refer to
that file. Each phase is one PR (or a small set of PRs) that ships and is tested on its
own. Work top to bottom. Tick boxes as you go so a lost session can resume here.

**Ground rules for every PR**
- Start by writing a failing regression test that reproduces the finding, then fix it.
- Run the full suite (`python -m pytest -q`, about 14 minutes) before merging.
- Schema changes go through an Alembic migration with a working `downgrade()`
  (`tests/test_migrations/` enforces this).
- Every security-relevant action gets an `audit_log_service.record_action` call, the
  same as existing routes.
- Update `SECURITY_REVIEW.md` / docs templates when behavior changes.

---

## Phase 0 — Land the in-flight work (about ½ hour)

- [x] Fix the failing `test_web_approvals.py::test_detail_page_shows_notice_instead_of_decide_form_for_own_recommendation`:
      put "a different approver must finalize it" on one line in
      `templates/exceptions/detail.html` (L84–85).
- [x] Full suite green (957 passed, 1 skipped) → commit the approvals queue work (`exceptions.py`,
      `approvals.html`, `detail.html`, `base.html`, `.gitignore`, test file).
      Done 2026-09-22 on branch `approvals-queue` (commits `9bb0adb`, `ae7868e`); not pushed.

## Phase 1 — Critical and high security fixes, small blast radius (1 PR, about 1 day)

Done 2026-09-22 on branch `phase-1-security-fixes`: `898451f` (S0), `a67d085` (S1),
`eee370a` (F2/U9/S7), plus error-page wording. Full suite: 969 passed, 1 skipped. Not pushed. Notes: forms other than accounts (customers, security
groups, issued items, ACH transactions) now get the app-wide 409 page on duplicates rather
than inline form errors. Inline errors for those are a nice-to-have for Phase 7.

### 1a. S0 — Customer-scoped data export
Files: `web/routers/data_export.py`, `tests/test_web/test_web_data_export.py`
- [x] Bank-wide routes (`/ui/settings/data-export*`): raise `WebForbidden` when
      `ctx.customer_id is not None`.
- [x] Per-customer routes (`/ui/customers/{customer_id}/data-export*`): when
      `ctx.customer_id is not None` and differs from the path `customer_id`, raise
      `WebNotFound` (don't reveal that the other customer exists).
- [x] Decision (2026-09-22): **customer users may export their own customer's data**, through
      the per-customer route only, as above. `data_export:run` stays unmasked.
- [x] Tests: customer-scoped user → 403 on bank-wide list/start/download; 404 on other
      customer's list/start/download; 200 on own customer's export (if allowed).
- [x] Same audit for the API: confirm no `/api/v1` export route exists (none found).

### 1b. S1 — Group reassignment takes effect immediately
Files: `auth/deps.py::decode_and_build_context`, `tests/test_auth/`, `tests/test_web/test_web_users.py`
- [x] After loading `membership`, resolve the group from `membership.security_group_id`
      (not the token claim) and put *that* id into `TenantContext.security_group_id`.
      This also fixes the WebAuthn verify/setup routes, which mint tokens from
      `ctx.security_group_id`.
- [x] Also verify `group.tenant_id == tenant_id` as a defensive check.
- [x] Tests: log in as Admin → `update_membership` to Viewer → next request to
      `/ui/users` is 403. Same over the API with a bearer token.

### 1c. F2 / U9 — No more bare 500s
Files: `main.py`, `web/routers/accounts.py`, `services/account_service.py`, `templates/error.html`
- [x] Add a catch-all `@app.exception_handler(Exception)` for `/ui/*` paths that logs the
      traceback and renders `error.html` (500, generic message, no stack trace). Leave
      `/api/*` returning JSON.
- [x] Account create: catch `IntegrityError` → re-render the form with "An account with
      that number / external ID already exists." Do the same for any other create form with
      unique constraints. Grep `UniqueConstraint` in `domain/` and check each form
      (customers, security groups, ACH return reasons, SSO connections, users).
- [x] S7 (same file): validate `customer_id` from the form with
      `customer_service.get_customer(db, ctx.tenant_id, …)`, and show a form error on a bad
      or foreign id. Reject malformed UUIDs cleanly.
- [x] Tests: duplicate account → 400/200 with error text, not 500; bogus `customer_id` →
      form error.

## Phase 2 — Password lifecycle (1 PR, about 1–2 days) — F7

Done 2026-09-22 on branch `phase-2-password-lifecycle` (`bccdd9c`, `500194c`). Full suite: 986 passed, 1 skipped. Not pushed.
Decisions made along the way (per the standing "go with the recommendation" rule):
- The temporary password is **shown once to the admin** (not emailed), on a no-store page,
  with a Copy button. Emailing a working password is weaker, and SMTP is optional anyway.
- Self-service change and reset are **also blocked in the demo organization** now, not
  in Phase 4, because otherwise this phase would have given public demo visitors a new way
  to lock each other out.
- A wrong *current* password on the change form counts toward the login lockout.
- No JSON API endpoint for changing a password. The API refuses sessions that must change
  their password and points them to the web app.
- Admins can't reset their own password from Users; they use Security like everyone else.

Files: `services/user_service.py`, `web/routers/security_settings.py` (self-service),
`web/routers/users.py` (admin), `api/v1/users.py`, templates, `auth/password_policy.py`
- [x] `user_service.change_password(session, user_id, current, new, policy)`: verify the
      current password, enforce the tenant/customer password policy (the existing
      `auth/password_policy.py`), rehash, reset `failed_login_attempts`/`locked_until`.
- [x] Self-service page under `/ui/security` ("Change password") with CSRF and audit log
      `user.password_change`; send a notification email ("your password was changed").
- [x] Admin reset (`user:manage`): sets a temporary password shown once (or emailed if SMTP
      is configured) and sets a new `User.must_change_password` flag (migration). Login
      redirects flagged users to the change-password page before anything else.
- [x] Hide/disable for SSO-only scopes (password login disabled) — nothing to change.
- [x] Cross-tenant caution: `User` is global (one account can have memberships in several
      tenants). Only allow an admin reset when the user has no *active* memberships in other
      tenants, or restrict it to platform staff. Otherwise one bank's admin could take over
      a Bookkeeper's access at another bank. **Decided (2026-09-22): block it.** Show
      "This user belongs to other organizations; they must change their own password."
      Add a test for it.
- [x] Update `docs/admin/authentication.html`.
- [ ] Bumps `token_version` — **moved to Phase 3** (it's listed there). Meanwhile: after an admin
      reset, the user's existing sessions are already quarantined, because every request checks
      `must_change_password`. After a *self-service* change, the user's other open sessions stay
      valid until Phase 3 lands.

## Phase 3 — Sessions: refresh, revocation, expiry UX (1 PR, about 2–3 days) — F1, U1, S2, S4

Done 2026-09-22 on branch `phase-3-sessions` (`918bc0f`, `213f288`, docs commit). Not pushed.
Full suite on the Phase 3 code: 986 passed, 1 skipped, plus 26 new session tests passing
(1,012 total). Three deliberate-breakage checks confirmed the new tests catch regressions in
the idle timeout, revocation, and maximum-length rules. Checked live in a browser: the
idle dialog appears on schedule and "Stay signed in" renews the session.

Decisions made along the way:
- **Logout ends only that session** (a new `revoked_session` table keyed by a per-login
  `sid`), not every device. "Sign out everywhere" is the separate `token_version` bump.
- **The idle timeout is enforced by the server**: the web UI can only renew a session
  whose access token hasn't expired (2-minute grace). Otherwise a refresh token could revive
  a session idle for hours. The API keeps standard refresh-after-expiry behavior.
- **Renewal never extends the maximum session length.** Near it, the dialog says to save
  work instead of offering "Stay signed in".
- **Organization switch** ends the old session (only once the switch completes, so
  abandoning a WebAuthn step doesn't sign the user out).
- Added a self-service **"Sign out other devices"** on Security, alongside the admin
  "Sign out everywhere" on Users. The admin version works even for users in other
  organizations (it grants nothing, and they can sign straight back in).
- **Found and fixed:** the CSRF cookie expired with the access token, so any form left
  open past 30 minutes failed on submit. It's now a browser-session cookie.
- **Found and fixed:** the API WebAuthn sign-in dropped `customer_id`, so customer-scoped
  users got the wrong membership (or none).
- **Found and fixed (docs):** "Data export timeout" was described as a retention period;
  it's a run-time limit.

Files: `web/security.py`, `web/deps.py`, new `web/routers/session.py`, `auth/security.py`,
`auth/deps.py`, `domain/user.py` + migration, `static/js/app.js`, `main.py`
- [x] **S2 — revocation:** add `User.token_version` (int, default 0; migration). Put a `tv`
      claim in every token; `decode_and_build_context` and API refresh reject a mismatch.
      Bump it on logout, password change/reset, user deactivation, and admin "sign out
      everywhere" (new button on the Users page). Old tokens with no `tv` count as 0, so no
      forced logout on deploy.
- [x] **F1 — web refresh:** add `POST /ui/auth/refresh` (path matches the existing
      `REFRESH_COOKIE_PATH`, CSRF by header). It validates the refresh cookie, re-resolves
      the membership (the same logic as `api/v1/auth.py::refresh`; extract a shared
      helper), and issues new access and refresh cookies.
- [x] `app.js` keep-alive: while the user is active (input or clicks since the last
      refresh), refresh silently **5 minutes** before access expiry. Expose the expiry to JS
      through a `<meta>` tag in `base.html`.
- [x] **U1:** a warning dialog **5 minutes** (decided 2026-09-22) before an *idle* session
      expires: "You'll be signed out in 5:00 — Stay signed in / Sign out now", with a live
      countdown. "Stay signed in" calls refresh.
- [x] Fallback for GET requests: when `get_web_context` sees an expired (not invalid) access
      token on a GET, redirect to `GET /ui/auth/resume?next=<path>`. The refresh cookie is
      path-scoped to `/ui/auth`, so only that route can see it. It refreshes and redirects
      back, or sends the user to login if the refresh fails. This is safe as a GET because it
      only re-issues the caller's own session and changes no data. Validate `next` with
      `safe_next_path`.
- [x] Fallback for POST requests: `WebAuthRequired` on a POST should use the `Referer`
      path, never the POST URL, as `next`.
- [x] Cookie `max_age` should use the tenant's override
      (`ctx.access_token_expire_minutes`), not the global setting.
- [x] Rename the settings labels (U7): "Idle sign-out after (minutes)" / "Maximum
      session length (minutes)". Validate that the maximum is greater than or equal to the
      idle timeout.
- [x] **S4:** middleware adds `Cache-Control: no-store` to `/ui/*` (except `/static`,
      `/ui/branding/*`) and `/api/*` responses.
- [x] Tests: refresh rotates cookies; refresh with a bumped `token_version` → 401; logout
      invalidates the copied access token; POST after expiry redirects to the referring
      page; `Cache-Control` header present.

## Phase 4 — Outbound requests, uploads, public demo (1–2 PRs, about 2 days) — S9, S8, S10, S3, S11

**Status: DONE 2026-09-23 on branch `phase-4-hardening` (final full-suite result below).** Progress log. The
newest entry is last. Each entry is committed, so resume from the last one:
- 4d started first (smallest). Then 4a → 4b → 4c.
- 4d DONE: compose Postgres bound to loopback.
- 4a DONE: new `auth/outbound_http.py` (URL check + a connect-time public-IP-only httpx
  transport that pins the vetted address, so DNS rebinding doesn't work). Used for OIDC
  discovery, JWKS, and token exchange, plus every endpoint the discovery document names.
  Save-time check on SSO forms (create and edit; the edit routes used to turn any
  ValueError into a 404). `oidc_allow_private_hosts` setting for local test IdPs,
  refused in production. OAuth `state` is bound in the signed cookie and checked on
  callback (S3). Login page errors are generic, with details in the server log. SSO tests now
  echo the real state. 90 SSO/auth tests pass.
- 4b DONE: logo/favicon type detected from the bytes with Pillow (PNG/JPEG/ICO only, no SVG);
  the declared Content-Type is ignored. Branding responses get `CSP: default-src 'none';
  sandbox` + nosniff (the security-headers middleware now keeps a route's own CSP).
  Legacy SVG logos stop being served. Bulk-upload downloads are always
  application/octet-stream. Old tests used fake image bytes and now use real tiny images
  (`tests/image_helpers.py`). 76 related tests pass.
- 4c DONE: central lock list in `web/demo_guard.py`, checked in web and API auth (one
  place to audit; a test checks every pattern still matches a real route). Hourly
  `demo_reset_job` (`demo_tenant_reset_interval_minutes`, default 60; the scheduler now
  also starts for it). **Found and fixed:** the demo reset never restored organization-level
  settings (banner and login messages, colors, dual control, password rules…), so a visitor's
  changes survived every reset. It now restores every Tenant column to a new demo's values.
  Demo notices on the demo's pages and its sign-in page. 34 demo tests pass.
- Docs DONE: README (SSO issuer rules, the local-testing setting, demo locks, hourly reset),
  admin demo docs, .env.example.
- Live check DONE: demo sign-in notice, in-app notice, and locked actions confirmed in a
  browser. **Found and fixed:** the lock page said "You don't have access to this" (it
  now says "Turned off in the demo"), and flash messages, the demo notice, and the tenant
  banner at the top of every page ran under the theme/help controls.
- Full suite before the final tweaks: 1,063 passed, 1 failed. The failure was the Phase 2 demo
  password test, which expected the form's own error but now gets the demo lock (403, the intended
  behavior); the test was updated and a service-level test added.

### 4a. S9 — SSRF-safe OIDC
Files: `auth/oidc_service.py`, `services/sso_service.py`, `config.py`
- [x] On save: require `https://` issuers. Reject IP-literal/`localhost` hosts.
- [x] On every fetch (discovery, JWKS, token): resolve the host and reject private,
      loopback, link-local, and multicast addresses. Disable redirects or re-validate
      each hop. A small `safe_http_client()` helper covers all three calls.
- [x] `config.oidc_allow_private_hosts: bool = False` (allowed only when
      `environment=development`) so local test IdPs still work.
- [x] Callback error page: show a generic "Single sign-on failed" and log the detail
      server-side.
- [x] **S3:** put the `state` value into the signed `sso_state` cookie and compare it on
      callback.

### 4b. S8 — Uploaded content served safely
Files: `services/tenant_service.py`, `web/routers/branding.py`, `web/routers/bulk_uploads.py`
- [x] Remove `image/svg+xml` from allowed logo types (or sanitize the SVG server-side; removal
      is simpler). Sniff the real type with Pillow at upload time, the same approach as
      `check_images.py::_image_media_type`, and store the *sniffed* type.
- [x] Branding responses: add `X-Content-Type-Options: nosniff` (already global) and
      `Content-Security-Policy: default-src 'none'; sandbox`.
- [x] Bulk-upload download: always `application/octet-stream` plus attachment.
- [x] Existing SVG logos: handled at serve time, with no migration and nothing deleted. A stored logo whose
      type isn't PNG/JPEG/ICO is treated as "no logo" (404, not shown) until re-uploaded.

### 4c. S10 — Demo guardrails
Files: new `web/demo_guard.py` dependency, routers listed below
- [x] `forbid_on_demo` dependency: raises `WebForbidden` with the message "Disabled in the public
      demo" when `ctx.tenant_id` is the demo tenant. Apply it to: SSO connection
      create/edit (bank and customer), password change/reset, user
      deactivate/membership edits for the seeded demo users, `require_webauthn` toggles,
      logo/favicon upload, session-timeout settings, data export, ML
      retrain/activate.
- [x] Banner/login messages: allow edits, but add an **hourly** scheduled demo reset
      (decided 2026-09-22) via the existing APScheduler, in addition to the idle reset.
      Show "This demo resets every hour" on the demo login page.
- [x] Show a "Demo mode — some settings are locked" notice in the base template for the
      demo tenant.

### 4d. S11
- [x] `docker-compose.yml`: `"127.0.0.1:5432:5432"`.

## Phase 5 — ML model choice per bank (2 PRs, about 4–5 days) — S6

**Decided (2026-09-22): support both, and let each bank choose.** A bank either joins the
**shared network model** (pools its decision data with other participating banks) or keeps
a **bank-only model** trained only on its own data. The shared model is run by the platform
operator, and a bank-only model is run by that bank's own admins.

### How scoring picks a model
The per-customer layer already exists (`MlScoringMode` AUTO/GLOBAL/CUSTOMER in
`domain/customer_ml_setting.py`, used by `ml/predict.py`). This adds a **bank layer**
between the customer model and the shared model:

```
customer model (per the customer's mode, as today)
  └─ else the bank's model source:
       SHARED  → shared network model
       PRIVATE → bank-only model (always exists: seeded from a copy of the shared model at switch time)
```
The customer mode `GLOBAL` keeps its DB value but its label changes to "Bank's model"
(meaning "ignore the customer-specific model and use whatever the bank uses"), so no
data migration is needed.

### PR 5a — Data model and scoring
- [ ] Migration: `Tenant.ml_model_source` enum `shared|private`, plus
      `ml_source_changed_at`, `ml_source_changed_by_user_id` (consent record), and
      `ml_private_switch_allowed_at` (see the 90-day lock below).
- [ ] Migration: `MlModel.tenant_id` nullable FK. `NULL` = shared network model; set =
      bank-only model; customer models also get their tenant_id filled in (backfill from
      `customer.tenant_id`). Unique "one active model" logic in `ml/registry.py` becomes
      per `(network_code, tenant_id, customer_id)`.
- [ ] Defaults (decided 2026-09-22): **every bank starts on `shared`**. Existing banks keep
      what they have (today that's shared for all of them), and new banks get the shared
      model until they choose to switch.
- [ ] **90-day lock for new banks** (decided): at tenant creation, set
      `ml_private_switch_allowed_at = created_at + 90 days`. Existing banks get `NULL` (no
      lock) in the migration. A bank can't switch to bank-only before that date; the
      Settings card shows "Available on <date>". A platform-operator override (audited) is
      recommended for exceptional cases. Switching back to shared is never locked.
- [ ] **Consent at onboarding:** since new banks now join the pool by default, show and
      record the data-pooling disclosure during bank setup (tenant creation /
      `/ui/wizard/bank` step), not only on the Settings card.
- [ ] **Seed-on-switch** (decided): switching to bank-only copies the currently active
      shared model (artifact file + metrics) into a new `MlModel` row owned by the bank
      (`tenant_id` set, `version` like `seed-from-shared-v7`, `metrics_json.seeded_from`
      = shared model id) and activates it immediately, so scoring never has a gap. The copy
      is a frozen snapshot: it doesn't receive later shared-model updates. Each later switch
      to bank-only seeds a fresh copy, and older bank models stay in history for rollback.
- [ ] **Champion/challenger** ("continue from there"): logistic regression can't keep
      learning from a copied model without the original (other banks') data, so bank
      retrains train on the bank's own decisions only, and a new model is promoted only
      if (a) it has at least `ml_bank_model_min_decisions` (new config, default 200) and
      (b) it beats the active model on the bank's most recent held-out decisions (AUC,
      recall on returns). Otherwise the model is recorded as `trained, not promoted` with the
      comparison shown on the admin page, and bank admins can still promote manually.
      A later option is blending the seed and bank models, weighted by the bank's data volume.
- [ ] `ml/registry.py::get_active_model_row(session, network, *, tenant_id=None, customer_id=None)`
      and `activate_model(..., expected_tenant_id=, expected_customer_id=)` — the ownership
      check is extended to the tenant.
- [ ] `ml/train.py::_load_labeled_decisions`:
      - shared model → only decisions from tenants where `ml_model_source == shared`
        (joined through `ExceptionItem.tenant_id` → `Tenant`);
      - bank model → only that tenant's decisions;
      - customer model → unchanged.
      Retrain cooldown key becomes `(network, tenant_id, customer_id)`.
- [ ] `ml/predict.py`: implement the precedence above.
- [ ] Remove the raw `tenant_id` feature (`networks/check/features.py` L52,
      `networks/ach/features.py` L20). The bank-only model makes per-bank behavior
      unnecessary as a feature. Release note: the shared model needs a retrain.
- [ ] `workers/tasks.py::retrain_job`: loop shared model → each private tenant's bank model
      → customer models (existing), using the same `_train_and_log` failure isolation.
- [ ] Fraud-training examples (`ml_training_example:write`): from a private bank, they feed
      only its bank model. From a shared bank, they feed the shared model only once the platform
      operator approves them (`approved_for_shared` flag + review list), to block poisoning.
- [ ] Tests: a private bank's decisions never appear in the shared training set; the
      precedence table (customer → bank → shared → none) for every combination; the
      `tenant_id` feature is gone; activation ownership checks.

### PR 5b — Governance, settings UI, platform operator
- [ ] **Platform operator** for the shared model: retrain/activate/feature-importance
      move behind platform auth (extend `PlatformApiKey` / `platform_api_key_deps.py`, plus
      a platform-admin web page). A tenant admin only sees read-only "Shared model vN,
      active since …, trained on M decisions from K banks" (counts only, never other bank
      names).
- [ ] **Bank admin** (`admin:manage`) gets full retrain/activate/rollback for its own
      bank-only model on `/ui/admin`, same as the existing per-customer page.
- [ ] Settings → "Fraud scoring model" card (`tenant:manage`):
      - radio: *Shared network model* / *Bank-only model*, each with a plain-language
        description of the trade-off (the shared model starts useful sooner; bank-only keeps
        data in-house);
      - joining shared requires a confirmation checkbox with data-pooling disclosure text
        (a config-supplied setting, like the WSUD legal text, and startup refuses the
        placeholder in production);
      - the change is audit-logged (`tenant.ml_source_change`) and records who/when.
- [ ] **Switching behavior** (shown in the UI before confirming):
      - shared → private (after the 90-day lock): the bank is immediately scored by its
        seeded copy of the shared model. Its data is excluded from the *next* shared
        retrain, and the platform operator is notified to retrain.
      - private → shared: scored by the shared model immediately; data joins the next
        shared retrain. The old bank-only models stay in history (can switch back).
- [ ] Customer ML page: relabel the `GLOBAL` mode to "Bank's model" and show which
      model a customer is actually scored by right now.
- [ ] Demo tenant (Phase 4c): lock this setting.
- [ ] Docs: `docs/admin/ml-admin.html` + README; close the IOU in `SECURITY_REVIEW.md`.
- [ ] Tests: switch blocked before day 90 and allowed after (freeze time); existing
      banks are never locked; the seeded model's scores equal the shared model's on the same
      input; a challenger with too little data or a worse AUC is not promoted;
      tenant admin → 403 on shared retrain/activate; bank admin can
      retrain/activate its own bank model but not another bank's; switching requires the
      confirmation checkbox and writes an audit entry; the tenant-facing shared-model
      summary never includes other tenants' identifiers.

## Phase 6 — Exception review UX (1–2 PRs, about 3 days) — U2, U3, U4

Files: `templates/exceptions/detail.html`, `templates/exceptions/list.html`,
`web/routers/exceptions.py`, `web/templates.py` (label filter)
- [ ] **U2 evidence panel:** a check exception shows an "Issued vs Presented" table (check #,
      amount, payee, date, account) with the mismatched fields highlighted, using
      `related_reference_id` → `IssuedItem`. An ACH exception shows the matched/closest
      authorization rule (max amount, SEC codes, company ID) and the transaction's values.
- [ ] Inline check image (front/back thumbnails → full-size viewer) when one exists,
      plus links to the paid item and image record.
- [ ] Apply the `currency` filter everywhere on the detail page. Add account and customer
      names.
- [ ] Decision deadline: show when the default disposition will fire ("Auto-return at
      4:00 PM ET — 2h 13m left"), using `customer_disposition_setting` / the sweep job's
      logic.
- [ ] **U3 safe forms:** outcome `<select>` starts on "— Choose —" and is `required`.
      Show only the reason input that matches the chosen outcome (small JS, with a
      server-side check already in `decision_service`). When dual control is off, and for
      a user with `exception:decide`, show only Decide (no stacked Recommend form).
      Add an optional confirmation for "Pay" when the ML score is high risk.
- [ ] **U4 queue:** default the filter to Open + Pending approval. Sort oldest first / by
      deadline. Add Account, Customer, and Date columns. Human-readable exception type labels
      (`exception_type_label` filter: `amount_mismatch` → "Amount mismatch"). Hide the ML
      column when no model is active.
- [ ] Approvals follow-ups (from the step 9 review): store `recommended_ach_return_reason_id`
      as a real FK (migration) instead of text matching; add a pending count badge on the
      "Approvals" nav item.
- [ ] Tests: form requires an explicit outcome; the evidence panel renders issued and paid
      values; the default queue filter excludes decided items.

## Phase 7 — Layout and polish (1 PR, about 1–2 days) — U5, U6, U7, U8

- [ ] **U5 mobile:** wrap every `<table>` in `.table-scroll { overflow-x:auto }` (put it in
      the shared table macro/`app.js` sortable helper so every page gets it). Toolbars and
      button rows get `flex-wrap: wrap`. Re-run the Playwright overflow check (the script
      logic is in the EVALUATION step 10 notes) and aim for 0px overflow on all 27 pages at
      390px.
- [ ] **U6 dashboard:** make the stat cards links to filtered lists. Add "Awaiting my
      approval", "Oldest open exception", and "Due today". Drop the redundant link list.
- [ ] **U7 settings:** fix the `input[type=color]` CSS (fixed width and height). Replace the
      absolute drop-directory path with the tenant-relative folder name. Label the two
      unlabeled inputs.
- [ ] **U8:** wrap the Fraud Training link in `admin/ml_models.html` with
      `can(ctx, "ml_training_example:write")`, or add "(requires the Fraud Training
      permission)".
- [ ] Regenerate screenshots (`scripts/generate_screenshots.py`).

## Phase 8 — Docs and operational readiness (about 1 day) — F5, F6, F4, F3, S5

- [ ] **F5:** write `docs/ARCHITECTURE.md` (data model, network-adapter pattern, matching
      rules, ML pipeline, tenancy layers). Point the README and code comments at it.
- [ ] **F6:** document "single process only" in the README/RUNBOOK, *or* add a leader lock
      (a Postgres advisory lock around each scheduled job; on SQLite, keep single-process).
- [ ] **S5:** document that the rate limiter is per process. A shared store (for example
      Redis) is optional and only needed for multi-instance deployments.
- [ ] **F4:** validate X9.37 Bundle Control (type 70). Get a real processor sample file and
      add it as a fixture.
- [ ] **F3:** keep the Textract/Azure providers as roadmap items. No change is needed
      (startup already guards against them).

---

## Decisions

| Phase | Question | Decision (2026-09-22) |
|-------|----------|-----------------------|
| 1a | Can customer users export their own data? | **Yes**, own customer only |
| 2 | Can one bank's admin reset a user who also belongs to other banks? | **No**, block it; the user self-serves |
| 3 | Idle warning / keep-alive interval | **Warn 5 min before timeout**; refresh on activity |
| 4c | Demo scheduled reset interval | **Hourly** |
| 5 | Shared vs. bank-only ML model | **Both, chosen per bank** |
| 5 · D1 | Default for existing / new banks | **Shared for all**; existing banks keep their current model source |
| 5 · D2 | Cold start for bank-only | **New banks locked out of switching for 90 days; switching seeds a copy of the shared model** (champion/challenger from there) |

## Estimated sequence

| Order | Phase | Size | Why here |
|-------|-------|------|----------|
| 0 | Land approvals work | XS | Unblocks a clean baseline |
| 1 | S0, S1, F2, S7 | S | Critical/high, tiny diffs, verified repros |
| 2 | Password lifecycle | M | High; Phase 3's revocation builds on it |
| 3 | Sessions | M | Biggest daily-use pain; completes S2 |
| 4 | SSRF, uploads, demo | M | Public demo is live exposure |
| 5 | ML model choice per bank | M–L | All decisions made |
| 6 | Exception review UX | M–L | Core workflow quality |
| 7 | Layout polish | S | Mechanical |
| 8 | Docs/ops | S | Before any real multi-instance deployment |
