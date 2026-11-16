# Cleveland EMS neighborhood geography: implemented v6, validation, and future work

## Provenance correction

The old v2/v3 prototype inadvertently used a Virginia Beach EMS feed. The
v6 project connects to the actual **City of Cleveland, Ohio** source:

- [EMS Calls for Service official ArcGIS item](https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6)
- [CAD_EMS_Public table](https://services3.arcgis.com/dty2kHktVXHrqO8i/ArcGIS/rest/services/data/FeatureServer/0)
- [Cleveland GIS neighborhood boundaries](https://services7.arcgis.com/ZodPOMBKsdAsTqF4/ArcGIS/rest/services/Cleveland_Neighborhoods/FeatureServer/147)

Unlike the former non-spatial Virginia Beach records, the Cleveland CAD table
**already includes** a `neighborhood` label and `census_tract` identifier. No
address geocoding or patient-coordinate approximation is required for the
initial neighborhood analysis.

## Implemented in v6

1. New, separate `cleveland_ems_records` table. Archived Virginia Beach rows
   remain isolated; the v6 site refuses mismatched source provenance.
2. Source schema and city validation. Only `city=Cleveland` source records are
   imported, with a valid incident date.
3. Case-insensitive *exact name* match between the official CAD neighborhood
   label and the published Cleveland boundary labels. Ambiguous/unmatched
   labels are **not guessed**.
4. Group by time window, source priority code and neighborhood.
5. Suppress neighborhood count cells below **11**. Export no individual
   records, incident identifiers or patient addresses to Cloudflare.
6. Publish exact mapped/unmapped counts and match-coverage percentage.
7. Interactive ranked top-ten area list, choropleth, area selection and
   context warnings for raw counts.

## Required interpretation

The choropleth ranks **published EMS records**. It does not rank distinct
patients, individual emergency incidents, ambulance availability, response
times, per-capita medical risks, or disease prevalence. Raw area volumes may
reflect population size, daytime visitors, geography and reporting practices.

If the source neighborhood label does not match the GIS polygon's name,
the record is excluded **from the mapped subset** rather than assigned
speculatively. The dashboard discloses mapping coverage.

The source's `CurrentPriorityKey` is a classification code (1–7);
no clinical priority meaning is assigned without source documentation.
`isDispatch` and `isTransport` are source flags, not elapsed-time metrics.

## Next geographic improvements

- **Check neighborhood-name coverage** in the real dataset, and review
  unmatched values against authoritative documentation rather than silently
  normalizing them.
- **Add comparable denominators:** population or daytime-population estimates
  with matched boundaries and years, if an official reliable dataset is
  available. Label population-adjusted statistics separately from raw counts.
- **Compare equivalent time windows** (same months, weekdays, and population
  exposure) with source completeness checks.
- **Show uncertainty and completeness:** count missing neighborhood labels,
  suppressed cells and source edit dates. A top-ten of 50% mapped rows is not
  a definitive citywide top-ten.
- **Geographic type stratification:** compare published incident-type mixes by
  area only after cell-suppression and anti-reconstruction safeguards.

## Important privacy rule

Do not export incident-level addresses, point coordinates, individual source
IDs, or combinations of filters that would reveal suppressed small-cell
counts. Do not infer ambulance station coverage from an unrelated or outdated
national facility catalog. The v6 map prioritizes the actual Cleveland
neighborhood data over station reference markers.
