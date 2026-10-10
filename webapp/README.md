# Cleveland EMS Analytics v2.1 — FastAPI / Python

This is a Python FastAPI website, separate from the original Streamlit project. It uses the City of Cleveland's public ArcGIS EMS Calls for Service table and includes a date-filterable statistical dashboard. The interface is built with HTML/CSS, Chart.js, and a small amount of browser JavaScript. SQLAlchemy supports SQLite locally and PostgreSQL for hosting.

## Launch locally

**Mac: double-click `../Open Cleveland EMS.command`.** It creates a local virtual environment on first launch, opens the browser, and refreshes stale data in the background. A second launch reuses installed dependencies. When closed, local updates stop.

Manual launch from `webapp/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python ingest.py --days 30
python -m uvicorn main:app --reload
```

Open http://127.0.0.1:8000 and inspect JSON API documentation at http://127.0.0.1:8000/docs.

### Historic data

`python ingest.py --all` backfills the published history. `python ingest.py --days 30` upserts a rolling 30-day window; re-running doesn't duplicate a known OBJECTID. A recent window doesn't include all historical records. The City updates the public feed on its own schedule, not live.

## Maps and privacy

**This release removes all raster map tiles.** A clean Leaflet vector map displays boundary polygons from the public [Cleveland neighborhood boundary layer](https://services7.arcgis.com/ZodPOMBKsdAsTqF4/ArcGIS/rest/services/Cleveland_Neighborhoods/FeatureServer/147). The server downloads the official GeoJSON the first time it's requested, validates it, and caches it to `data/cleveland_neighborhoods.geojson`.

**Important:** This EMS dataset is a table with a `Block_Location` text field, **not** a spatial point layer with a validated neighborhood column. We have *not* proved an incident-to-neighborhood match. Therefore neighborhood shapes are gray by default and are explicitly labeled *unavailable*, not zero. Don't claim that higher/lower call areas are known until this step is solved.

When a reviewed assignment CSV is available, the app supports privacy-preserving choropleth colors and ranking:

1. Validate that each record ID maps to the correct *official* neighborhood (using independently checked geocoding/census joins and error analysis). **Do not guess from street names.**
2. Store that checked crosswalk privately as `object_id,neighborhood` CSV outside source control.
3. Run:

   ```bash
   python import_verified_areas.py /path/to/reviewed.csv --source 'Validated census-geocoder output reviewed against official city neighborhood polygons'
   ```
4. The API `/api/areas` aggregates only those reviewed assignments and suppresses counts below **11** per area for the selected time period/priority. The browser colors eligible neighborhoods; unverified or suppressed areas remain gray.

`/api/areas` contains no incident addresses, coordinates, or IDs. Never check the crosswalk CSV into GitHub. Neighborhood totals can differ from all call totals because only verified matches are counted. Caution: raw call counts are not per-capita measures or indicators of neighborhood danger.

## Publishing a shareable website

A stable web URL needs a hosting provider. AWS is **not necessary**. `../render.yaml` is a starting Render Blueprint for a FastAPI web process. It intentionally does not auto-create paid resources.

1. Add this project to a GitHub repository (the default branch should contain `webapp/` and `render.yaml`).
2. On [Render](https://render.com/docs/your-first-deploy), connect GitHub and create a Python web service (or use the included Blueprint). The app starts with `uvicorn main:app --host 0.0.0.0 --port $PORT`, with root directory `webapp`.
3. Add a **persistent, externally managed PostgreSQL database**. Set Render's `EMS_DATABASE_URL` environment variable to its connection URL. The application normalizes `postgres://` and `postgresql://` to the psycopg v3 driver automatically.
4. To perform daily refreshes, configure a separate scheduler. One option is the included `.github/workflows/daily-ems-sync.yml` in the repository root. Add **repository secret `EMS_DATABASE_URL`** with your database's **externally reachable** connection string. The GitHub scheduler cannot connect via a provider's private-only database hostname. Run the workflow manually once (with `full_history=true` if appropriate) then watch the scheduled import logs. The scheduled workflow runs daily at 13:37 UTC. Scheduled Actions can be delayed or missed; this is not a hard real-time guarantee.
5. Verify the public URL, that import successes appear in the header, and that all-time filters actually cover the imported history.

**Cost caution:** Render's free web service can sleep after 15 minutes idle, so the first visitor may wait for startup. Its filesystem is ephemeral and cannot safely store SQLite data across restarts. Free Render PostgreSQL currently expires after 30 days. For a lasting public portfolio, use a persistent DB plan or a different host you trust after checking up-to-date pricing. Do not publish database credentials or keep test passwords.

This is *deployment-ready code*, not a deployed website. A local `127.0.0.1` address is never public.

## Tests

```bash
pytest -q
```

Includes API, import idempotency, date and DST filter, GeoJSON sanitization, geographic suppression, and absence of raster tiles. ArcGIS network calls are mocked during automated tests. Browser visuals and actual city geographic matches must be verified on a machine with internet access.

## Remaining steps

- Validate the ArcGIS feed's location-to-neighborhood matches, then compute real safe geographic counts.
- Deploy the public backend and reliably schedule ingestion, with monitoring and backups.
- Backfill the full historical data; optimize large queries and add CI for PostgreSQL.
- Audit the page on mobile and check accessibility and chart/map rendering on different browsers.

Official data: https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6.

 
### Source identity and reporting-lag audit

The public `OBJECTID` is a unique *source row* identifier; it is **not established as a unique emergency incident**. The ArcGIS table also contains `EMS_Call_Number` and `Unit_Callsign`. The dashboard deliberately calls its metrics *published records* until their relationships are checked.

To audit the last 30 days without changing Neon or displaying raw incident identifiers:

```bash
cd webapp
python audit_source.py --days 30
```

Or run GitHub Actions **Audit EMS source data** → **Run workflow** → `main` → `30`. The workflow produces an aggregate-only JSON artifact and prints totals for repeated source call numbers, multiple unit callsigns, and recent daily counts. An identifier appearing more than once does **not** prove duplicates are errors: a single incident may produce more than one unit-level record. The audit is diagnostic, not a deduplication rule.

The source can publish or correct historical records after their dispatch date. A sharp fall in the latest daily source records must not be claimed to represent an actual fall in emergency activity without validation. The daily importer refreshes only the latest 30 days by default; if source corrections arrive later, operators may need a wider backfill.

### Identifier reuse by date

The source audit also reports how many EMS call numbers appear on different Cleveland-local dispatch dates, how many span seven or more calendar days, and distinct *call numbers per day* (not unique incidents). Call numbers occurring on widely separated dates must not be interpreted as one continuous emergency. Repeated call-number + unit + dispatch-date groups are diagnostic and do not necessarily represent incorrect duplicate rows. The audit outputs aggregate counts only, not identifiers.
