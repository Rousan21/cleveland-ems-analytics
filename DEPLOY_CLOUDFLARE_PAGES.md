# Deploy Cleveland EMS Analytics to Cloudflare Pages (free tier)

The existing **Render + FastAPI + Neon** application stays online. The new public
dashboard is hosted as static files by **Cloudflare Pages**. GitHub Actions reads
Neon, calculates the exact preset summaries via the existing Python code, and
uploads *only aggregate JSON and public neighborhood boundaries*. Neither
database credentials nor raw incident-level records go into Pages.

The Cloudflare project name used below is **cleveland-ems-explorer**. If this
name is taken, choose another name and change it in **both**
`.github/workflows/deploy-cloudflare-pages.yml` and
`.github/workflows/daily-ems-sync.yml` before deployment.

## One-time Cloudflare setup

1. Create or sign into a free Cloudflare account at https://dash.cloudflare.com .
2. Open **Workers & Pages** > **Create application** > **Pages** >
   **Direct Upload / Drag and drop your files**. Use project name
   `cleveland-ems-explorer`. Upload a tiny temporary `index.html` to create
   the project (GitHub Actions will replace this placeholder). Choose the
   production branch `main` if offered.
   - Choose **Direct Upload**, *not* Connect to Git. GitHub Actions builds the
     site from a private Neon credential and deploys it with Wrangler.
   - Cloudflare documents these as distinct project modes.
3. In Cloudflare, open **Manage account > Account API Tokens** and create a
   **custom token** with permission **Account > Cloudflare Pages > Edit** for
   only your account. Store it securely and do not post it in chats or commits.
4. Copy your Cloudflare **Account ID** from the account's dashboard (not a
   website/zone ID).
5. In https://github.com/Rousan21/cleveland-ems-analytics/settings/secrets/actions ,
   add the following **repository secrets**:
   - `CLOUDFLARE_API_TOKEN` = the API token from step 3
   - `CLOUDFLARE_ACCOUNT_ID` = the Account ID from step 4
   - Keep the *existing* `EMS_DATABASE_URL` secret as-is. Do not put that
     database URL in Cloudflare Pages.
6. Merge the reviewed migration pull request to `main`. Open
   **Actions > Deploy EMS dashboard to Cloudflare Pages > Run workflow**
   (select `main`), or use the automatic deployment from the merge. Inspect
   the action logs for successful snapshot generation and Wrangler deployment.

Once published, the project will be available at the Cloudflare-provided
`*.pages.dev` URL. Confirm the actual URL in Cloudflare; the hostname may gain
a suffix if the requested name was taken.

## Ongoing automatic updates

- **On code changes to `main`:** `deploy-cloudflare-pages.yml` recomputes
  summaries from Neon and publishes the refreshed static site.
- **Daily:** `daily-ems-sync.yml` ingests source data into Neon, then generates
  and deploys the new static snapshots *only after a successful import*.
- **Without Cloudflare secrets:** deployment is skipped, leaving your current
  Render website undisturbed.

## How filters work

- Preset windows: `24h`, `7d`, `30d`, `90d`, `1y`, `all`.
- Priority selections: `all`, `1`, `2`, `3`.
- All 24 combinations are exported with **exact existing median computations**
  and privacy-safe neighborhood summaries.
- Arbitrary **custom date** queries call the original Render API instead,
  preserving exact results but possibly taking longer on a cold start.
  Render must redeploy the updated `main.py` to enable CORS.
- Data on Pages updates at build time, not per visitor. For example, the
  `24h` snapshot represents the 24 hours leading up to the last export,
  rather than a rolling 24-hour interval at the moment each visitor clicks.

## Validation checklist

1. Open the Pages site and select **30 days** / **All priorities**.
2. Verify charts, counts, and map boundaries render without Render requests.
3. Change to **7 days** and **Priority 1**; check the values change.
4. Use a **Custom** date range: this should contact Render and return
   aggregate results, possibly after a cold start.
5. Confirm privacy: no JSON contains block addresses, individual incident
   records, or database credentials.
6. Run `pytest -q` from `webapp/` before merging.

## Local export

From `webapp/` with dependencies installed and `EMS_DATABASE_URL` set:

```bash
python export_static.py --output ../site_build
```

Do **not** commit `site_build/`: it contains only public aggregates, but the
generated snapshots belong in the deployment artifact, not Git history.

Cloudflare documentation:
- https://developers.cloudflare.com/pages/get-started/direct-upload/
- https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
