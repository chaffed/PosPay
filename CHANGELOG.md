# Changelog

## 1.5.0 — 2026-09-23

A security, reliability and usability release. It fixes every finding from the September
2026 review ([EVALUATION.md](EVALUATION.md)). It also lets each bank choose which fraud
model scores its exceptions, and it adds new screens for deciding exceptions.

### Upgrading from 1.0.0

- Run `alembic upgrade head`. The Docker image does this on startup. The new migrations
  only add columns and fill in values for existing rows.
- **Existing banks stay on the shared fraud model**, with nothing to do. New banks start
  on it too, and can switch to a bank-only model after 90 days.
- **Model files are now fingerprinted.** The upgrade records each existing model file's
  SHA-256. A model whose file can't be found during the upgrade isn't loaded until it's
  retrained. Its exceptions go unscored in the meantime, and it's logged.
- **Several instances:** read "Running more than one instance" in the README first.
  Several instances against one database are supported on Postgres only, and they need a
  shared volume for files.
- The public demo organization now resets every hour, and some destructive actions are
  locked there.

### Security

- A customer-scoped user could export the whole bank's data. Exports are now limited to
  the caller's own customer.
- Changing a user's security group now takes effect on their next request, not when
  their token expires.
- Logging out, changing a password, and an admin's "sign out everywhere" now end sessions
  on the server.
- SSO issuer URLs can't reach private or internal addresses, and the OIDC `state` is
  verified.
- Uploaded SVG logos and bulk-upload downloads are served safely.
- Only the platform operator can train or activate the shared fraud model. Banks control
  only their own models. A bank's fraud-training examples reach the shared model only after
  the operator approves them.
- Model files are verified against their recorded SHA-256 before they're loaded.
- The development `docker-compose.yml` publishes Postgres on localhost only.

### New

- **Fraud model choice per bank:** each bank uses the shared model or its own model.
  Switching copies the shared model, so scoring never stops. New versions replace the
  active model only if they do at least as well on the same recent decisions. See
  Settings → Fraud scoring, and the platform operator API.
- **Exception review:** a detail page that shows the evidence (images, OCR, the matching
  issued item, which checks failed and why), with no default choice on the decision
  forms. The queue opens on items that need attention. There's also an Approvals queue for
  maker/checker review, with a count in the navigation.
- **Password lifecycle:** people can change their own password, admins can reset one, and
  a password change can be required at next login.
- **Sessions:** activity keeps a session alive, and the page warns 5 minutes before it
  would expire.
- A dashboard built around what needs doing.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how PosPay fits together, and why.

### Fixes

- X9.37 files are checked against their bundle control totals as well as their cash
  letter and file totals. If any total doesn't match, the whole file is rejected.
- On Postgres, scheduled jobs run on one instance at a time.
- Errors show friendly pages and form messages instead of bare 500s or raw database text.
- Pages no longer scroll sideways on phones. The settings and admin pages were tidied.
