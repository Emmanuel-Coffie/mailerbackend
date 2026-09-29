# Validation results

## Frontend integration — 2026-09-29

- Backend regression: **41 passed, 0 failed** (2.836 seconds), isolated SQLite.
- Django system checks: **0 issues**. Migration drift: **no changes detected**.
- Frontend TypeScript: **passed, 0 errors**.
- Vitest: **22 passed, 0 failed**, across 3 files (39.64 seconds).
- Production Vite build: **passed**; all JavaScript chunks below 500 kB.
  Two non-blocking dependency annotation warnings originate in Zod; Rollup removes
  the annotations. No application build errors.
- Playwright against compiled production assets and real Django:
  **2 passed, 0 failed** (1.4 minutes including build/startup).
- Development-server browser run: **2 passed, 0 failed** (33.6 seconds, before
  final stale-data/CSV/polling improvements; final changes covered by production run).
- Formatting: Prettier source check passed.
- `npm audit`: **0 vulnerabilities**, including development dependencies.
- Premium UI strict audit: **0 findings**. DESIGN.md lint: **0 errors**, 4
  informational unused-component-token warnings; runtime tokens live in theme/CSS.
- Desktop analytics and 390px mobile dashboard screenshots visually inspected.
  Browser assertion confirms no page-level horizontal overflow on mobile.

The integrated browser workflow exercised actual JWT login and CORS, contact
creation/edit/deletion, dirty-dialog Escape/discard, delete confirmation/cancel,
offline error/retry, CSV invalid/duplicate counts, list membership, template
creation/rendered preview, seven-step draft saves, server preparation counts,
test delivery and campaign delivery through mocked Resend, recipient history,
analytics, a signed delivery webhook, public unsubscribe and repeated unsubscribe,
exclusion from later preparation, future scheduling, cancellation, settings and
mobile navigation. Unit tests additionally cover validation, authorization,
concurrent refresh, refresh failure, error normalization, null analytics rates,
invalid unsubscribe, safe HTML previews, and stale async response handling.

Provider calls were mocked. The test harness uses a dedicated SQLite database
and eager Celery tasks; no real email, Redis transport, MySQL row locking, DNS,
public HTTPS or provider account was exercised. The frontend CI job was added but
has not run remotely. The existing MySQL CI job remains intact.

## Backend baseline — 2026-09-28

Validated locally on 2026-09-28 using the project `.venv` (Python 3.12).

- `python manage.py check --settings=bulkmailer.test_settings`: passed, no issues.
- `python manage.py check --deploy`: passed, no issues, with a temporary random
  signing key and `DEBUG=False`, using the normal MySQL application settings.
  This settings check does not establish a database connection.
- `python manage.py migrate --settings=bulkmailer.test_settings --noinput`:
  all Django and mailing migrations applied successfully to isolated SQLite.
- `python manage.py makemigrations --check --dry-run --settings=bulkmailer.test_settings`:
  no model changes missing migrations.
- `python manage.py test --settings=bulkmailer.test_settings -v 1`:
  **41 tests passed, 0 failed**, final run 1.469 seconds.
- `python -m pip check`: no broken requirements.
- Development-server startup on `127.0.0.1:8017`: successful.
- Real HTTP `/admin/login/`: **200**.
- Real unauthenticated HTTP `/api/email/contacts/`: **401**.
- JWT obtain/refresh, authenticated CRUD, admin pages/forms, CSV validation,
  templates, preparation/snapshots, mocked sending, retry/exhaustion, scheduling,
  cancellation, queue-outage recovery, signatures, webhook idempotency, early
  webhook reconciliation, unsubscribe, suppression and task discovery: covered
  by the passing tests.

No real email was sent. Test provider calls are mocked and the isolated settings
disable the Resend key. `.env` and an administrator password were not generated.

MySQL, Redis and Docker were not installed on the host. Therefore these results
do **not** claim MySQL migration/concurrency validation or live Redis/Celery
transport validation. Ordinary application settings use MySQL exclusively.
The supplied GitHub Actions workflow runs migrations and the suite against MySQL
with Redis available; that workflow has not been executed from this workspace.

Live sending additionally requires a verified Resend domain, its DNS records,
an API key, sender configuration, and a public HTTPS webhook with a signing
secret. Nginx/systemd files are deployment examples, not an executed deployment.
