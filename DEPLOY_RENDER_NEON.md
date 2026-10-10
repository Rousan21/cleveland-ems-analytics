# Publish Cleveland EMS Analytics v2.2 — Render + Neon (free start)

**This guide requires a one-time sign-in to GitHub, Neon, and Render.** Do not post a database connection URL in a GitHub issue, chat message, commit, screenshot, or README.

## What the project does

- **Render Free Web Service** hosts the Python FastAPI UI, accessible from a public HTTPS URL.
- **Neon Free PostgreSQL** stores public EMS records persistently. Local SQLite is for development only.
- **GitHub Actions** imports Cleveland's published records to Neon daily; only public aggregate data is returned by the app.
- The Cleveland polygon map intentionally does *not* shade call hotspots without independently verified incident-to-neighborhood assignments.

## 1. Add the new app to your existing GitHub repo

Extract this ZIP in Finder. The extracted folder contains `webapp/`, `render.yaml`, `.github/`, and this file. In Terminal, from the folder containing those files, run:

```bash
# Use the path to your existing local Git clone. This is a likely location; change if different:
REPO="$HOME/cleveland-ems-analytics"
[ -d "$REPO/.git" ] || { echo "Not a git repository: $REPO"; exit 1; }
mkdir -p "$REPO/webapp" "$REPO/.github/workflows"
cp -R webapp/. "$REPO/webapp/"
cp render.yaml "$REPO/render.yaml"
cp .github/workflows/*.yml "$REPO/.github/workflows/"
cp DEPLOY_RENDER_NEON.md "$REPO/DEPLOY_RENDER_NEON.md"
# Optional but recommended: copy v2.2's root .gitignore entries into your repo's existing .gitignore manually.
cd "$REPO"
git status --short
```

**Before committing:** look at `git status --short` and ensure no `.env`, `.venv`, `.db`, `.sqlite`, patient/location CSV, or credential files are staged. Your existing `app.py`, `src/`, and `README.md` are left as-is. Only after reviewing:

```bash
git add webapp .github/workflows render.yaml DEPLOY_RENDER_NEON.md
git status --short
git commit -m "Add FastAPI EMS dashboard and Render deployment"
git push origin main
```

If your default branch isn't `main`, adjust the last command. For extra safety, use a feature branch and pull request instead of pushing to main. If git reports an error, stop and resolve it rather than force pushing.

## 2. Create the persistent database in Neon

1. Open https://console.neon.tech/ and create a **Free** project named `cleveland-ems-analytics`.
2. Pick a region close to the Render location you plan to use (typically US East).
3. Open the **Connect** dialog. Select connection string format and copy a **Postgres URL**, starting `postgresql://` or `postgres://`, typically ending with `?sslmode=require`.
4. You can use a pooled URL for the web app and a direct URL for import/schema setup, but for the first prototype a single valid URL is sufficient. Never place the actual URL in tracked files.

**Important:** The public dashboard and automated importer must point at the SAME Neon project's database/branch. Otherwise the site will show an empty database even after a successful import.

## 3. Publish the web application on Render

1. Open https://dashboard.render.com/ and choose **New > Web Service**.
2. Connect your GitHub account, then select `Rousan21/cleveland-ems-analytics`.
3. Choose branch `main` (or the branch that contains v2), and set the following values:

| Setting | Value |
| --- | --- |
| Language | Python |
| Root directory | `webapp` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |
| Instance | **Free** |

4. Under **Environment**, add `EMS_DATABASE_URL` as the **key**; the **value** is the exact Neon connection string copied in step 2.
5. Create the web service and wait for its deployment. Render assigns a public `https://...onrender.com` address. Avoid putting database credentials into commands, screenshots, code, or logs.
6. Visit `/`, `/health`, and `/api/summary?window=30d` under your Render URL. Expect the dashboard to show zero records until the database is populated.

Alternatively, you can use the included repository-root `render.yaml` as a Render Blueprint; it configures only the free web service. It does not create a database or scheduler.

## 4. Backfill the database from GitHub Actions

1. In the GitHub repository, go to **Settings > Secrets and variables > Actions**.
2. Create a **New repository secret** named `EMS_DATABASE_URL` containing the Neon connection URL. This is required separately from Render's environment variable.
3. Go to **Actions > Daily EMS data update > Run workflow**, select `main` and set `full_history` to **false** for a small initial test. Watch the run and confirm it completes.
4. Refresh the public dashboard. Check that `/api/summary?window=30d` shows nonzero records and a last successful import timestamp. If zero or an error, inspect the *Action logs*, *Neon database*, and *Render logs*.
5. After the small test, use **Run workflow** with `full_history=true` **one time** to import the available history. It can take significant time. Monitor Neon storage and compute limits; avoid uncontrolled retries.
6. The committed workflow runs daily around **13:37 UTC** and rechecks the last 30 days. Scheduled runs can be delayed or missed. The `All imported` filter shows only periods actually in the database.

### GitHub Actions caveats

Scheduled workflows run only from the repository's **default branch**. On inactive public repositories, GitHub may disable scheduled workflows after **60 days**. Confirm periodic successful Actions runs and use manual workflow dispatch to recover. Failed imports are visible in `/api/summary` and the GitHub Actions log.

## 5. Test like a recruiter

- Open the public URL in a private/incognito window **without signing in**.
- Check mobile layout, map boundary visibility, date presets, and chart interactions.
- Leave the site idle for 20 minutes and revisit it. A free Render service sleeps after 15 minutes; a cold start can take ~1 minute. This is a plan limitation, not a Python error.
- Check the `Last successful import` and `Newest dispatch` captions. They're different: the source may publish records with delay.
- Keep neighborhood call totals grey until matched geographic records are validated. Only verified per-neighborhood aggregates with privacy suppression can be shown.
- Do not use the local SQLite DB for hosted persistence: Render's free instance filesystem is ephemeral.

## Free plan cautions

- Render Free web service can spin down and can consume included monthly quotas.
- Neon Free project storage is currently **1 GB** and subject to monthly compute limits; always check the latest plan page.
- Your dataset size may exceed free limits if history grows. Check Neon storage and import logs before attempting an all-history import.
- Free tier services have service availability limits and should not be described as guaranteed 24/7.

## References

- Render: https://render.com/docs/your-first-deploy and https://render.com/docs/free
- Neon: https://neon.com/pricing and https://neon.com/docs/connect/connect-intro
- GitHub: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- EMS dataset: https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6
