# Cleveland EMS Analytics

<img width="2834" height="1494" alt="Cleveland EMS Analytics v2 dashboard screenshot" src="https://github.com/user-attachments/assets/0af9715e-28b3-44bd-8b8c-d9b39f9e0054" />

*Screenshot from the earlier v2 interface. The hosted v3 dashboard uses an updated design.*


**A deployed, end-to-end public-data analytics application built with Python, FastAPI, PostgreSQL, and automated ingestion.**

[**Explore the Cloudflare dashboard ↗**](https://cleveland-ems-explorer.pages.dev/) · [Original FastAPI deployment](https://cleveland-ems-analytics.onrender.com/) · [FastAPI API docs](https://cleveland-ems-analytics.onrender.com/docs) · [View source data](https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6)

> **Independent educational project.** Not affiliated with or endorsed by Cleveland EMS. It analyzes published records, **not verified unique emergency incidents**. Call-to-event time intervals are exploratory and should not be interpreted as official EMS response-time performance measures.

## What it does

An interactive dashboard for exploring the City of Cleveland's published emergency medical services data:

- **Time filters:** past day, 7 days, 30 days, 3 months, 1 year, all imported records, or a custom date range.
- **Priority filters:** explore published priority codes independently or together.
- **Operational trends:** daily dispatch records, priority mix, and dispatch records by Cleveland-local hour.
- **Timing analysis:** median call-to-dispatch and call-to-on-scene intervals for records with valid timestamps.
- **Geographic overview:** official Cleveland neighborhood boundaries, shown as a clean vector map.
- **Data freshness:** last successful import, snapshot generation time, and newest published dispatch timestamp.
- **Actionable summaries:** busiest dispatch hour, most common source priority and valid timing-pair coverage for every filtered view.
- **Aggregate export:** download date-level record counts as CSV, without individual incident identifiers or addresses.
- **Publication-history audit:** daily append-only citywide count snapshots show whether previously imported dispatch-date totals have changed after later imports. This observation begins only once the feature is deployed; it cannot infer earlier publication delays.
- **Interpretation guidance:** summaries for older observed weekdays, prominent uncertainty warnings for the newest seven calendar dates, and practical-use guidance that distinguishes exploration from operational recommendations.
- **Neighborhood explorer:** interactive official boundary selection by neighborhood name, without plotting incident locations or inventing an EMS hotspot map.
- **Creator attribution:** discreet website credit with a source-code link.

The public dashboard is served from **Cloudflare Pages** for fast, inexpensive access. **Neon PostgreSQL** stores the source records, while **GitHub Actions** updates and exports privacy-preserving aggregate snapshots daily. The original **Render/FastAPI** deployment remains available for uncommon custom date filters and backend API demonstrations. The importer upserts by source `OBJECTID` to avoid duplicate rows on repeated runs.

## Questions this project helps answer

| Research question | Evidence shown | Important boundary |
|---|---|---|
| Which dispatch hours or weekdays have higher published activity? | Filtered counts, hourly distributions, and historical weekday averages | Published rows are not verified distinct emergencies; the recent seven-calendar-day period is excluded from weekday comparisons as a **caution heuristic**, not a measured completeness threshold |
| Is the latest downward trend reliable? | Successive daily aggregate count snapshots reveal changes to already-imported dispatch dates | Changes may reflect source revisions or importer behavior; a baseline snapshot alone does not establish lag or completeness |
| Can I compare call-to-event timing? | Valid timestamp-pair coverage and exploratory median intervals | These are not official response-time measures or evidence of patient outcomes |
| Where are the records concentrated geographically? | **Not yet answerable** with verified neighborhoods; official boundary reference can be explored | No derived hotspots or neighborhood demand rankings without a validated record-to-area relationship |

The project aims to help visitors identify **which patterns merit investigation** and which conclusions the public data does not yet justify. It does not recommend EMS staffing, identify patient locations, or claim operational improvements.

### How publication-history monitoring works

After each successful daily import, `python webapp/publication_history.py capture` records citywide *published row counts by dispatch date* for a recent calendar window. Each capture is append-only in the Neon `ems_publication_snapshots` table; the Cloudflare export emits only the daily counts and observation dates in `/api/publication-history.json`. A later snapshot can show how a prior date's count changed. **History starts from the first deployed capture, not retroactively**, and observations cannot on their own prove whether source publication delays or ingestion issues caused changes.

## Architecture

```text
City of Cleveland ArcGIS REST API
           |
      Python importer
      (GitHub Actions)
           |
       Neon PostgreSQL
           |
   Python aggregation/export
   (24 preset filter combinations)
           |
     Static JSON snapshots
           |
      Cloudflare Pages
  HTML / CSS / Chart.js / Leaflet
           |
         Browser

Render / FastAPI = custom date ranges + interactive API docs
CI = pytest + JavaScript syntax checks
```

**Technical stack:** Python 3.12 · FastAPI · SQLAlchemy · PostgreSQL (Neon) · Cloudflare Pages · Render · GitHub Actions · pytest · Chart.js · Leaflet · HTML/CSS/JavaScript · ArcGIS REST API.

**Why precompute?** Preset filters load small, cached JSON results rather than waiting for a free-tier Python service to wake up and repeat the same calculations. The database-backed pipeline still performs exact median calculations and enforces geographic reporting thresholds. Snapshots are generated daily, so a "24h" preset reflects the 24 hours ending at the displayed snapshot timestamp, not a continuously moving per-visitor window.

**Careful interpretation:** The highlights summarize **published dispatch records**. They do not claim to count distinct incidents, establish official EMS performance measures or predict future demand. Timestamp completeness reports the fraction of eligible published dispatch records with valid call-to-scene timestamp pairs.

## Engineering changes in v3

- Served the public dashboard as static assets with daily automated deployments, preserving the backend for advanced queries.
- Avoided transferring unused ORM/location columns from PostgreSQL for aggregate statistics.
- Added short-lived browser caching, concurrent aggregate requests, stale-response protection, in-place Chart.js updates and lazy map initialization.
- Added data-quality insight cards and a public, aggregate-only CSV export.
- Added tests for timestamp completeness and static build privacy, plus a JavaScript syntax check in CI.

```bash
cd webapp
pytest -q
node --check static/dashboard.js
```

**Performance claims:** Any published before/after load time should come from reproducible measurement in browser developer tools; the project does not currently claim a measured percentage improvement.

## Live application

**[Open the Cloudflare dashboard](https://cleveland-ems-explorer.pages.dev/)**

The dashboard provides date-filterable, precomputed published-data analysis for standard filters. Custom ranges still use Render/FastAPI, which may experience a free-tier cold start.

Useful endpoints:
- [`/health`](https://cleveland-ems-analytics.onrender.com/health) — FastAPI application readiness
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
  publication_history.py  Daily aggregate publication-count snapshots
  ingest.py                Idempotent source-row upsert
  geography.py             Neighborhood boundaries and safe aggregates
  audit_source.py          Read-only, aggregate data-quality diagnostics
  templates/ + static/     Interactive dashboard, neighborhood selector and reliability explainer
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
