# The Lobby

Private Valorant inhouse hub: match archive, all-time player profiles, advanced analytics and Playstyle Insights.

This version supports two storage modes:

- **Local mode**: SQLite file + raw JSON files, useful for development on your PC.
- **Vercel mode**: FastAPI on Vercel + Turso remote SQLite. The raw Tracker JSON is stored inside Turso as well, so the app does not depend on Vercel's temporary filesystem.

## Local setup

Requires Python 3.13.

```powershell
python -m pip install -r requirements.txt
python server.py
```

Then open `http://127.0.0.1:8765`.

Without `TURSO_DATABASE_URL`, the application automatically uses the local `inhouse.db` database.

For admin access in PowerShell:

```powershell
$env:ADMIN_USER="admin"
$env:ADMIN_PASSWORD="your-password"
python server.py
```

Then visit `http://127.0.0.1:8765/admin/import`.

## Vercel + Turso

The production setup is intentionally small:

1. Vercel runs the FastAPI application.
2. Turso stores the normalized statistics **and** the immutable raw Tracker JSON.
3. GitHub stores only the source code.

No production SQLite file or raw match JSON is committed to Git.

### Required environment variables

```env
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
ADMIN_USER=...
ADMIN_PASSWORD=...
DISCORD_INVITE=https://discord.gg/yAqfGTbtPw
```

`TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are provided automatically when a Turso database is connected through the Vercel Marketplace.

The schema is created automatically the first time the app connects to an empty Turso database.

## Deploying on Vercel

1. Import the GitHub repository into Vercel.
2. Keep the detected Python/FastAPI settings; no custom build command is needed.
3. Add/install **Turso Cloud** from the project's Storage/Marketplace area and connect a database.
4. Add `ADMIN_USER` and `ADMIN_PASSWORD` in Vercel Project Settings → Environment Variables.
5. Redeploy.
6. Check `/health`, then the homepage.
7. Open `/admin/import`, authenticate, and import the first real match JSON.

Vercel has a hard request-body limit of 4.5 MB for Functions. Historical Tracker match payloads used while developing The Lobby were below that limit; the app itself caps imports at 4.4 MB by default.

## Runtime data

Local mode:

- `inhouse.db`
- `data/raw/*.json`

Vercel/Turso mode:

- normalized statistics → Turso tables
- immutable Tracker payloads → `raw_matches` table in Turso

The public pages never need direct Turso credentials; all database access happens server-side.

## Git workflow

```powershell
git add .
git commit -m "Prepare The Lobby for Vercel"
git push
```

Once the Vercel project is connected to the GitHub repository, pushes to `main` automatically trigger deployments.

## Admin routes

- `/admin/import`
- `/admin/data-audit`

They use HTTP Basic Auth and remain locked when admin credentials are not configured.

## Health check

`/health` returns `ok` when the application is running.


## Serverless import performance

Remote Turso imports are batched into multi-row SQL statements to avoid thousands of network round trips. Interrupted imports are marked and safely retried on the next upload of the same Match ID.


### Temporary diagnostic route

`/admin/debug-advanced` is protected by the same Basic Auth as the import page and returns the full Advanced traceback only to an authenticated admin. Remove it after the Turso Advanced issue is fixed.
