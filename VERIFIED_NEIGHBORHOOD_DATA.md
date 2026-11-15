# Roadmap: verified neighborhood EMS dispatch volumes

## Goal

Show **which Cleveland neighborhoods have the most published EMS dispatch records**
within a selected period, without manufacturing addresses, matching nearby
stations to calls, or presenting misleading counts as incidence or risk.

## What is supported today

- The public City of Cleveland `EMS_Calls_for_Service` ArcGIS layer is a
  **table** (not point geometry).
- Its published fields include `Block_Location`, but the ingested record
  currently has no independently validated neighborhood key or coordinate.
- The database already has a reviewed-assignment table, `ems_verified_areas`,
  and can calculate privacy-suppressed area aggregates from it.
- As of November 15, 2026, the current Neon table contains **zero** reviewed
  EMS row-to-neighborhood assignments. Accordingly, no truthful ranking exists.
- A separate historical national GIS catalog publishes **EMS facility positions** (last edited in 2021), but this is not a verified current City of Cleveland station roster.
  These are not incident locations or demand measures.

## Minimum defensible method

1. **Identify authoritative geography.** Obtain a City-published, validated
   record-to-tract or neighborhood column, or an authoritative block-address
   locator that can reproducibly assign a source location to a census tract or
   Cleveland neighborhood. Check license and permitted use.
2. **Do not equate address-like text with a verified location.** Public
   `Block_Location` values are not inherently reliable geocodes. Review address
   normalization, block-level ambiguity, city jurisdiction, mismatched streets,
   and neighborhoods crossing census-tract boundaries. Never assume that a
   street name or partial address identifies a unique neighborhood.
3. **Quality-assure the join.** Measure the match success rate and mismatch
   types, review a randomized sample against authoritative GIS boundaries, and
   withhold ambiguous points. Keep an audit of the source, transform version,
   manual review and confidence criteria.
4. **Only import validated assignments.** Reuse the existing
   `import_verified_areas.py` workflow to populate only reviewed
   `OBJECTID → neighborhood` pairs. Never export that lookup or individual
   call locations to the frontend.
5. **Report coverage.** Display *eligible source rows*, *rows with reviewed
   area assignments*, and the percentage matched. A small nonrepresentative
   subset cannot justify an all-city "highest demand" ranking.
6. **Protect low counts.** Suppress neighborhood counts below 11; do not expose
   address lists, points, individual source IDs, or filter combinations that
   permit reconstructing small counts.
7. **Compare like with like.** Only compare areas for equivalent time windows
   and documented coverage. Published rows may represent multiple units for
   one emergency; label the values as **published dispatch rows**, never
   unique calls or patient counts.
8. **Provide context when available.** A raw-count ranking is not a
   population-normalized EMS rate. Population, daytime population, age
   structure and geographic area all can affect comparison. Include official
   denominator sources and uncertainty before claiming relative risk.

## Useful v6 map features after validation

- Toggle between *published dispatch rows* and a clearly labeled,
  **population-normalized** statistic if suitable denominators are obtained.
- Area ranking with reported assignment coverage and the chosen time/priority
  filters; reference map shades verified aggregates only.
- Click a neighborhood to inspect its aggregate count, filtered rank and
  percentage of all **verified** rows, with source/caveat tooltips.
- Compare two periods, excluding dates marked provisional, with at-least-11
  suppression for every published cell.
- Show **historical EMS facilities** as an independent geographic reference layer,
  without inferring station service territory or resource availability.

## Data sources

- Official EMS Calls for Service dataset:
  https://www.arcgis.com/home/item.html?id=d5d71757cc73400d843c98bcb46e46b6
- Official ArcGIS EMS data table:
  https://services2.arcgis.com/CyVvlIiUfRBmMQuu/arcgis/rest/services/EMS_Calls_for_Service2/FeatureServer/0
- National historical EMS facility catalog:
  https://services5.arcgis.com/HDRa0B57OVrv2E1q/ArcGIS/rest/services/Emergency_Medical_Service_Stations/FeatureServer/0

Until this validation work is performed, any map coloring neighborhood
polygons by "EMS activity" would be unsupported by this dataset.
