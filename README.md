# Cleveland EMS Analytics

**A source-verified, interactive public-data explorer of emergency medical services activity in Cleveland, Ohio.**

[Explore the v6 preview](https://dashboard-v6-real-cleveland.cleveland-ems-explorer.pages.dev/) · [Official City of Cleveland dataset](https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6) · [Source code and setup](webapp/) · [GitHub Actions](https://github.com/Rousan21/cleveland-ems-analytics/actions)

![Cleveland EMS geographic explorer — source-matched neighborhoods](assets/dashboard.png)

*The interactive geographic explorer: Cleveland neighborhoods shaded by published EMS record volume, with rankings and geographic match coverage.*

## Why this project exists

Public emergency-services records can help answer **where activity is concentrated, which situations are commonly recorded, and when activity occurs**. But raw counts can easily mislead: the source city, geographic labels, publication timing, and record definitions all matter.

I built Cleveland EMS Analytics as a practical, end-to-end data project: from public ArcGIS ingestion and PostgreSQL storage to interactive geographic exploration, evidence-led charts, and explicit uncertainty.

## What you can explore

| Question | What the dashboard shows |
| --- | --- |
| **Where is published activity concentrated?** | Cleveland neighborhood choropleth, top-ten list, selected area counts and leading reportable incident category |
| **What kinds of calls appear most often?** | Top-eight recorded **dispatch classifications**, shown as readable horizontal bars with counts and shares of all selected records |
| **When are calls recorded?** | A complete-local-day trend and hour-of-day distribution |
| **Are patients transported or units dispatched?** | Source-based transport and dispatch indicator percentages calculated only among known values |
| **How do filters affect the data?** | Six preset date windows, a source-driven selector for the ten most frequent incident types, and aggregate-only daily CSV export |
| **What should a visitor make of the numbers?** | Area rankings, the incident-type distribution, and daily/hourly patterns directly reflect the selected filters |
| **How reliable is this particular view?** | Source-data validation is enforced in the export pipeline, not shown as a large public-facing statistics panel |

![Top dispatch classifications and their shares of Cleveland EMS records](assets/incident-types.png)

*The citywide incident-type chart appears with All incident types. Selecting one of the ten most frequent source classifications filters the map, daily trend and metrics together. Selecting a neighborhood instead updates the map's geographic detail, not the citywide charts. Labels reflect dispatch-time classifications, **not medical diagnoses**.*

## Example finding: dispatch classifications and time of day

To demonstrate an analytical question beyond a dashboard screenshot, I queried **29 complete Cleveland-local days (October 17–November 14, 2026)** and examined the `OVERDOSE / POISONING (INGESTION)` **dispatch classification**. The question was whether its share of all published EMS records varied across the day.

| Cleveland-local incident time | Records classified overdose/poisoning | All published EMS rows | Share of rows |
| --- | ---: | ---: | ---: |
| 6:00–11:59 a.m. | 40 | 2,317 | 1.7% |
| 6:00–11:59 p.m. | 93 | 2,614 | 3.6% |

**Observation:** The evening share was approximately twice the morning share (3.6% vs. 1.7%) in this 29-day snapshot. Across the full day, **260 of 9,560** published rows had this classification.

**Why it matters:** This suggests a focused research question: *Does this difference persist across longer periods, weekdays versus weekends, and seasons?* A public-health analyst could investigate further before proposing any intervention.

**Limits:** This is the *dispatch-time label*, not a confirmed medical diagnosis, unique-patient count or direct measure of overdose incidence. The selected period is short; reporting practices and other factors may affect the pattern. It is **not** evidence of a cause or a basis for staffing changes.

The website remains focused on **where, what, and when**. This worked example belongs in the case study, not as another public-facing chart.

## Source, integrity and definitions

- **Authoritative source:** City of Cleveland, Ohio, [`CAD_EMS_Public` ArcGIS table](https://services3.arcgis.com/dty2kHktVXHrqO8i/ArcGIS/rest/services/data/FeatureServer/0), item `d5d71757cc73400d843c98bcb46e46b6`. Imports reject rows whose `city` field is not Cleveland and check expected source fields before writing.
- **Published records ≠ unique emergencies:** one row is not independently verified as one incident or patient. Counts are descriptive, not a measure of incidence, ambulance demand, or response performance.
- **Geography:** source-provided neighborhood labels are matched case-insensitively to official Cleveland GIS polygons. Unmatched records are excluded from mapped counts, match coverage is published, and area/category cells below **11** are withheld.
- **Incident classifications:** `IncidentTypeDescription` reflects the situation as understood at dispatch time; it is not a confirmed diagnosis.
- **`NO DISPATCH` is a separate source classification, not a substitute for `isDispatch=false`.** A direct audit of imported Cleveland records found `NO DISPATCH` on records with both true and false dispatch indicators. The dataset does not establish why those values differ, so selecting this category displays a short caution instead of making unsupported assumptions about ambulance response.
- **Dispatch and transport:** the City's field metadata defines `isDispatch=true` as one or more units dispatched, and `isTransport=true` as an incident resulting in patient transport. Neither gives the number of unique patients, units, hospital admissions, or a response-time measurement.
- **Priorities:** The raw source has priority codes 1–7, but their meanings are not all documented. They remain accessible as underlying data, not a prominent public filter.
- **Publication dates:** a rolling window begins mid-day. Partial boundary dates are excluded from the **comparative daily chart** but retained in headline totals and CSV. Even complete older dates may later be revised.

## Architecture

```text
        City of Cleveland ArcGIS CAD_EMS_Public
                         │
              Schema + city validation
                         │
              Python incremental importer
                  ObjectId upserts
                         │
                Neon PostgreSQL
           cleveland_ems_records
                         │
          Python aggregate & area summaries
                  │               │
     Official Cleveland     6 date windows ×
     neighborhood polygons 11 incident choices
                  │               │
                  └───────┬───────┘
                          ▼
            Privacy-thresholded JSON
                          │
                   Cloudflare Pages
            Leaflet map · category bars
             daily/hourly charts · CSV

     GitHub Actions = tests + source QA + scheduled sync
     FastAPI = optional Cleveland-only aggregate API
```

**Stack:** Python 3.12, SQLAlchemy, PostgreSQL/Neon, FastAPI, GitHub Actions, Cloudflare Pages, JavaScript, Chart.js, Leaflet and ArcGIS REST.

Static builds precompute **66 date/incident selections** to avoid repeated database queries on each click. The browser receives aggregates and public neighborhood polygons—no individual EMS records, patient addresses, source incident IDs, or database secrets.

## Engineering decisions and lessons

**Fixing source provenance.** An audit exposed that a previous prototype had unintentionally used **Virginia Beach, Virginia** EMS data. I replaced its source with Cleveland's official feed, added independent Cleveland tables, and introduced checks that prevent incompatible data from being published. The old database records remain isolated for historical testing.

**Removing misleading trends.** Partial first/current days created apparent dramatic declines in a rolling 30-day graph. The dashboard now plots comparable complete Cleveland-local dates while disclosing excluded dates and preserving full-period totals.

**Making the map robust.** The interface uses verified neighborhood labels and polygons, keeps GIS matching available as a small source note, suppresses small-area cells, and is tested in a real browser. Serving Leaflet styles locally also resolved a real CSS/CDN issue that distorted the map.

**Choosing useful metrics.** Unsupported legacy response-time medians and a lower-value priority doughnut were removed. The interface now prioritizes **where, what, and when**, including the leading source incident classifications.

**Data quality is verified behind the scenes.** Every filter is checked for consistent citywide and geographic totals, field-value completeness, and source provenance. These tests run during deployment rather than cluttering the public dashboard with technical diagnostics.

**Fail-closed export checks.** Before publishing each of the 66 snapshots, the exporter verifies that citywide daily/hourly/priority totals reconcile, top-category counts do not exceed the total, record-quality denominators are valid, and geographic matched/unmatched totals reconcile with the same selection. Contradictory snapshots are rejected rather than deployed.

## Run it locally

```bash
git clone https://github.com/Rousan21/cleveland-ems-analytics.git
cd cleveland-ems-analytics
git switch dashboard-v6-real-cleveland-data  # until PR #10 is merged
cd webapp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python cleveland_pipeline.py sync --days 30
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000` or `http://127.0.0.1:8000/docs`. A local SQLite DB works without credentials; set `EMS_DATABASE_URL` to use your own Neon PostgreSQL database. See [webapp/README.md](webapp/README.md) for detailed commands. Import a longer history to populate the year/all-imported presets.

```bash
pytest -q
node --check static/dashboard.js
node --check static/v6.js
python audit_cleveland_source.py
python audit_map_geometry.py
```

CI additionally runs a headless Chrome check for desktop/mobile map sizing, geographic interaction, daily-chart boundaries and recorded-category rendering.

## Next improvements

The public interface now emphasizes incident types, geography, and daily/hourly trends; verbose evidence-quality panels were removed to make the project easier to explore. The next priorities are **automated alerts for failed or anomalous imports**, a concise **first-time visitor walkthrough**, and **measured performance and update-reliability results**. These would strengthen the site without unnecessary charts or a neighborhood-comparison feature.

---

**Independently designed and developed by Adam Al-Rousan.** Not affiliated with or endorsed by the City of Cleveland or its EMS division. Exploratory public-data analysis, not a live dispatch monitor or a basis for emergency-resource deployment.
