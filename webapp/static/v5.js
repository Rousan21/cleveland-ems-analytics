/* Map-first interactions: authoritative boundaries + public station facilities.
   No raw EMS call coordinates, address inference, or fabricated hotspot claims. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const fmt = n => Number(n ?? 0).toLocaleString("en-US");
  let chosenArea = "";
  let stationGroup = null;
  let stationRows = [];
  let mapReady = false;
  const FALLBACK =
    "Official neighborhood outlines alone do not determine EMS call volume. Verified call-to-neighborhood records are needed for a ranking.";

  function ringContains(point, ring) {
    let inside = false;
    if (!Array.isArray(ring) || ring.length < 4) return false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = Number(ring[i][0]), yi = Number(ring[i][1]);
      const xj = Number(ring[j][0]), yj = Number(ring[j][1]);
      const crosses = (yi > point[1]) !== (yj > point[1]) &&
        point[0] < (xj - xi) * (point[1] - yi) / (yj - yi) + xi;
      if (crosses) inside = !inside;
    }
    return inside;
  }

  function withinGeometry(point, geom) {
    if (!geom || !Array.isArray(geom.coordinates)) return false;
    const polygons = geom.type === "Polygon" ? [geom.coordinates] :
      geom.type === "MultiPolygon" ? geom.coordinates : [];
    return polygons.some(poly => Array.isArray(poly) && poly.length &&
      ringContains(point, poly[0]) &&
      !poly.slice(1).some(hole => ringContains(point, hole)));
  }

  function areaLayer(name) {
    if (!state.mapLayer || !name) return null;
    let selected = null;
    state.mapLayer.eachLayer(layer => {
      if (layer.feature?.properties?.name === name) selected = layer;
    });
    return selected;
  }

  function stationsInArea(name) {
    const layer = areaLayer(name);
    if (!layer) return [];
    return stationRows.filter(s => withinGeometry([s.lon, s.lat], layer.feature.geometry));
  }

  function highlightArea() {
    const layer = areaLayer(chosenArea);
    if (layer) {
      layer.setStyle({color: "#8dfff0", weight: 3, opacity: 1, fillOpacity: .98});
      layer.bringToFront();
    }
    if (stationGroup) stationGroup.bringToFront?.();
  }

  function updateAreaDetails() {
    const total = state.areaData?.areas?.find(r => r.name.toLowerCase() === chosenArea.toLowerCase());
    byId("selected-neighborhood-name").textContent = chosenArea || "Explore an area";
    const description = byId("selected-neighborhood-copy");
    const nearbyStations = stationsInArea(chosenArea);

    if (!chosenArea) {
      description.textContent =
        "Choose a neighborhood boundary to see facilities located inside it. Public station locations do not measure call volume or emergency coverage.";
      byId("geo-next-copy").textContent = stationRows.length
        ? "Click a glowing station marker for its public facility name and address. Call locations are never plotted."
        : "Neighborhood outlines are geographic references. Facility markers appear if the official station layer is available.";
    } else {
      const areaInfo = total
        ? `${fmt(total.count)} verified, aggregated dispatch rows have been assigned to this neighborhood for the selected filters. `
        : "EMS call totals for this neighborhood are not validated or are suppressed. Gray does not mean zero. ";
      const stationInfo = stationRows.length
        ? `${fmt(nearbyStations.length)} published EMS station ${nearbyStations.length === 1 ? "location" : "locations"} fall within its mapped boundary.`
        : "Station facilities currently unavailable.";
      description.textContent = areaInfo + stationInfo;
      byId("geo-next-copy").textContent = nearbyStations.length
        ? `Facilities inside the mapped boundary: ${nearbyStations.map(s => s.name).slice(0, 8).join("; ")}. Station proximity is not proof of response coverage.`
        : "No public station point was matched inside this boundary; that does not mean it is unserved.";
    }
  }

  function selectArea(name, zoom = false) {
    if (!mapReady) return;
    chosenArea = name || "";
    byId("neighborhood-select").value = chosenArea;
    byId("neighborhood-reset").disabled = !chosenArea;
    updateMapColors(); // Emits ems:map-style to reapply active highlighting.
    updateAreaDetails();
    const layer = areaLayer(chosenArea);
    if (zoom && layer && state.map) {
      state.map.fitBounds(layer.getBounds(), {padding:[24,24], maxZoom: 12});
    }
  }

  function stationMarker(item) {
    const marker = L.marker([item.lat, item.lon], {
      keyboard: true, riseOnHover: true,
      icon: L.divIcon({
        className: "leaflet-div-icon",
        html: '<span class="station-pin" aria-hidden="true"></span>',
        iconSize: [25,25], iconAnchor: [12,12],
      })
    });
    // DOM text, not an interpolated HTML string.
    const popup = document.createElement("div");
    popup.style.minWidth = "140px";
    const name = document.createElement("strong");
    name.textContent = item.name;
    const address = document.createElement("p");
    address.textContent = item.address || "Address not supplied by GIS";
    address.style.marginTop = "7px";
    popup.append(name, address);
    marker.bindPopup(popup, {autoPan: true, maxWidth: 235});
    marker.on("click", () => {
      let found = "";
      state.mapLayer?.eachLayer(layer => {
        if (!found && withinGeometry([item.lon, item.lat], layer.feature?.geometry)) {
          found = layer.feature.properties.name;
        }
      });
      if (found) selectArea(found, false);
    });
    return marker;
  }

  async function populateStations() {
    if (!mapReady || !window.L || !state.map) return;
    if (document.body.dataset.staticSite !== "true") {
      byId("station-count").textContent = "—";
      byId("geo-data-status").textContent = "BOUNDARIES ONLY";
      return;
    }
    try {
      const response = await fetch("/api/ems-stations.json");
      if (!response.ok) throw new Error("Station data not available");
      const data = await response.json();
      if (data.status !== "ready" || !Array.isArray(data.stations)) throw new Error("Stations unavailable");
      stationRows = data.stations.filter(item =>
        typeof item.name === "string" && Number.isFinite(item.lat) && Number.isFinite(item.lon));
      stationGroup = L.layerGroup(stationRows.map(stationMarker));
      if (byId("show-stations").checked) stationGroup.addTo(state.map);
      byId("station-count").textContent = fmt(stationRows.length);
      byId("geo-data-status").textContent = "OFFICIAL GIS";
      updateAreaDetails();
    } catch {
      byId("station-count").textContent = "Unavailable";
      byId("geo-data-status").textContent = "FACILITIES UNAVAILABLE";
      byId("geo-next-copy").textContent =
        "The public station layer could not be loaded. Neighborhood boundaries and call filters are unaffected.";
    }
  }

  function initializeMap() {
    if (!state.mapLayer || mapReady) return;
    mapReady = true;
    const dropdown = byId("neighborhood-select");
    const names = [];
    state.mapLayer.eachLayer(layer => {
      const name = layer.feature?.properties?.name;
      if (typeof name === "string" && name.trim()) names.push(name);
    });
    dropdown.replaceChildren();
    const initial = document.createElement("option");
    initial.textContent = "Explore a neighborhood";
    initial.value = "";
    dropdown.append(initial);
    for (const name of [...new Set(names)].sort((a, b) => a.localeCompare(b))) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      dropdown.append(option);
    }
    dropdown.disabled = false;
    dropdown.addEventListener("change", () => selectArea(dropdown.value, true));
    byId("neighborhood-reset").addEventListener("click", () => {
      selectArea("", false);
      state.map.fitBounds(state.mapLayer.getBounds(), {padding:[15,15]});
    });
    byId("show-stations").addEventListener("change", evt => {
      if (!stationGroup) return;
      if (evt.target.checked) stationGroup.addTo(state.map);
      else stationGroup.removeFrom(state.map);
    });
    updateAreaDetails();
    populateStations();
  }

  function reflectAreaCoverage(result) {
    const matched = result?.mapped_records;
    byId("geo-mapped-count").textContent = Number.isInteger(matched) ? fmt(matched) : "—";
    const isReady = result?.status === "ready" && Array.isArray(result?.areas) && result.areas.length > 0;
    byId("area-ranking-badge").textContent = isReady ? "VERIFIED AGGREGATES" : "VERIFICATION REQUIRED";
    byId("area-ranking-title").textContent = isReady ? "Highest verified area counts" : "Area call-volume ranking";
    if (isReady) {
      const leader = result.areas[0];
      byId("map-explainer").textContent =
        `Among verified, reportable neighborhood assignments, ${leader.name} has the most published rows (${fmt(leader.count)}) for this filter. This is not an adjusted rate per resident or evidence of higher medical risk.`;
    } else {
      byId("map-explainer").textContent = result?.status === "suppressed"
        ? "Verified neighborhood totals are below the privacy reporting threshold (11), so rankings are suppressed."
        : FALLBACK;
    }
    updateAreaDetails();
  }

  function renderInterpretation(data) {
    const count = Number(data.records || 0);
    const best = [...(data.hours || [])].sort((a, b) => b.count - a.count)[0];
    const period = data.window === "all" ? "all imported dates" : data.window;
    const weekdayCaution =
      "Most recent source dates may be incomplete, so compare multiple periods before drawing conclusions.";
    if (!count || !best || best.count <= 0) {
      byId("brief-title").textContent = "No published rows in this selection";
      byId("brief-detail").textContent =
        "Try a wider period or a different source priority code before interpreting activity.";
      byId("brief-caveat").textContent = weekdayCaution;
      return;
    }
    const hour = new Date(Date.UTC(2020,0,1,Number(best.hour))).toLocaleTimeString(
      "en-US",{hour:"numeric",hour12:true,timeZone:"UTC"});
    const share = (100 * Number(best.count) / count).toFixed(1);
    byId("brief-title").textContent = `Dispatches peaked around ${hour} in this selection`;
    byId("brief-detail").textContent =
      `Across ${period}, ${fmt(best.count)} published dispatch records (${share}% of the selection) occurred in this hour of day. Use this to identify a period for closer comparison—not to infer ambulance deployment or capacity.`;
    byId("brief-caveat").textContent = weekdayCaution;
  }

  document.addEventListener("ems:summary", evt => renderInterpretation(evt.detail));
  document.addEventListener("ems:areas", evt => reflectAreaCoverage(evt.detail));
  document.addEventListener("ems:map-ready", initializeMap);
  document.addEventListener("ems:map-style", highlightArea);
  document.addEventListener("ems:neighborhood-selected", evt => selectArea(evt.detail.name, false));

  if (state.currentData) renderInterpretation(state.currentData);
  if (state.mapLayer) initializeMap();
  if (state.areaData) reflectAreaCoverage(state.areaData);
})();
