# Deployment and monitoring handoff

These steps require your own hosting, PostgreSQL, Resend, GitHub, and Asniher accounts. They have not been performed for this source package.

1. Push the project to an empty GitHub repository. Wait for the PostgreSQL-backed GitHub Actions tests to pass.
2. On a Docker-capable **always-on** host, provision PostgreSQL and a web service built from this repository's Dockerfile. Do not choose a static host or a runtime that freezes background threads between HTTP requests.
3. Configure `DATABASE_URL`, `DB_SSLMODE`, `API_TOKEN`, `RESEND_API_KEY`, `EMAIL_FROM`, `WORKER_ENABLED=true`, and `PORT` through the host's secret/environment settings. Use the database provider's required TLS settings. Keep secrets out of GitHub source.
4. Deploy. Container startup runs migrations. Route HTTPS traffic to the container's port. Set the host's health path to `/health` if supported. Enable restart-on-failure and retain application logs.
5. Open `https://YOUR_HOST/health`: expect HTTP 200 and `{"app":"up","database":"up"}`. Open the dashboard, connect using your token, and create your own real application.
6. Queue a reminder to your own permitted inbox. Check the queue reaches `sent` and inspect the real message in your inbox. Save evidence without exposing credentials. Do not confuse provider acceptance with inbox delivery.
7. Sign in to [Asniher](https://asniher.com/) and configure an HTTP GET monitor for the **public HTTPS `/health` URL**, with expected status 200. No API token is needed for this route. Use the monitor's available interval and alert settings. Exact UI labels are not verified here because the site could not be accessed during preparation.
8. Wait until the monitor records a genuine successful check. Capture a screenshot showing the service name, endpoint, status, and time. Avoid account details and secrets. Save it as `docs/asniher-monitor.png` and embed it in README with `![Asniher monitor](docs/asniher-monitor.png)`.
9. Optionally demonstrate database failure on a staging deployment: temporarily point it to an unreachable test database, redeploy, and confirm `/health` is 503. Restore the correct configuration and confirm recovery. Do not disrupt a service containing important data.
10. Commit the real screenshot, your actual deployed URL, and updated assignment status. Submit your actual GitHub URL.

## Submission checklist

- [ ] GitHub URL works for the teacher.
- [ ] GitHub Actions PostgreSQL tests pass.
- [ ] App runs in production with PostgreSQL.
- [ ] A real reminder was accepted by Resend and checked in your inbox.
- [ ] `/health` returns 200 when the database is reachable.
- [ ] A database outage returns 503 (verified in staging).
- [ ] Asniher monitors the live endpoint.
- [ ] Genuine monitor screenshot is committed and displayed in README.
- [ ] README includes the real deployed URL.
- [ ] No keys, passwords, API token, or `.env` file are committed.
