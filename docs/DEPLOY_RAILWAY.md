# Deploying ExamSentinel to Railway

> **Audience:** Whoever is doing the first production deploy, or rolling back a broken one.
> **Last updated:** May 2026 (Railway dashboard layout current as of this date).

This document walks through provisioning the ExamSentinel API on [Railway](https://railway.app) end-to-end. The Railway control plane is GUI-driven and not scriptable from this repository, so each step describes what to click in the dashboard.

---

## 0. Before you begin

You need:

- A Railway account (free tier is sufficient for the initial bring-up; upgrade once you onboard real students).
- Push access to the GitHub repository hosting this codebase, with the `main` branch in the state you want deployed.
- A terminal with `python` available locally — only used to **generate** the secrets you will paste into Railway.
- Optionally `psql` on your machine for the smoke test in §8. Not required if you use Railway's built-in query console.

The repository already contains every file Railway needs:

| File | Purpose |
|---|---|
| `Procfile` | Declares the `web` and `release` processes. |
| `runtime.txt` | Pins Python `3.11.x`. |
| `requirements.txt` | Pip dependencies. |
| `server/wsgi.py` | Exposes `app` for gunicorn and for `flask --app server.wsgi`. |
| `server/migrations/` | Alembic scripts; `release` runs `flask db upgrade` against this directory. |

You should not need to edit any of those during deploy.

---

## 1. Create the Railway project from the GitHub repo

1. Sign in at <https://railway.com> (Railway moved off `railway.app` for the dashboard during 2024; both URLs still resolve).
2. Click **New Project** in the top-right.
3. Choose **Deploy from GitHub repo**.
4. If this is your first time, click **Configure GitHub App** and grant Railway access to the `ExamSentinel` repository. Otherwise pick the repo from the list.
5. Railway will create a project containing one **service** (the web app) and start the first build immediately. Let it run; it will fail or stall partway because there is no database and no secrets yet — that is expected. We will fix it in §2 and §4.

> **Why GitHub-driven deploys?** Every push to the configured branch (defaults to `main`) triggers a new build. There is no `railway up` step in our workflow.

---

## 2. Attach a managed PostgreSQL database

1. Inside your new project, click **+ New** → **Database** → **Add PostgreSQL**.
2. Railway provisions a Postgres 16 instance in the same project. Wait for the green **Available** indicator on the database tile.
3. Click the database tile, then the **Variables** tab. You should see `DATABASE_URL`, `PGHOST`, `PGUSER`, etc. already populated. **Do not edit these.** Railway manages them.

### 2.1 Confirm the web service can see `DATABASE_URL`

Railway *usually* auto-injects `DATABASE_URL` into every service in the project as a **reference variable** (the value `${{Postgres.DATABASE_URL}}` resolves at deploy time). Verify:

1. Click your **web service** tile (not the Postgres tile).
2. Open the **Variables** tab.
3. Look for a `DATABASE_URL` row whose value reads something like `${{Postgres.DATABASE_URL}}`.

If the row is **missing**, add it manually:

1. Click **+ New Variable**.
2. Name: `DATABASE_URL`.
3. Value: click the small **link icon** in the value field, choose the Postgres service, and pick `DATABASE_URL`. The value box will show `${{Postgres.DATABASE_URL}}`.
4. Click **Add**.

Reference variables are preferred over hard-pasting the connection string because Railway will rotate the password if the database is rebuilt; the reference always resolves to the current value.

### 2.2 ⚠️ `postgres://` vs `postgresql://`

Railway's `DATABASE_URL` is sometimes emitted with the legacy `postgres://` scheme, which **SQLAlchemy 2.x rejects**. The application defends against this in `server/app/config.py` — `_resolve_database_uri()` rewrites `postgres://...` to `postgresql://...` before SQLAlchemy ever sees it.

If a future Railway change breaks this assumption and you see a deploy fail with:

```
sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres
```

…the fix is **not** to mutate the env var in the dashboard. Confirm the normalisation is still in place at `server/app/config.py:_resolve_database_uri`. If the file has been edited and the rewrite is gone, restore it.

---

## 3. Generate secrets locally

Both `SECRET_KEY` and `JWT_SECRET_KEY` need to be long, random, and **never** reused between projects. Generate them on your machine:

```bash
python -c "import secrets; print(secrets.token_hex(64))"
```

Run that command **twice** and keep both outputs handy — one for each variable. Each output is 128 hexadecimal characters.

> Do not paste these into chat, screenshots, the issue tracker, or your shell history if you can avoid it. They are bearer-equivalent for the entire app's session and JWT subsystems.

---

## 4. Set the application environment variables

Back in the Railway dashboard, on the **web service → Variables** tab, click **+ New Variable** for each row below.

| Name | Value | Notes |
|---|---|---|
| `SECRET_KEY` | first `token_hex(64)` output | Flask session signing key. |
| `JWT_SECRET_KEY` | second `token_hex(64)` output | Used by Flask-JWT-Extended; must differ from `SECRET_KEY`. |
| `FLASK_ENV` | `production` | Disables the dev SQLite fallback and triggers strict validation. |
| `CORS_ALLOWED_ORIGINS` | `*` | **Temporary.** We will tighten this once the desktop client's origin is finalised. |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Reference variable from §2.1; should already be present. |

`PORT` is injected automatically by Railway — do not set it yourself.

After saving the last variable, Railway will queue a fresh deploy.

---

## 5. Verify the build

1. Click the **Deployments** tab on your web service.
2. Click the most recent deploy row to open its log stream.
3. Watch the **Build Logs** panel. You should see, in order:
   - `Detected Python` (Nixpacks finds `runtime.txt`/`requirements.txt`).
   - `pip install -r requirements.txt` succeeding for every package in `requirements.txt`.
   - A green `Build successful` banner.
4. Switch to **Deploy Logs** (same panel, second tab in newer dashboards). You should see:
   - `Running release: flask --app server.wsgi db upgrade`
   - `INFO [alembic.runtime.migration] Running upgrade <none> -> 7fd62e721315, initial schema` (on the very first deploy; subsequent deploys just say `Will assume transactional DDL.` and exit immediately because the head is already applied).
   - A line indicating the release phase completed with exit code `0`.
   - `Starting gunicorn` followed by `Listening at: http://0.0.0.0:<port>` and worker boot lines.

If the release phase fails, the deploy is rolled back automatically and the previous version stays live. Read the alembic traceback in the logs and fix the migration or the model on a feature branch before re-deploying.

---

## 6. Reach the public URL

1. On the web service tile, open the **Settings** tab.
2. Scroll to **Networking**.
3. Click **Generate Domain**. Railway returns a URL like `https://examsentinel-production-xxxx.up.railway.app`. TLS is terminated by Railway's edge; you do not manage certificates.
4. (Optional) Add a custom domain via **Custom Domain → + Add Domain** and follow the CNAME instructions.

### 6.1 Smoke test the health endpoint

In a browser or with `curl`:

```
https://<your-railway-domain>/api/v1/health
```

Expected response (HTTP 200):

```json
{
  "database": "postgresql",
  "status": "ok",
  "timestamp": "2026-05-03T15:42:11.301284Z",
  "version": "v1"
}
```

The `"database": "postgresql"` field confirms the dialect-detection helper resolved the live PG dialect (the SQLite dev fallback would say `"sqlite"`).

If you instead get a `500` with `status: "degraded"`, the server reached gunicorn but the `SELECT 1` probe against Postgres failed. Most common cause: the release phase *appeared* to succeed but the connection at request time is using a stale env var from a previous deploy. Trigger a redeploy (§9.1).

---

## 7. Confirm the schema landed in PostgreSQL

You have two options.

### 7.1 Railway's built-in query console

1. Click the **Postgres** tile in your project.
2. Open the **Data** tab.
3. The left rail lists every table. You should see exactly the eleven application tables plus `alembic_version`:
   ```
   alembic_version
   answers
   courses
   departments
   enrollments
   exam_sessions
   exams
   incident_logs
   questions
   students
   teachers
   users
   ```

### 7.2 `psql` against the public connection string

1. Click the **Postgres** tile → **Variables** tab → copy the value of **`DATABASE_PUBLIC_URL`** (not `DATABASE_URL` — the latter is the private network URL only reachable from inside Railway).
2. From your local terminal:
   ```bash
   psql "<paste-DATABASE_PUBLIC_URL>"
   ```
3. At the `examsentinel=>` prompt run:
   ```
   \dt
   ```
   You should see the same eleven application tables plus `alembic_version`.
4. Spot-check the alembic head:
   ```sql
   SELECT version_num FROM alembic_version;
   ```
   Expected output: a single row matching the latest revision id committed under `server/migrations/versions/` (the initial schema is `7fd62e721315`).
5. `\q` to exit.

> **Security note.** The public URL exists because Railway exposes Postgres on a TCP proxy for developer convenience. Treat it as bearer credentials. Rotate it (Postgres tile → **Settings** → **Reset Credentials**) if it ever leaks.

---

## 8. Reading live logs

Two surfaces:

- **Per-deploy logs** — scroll into a specific deploy from the **Deployments** tab. Useful for post-mortems on a failed release.
- **Live tail** — on the web service tile, the bottom of the **Deployments** tab shows the active deploy with a **View Logs** button. Click it for a stream that updates as gunicorn handles requests. Filter with the search box at the top of the panel.

For a CLI experience, install the [Railway CLI](https://docs.railway.com/guides/cli):

```bash
railway login
railway link            # pick the project + service
railway logs            # streams the active deploy
railway logs --service Postgres   # stream Postgres logs instead
```

---

## 9. Operations

### 9.1 Redeploy without a code change

Useful when env vars changed or the worker is wedged.

1. Web service → **Deployments** tab.
2. Click the **⋯** menu on the latest successful deploy.
3. Choose **Redeploy**.

Railway re-runs the build (cached layers usually), the release phase (which is a no-op when there are no new migrations), and bounces the workers.

### 9.2 Rolling back to a previous deploy

The release phase is **forward-only** for migrations — Alembic does not run `downgrade` automatically. A rollback that includes a schema change therefore needs two steps:

**Code rollback only (no schema change):**

1. Web service → **Deployments**.
2. Find the last known-good deploy in the list.
3. Click its **⋯** menu → **Redeploy**.
4. Railway promotes that build's image without rebuilding. The active deploy gets replaced within ~30 seconds.

**Code rollback with schema rollback:**

1. Identify the alembic revision that was current *before* the bad deploy. Get it from the previous deploy's logs (`Running upgrade <prev> -> <bad>`) or from `alembic_version` in the Postgres console.
2. On a feature branch locally, run:
   ```bash
   flask --app server.wsgi db downgrade <prev_revision>
   ```
   …then commit a no-op change that pins the desired alembic head, push, and let Railway redeploy.
3. Only then redeploy the previous code build via the **⋯** → **Redeploy** path above.

> Railway has no "transactional rollback that also reverses migrations". You own the schema lifecycle; Railway only owns the container lifecycle.

### 9.3 Pausing a service

Web service → **Settings** → **Suspend Service**. Stops the workers without destroying the database. Resume from the same screen.

---

## 10. Definition of Done checklist

You are done when **all** of these are true:

- [ ] The Railway project shows two services in the **Available** state: the web app and Postgres.
- [ ] The web service **Variables** tab lists `DATABASE_URL` (reference), `SECRET_KEY`, `JWT_SECRET_KEY`, `FLASK_ENV=production`, `CORS_ALLOWED_ORIGINS=*`.
- [ ] The latest deploy's logs show `flask db upgrade` completing successfully and gunicorn listening on `$PORT` with two workers.
- [ ] Hitting `https://<your-railway-domain>/api/v1/health` from a browser returns HTTP 200 with `"database": "postgresql"` and `"status": "ok"`.
- [ ] Either the Railway **Data** console or `psql \dt` lists the 11 application tables plus `alembic_version`.

If all five boxes are ticked, deploy is verified. Tighten `CORS_ALLOWED_ORIGINS` once the desktop client ships, and rotate the secrets you generated in §3 if any of them have ever been pasted somewhere insecure.
