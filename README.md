# Mailflow — bulk email management

A Django/DRF internal bulk email backend. MySQL is the application database;
Redis brokers Celery work. The React/TypeScript frontend, Django Admin, and REST
API support contact imports, lists, templates, preparation, test delivery,
sending, scheduling, cancellation, suppression, and delivery history.

## Project layout

```text
manage.py
bulkmailer/             settings, URL routing, Celery, WSGI/ASGI
frontend/               React, TypeScript, Vite, MUI, browser and unit tests
mailing/
  models.py             contacts, lists, campaigns, recipients, events, opt-outs
  admin.py              admin pages, CSV form, test email form, campaign actions
  serializers.py        input validation and API representations
  views.py, urls.py      staff-only APIs and public unsubscribe
  services.py           preparation, CSV, provider integration, opt-outs
  tasks.py              campaign worker and minute scheduler
  webhooks.py           signature verification and event processing
  utils.py              safe variable renderer
  migrations/           initial schema
  templates/admin/      small extensions to standard Django Admin
  tests/                mocked-provider automated tests
deploy/                 Nginx and systemd examples
docs/                   Postman collection and sample CSV
.github/workflows/      MySQL-backed CI test job
compose.yaml            local MySQL and Redis services
.env.example
requirements.txt        compatible direct dependency constraints
requirements-lock.txt   exact locally tested dependency versions
```

## Requirements

- Python 3.12 recommended (the project uses Django 5.2 LTS).
- Node.js 22.12+ and npm for the frontend.
- MySQL 8.4 recommended, with an InnoDB/utf8mb4 database.
- Redis 7.x.
- Linux or WSL2 for production Celery/Gunicorn. Native Windows can run Django;
  a Celery `--pool=solo` worker is suitable for local experimentation only.
- Docker Desktop is optional; the supplied Compose file provides MySQL/Redis.

## Installation on Windows / PowerShell

Run from this repository directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Paste the generated value into `SECRET_KEY` in `.env`. Set a database password
and the other environment values below. Do not commit `.env`.

This checkout already has a virtual environment created during implementation.
If Python is not on PATH, its working executable is `.\.venv\Scripts\python.exe`.
Use that executable in place of `python` without needing activation.

On Linux/WSL:

```bash
python3 -m venv .venv
source .venv/bin/activate
# Debian/Ubuntu: needed when mysqlclient builds from source
sudo apt-get install python3-dev default-libmysqlclient-dev build-essential pkg-config
pip install -r requirements.txt
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

For exact tested dependencies, install `requirements-lock.txt` instead. The lock
includes a Linux-only Gunicorn marker so it is also usable on Windows.

## Database and Redis

With Docker Desktop installed and running, set `DATABASE_PASSWORD` in `.env`:

```bash
docker compose up -d mysql redis
docker compose ps
```

The Compose database/user defaults are `bulkmailer`, matching `.env.example`.
Both service ports bind only to localhost. Data persists in named Docker volumes.
Database credentials are initialized on the first start; changing `.env` later
does not change an existing database user's password.

Alternatively, in your installed MySQL server as an administrator:

```sql
CREATE DATABASE bulkmailer CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'bulkmailer'@'localhost' IDENTIFIED BY 'replace-with-your-own-password';
GRANT ALL PRIVILEGES ON bulkmailer.* TO 'bulkmailer'@'localhost';
```

Set `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST`, and
`DATABASE_PORT` to match. For a remote database, use an appropriately restricted
MySQL host grant and private network/TLS configuration.

For Redis installed under Linux/WSL, instead of Compose:

```bash
redis-server --appendonly yes
```

Keep Redis private. No unauthenticated public Redis port is needed.

## Environment reference

Every supported application variable is in `.env.example`:

- `DEBUG`: `True` locally; `False` in production.
- `SECRET_KEY`: required random Django signing secret; no application fallback.
- `ALLOWED_HOSTS`: comma-separated hosts, without schemes.
- `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST`,
  `DATABASE_PORT`: MySQL connection; default port `3306`.
- `REDIS_URL`: default Redis connection, `redis://localhost:6379/0`.
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`: default to `REDIS_URL` when unset.
- `RESEND_API_KEY`: required for live sends.
- `RESEND_WEBHOOK_SECRET`: signing secret required for webhook reception.
- `RESEND_FROM_EMAIL`: valid address at your verified sending domain.
- `RESEND_FROM_NAME`: optional sender display name.
- `RESEND_REPLY_TO`: optional reply address.
- `FRONTEND_URL`: allowed frontend origin, default `http://localhost:5173`.
- `BACKEND_URL`: public backend base URL used in unsubscribe links; default
  `http://localhost:8000`. Use an externally reachable HTTPS URL in production.
- `DEFAULT_TIMEZONE`: default `UTC`; API schedules accept timezone-aware ISO dates.
- `EMAIL_BATCH_SIZE`: database processing chunk size, default `50`, clamped to
  `1..100`. Worker sends each recipient individually within each chunk.
- `EMAIL_RETRY_LIMIT`: retries per recipient after the initial attempt, default `3`.
- `EMAIL_ALLOWED_TEST_RECIPIENTS`: optional comma-separated allowlist, enforced
  only when `DEBUG=True`. Populate before local live testing. Empty disables it.
- `CSV_MAX_BYTES`: maximum CSV upload bytes, default `5242880` (5 MiB).
- `TRUST_PROXY`: `True` only behind a trusted proxy that overwrites
  `X-Forwarded-Proto`; default `False`.

You can also set the standard `DJANGO_SETTINGS_MODULE` environment variable.
Never use `bulkmailer.test_settings` for a deployed application.

## Migrate, create admin, and run

After configuring MySQL:

```bash
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://localhost:8000/admin/` and log in. In separate activated terminals:

```bash
celery -A bulkmailer worker -l info
celery -A bulkmailer beat -l info
```

For local native Windows experiments use:

```powershell
celery -A bulkmailer worker -l info --pool=solo
```

Run one Beat instance. Its periodic task claims due schedules with row locks and
also recovers queued/stalled work after five minutes. Celery task discovery uses
`mailing.tasks.send_campaign` and `mailing.tasks.dispatch_due_campaigns`.

## Run the frontend

With Django running on port 8000, open another terminal:

```powershell
cd frontend
npm.cmd ci
Copy-Item .env.example .env.local
npm.cmd run dev
```

Open `http://localhost:5173` and use the Django staff/superuser account created
above. Use `localhost` consistently: CORS allows exactly `FRONTEND_URL`.
On Linux/macOS use `npm` and `cp .env.example .env.local`. The only frontend
environment variable is `VITE_API_BASE_URL`; never put provider keys in it.
JWT tokens are kept in memory; refreshing the browser requires signing in again.

Start with Contacts → Import CSV, create a Contact List, then a Template and
Campaign. The seven-step wizard saves a real backend draft, prepares recipients,
offers a test email, and confirms the server's eligible count before sending or
scheduling. Active campaign details poll every six seconds. Settings displays
configuration status only; change actual credentials in the backend environment.

See `frontend/README.md` for frontend tests and `frontend/BACKEND_INTEGRATION.md`
for API contracts and integration limits. For an isolated browser test without
MySQL/Redis or live sending, run `npm.cmd run test:e2e` after installing Playwright
Chromium with `npx.cmd playwright install chromium` from `frontend/`.

## Resend setup (manual)

1. Create a Resend account and add your sending domain.
2. Add the DNS records displayed by Resend at your DNS provider; verify the domain.
3. Create a sending API key. Put it in `RESEND_API_KEY`.
4. Set `RESEND_FROM_EMAIL` to an address at the verified domain, and optionally
   set `RESEND_FROM_NAME` and `RESEND_REPLY_TO`.
5. Set `BACKEND_URL` to your public HTTPS backend URL.
6. Create a Resend webhook for
   `https://YOUR-DOMAIN/api/email/webhooks/resend/`.
7. Subscribe to `email.sent`, `email.delivered`, `email.bounced`, `email.failed`,
   `email.complained`, `email.opened`, `email.clicked`, and `email.suppressed`.
   Other signed event types are stored too, without inventing state transitions.
8. Copy the webhook signing secret to `RESEND_WEBHOOK_SECRET`; restart web/worker
   processes after changing environment configuration.
9. Enable open/click tracking in the sending domain's Resend configuration if
   you want engagement events. Opens are tracking signals, not proof a person read
   a message; client privacy features and link scanners affect these signals.
10. Populate the development allowlist and send one test before live campaigns.

Provider documentation checked during implementation:
[send](https://resend.com/docs/api-reference/emails/send-email),
[batch](https://resend.com/docs/api-reference/emails/send-batch-emails),
[idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys),
[verification](https://resend.com/docs/webhooks/verify-webhooks-requests),
[events](https://resend.com/docs/webhooks/event-types), and
[tracking](https://resend.com/blog/open-and-click-tracking).

The official Python SDK uses `resend.Emails.send(params, options)` and
`resend.Batch.send(messages, options)`. The service implements both; campaigns
use individual sends for per-recipient suppression checks and stable idempotency
keys. Resend's current batch maximum is 100 messages. No account/Free-plan quotas
are hard-coded. `reply_to` is passed as an address string. Signatures are verified
with the officially supported Svix library against the raw request body and all
three `svix-*` headers.

## Admin workflow

1. Create a contact list under Mailing → Contact lists.
2. Under Contacts, use **Import CSV**, optionally selecting that list. You can
   also add/edit individual contacts and use the list's contact selector.
3. Create an email template. Supported variables: `{{first_name}}`,
   `{{last_name}}`, `{{company}}`, `{{position}}`. Missing/unknown variables become
   empty strings; HTML variable values are escaped. No template code executes.
4. Create a draft campaign, select lists and optionally a template. Campaign
   content overrides template content; blank fields copy the template at queue
   or schedule time. A campaign has its own sender/reply-to overrides.
5. Use the campaign's **Send test email** link to test a single address.
6. On the campaign list select drafts and choose **Prepare** to inspect snapshots,
   then **Queue** to send. Or save a future `scheduled_at` on the draft and choose
   **Schedule**. Use **Cancel** to stop future sends.
7. Inspect recipients, events, suppressions and unsubscribes in read-only history
   views. Campaign counts appear in campaign detail. Delivery history is protected
   from deletion; draft campaigns can be deleted through the API.

The created superuser can use all admin operations. Other staff users can use
all management APIs; standard Django model permissions govern their admin pages.

## REST API routes

All paths use trailing slashes. Management routes require a user with `is_staff`.
JWT and authenticated Django sessions are supported (sessions require CSRF for
unsafe methods). For Postman use `Authorization: Bearer <access>`.

```text
POST   /api/auth/token/                    {username, password}
POST   /api/auth/token/refresh/            {refresh}
GET    /api/email/dashboard/
GET    /api/email/settings/status/

GET,POST          /api/email/contacts/
GET,PUT,PATCH,DELETE /api/email/contacts/<id>/
POST   /api/email/contacts/import/         multipart file, optional contact_list_id
GET,POST          /api/email/lists/
GET,PUT,PATCH,DELETE /api/email/lists/<id>/
POST   /api/email/lists/<id>/add-contacts/  {contact_ids: [1,2]}
POST   /api/email/lists/<id>/remove-contacts/ {contact_ids: [1,2]}
GET,POST          /api/email/templates/
GET,PUT,PATCH,DELETE /api/email/templates/<id>/
POST   /api/email/templates/<id>/preview/  {first_name, last_name, company, position}

GET,POST          /api/email/campaigns/
GET,PUT,PATCH,DELETE /api/email/campaigns/<id>/
POST   /api/email/campaigns/<id>/prepare/
POST   /api/email/campaigns/<id>/test/      {email}
POST   /api/email/campaigns/<id>/send/
POST   /api/email/campaigns/<id>/schedule/  {scheduled_at: "2026-10-05T09:00:00Z"}
POST   /api/email/campaigns/<id>/cancel/
GET    /api/email/campaigns/<id>/analytics/
GET    /api/email/campaigns/<id>/recipients/

GET,POST /api/email/unsubscribe/<token>/   public, opaque token, repeat-safe
POST     /api/email/webhooks/resend/       public, requires valid Svix signature
```

Contact query parameters: `page`, `search`, `status`, `company`, `contact_lists`,
and `ordering` (`email`, `company`, `created_at`, `first_name`, `last_name`; prefix
with `-` for descending). Recipient queries: `page`, `status`, `email`, `company`,
`search`. Page size is 50. Campaign listing supports `status`, `search`, `ordering`.

CSV accepts UTF-8 (including BOM), a required `email` column and optional
`first_name,last_name,company,phone,position`. See `docs/contacts-example.csv`.
Invalid rows and repeated normalized emails are skipped. Existing contacts are
not overwritten but can join the selected list. Counts have these identities:
`total = invalid + duplicates + valid`; `valid = imported + existing`.

Analytics rates are percentages (0..100 under ordinary event ordering), or null
when the denominator is zero. Delivery/bounce/unsubscribe use sent as denominator;
open/click use delivered. Counts represent unique recipients with the relevant
timestamp, even if several provider events report the same engagement. Delayed
webhooks can temporarily produce inconsistent rates; raw events remain available.

## Postman / Insomnia

Import `docs/Bulkmailer.postman_collection.json`. Set `base_url`, `username`, and
`password` in your local collection variables; do not export real credentials.
The login request captures access/refresh tokens. CRUD create requests capture
IDs for subsequent requests. CSV import requires selecting a local file.

Run login → create contact → create list → add contacts → create template →
create campaign → prepare → test → send. For scheduling, create a separate draft
instead of scheduling an already queued campaign. Webhooks must be signed; use
the automated signature tests or a configured Resend webhook for those requests.

## Delivery safety and operational behavior

- Preparation deduplicates contacts across lists and excludes invalid/inactive/
  suppressed addresses. Repeated preparation does not duplicate snapshots.
- Every actual send rechecks the current contact and suppression table. Changing
  contact status to an inactive status preserves an email suppression record.
  Returning status to active does not erase suppression; suppression removal is
  an explicit admin operation.
- Preparing again preserves snapshots for retained contacts, removes draft
  recipients no longer in the eligible audience, and adds newly eligible ones.
  Queued/scheduled campaign content and audience are immutable through the API.
- Each marketing message gets an opaque unsubscribe URL in HTML, text, and
  List-Unsubscribe headers; both GET and one-click POST work without login.
  As requested, a GET opts out immediately, including when a link scanner follows it.
- Recipient uniqueness, database row locks and deterministic provider keys guard
  duplicate delivery. Retries reuse the exact stored request, including after
  a worker crash. Provider idempotency lasts 24 hours; ambiguous attempts older
  than 23 hours fail for manual reconciliation instead of risking another send.
- Temporary network, 429, and selected 5xx errors retry with 30/60/120 second
  backoff by default. Permanent failures remain failed. Inspect provider logs
  for detailed diagnostics; application errors intentionally omit provider bodies.
- Cancellation stops future unsent recipients. A request already accepted by
  Resend cannot be recalled; cancellation may wait for an in-flight send's row lock.
- Queue publication failures leave durable queued state for Beat to retry.
  Stale work can be redispatched; recipient locks and idempotency make this safe.
- Webhooks are deduplicated by provider/event ID, and unique recipient counts
  prevent different event IDs from double-counting an open/delivery. Bounce
  evidence wins over late delivery. Events arriving before message-ID persistence
  are reconciled after the send. Unmatched valid events remain stored.
- A completed campaign means local processing finished, not that all mail was
  delivered. Inspect failure counts and subsequent webhook outcomes.
- For this simple internal backend, sends within one campaign serialize around
  database row locks. This favors correctness over high-throughput bulk delivery.

## Automated tests

No automated test sends real email. Provider calls are mocked. Isolated local
tests need neither MySQL nor Redis:

```bash
python manage.py check --settings=bulkmailer.test_settings
python manage.py migrate --settings=bulkmailer.test_settings --noinput
python manage.py test --settings=bulkmailer.test_settings -v 2
python manage.py makemigrations --check --dry-run --settings=bulkmailer.test_settings
```

The isolated settings use SQLite solely for tests. The ordinary settings always
use MySQL. To test your configured MySQL database:

```bash
python manage.py test -v 2
```

Django creates a separate `test_bulkmailer` database. Give the test database user
permission to create/drop that database, or use a separate CI account. Do not
grant a production runtime account global database permissions. The supplied
GitHub Actions job provisions MySQL and Redis and runs migrations plus tests.

Local implementation validation used Python 3.12, Django 5.2.17, DRF 3.16.1,
Celery 5.6.3 and Resend 2.48.0. See `VALIDATION.md` for the final recorded checks
and environment limitations.

## Production deployment

Use Linux/WSL for Gunicorn/Celery. Deploy this directory at `/srv/bulkmailer`,
create a dedicated `bulkmailer` system user, provision MySQL/Redis, and install
dependencies in its virtual environment. Restrict `.env` access to that user.
Set `DEBUG=False`, a strong `SECRET_KEY`, correct `ALLOWED_HOSTS`, HTTPS
`BACKEND_URL`/`FRONTEND_URL`, and `TRUST_PROXY=True` behind the supplied Nginx proxy.

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
gunicorn bulkmailer.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 60
```

Install the three example systemd units from `deploy/`, adapting user/path values.
Build the frontend with `npm ci && npm run build` inside `frontend/`, setting
`VITE_API_BASE_URL` to the public backend HTTPS origin before the build. The Nginx
example serves `frontend/dist` with SPA route fallback and proxies API/admin.
Replace the host/certificate/static paths in `deploy/nginx.conf`, obtain a valid
TLS certificate using your hosting provider or ACME tooling, test with `nginx -t`,
then enable the proxy. Do not expose Gunicorn directly when trusting proxy headers.
Django enforces HTTPS redirects, secure cookies and HSTS when debug is disabled.
CORS permits only the configured frontend origin. Keep backups of MySQL and
monitor worker failures, queued campaign ages, and webhook delivery failures.

## Current limits

The application code, migrations and mocked end-to-end workflow are implemented.
MySQL/Redis/Docker were unavailable in the implementation environment, so actual
MySQL row-lock concurrency, Redis transport and hosted HTTPS infrastructure have
not been exercised locally. Run the MySQL CI job or the commands above before
production rollout. Live email delivery needs your Resend credentials, verified
domain/DNS, and public webhook URL. No DNS changes or real sends were performed.
