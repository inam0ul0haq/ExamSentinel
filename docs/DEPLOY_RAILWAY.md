# Deploying ExamSentinel to Railway

> **Audience:** Whoever is doing the first production deploy, or rolling back a broken one.
> **Last updated:** May 2026 (Railway dashboard layout current as of this date).

This document walks through provisioning the ExamSentinel API on [Railway](https://railway.app) end-to-end. The Railway control plane is GUI-driven and not scriptable from this repository, so each step describes what to click in the dashboard.

---

## 0. Before you begin

You need:

- A Railway account (free tier is sufficient for the initial bring-up; upgrade once you onboard real students).
- Push access to the GitHub repository hosting this codebase, with the `main` branch in the state you want deployed. **Before starting, verify the branch contains** `Procfile`, `runtime.txt`, `requirements.txt`, and `server/migrations/versions/*.py`. If any of those are missing from the last push, commit and push first — Railway only sees what's on the remote.
- A terminal with `python` available locally — used to generate secrets in §3 and (if needed) to run the manual migration in §5.5.
- Optionally `psql` on your machine for the §7 smoke test. Not required if you use Railway's built-in query console.

The repository already contains every file Railway needs:

| File | Purpose |
|---|---|
| `Procfile` | Declares the `web` and `release` processes (at **repo root**, not `server/`). |
| `runtime.txt` | Pins Python `3.11.x`. |
| `requirements.txt` | Pip dependencies. |
| `server/wsgi.py` | Exposes `app` for gunicorn and for `flask --app server.wsgi`. |
| `server/migrations/versions/*.py` | Alembic scripts. If this folder is empty on the remote, the release phase will succeed as a no-op and no tables will ever be created — see §5.5. |

You should not need to edit any of those during deploy.

---

## 1. Create the Railway project from the GitHub repo

1. Sign in at <https://railway.com> (Railway moved off `railway.app` for the dashboard during 2024; both URLs still resolve).
2. Click **New Project** in the top-right.
3. Choose **Deploy from GitHub repo**.
4. If this is your first time, click **Configure GitHub App** and grant Railway access to the `ExamSentinel` repository. Otherwise pick the repo from the list.
5. Railway will create a project containing one **service** (the web app) and start the first build immediately. It **will fail** because there is no database and no secrets yet — that is expected. Don't waste time reading the traceback; just let the first deploy go red and proceed to §2. The deploy we actually care about is the one that runs automatically after §4 is saved.

> **Why GitHub-driven deploys?** Every push to the configured branch (defaults to `main`) triggers a new build. There is no `railway up` step in our workflow. If you want to redeploy the *same* commit without pushing, use **⋯ → Redeploy** on the deploy row (see §9.1).

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

Add **all five** variables below before you walk away. Missing any one of `SECRET_KEY`, `JWT_SECRET_KEY`, or `DATABASE_URL` — or leaving `CORS_ALLOWED_ORIGINS` as `*` — causes the workers to boot-loop with a `ConfigError` (see §5.4).

| Name | Value | Notes |
|---|---|---|
| `FLASK_ENV` | `production` | Disables the dev SQLite fallback and triggers strict validation. **Add this first**; the other validators only fire when `FLASK_ENV != development`. |
| `SECRET_KEY` | first `token_hex(64)` output | Flask session signing key. **Required** when `FLASK_ENV != development`. Empty strings count as missing. |
| `JWT_SECRET_KEY` | second `token_hex(64)` output | Used by Flask-JWT-Extended; must differ from `SECRET_KEY`. Also required. |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:1420` | **Not `*`** — the config validator rejects `*` outside development (see `server/app/config.py` `validate()`). A single origin like `http://localhost:1420` (Tauri default dev) is fine for now. **Do not put your own Railway URL here** — CORS lists the *frontends* allowed to call the API, never the API itself. Replace with the real desktop-client origin(s) once that client ships. |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Reference variable from §2.1; should already be present. If it isn't, add it via the value field's **link icon** — do not paste the raw connection string. |

`PORT` is injected automatically by Railway — do not set it yourself.

All variable names are **case-sensitive and underscore-sensitive**. `SECRET-KEY`, `SecretKey`, `FLASK_SECRET_KEY`, etc. will all pass straight through the validator because none of them match `SECRET_KEY`, and gunicorn will then crash with `SECRET_KEY is required outside development.` Copy the names from this table exactly, character for character.

After saving the last variable, Railway will queue a fresh deploy.

---

## 5. Watch the deploy — three separate log phases

Railway's deploy has **three phases** that each emit their own log stream, shown stacked inside a single deploy row. Most first-deploy confusion comes from only reading one of them. Open the **Deployments** tab → click into the most recent deploy → and look at each phase in order.

### 5.1 Phase 1 — Build Logs

You should see, in order:

- `Detected Python` (Nixpacks finds `runtime.txt` / `requirements.txt` at the repo root).
- `pip install -r requirements.txt` succeeding for every package in `requirements.txt`.
- A green `Build successful` banner.

If this phase fails: usually a missing dependency or a Python version mismatch. Fix `requirements.txt` / `runtime.txt` on a branch and push.

### 5.2 Phase 2 — Release / Pre-deploy Logs (this is where migrations run — **read carefully**)

The `release:` line in `Procfile` runs `flask --app server.wsgi db upgrade` in a short-lived container **before** the web workers boot. Look for a section labelled **Pre-deploy command** or **Release Logs** (exact label varies by dashboard version; it sits between Build and Deploy).

On the **first** deploy against an empty database, you must see this exact line:

```
INFO  [alembic.runtime.migration] Running upgrade  -> 7fd62e721315, initial schema
```

On **every subsequent** deploy (no new migrations), you will instead see:

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

…and the phase exits in under a second. No `Running upgrade` line is expected because the head revision is already applied.

**If the release phase is missing entirely, empty, or says `Path doesn't exist: '/app/migrations'`**, Railway did not pick up the `release:` line from your Procfile. This happens occasionally and is fixed once, manually, in §5.3.

**If the release phase succeeded but the Data tab in §7 still shows no tables**, the release ran against the wrong database (usually because `DATABASE_URL` wasn't yet visible at release time). Jump to §5.5 to bootstrap the schema manually.

### 5.3 Setting the pre-deploy command explicitly (one-time, only if §5.2 didn't run)

Some Railway projects do not honour the Procfile `release:` line automatically and need the command configured in the UI as well:

1. Web service → **Settings** tab.
2. Scroll to **Deploy → Pre-deploy Command** (sometimes labelled **Custom Start Command → Pre-deploy**).
3. Paste exactly:
   ```
   flask --app server.wsgi db upgrade
   ```
4. Click **Save** (or **Apply**; wording varies). Railway will re-queue a deploy automatically.

This is belt-and-braces: the Procfile already declares the same command, but Railway's UI setting takes precedence when both exist. After setting it once, §5.2's release phase will reliably appear on every future deploy.

### 5.4 Phase 3 — Deploy Logs (gunicorn workers)

After the release phase exits 0, you should see:

- `Starting gunicorn 23.0.0`
- `Listening at: http://0.0.0.0:<port>` (port chosen by Railway, exposed via `$PORT`)
- `Booting worker with pid: 2` and `Booting worker with pid: 3` (two workers, per the `--workers 2` flag in `Procfile`)
- **No** repeated `Worker exiting` / `Worker failed to boot` lines.

If instead you see:

```
[ERROR] Worker (pid:2) exited with code 3
[ERROR] Worker failed to boot.
app.config.ConfigError: Invalid configuration:
  - SECRET_KEY is required outside development.
  - CORS_ALLOWED_ORIGINS='*' is forbidden outside development; set an explicit comma-separated origin list.
```

…then `server/app/config.py::Config.validate()` rejected your env vars. Fix using the table below. After saving the variables, Railway redeploys within seconds — **no rebuild is needed** because the container image hasn't changed.

| Error bullet | Fix |
|---|---|
| `SECRET_KEY is required outside development.` | Add the `SECRET_KEY` variable (case-sensitive) with a 128-hex value from `python -c "import secrets; print(secrets.token_hex(64))"`. Empty strings count as missing. |
| `JWT_SECRET_KEY is required outside development.` | Same as above with a **different** random value under the name `JWT_SECRET_KEY`. |
| `CORS_ALLOWED_ORIGINS='*' is forbidden outside development; set an explicit comma-separated origin list.` | Change the value from `*` to an explicit comma-separated list, e.g. `http://localhost:1420`. |
| `DATABASE_URL is required when FLASK_ENV is not 'development'. Set DATABASE_URL to a valid PostgreSQL connection string.` | Attach Postgres (§2), then add `DATABASE_URL` as a reference variable pointing at `${{Postgres.DATABASE_URL}}`. |

### 5.5 Manual schema bootstrap — when the release phase ran but no tables appeared

Sometimes Railway's release phase reports success but the Postgres Data tab in §7 stays empty. The two common causes are:

- The release container didn't actually have `DATABASE_URL` injected yet (can happen on the *very first* deploy, before reference variables resolve), so it fell back to an ephemeral SQLite file that was discarded when the container exited.
- The Procfile `release:` line was silently ignored, so `flask db upgrade` never ran.

Either way, the fastest unblock is to run the migration **from your machine** against the Railway Postgres, one time, to bring the schema up to head. Future deploys will then find the head already applied and no-op correctly.

**Step A — get the public Postgres URL.**

1. Railway → click the **Postgres** tile (not the web service).
2. **Variables** tab.
3. Copy the value of **`DATABASE_PUBLIC_URL`** (not `DATABASE_URL` — that one only works from inside Railway's private network). It looks like `postgresql://postgres:XXXXX@roundhouse.proxy.rlwy.net:12345/railway`.

**Step B — run `flask db upgrade` locally against that URL.**

Open PowerShell in the `server/` folder. The venv there should already have Flask, SQLAlchemy, and psycopg2 installed from `..\requirements.txt`.

```powershell
# Scope these env vars to just this shell so they don't leak into other work.
$env:DATABASE_URL        = "<paste-DATABASE_PUBLIC_URL-here>"
$env:FLASK_ENV           = "production"
$env:SECRET_KEY          = "any-non-empty-string-for-this-shell"
$env:JWT_SECRET_KEY      = "any-other-non-empty-string"
$env:CORS_ALLOWED_ORIGINS = "http://localhost:1420"

.\.venv\Scripts\flask.exe --app app db current
.\.venv\Scripts\flask.exe --app app db upgrade
.\.venv\Scripts\flask.exe --app app db current
```

Expected:

- First `db current`: prints nothing (the remote has no alembic version row yet).
- `db upgrade`: prints `Running upgrade  -> 7fd62e721315, initial schema` and exits 0.
- Second `db current`: prints `7fd62e721315 (head)`.

**Step C — refresh Railway's Data tab.** Back in Postgres tile → **Data** → browser refresh. You should now see all 12 tables (see §7).

**Step D — close the loop.** Also do §5.3 (Pre-deploy Command in Settings) if you haven't already, so the *next* migration you write ships automatically instead of needing a manual run.

> **Why is it safe to set a throwaway `SECRET_KEY` in the local shell?** Because `db upgrade` never signs anything with it — it only needs to pass `Config.validate()`. The real production `SECRET_KEY` on Railway is separate and untouched.

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

   **If the list is empty**, the release phase didn't actually apply the migration to this database. Go back to §5.5 and run the manual bootstrap — it takes about 90 seconds and is safe to retry.

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
- [ ] The web service **Variables** tab lists `FLASK_ENV=production`, `SECRET_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL` (as a reference to `${{Postgres.DATABASE_URL}}`), and `CORS_ALLOWED_ORIGINS` set to an **explicit origin list** (not `*`, not the API's own URL).
- [ ] The latest deploy's **Release/Pre-deploy Logs** show either `Running upgrade  -> 7fd62e721315, initial schema` (first deploy) or a clean no-op (subsequent deploys) — §5.2.
- [ ] The latest deploy's **Deploy Logs** show `Listening at: http://0.0.0.0:<port>` and both workers stay booted with no `Worker failed to boot` lines — §5.4.
- [ ] Hitting `https://<your-railway-domain>/api/v1/health` from a browser returns HTTP 200 with `"database": "postgresql"` and `"status": "ok"` — §6.1.
- [ ] Either the Railway **Data** console or `psql \dt` lists the 11 application tables plus `alembic_version` — §7.

If all six boxes are ticked, deploy is verified. Replace the placeholder `CORS_ALLOWED_ORIGINS` value with the real desktop-client origin(s) the day that client ships, and rotate the secrets you generated in §3 if any of them have ever been pasted somewhere insecure.
