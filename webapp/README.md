# Cleveland EMS Analytics — FastAPI Web Application

**[Live website](https://cleveland-ems-analytics.onrender.com/)** · [Repository overview](../README.md)

This `webapp/` directory is the deployed Python FastAPI application. Its public frontend uses HTML/CSS/JavaScript, Chart.js, and a tile-free Leaflet vector map. `SQLAlchemy` supports SQLite for local testing and Neon PostgreSQL for public hosting. The original Streamlit prototype remains at the repository root.

## Local development

From the `webapp/` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python ingest.py --days 30
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000` and the OpenAPI page at `http://127.0.0.1:8000/docs`. The default local database is SQLite at `data/ems_v2.db`. The `ingest.py` script fetches paginated source records; `--days 30` refreshes the recent window and `--all` requests all available source history. An `OBJECTID` upsert means the same source row won't be inserted twice by rerunning the importer.

To connect to PostgreSQL, set `EMS_DATABASE_URL` in the application process environment, using a standard Neon connection URL. Keep database passwords in a private environment variable, not committed files.

## Deployment

The deployed project uses:

- Render (free Python web service), configured from the GitHub repository with root directory `webapp`.
- Neon PostgreSQL, configured through Render environment variable `EMS_DATABASE_URL`.
- GitHub Actions workflow `daily-ems-sync.yml` to import a rolling 30-day source window each day with the GitHub repository secret `EMS_DATABASE_URL`.
- `ci.yml` for tests on commits and pull requests.

The repository-level `render.yaml` provides a corresponding example service configuration. The free web service may sleep while idle; no persistent database records are stored on Render's temporary filesystem. Follow `../DEPLOY_RENDER_NEON.md` for initial setup steps.

## Source-data interpretation

The dashboard intentionally counts **published dispatch records** and does *not* claim these equal independent emergency incidents. The public ArcGIS table contains `EMS_Call_Number` and `Unit_Callsign` in addition to `OBJECTID`. A diagnostic audit found many different source rows sharing call/unit/dispatch-time identifiers. Some recent days also contain fewer published source rows; reporting lag or corrections remain possible.

Read-only diagnostics:

```bash
python audit_source.py --days 30
```

Or use GitHub Actions **Audit EMS source data** with a chosen date window. Audit output contains only aggregate statistics, not individual source IDs or addresses. The audit never connects to Neon or edits the database.

The neighborhood map uses the city’s [official neighborhood boundary layer](https://services7.arcgis.com/ZodPOMBKsdAsTqF4/ArcGIS/rest/services/Cleveland_Neighborhoods/FeatureServer/147) as a geographic reference. EMS source rows do not carry a validated neighborhood/point assignment. The app must not display area-specific EMS call totals until independently verified assignments are available. Area totals below 11 records are suppressed.

Public analytics uses time-zone-aware date filtering (Cleveland local time), median call-to-dispatch and call-to-scene intervals where both timestamps are valid, and aggregated daily, hourly and priority statistics. These are exploratory measures, **not official response-time performance statistics**.

## Tests

```bash
pytest -q
```

Tests cover date handling, APIs, source-data auditing, geography/privacy guards, and import logic using mocked external services. Actual ArcGIS availability and rendering should still be validated in a live browser.

**Data source:** [City of Cleveland Division of EMS — ArcGIS](https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6).
