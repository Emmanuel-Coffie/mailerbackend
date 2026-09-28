# Validation results

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
