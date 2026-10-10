# Cleveland EMS Analytics

<img width="2834" height="1494" alt="image" src="https://github.com/user-attachments/assets/0af9715e-28b3-44bd-8b8c-d9b39f9e0054" />


**A deployed, end-to-end public-data analytics application built with Python, FastAPI, PostgreSQL, and automated ingestion.**

[**Explore the live dashboard ↗**](https://cleveland-ems-analytics.onrender.com/) · [FastAPI API docs](https://cleveland-ems-analytics.onrender.com/docs) · [View source data](https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6)

> **Independent educational project.** Not affiliated with or endorsed by Cleveland EMS. It analyzes published records, **not verified unique emergency incidents**. Call-to-event time intervals are exploratory and should not be interpreted as official EMS response-time performance measures.

## What it does

An interactive dashboard for exploring the City of Cleveland's published emergency medical services data:

- **Time filters:** past day, 7 days, 30 days, 3 months, 1 year, all imported records, or a custom date range.
- **Priority filters:** explore published priority codes independently or together.
- **Operational trends:** daily dispatch records, priority mix, and dispatch records by Cleveland-local hour.
- **Timing analysis:** median call-to-dispatch and call-to-on-scene intervals for records with valid timestamps.
- **Geographic overview:** official Cleveland neighborhood boundaries, shown as a clean vector map.
- **Data freshness:** the date of the most recent successful import and the newest dispatch timestamp in the database.

The application runs publicly on **Render** and stores data in **Neon PostgreSQL**. **GitHub Actions** retrieves newly published source rows each day, upserting by source `OBJECTID` so reruns don't create extra copies of existing source rows.

## Architecture

```text
City of Cleveland ArcGIS REST API
              |
         Python importer
      (requests + SQLAlchemy)
              |
      Neon PostgreSQL database
              |
           FastAPI
   /api/summary | /api/areas
              |
  HTML/CSS + Chart.js + Leaflet
              |
        Render web service

GitHub Actions --> daily ingest + automated tests
```

**Technical stack:** Python 3.12 · FastAPI · SQLAlchemy · PostgreSQL (Neon) · Render · GitHub Actions · pytest · Chart.js · Leaflet · HTML/CSS/JavaScript · ArcGIS REST API.

## Live application

**[Open Cleveland EMS Analytics](https://cleveland-ems-analytics.onrender.com/)**

The dashboard provides real, date-filterable published-data analysis. Render's free tier can temporarily spin down when idle, so the first request after inactivity may take longer.

Useful endpoints:
- [`/health`](https://cleveland-ems-analytics.onrender.com/health) — application readiness
- [`/api/summary`](https://cleveland-ems-analytics.onrender.com/api/summary) — aggregated public statistics
- [`/api/neighborhood-boundaries`](https://cleveland-ems-analytics.onrender.com/api/neighborhood-boundaries) — neighborhood outlines
- [`/docs`](https://cleveland-ems-analytics.onrender.com/docs) — automatically generated FastAPI documentation

## Why the numbers are labeled “published records”

Real-world EMS source data has a nontrivial record structure. A 30-day **read-only source audit** found approximately 30,000 source rows but far fewer distinct `EMS_Call_Number` values; many rows shared the same call number, unit callsign, and dispatch timestamp. Distinct source rows are not necessarily distinct emergency incidents.

Rather than silently deleting records or publishing an unsupported count of “unique emergencies,” the dashboard transparently reports **published dispatch records**. The most recent days may also be incomplete or revised later by the publishing system. These limitations are called out directly on the dashboard.

**Map limitations:** The EMS data does not provide a validated neighborhood identifier or incident point geometry. The vector map displays official neighborhood boundaries, **not** verified incident hotspots. The application deliberately keeps neighborhood-level EMS counts unavailable until validated matches are obtained; gray means unavailable, not zero.

**Privacy:** Public endpoints serve aggregates and neighborhood outlines, never raw incident locations, record identifiers, or unit-level detail. Geographic area aggregates have a minimum reporting threshold.

## Run locally (FastAPI application)

```bash
git clone https://github.com/Rousan21/cleveland-ems-analytics.git
cd cleveland-ems-analytics/webapp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Local development uses SQLite if EMS_DATABASE_URL is not configured.
python ingest.py --days 30
uvicorn main:app --reload
```

Visit **http://127.0.0.1:8000**. Run `pytest -q` from `webapp/` to execute the test suite. Source data collection requires an internet connection.

To use PostgreSQL, set `EMS_DATABASE_URL` in your environment to a secure database connection string. Never commit credentials or a populated `.env` file.

## Repository layout

```text
webapp/                    FastAPI app, analytics, ArcGIS ingest and tests
  main.py                  Routes and HTML frontend
  analytics.py             Date-filtered public metrics
  ingest.py                Idempotent source-row upsert
  geography.py             Neighborhood boundaries and safe aggregates
  audit_source.py          Read-only, aggregate data-quality diagnostics
  templates/ + static/     Dashboard interface and charts
  tests/                   Automated tests
.github/workflows/
  ci.yml                   Test on pushes and pull requests
  daily-ems-sync.yml       Scheduled database updates
  audit-ems-source.yml     On-demand public-source diagnostic
render.yaml                Render web-service configuration
app.py / src/ / sql/       Original Streamlit/SQLite prototype
```

The original Streamlit prototype is preserved in the repository as an earlier version; **the public demo is the FastAPI app in `webapp/`**.

## Design choices and engineering highlights

- Chose a **separate hosted database** to preserve records across free-tier web-service restarts.
- Built a **paged ArcGIS ingest** with retry-safe upserts keyed on published `OBJECTID`.
- Handled **time-zone-aware date windows** and computed timing statistics only where timestamps support them.
- Exposed aggregate-only API endpoints and avoided unvalidated incident-level mapping.
- Added **continuous integration and scheduled updates** while keeping secrets in deployment and GitHub settings.
- Validated the source’s repeated identifiers and disclosed data uncertainty rather than exaggerating emergency or hotspot counts.

## Further enhancements

Potential extensions include expanding the historical backfill after checking free-tier storage, validated geographic joins for neighborhood totals, and historical monitoring of source publication delays. These are future enhancements rather than requirements for running the public dashboard.

**Data source:** [City of Cleveland Division of EMS — ArcGIS](https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6).

---

*Created as a practical software-engineering and data-systems project combining public safety experience with backend development, cloud deployment, and real-world data quality.*
