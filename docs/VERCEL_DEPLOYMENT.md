# Vercel Deployment

The hosted deployment (`icc-platform-2.vercel.app`) runs the Flask application as a
single Python serverless function, backed by Supabase PostgreSQL and Upstash/Vercel KV
Redis. `docs/NATIVE_DEPLOYMENT.md` remains the documented path for an institutional
server; this file documents the target actually in use.

## How a request is served

`vercel.json` rewrites `/(.*)` to `/api`, and `api/index.py` exposes `create_app()`.
There is no CDN static layer: `/static/*` is served by the function too, which is why
`app/__init__.py` sets the `Cache-Control` headers itself.

`outputDirectory` points at `public/`, which holds only `robots.txt`.

> **This is load-bearing.** Vercel publishes the output directory as static files, and
> the generated route table handles the filesystem *before* the rewrite. It was
> previously set to `"."`, which published the entire repository: `/app/config.py`,
> `/instance/*.db`, `/instance/UAT_CREDENTIALS.txt`, `/instance/dev_secret_key`,
> `/supabase/.temp/pooler-url` and `/terraform/main.tf` were all downloadable by
> anyone. Never point `outputDirectory` at a directory containing source or secrets.

`.vercelignore` is the second line of defence. A CLI deploy does **not** read
`.gitignore`, so everything secret must be listed there as well.

## Deploy from Git, not from the CLI

Connect the Vercel project to the GitHub repository and deploy from `main`.

A Git deploy honours `.gitignore`, so untracked databases and secrets cannot be
uploaded even if `.vercelignore` is later edited. A `vercel --prebuilt` deploy from a
developer machine uploads whatever is on that machine; that is how the exposure above
happened, and it is also why production drifted several commits behind the repository.

Migrations run automatically: the `buildCommand` is
`MIGRATION_ONLY=true uv run --frozen python -m flask --app run.py db upgrade`.
`MIGRATION_ONLY` relaxes `ProductionConfig.validate()` so the build does not need the
full serving configuration.

Frontend assets are **not** built on Vercel. `app/static/ui/` is committed; run
`npm run build:ui && npm run check:assets` locally and commit the result.

## Required environment variables

| Variable | Value |
|---|---|
| `APP_ENV` | `production` — any other spelling now raises rather than silently selecting the development config |
| `SECRET_KEY` | long random string; rotating it signs everyone out |
| `DATABASE_URL` | Supabase connection string |
| `SUPABASE_POOLER_HOST` | pooler host; the direct endpoint is IPv6-only and Vercel needs IPv4 |
| `RATELIMIT_STORAGE_URI` | `rediss://…` — `memory://` is rejected, and would silently stop enforcing limits across instances anyway |
| `UPLOAD_SESSION_STORAGE_URI` | `rediss://…` — without it, chunked uploads use an in-process dict that cannot survive between invocations |
| `CRON_SECRET` | random string; see Scheduled jobs |
| `DISABLE_EXTERNAL_INTEGRATIONS` | `true` until the GCP job/SMTP stack exists |
| `VERCEL` | set by the platform; selects `NullPool` so frozen instances cannot exhaust Supabase's session-pool client limit |

Upload sizes are clamped automatically when `VERCEL` is set. Vercel rejects a request
body over 4.5 MB at the edge, before Flask sees it, so `MAX_CONTENT_LENGTH` and
`UPLOAD_CHUNK_SIZE_BYTES` are capped at 4 MB regardless of what the environment asks
for. Raising them past that ceiling cannot work on this platform.

## Region

`vercel.json` pins `"regions": ["hnd1"]` (Tokyo) to match the Supabase pooler at
`aws-0-ap-northeast-1`. The function previously ran in `iad1` (Washington) while the
database was in Tokyo and users were in India — a trans-Pacific round trip per query,
and the home page issues ~39.

Confirm `hnd1` is available on the current plan before deploying; a plan that allows
only one fixed region will reject this. Moving Supabase to Mumbai and the function to
`bom1` would be better for Indian users, but that is a new project plus a data
migration.

## Scheduled jobs

`app/blueprints/internal_jobs.py` was written for Cloud Scheduler and Cloud Tasks with
Google OIDC. Neither exists here, so before this change nothing ever invoked them: no
deadline reminders, no notification delivery, and `AUDIT_RETENTION_DAYS` /
`REJECTED_APPLICATION_RETENTION_DAYS` were dead settings.

Vercel Cron invokes its targets with **GET** and cannot mint a Google OIDC token, so it
uses a separate entry point: `GET /internal/jobs/cron/<job>`, authorized by the
`CRON_SECRET` that Vercel sends as a bearer token, compared with `hmac.compare_digest`.
The POST + OIDC endpoints are unchanged, so the GCP path still works.

**No crons are currently configured.** The `crons` block was removed from
`vercel.json` because the account is on the Hobby plan, which rejects the deployment
outright with `cron_jobs_limits_reached`: Hobby permits only daily schedules, and
`notifications-deliver` needs `*/15 * * * *`. Nothing scheduled runs today — no
deadline reminders, no notification delivery, no retention pruning.

To restore them, upgrade the team to Pro and add back:

```json
  "crons": [
    { "path": "/internal/jobs/cron/reminders", "schedule": "0 2 * * *" },
    { "path": "/internal/jobs/cron/notifications-deliver", "schedule": "*/15 * * * *" },
    { "path": "/internal/jobs/cron/retention", "schedule": "30 3 * * *" }
  ],
```

`CRON_SECRET` is already set in the production environment, so the endpoints are live
and authorized; only the schedule that invokes them is missing.

## Known platform limits

- **Document upload is disabled** until live Drive credentials are supplied.
  `DISABLE_EXTERNAL_INTEGRATIONS=true` leaves `DRIVE_VALIDATION_MODE=mock`, and
  production refuses an upload it cannot actually persist rather than reporting a
  success that did not happen (audit B08). See the beta release runbook §1 for the
  Shared Drive folder, service-account key, and Content manager grant required.
- **Password-reset email is fire-and-forget** (`app/services/passwords.py` submits to a
  `ThreadPoolExecutor` and returns). A serverless function is frozen the instant it
  responds, so those messages will often never send. Latent while
  `NOTIFICATION_EMAIL_MODE=disabled`; must be moved onto the cron-delivered
  notification queue before email is enabled.
- **Report jobs** need Cloud Tasks (`enqueue_report_job` returns `None` otherwise) and
  stay `Queued`.
- Sessions last 8 hours, so an installed home-screen app asks for a fresh login daily.

## Rotating credentials

Because the repository was publicly served, treat these as compromised and rotate
them, then redeploy:

1. Supabase database password → update `DATABASE_URL`.
2. Vercel KV / Upstash tokens: `KV_REST_API_TOKEN`, `KV_REST_API_READ_ONLY_TOKEN`,
   `REDIS_URL`, `KV_URL`.
3. `SECRET_KEY` (signs everyone out, which is the point).
4. Delete local `instance/*.db`, `instance/UAT_CREDENTIALS.txt`, `instance/dev_secret_key`.
5. Review Supabase connection logs for unfamiliar clients.

Verify the exposure is closed after deploying:

```bash
for p in /app/config.py /instance/erp_development.db /instance/UAT_CREDENTIALS.txt \
         /instance/dev_secret_key /supabase/.temp/pooler-url /uv.lock \
         /terraform/main.tf /vercel.json /requirements.txt; do
  printf "%-36s " "$p"
  curl -s -o /dev/null -w "%{http_code}\n" "https://icc-platform-2.vercel.app$p"
done
```

Every line must be 404 or 302. `/healthz`, `/login` and `/static/ui/assets/*.css` must
still be 200.
