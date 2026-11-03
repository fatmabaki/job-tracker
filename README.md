# JobFlow — Job Application Tracker

A small single-user **monolithic backend** with a black/gray dashboard. Track applications, update their stage, record notes, and schedule email follow-up reminders to your own inbox. One deployable Python application runs the API and a background worker; PostgreSQL is the persistent database and queue. No Redis or separate email microservice is required.

## Assignment status

| Requirement | Implementation | Evidence still needed |
|---|---|---|
| Four layers | `app/api`, `app/services`, `app/data`, `app/models`; architecture test | — |
| PostgreSQL | Versioned migrations, seed command, env configuration | Run database tests in CI or locally |
| Resend queue | Persisted pending/sent/failed jobs, scheduled delivery, four total attempts | Configure real Resend key and verify a delivered email |
| Health and monitoring | Public `GET /health`, actual database query, 200/503 responses | Live deployment and genuine Asniher screenshot |
| Delivery | README, `.env.example`, Docker, tests, clean local Git history | Push to your GitHub account and submit its URL |

**This source package is not yet a deployed or monitored submission.** No real email credentials are included and no monitor screenshot is fabricated.

## Quick start — Docker (recommended)

Install Docker Desktop with Compose. Extract this folder and open a terminal inside it.

```bash
cp .env.example .env
```

On Windows Command Prompt use `copy .env.example .env` instead. Edit `.env`:

- Replace `API_TOKEN` with a long random value (24+ characters).
- Set your real `RESEND_API_KEY`.
- Set `EMAIL_FROM` to a sender allowed by your Resend account. For real recipients, verify your domain as required by Resend. The onboarding sender is for permitted testing only.

```bash
docker compose up --build -d
docker compose exec app python -m app.cli seed
```

Open <http://localhost:8000>. Enter `API_TOKEN` in the dashboard and click **Connect**. Add applications, edit their stage, then click **Remind me** and enter your own email. Leave the time blank to enqueue an immediate reminder. Refresh the queue to inspect delivery status and attempts. Swagger docs: <http://localhost:8000/docs>; pass `Authorization: Bearer YOUR_TOKEN` when calling the API (or use curl below).

```bash
docker compose logs -f app
docker compose down
```

The named PostgreSQL volume preserves records across restarts. `docker compose down -v` deletes them.

## Local Python development

Use Python 3.12 and PostgreSQL 16. Create a database named `tracker` and a database user first, then set `DATABASE_URL` in `.env` to match.

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead:
# .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Export the values from `.env` into your terminal, or use Uvicorn's env-file support after `pip install python-dotenv`:

```bash
# macOS/Linux; only source the .env file you created yourself:
set -a
. ./.env
set +a
python -m app.cli migrate
python -m app.cli seed
python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers 1
```

In PowerShell use `$env:DATABASE_URL="postgresql://..."`, `$env:API_TOKEN="..."`, `$env:RESEND_API_KEY="..."`, and `$env:EMAIL_FROM="..."` before the migration/start commands. Python commands do not automatically load `.env`. Docker Compose loads it for you.

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Required PostgreSQL connection URL; never hardcoded in application code |
| `DB_SSLMODE` | `prefer` locally; use your production database provider's TLS requirement (normally `require` or verified TLS) |
| `API_TOKEN` | Required shared workspace token; minimum 24 characters |
| `RESEND_API_KEY` | Resend API credential; missing key makes due jobs fail and retry |
| `EMAIL_FROM` | Authorized sender address |
| `WORKER_ENABLED` | `true` by default; set `false` for isolated API tests |
| `WORKER_POLL_SECONDS` | Idle polling interval, default 2 seconds |
| `PORT` | Docker production listening port, default 8000 |
| `TEST_DATABASE_URL` | Dedicated disposable test database; integration tests truncate its application tables |

The application intentionally uses a single shared workspace token, not a multi-user account system. Do not give it to untrusted users; authenticated clients can view/edit all records and enqueue emails. Keep it out of URLs, screenshots, logs, and committed files. Dashboard tokens stay in the current page's memory and are not persisted to browser storage.

## Architecture

```mermaid
flowchart TD
    A[API: routes and validation] --> B[Services: tracker and email worker]
    B --> C[Data: PostgreSQL repositories]
    C --> D[Models: entities and DTOs]
```

`main.py` is the composition/lifecycle root. Internal layer imports only access the immediately lower layer. DTOs are defined in `models` and re-exported upward through data/services so API and service modules do not skip layers. Models have no application imports. SQL, migrations, database connections, transactions, and seed data live only in `data`. Routes handle authentication, validation, HTTP status codes, and errors. Services handle use cases, health decisions, and outbound Resend integration; they contain no FastAPI/request/response code. Outbound Resend HTTP calls are an external integration, not incoming API response handling.

The API enqueues immutable email snapshots and returns **202** without contacting Resend. The worker uses PostgreSQL `FOR UPDATE SKIP LOCKED` to claim a due row. The row lock remains held through the bounded provider call, preventing concurrent workers from processing the same row. On success it records `sent`, the provider ID, and timestamp. On error it records a generic non-secret error and backs off for **10, 20, 40 seconds** between attempts. After the fourth failed attempt it records `failed`. That is **one initial attempt plus three retries**. Future jobs remain `pending` until due.

A process crash rolls back its transaction and unlocks the job for another worker. Each job uses a stable Resend idempotency key. Resend retains these keys for 24 hours, so this is at-least-once processing with provider deduplication in that window, not an unlimited exactly-once guarantee. If an outage spans the deduplication window after an ambiguous delivery, investigate provider history before resuming. `sent` means accepted by Resend, not guaranteed inbox delivery; bounce/delivery webhooks are beyond this assignment.

Migrations are transactional and tracked in `schema_migrations`; an advisory lock serializes migration runners. Seed data is idempotent and never sends or queues email. The Docker startup applies migrations before starting the API. Run one Uvicorn worker per container; do not use serverless hosting that suspends background execution. PostgreSQL row locking also supports multiple always-on instances.

## Example requests

Replace `YOUR_TOKEN` with your token. Examples use a POSIX shell; on Windows use `curl.exe` and adapt quoting or use an API client.

```bash
curl -i http://localhost:8000/health
# 200 {"app":"up","database":"up"}
# Database unreachable: 503 {"app":"up","database":"down"}

curl -X POST http://localhost:8000/api/applications \
  -H 'Authorization: Bearer YOUR_TOKEN' -H 'Content-Type: application/json' \
  -d '{"company":"Example Studio","role":"Frontend Developer","status":"applied","notes":"Applied through their website"}'

curl http://localhost:8000/api/applications -H 'Authorization: Bearer YOUR_TOKEN'

curl -X PUT http://localhost:8000/api/applications/1 \
  -H 'Authorization: Bearer YOUR_TOKEN' -H 'Content-Type: application/json' \
  -d '{"company":"Example Studio","role":"Frontend Developer","status":"interview","notes":"Prepare React examples"}'

curl -X POST http://localhost:8000/api/applications/1/reminders \
  -H 'Authorization: Bearer YOUR_TOKEN' -H 'Content-Type: application/json' \
  -d '{"recipient":"your-own-inbox@example.com"}'
# Optional scheduled_at: an ISO-8601 timestamp with a timezone, in the future.

curl http://localhost:8000/api/email-jobs -H 'Authorization: Bearer YOUR_TOKEN'

curl -X DELETE http://localhost:8000/api/applications/1 -H 'Authorization: Bearer YOUR_TOKEN'
```

Deleting an application also deletes its queued reminder history. List endpoints return at most the most recent 500 records. Valid stages: `saved`, `applied`, `interview`, `offer`, `rejected`. Unknown records return 404, invalid payloads 422, absent/wrong token 401, and database failures 503 without leaking connection details.

## Tests

```bash
python -m pytest -q
# Also execute real PostgreSQL tests (dedicated disposable DB only):
TEST_DATABASE_URL=postgresql://tracker:tracker@localhost:5432/tracker_test python -m pytest -q
```

Tests cover authorization, validation, API enqueue-only behavior, missing records, health success/failure, layer boundaries, and dashboard serving. PostgreSQL integration tests cover migrations, CRUD, scheduling, successful processing, and three retries followed by terminal failure. Without `TEST_DATABASE_URL`, database tests explicitly skip. GitHub Actions supplies PostgreSQL and runs the whole suite on each push and pull request. Real Resend delivery needs your configured account; tests do not send real emails.

## Production deployment and Asniher evidence

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). You must finish those account-dependent steps before submitting. A Docker image and instructions are provided; no live URL or monitor exists yet.

## GitHub delivery

If starting from the ZIP sources:

```bash
git init
git add .
git commit -m "Build layered job tracker with persistent email queue"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/job-tracker.git
git push -u origin main
```

The download also contains `job-tracker-history.bundle`, which preserves the prepared commit history. To use it instead, run the following from the extracted folder; it creates a separate checkout:

```bash
git clone job-tracker-history.bundle ../job-tracker-repo
cd ../job-tracker-repo
git remote remove origin
git remote add origin https://github.com/YOUR_USERNAME/job-tracker.git
git push -u origin main
```

Create an empty GitHub repository first (no generated README). Do not commit `.env`. Add your real deployed URL and monitoring screenshot to the README before final submission. Submit the actual GitHub repository link to your teacher.

## References

- [Resend sending API](https://resend.com/docs/api-reference/emails/send-email)
- [Resend idempotency keys](https://resend.com/changelog/idempotency-keys)
- [Asniher](https://asniher.com/)
