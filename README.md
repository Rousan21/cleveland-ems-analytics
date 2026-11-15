# Cleveland EMS Analytics

**An independent, end-to-end public safety analytics project built with Python, SQL, FastAPI, Neon PostgreSQL, automated data ingestion, Cloudflare Pages, Chart.js and Leaflet.**

**[Live Cloudflare dashboard](https://cleveland-ems-explorer.pages.dev/)** · [Official Cleveland EMS dataset](https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6) · [FastAPI documentation](https://cleveland-ems-analytics.onrender.com/docs)

> **Important release note:** The live site may still show an older archived prototype until the v6 source-correction PR is merged and deployed. The v6 branch is the accurate Cleveland-only implementation; do not quote older website statistics as Cleveland results.

## The problem

Public EMS data can answer useful questions—but only if data provenance, geography, and definitions are sound. A useful dashboard should help people examine:

- **Which Cleveland neighborhoods have higher published EMS record counts?** An interactive choropleth shades Cleveland neighborhoods using the source-provided neighborhood field. A ranked list and details panel show count, rank, share and data-matching coverage.
- **When does activity occur?** Compare published rows by day and Cleveland-local incident hour for six preset time windows.
- **How do categories differ?** Filter the source priority codes (1–7), compare priority mix and view the most common incident type.
- **How often are records marked dispatched or transported?** Compute proportions **only among rows with an explicit known flag**.

These are **descriptive, exploratory metrics**, not official ambulance performance statistics or emergency-deployment recommendations.

## Official Cleveland data—not another city's data

**The v6 dashboard uses this exact authoritative ArcGIS item:**

- **Publisher:** City of Cleveland, Ohio, Division of Emergency Medical Service (EMS).
- **ArcGIS item:** [EMS Calls for Service, `d5d71757cc73400d843c98bcb46e46b6`](https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6)
- **Service:** [`CAD_EMS_Public` table](https://services3.arcgis.com/dty2kHktVXHrqO8i/ArcGIS/rest/services/data/FeatureServer/0)
- **Available attributes:** `ObjectId`, `IncidentDate`, `city`, `neighborhood`, `census_tract`, `CurrentPriorityKey`, `IncidentTypeDescription`, `isDispatch`, and `isTransport`.

A source-validation check confirms the expected fields. The importer accepts **only** records with `city = Cleveland` (case-insensitive) and a valid incident timestamp. It stores no incident number, patient information, or precise call address.

**Source correction:** The earlier v2/v3 portfolio prototype inadvertently ingested records from **Virginia Beach, Virginia** into `ems_calls_v2`. An independent database audit caught this mismatch. The v6 pipeline uses separate `cleveland_ems_records` and `cleveland_ems_sync_runs` tables, and the public exporter refuses to publish data without the exact Cleveland ArcGIS source ID. The previous code and table are kept isolated for historical regression testing and are **not** used for the new dashboard. Existing legacy records are not deleted by this migration.

## The geographic explorer

A **source-first geographic join** is possible because official Cleveland CAD records already contain a neighborhood label:

1. Ingest the source-provided neighborhood names from Cleveland records.
2. Retrieve Cleveland GIS neighborhood boundary polygons.
3. Match names case-insensitively; **do not guess** mismatched names.
4. Count published rows by neighborhood for the selected period and source priority code.
5. Suppress area cells smaller than 11.
6. Map only reportable aggregates; publish an exact match-coverage percentage, matched/unmatched totals and the top 10 ranked neighborhoods.

The map and ranking show **raw published record counts**, not unique emergencies, per-resident incidence, disease risk, ambulance demand, or measured service coverage. Areas with unavailable/suppressed counts do not mean zero calls.

## Data pipeline

```text
Official City of Cleveland CAD_EMS_Public
                |
      GitHub Actions importer
    source ID + schema checks
    city="Cleveland" required
                |
      Neon PostgreSQL (v6)
     cleveland_ems_records
       (no incident IDs)
                |
      Python aggregation
  6 time windows × 8 priority filters
                |
    Public summary JSON +
  validated neighborhood GIS
                |
         Cloudflare Pages
   Leaflet / Chart.js / JS / CSS
                |
     Browser: map + rankings

Optional FastAPI endpoint: identical Cleveland-only summary and area aggregations.
Historical v2/Virginia Beach modules and tables remain archived, not displayed.
```

The deploy exports **48 exact preset filter combinations**, calculated from the same fixed UTC timestamp for a consistent snapshot. GitHub Actions refreshes recent records daily, using idempotent `ObjectId` upserts. The first bootstrap imports a longer historical window; `All imported` means the records currently stored in Neon, **not all years in the source**.

No database credentials or individual EMS records are delivered to browsers. Custom date filtering is temporarily disabled in the Cloudflare UI during the verified-source migration; the FastAPI interface supports custom dates after its corrected deployment.

## Real-world engineering and testing

- Python/SQL ETL with ArcGIS keyset pagination, schema/municipality validation and upserts.
- Neon PostgreSQL persistent storage and isolated source-specific tables.
- Date handling in `America/New_York` with UTC source timestamps.
- Responsive dark dashboard, interactive Leaflet choropleth, ranked area selection and CSV export of daily **aggregate counts only**.
- Geographic name-matching and privacy suppression for small cells.
- pytest covers source provenance, cross-city rejection, idempotency, API behavior, geographic matching and exported asset safety; GitHub Actions checks JavaScript syntax.
- Cloudflare static deployment keeps routine filtering fast without a sleeping Python instance.

Local tests:

```bash
cd webapp
pip install -r requirements.txt
pytest -q
node --check static/dashboard.js
node --check static/v6.js
```

The source-check diagnostic can be run manually with `python audit_cleveland_source.py`, using only the public ArcGIS API. A Neon URL goes in `EMS_DATABASE_URL` as a GitHub secret or environment variable—never committed.

## Interpretation and limitations

- **Published records are not independently verified unique emergency incidents.** One incident may generate multiple rows; do not report the count as patients or ambulance deployments.
- **Priority codes 1–7** are reproduced from the source. Their clinical meanings are not guessed.
- **Dispatch/transport flags** indicate source classifications. The Cleveland feed does **not** include the call-to-dispatch and on-scene timestamps used in the archived prototype; the v6 site correctly removes those interval metrics.
- **Geographic rankings** include only records whose source neighborhoods match the known GIS boundary labels. Coverage is shown so visitors can judge how representative a ranking is.
- **Recent-day counts** may be incomplete or revised later. The site does not claim a specific reporting lag without measurement.
- **Raw counts are not risk rates:** differences in population, visitor activity and land use affect comparisons. A future population-adjusted view would need carefully matched, credible denominators.
- **No patient-level maps:** individual incident points and addresses are never distributed.

## Roadmap

The most compelling future extensions are: year-over-year **same-season** comparisons, validated population-normalized geographic rates, testable associations between recorded incident categories and time-of-day patterns, and verified area coverage auditing. A benchmarked deployment-performance comparison would also strengthen engineering claims. Forecasting or resource optimization should come **only after** evaluating data completeness, bias, leakage and appropriate operational ground truth.

---

Independent portfolio project developed by **Adam Al-Rousan**. Not affiliated with or endorsed by the City of Cleveland or its Division of EMS. Data is provided by the City's ArcGIS public-data service. Public-data limitations and updates remain subject to the City's own terms and disclaimers.
