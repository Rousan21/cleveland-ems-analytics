# Cleveland EMS Analytics — application and pipeline

[Project case study and screenshots](../README.md) · [Verified v6 Cloudflare preview](https://dashboard-v6-real-cleveland.cleveland-ems-explorer.pages.dev/) · [Official Cleveland CAD source](https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6)

This folder contains the **Cleveland-only v6 application**: Python ingestion, SQLAlchemy models, geographic aggregation, a FastAPI API, a Cloudflare static exporter, and the Leaflet/Chart.js frontend.

> **Deployment status:** This code is in [PR #10](https://github.com/Rousan21/cleveland-ems-analytics/pull/10) and has not been merged into `main`. The earlier `ingest.py` and `legacy_virginia_beach_api.py` represent an archived **Virginia Beach prototype**, not the current Cleveland data source. Do not use those for a Cleveland import.

## Local setup

```bash
cd webapp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Local SQLite is the default when EMS_DATABASE_URL is unset.
# To use Neon, set EMS_DATABASE_URL to YOUR database connection URI privately.
python cleveland_pipeline.py sync --days 30
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000` or FastAPI documentation at `http://127.0.0.1:8000/docs`.

## Useful commands

```bash
# Import / upsert recent Cleveland CAD records:
python cleveland_pipeline.py sync --days 45

# One-time longer backfill only if Cleveland table is empty:
python cleveland_pipeline.py bootstrap --days 400

# Create 66 static date/incident-type snapshots and public GIS assets:
# Requires EMS_DATABASE_URL for the chosen PostgreSQL database.
python export_static.py --output ../site_build

# Offline tests, JavaScript syntax checks, read-only source and GIS audits:
pytest -q
node --check static/dashboard.js
node --check static/v6.js
python audit_cleveland_source.py
python audit_map_geometry.py
```

## Official source contract

**Source:** [City of Cleveland, Ohio `CAD_EMS_Public` ArcGIS table](https://services3.arcgis.com/dty2kHktVXHrqO8i/ArcGIS/rest/services/data/FeatureServer/0), item `d5d71757cc73400d843c98bcb46e46b6`.

| Attribute | Use |
| --- | --- |
| `ObjectId` | Idempotent upsert key; not exported to browser |
| `IncidentDate`, `city` | Cleveland-local timing and strict jurisdiction validation |
| `neighborhood`, `census_tract` | Geographic context; exact-name matching to Cleveland GIS neighborhood polygons |
| `CurrentPriorityKey` | Preserved source codes for internal provenance and testing; not a public dashboard filter |
| `IncidentTypeDescription` | Dispatch-time category; not a verified medical diagnosis |
| `isDispatch` | City definition: one or more units dispatched when true |
| `isTransport` | City definition: the incident resulted in patient transport when true |

Only minimal analytic fields are stored in `cleveland_ems_records`; `cleveland_ems_sync_runs` separately records source refresh attempts. The source is validated before importing, and the exporter rejects data without the correct Cleveland provenance.

## Aggregation and privacy

- Six time windows × (All types plus ten common source-based incident types) generate **66 precomputed** combinations of citywide counts and area summaries.
- “All incident types” displays the top-eight classification chart. The separate dropdown offers the ten most frequent recorded source types, each of which filters citywide metrics, the map, and daily/hourly trends; categories beyond the top eight remain part of the All-types chart denominator.
- The map uses `neighborhood` labels that match official boundaries; unmatched records are excluded from mapped totals, and the site reports matching coverage.
- Area and neighborhood-category counts under **11** are not exposed as individual cells.
- The daily trend uses complete `America/New_York` calendar days when comparing days; incomplete rolling-window boundary dates remain in KPIs and daily CSV.
- `record_quality` reports count-based field availability (coded incident types, known flags, labeled neighborhoods) for the exact selected filter. Those quality counts are checked internally and are no longer presented as a large public-facing panel; the percentages **do not certify completeness of the City's published feed**.
- The GIS match percentage is calculated separately from the area summary, as `mapped_records / eligible_records`; geographic findings are restricted to the matched subset.
- Export validation refuses a build when `daily`, `hours` or `priorities` sums disagree with `records`, when top category totals or quality counts exceed their denominators, or when geographic mapped and unmapped counts do not reconcile with citywide totals.
- Source records are **not** independently verified unique emergency incidents. No patient addresses, incident IDs, or individual call coordinates reach the frontend.
- Transport and dispatch indicators do not independently measure the number of patients, units, hospital admissions, or emergency response time.

## Validation

`pytest -q` covers source-city and schema guards, idempotency, APIs, privacy thresholding, geographic joins, aggregate filters and snapshot assets. GitHub Actions runs additional source and polygon checks and a headless desktop/mobile Chrome review of the deployed preview, including the map, the call-type selector and daily trend endpoints.

Cloudflare Pages serves only snapshots and frontend files. The database URI and Cloudflare deployment credentials are stored in GitHub Actions secrets, not in the codebase. Static preview deployments remain separate from production until the PR is merged.
