/* v4 interpretation layer. Runs after dashboard.js; uses only aggregate data.
   No individual incident rows, geocoding, or unsupported hotspot claims. */
(() => {
  'use strict';

  const byId = id => document.getElementById(id);
  const numeric = x => Number(x ?? 0);
  const fmt = x => numeric(x).toLocaleString('en-US');
  const weekday = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  let selectedNeighborhood = '';
  let latestHistory = null;

  function selectedDateLabel(iso) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || '')) return 'unknown date';
    return new Date(iso + 'T12:00:00Z').toLocaleDateString('en-US',
      {timeZone: 'UTC', month:'short', day:'numeric', year:'numeric'});
  }

  function olderRecords(data) {
    const cutoff = data.publication_caution_start || '9999-12-31';
    return (data.daily || []).filter(day => day.date < cutoff && numeric(day.count) >= 0);
  }

  function topHistoricalWeekday(data) {
    const older = olderRecords(data);
    // Require at least 2 observed historical dates per weekday for interpretation.
    if (older.length < 21) return null;
    const sums = Array(7).fill(0), samples = Array(7).fill(0);
    for (const day of older) {
      const index = new Date(day.date + 'T12:00:00Z').getUTCDay();
      if (!Number.isInteger(index)) continue;
      sums[index] += numeric(day.count);
      samples[index] += 1;
    }
    const ranked = samples.map((n, i) => ({day:weekday[i], n, mean:n ? sums[i] / n : 0}))
      .filter(v => v.n >= 2).sort((a,b) => b.mean - a.mean);
    return ranked.length === 7 ? ranked[0] : null;
  }

  function renderGuidance(data) {
    const older = olderRecords(data);
    const rowSeries = Array.isArray(data.daily) ? data.daily : [];
    const recent = rowSeries.filter(v => data.publication_caution_start &&
      v.date >= data.publication_caution_start);
    const latest = rowSeries[rowSeries.length - 1];
    const baseline = older.slice(-28);
    const baselineMean = baseline.length >= 7
      ? baseline.reduce((n, row) => n + numeric(row.count), 0) / baseline.length : null;

    const peakWeekday = topHistoricalWeekday(data);
    if (peakWeekday && baselineMean !== null) {
      byId('brief-title').textContent = `${peakWeekday.day}s show higher average published activity`;
      byId('brief-detail').textContent =
        `Across the earlier observed dates in this selection, ${peakWeekday.day}s averaged ${fmt(Math.round(peakWeekday.mean))} published dispatch rows. This can guide which historical periods to investigate—not staffing decisions or forecasts.`;
    } else if (numeric(data.records) > 0) {
      byId('brief-title').textContent = 'Explore activity patterns with historical context';
      byId('brief-detail').textContent =
        'This selection has too few earlier observed dates for a weekday comparison. Try 90 days or All imported, then compare the recorded dispatch hours and source priority mix.';
    } else {
      byId('brief-title').textContent = 'No published dispatch rows for this selection';
      byId('brief-detail').textContent =
        'Choose a broader date range or different source priority code before interpreting activity patterns.';
    }
    byId('brief-caveat').textContent =
      'Interpretation uses published dispatch rows; weekday comparisons exclude the latest seven Cleveland-local calendar dates as a caution, not a measured completeness threshold.';

    const chartKey = document.querySelector('.chart-key');
    if (chartKey) chartKey.hidden = recent.length === 0;
    if (recent.length && latest && latest.date >= data.publication_caution_start) {
      byId('trend-warning').textContent =
        `The dashed right-hand segment covers the most recent seven Cleveland-local calendar dates (beginning ${selectedDateLabel(data.publication_caution_start)}). That seven-day marker is a caution heuristic, not proof of delayed records. Earlier dates may also be revised. Do not mistake fewer published rows for fewer emergencies.`;
    } else {
      byId('trend-warning').textContent =
        'Dates in this historical selection can still be revised by the source. Published dispatch rows are not verified distinct emergencies.';
    }

    if (!recent.length || !latest) {
      byId('recent-count').textContent = 'Outside this range';
      byId('recent-context').textContent =
        'The selected range does not include the current seven-calendar-day reporting caution window. Choose 30 days to inspect the recent decline.';
    } else {
      byId('recent-count').textContent = `${fmt(latest.count)} rows`;
      if (baselineMean !== null && baselineMean > 0) {
        const difference = Math.round((1 - numeric(latest.count) / baselineMean) * 100);
        const comparison = difference >= 0
          ? `${difference}% below` : `${Math.abs(difference)}% above`;
        byId('recent-context').textContent =
          `${selectedDateLabel(latest.date)} had ${fmt(latest.count)} published rows, ${comparison} the average (${fmt(Math.round(baselineMean))}) of ${baseline.length} earlier observed dates. This is a publication comparison, not an observed change in emergency demand.`;
      } else {
        byId('recent-context').textContent =
          `Latest recorded date: ${selectedDateLabel(latest.date)}. Choose at least 30 days for comparison with earlier published records.`;
      }
    }
  }

  function historyRow(day) {
    const row = document.createElement('div');
    row.className = 'history-item';
    const name = document.createElement('strong');
    name.textContent = selectedDateLabel(day.date);
    const counts = document.createElement('span');
    counts.textContent = `${fmt(day.first_observed)} → ${fmt(day.latest_observed)}`;
    const delta = document.createElement('span');
    delta.className = 'history-delta ' +
      (day.net_change > 0 ? 'gain' : day.net_change < 0 ? 'loss' : 'same');
    delta.textContent = `${day.net_change > 0 ? '+' : ''}${fmt(day.net_change)} rows`;
    row.append(name, counts, delta);
    return row;
  }

  function renderPublicationHistory(result) {
    const container = byId('history-rows');
    container.replaceChildren();
    if (!result || !result.observations) {
      byId('history-status').textContent = 'Monitoring is starting. No past capture history exists yet.';
      const note = document.createElement('p');
      note.textContent = 'The daily pipeline will start recording citywide counts after deployment. We cannot infer historical backfill from a single snapshot.';
      container.append(note);
      return;
    }
    byId('history-status').textContent =
      `${fmt(result.observations)} observed import snapshot${result.observations === 1 ? '' : 's'} · Last observation ${new Date(result.latest_observation_at).toLocaleDateString('en-US')}`;

    const comparable = [...(result.days || [])].filter(v => numeric(v.samples) >= 2)
      .sort((a,b) => b.date.localeCompare(a.date));
    if (!comparable.length) {
      const note = document.createElement('p');
      note.textContent = 'At least two daily observations of the same dispatch date are needed to measure revisions.';
      container.append(note);
      return;
    }

    for (const day of comparable.slice(0, 6)) container.append(historyRow(day));
    const changed = comparable.filter(v => numeric(v.net_change) !== 0);
    byId('history-footnote').textContent =
      `${changed.length} of ${comparable.length} observed dates changed between first and latest capture. Changes may be positive or negative; no date is certified complete. Counts are citywide and exclude incident details.`;
  }

  async function loadPublicationHistory() {
    if (document.body.dataset.staticSite !== 'true') {
      byId('history-status').textContent = 'The daily change monitor is published on the Cloudflare dashboard.';
      byId('history-rows').textContent =
        'The FastAPI version does not export historical publication snapshots.';
      return;
    }
    try {
      const response = await fetch('/api/publication-history.json');
      if (!response.ok) throw new Error('History is unavailable');
      latestHistory = await response.json();
      renderPublicationHistory(latestHistory);
    } catch {
      byId('history-status').textContent = 'History could not be retrieved.';
      byId('history-rows').textContent = 'The date and priority filters remain available. Please try reloading the dashboard.';
    }
  }

  function selectedLayer() {
    let found = null;
    if (!selectedNeighborhood || !state.mapLayer) return found;
    state.mapLayer.eachLayer(layer => {
      if (layer.feature?.properties?.name === selectedNeighborhood) found = layer;
    });
    return found;
  }

  function updateNeighborhoodCard() {
    const heading = byId('selected-neighborhood-name');
    const description = byId('selected-neighborhood-copy');
    if (!selectedNeighborhood) {
      heading.textContent = 'Select an area on the map';
      description.textContent =
        'Explore an official Cleveland neighborhood boundary. The outlines alone cannot show EMS call locations or hotspot activity.';
      return;
    }
    heading.textContent = selectedNeighborhood;
    const row = state.areaData?.areas?.find(entry =>
      entry.name.toLowerCase() === selectedNeighborhood.toLowerCase());
    if (row) {
      description.textContent =
        `${fmt(row.count)} verified, aggregated published dispatch rows for this area and the selected filters. Small neighborhood totals are suppressed; this is not a unique-incident count.`;
    } else if (state.areaData?.status === 'suppressed') {
      description.textContent =
        'No reportable neighborhood total is shown for this selection: values below the privacy reporting threshold are withheld.';
    } else {
      description.textContent =
        'The boundary is verified, but no validated EMS record-to-neighborhood match is available. Gray does not mean zero calls, and this map is not a hotspot map.';
    }
  }

  function highlightNeighborhood() {
    if (!selectedNeighborhood || !state.mapLayer) return;
    const layer = selectedLayer();
    if (layer) {
      layer.setStyle({color:'#126f82',weight:3.2,opacity:1});
      layer.bringToFront();
    }
  }

  function selectNeighborhood(name, zoom) {
    if (!state.mapLayer) return;
    selectedNeighborhood = name || '';
    const select = byId('neighborhood-select');
    select.value = selectedNeighborhood;
    byId('neighborhood-reset').disabled = !selectedNeighborhood;
    updateMapColors(); // Updates verified totals, then reapplies the active outline.
    updateNeighborhoodCard();
    const layer = selectedLayer();
    if (zoom && layer && state.map) {
      state.map.fitBounds(layer.getBounds(), {padding:[24,24], maxZoom:12});
    }
  }

  function setupMapExplorer() {
    if (!state.mapLayer) return;
    const select = byId('neighborhood-select');
    const names = [];
    state.mapLayer.eachLayer(layer => {
      const n = layer.feature?.properties?.name;
      if (typeof n === 'string' && n.trim()) names.push(n.trim());
    });
    names.sort((a,b) => a.localeCompare(b));
    select.replaceChildren();
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Choose a neighborhood…';
    select.append(placeholder);
    for (const name of [...new Set(names)]) {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      select.append(option);
    }
    select.disabled = false;
    select.addEventListener('change', () => selectNeighborhood(select.value, true));
    byId('neighborhood-reset').addEventListener('click', () => {
      selectNeighborhood('', false);
      state.map.fitBounds(state.mapLayer.getBounds(), {padding:[12,12]});
    });
    updateNeighborhoodCard();
  }

  document.addEventListener('ems:summary', event => renderGuidance(event.detail));
  document.addEventListener('ems:map-ready', setupMapExplorer);
  document.addEventListener('ems:neighborhood-selected', event =>
    selectNeighborhood(event.detail.name, false));
  document.addEventListener('ems:map-style', highlightNeighborhood);
  document.addEventListener('ems:areas', () => updateNeighborhoodCard());

  // Static summary requests may already be underway while this script loads.
  if (state.currentData) renderGuidance(state.currentData);
  if (state.mapLayer) setupMapExplorer();
  loadPublicationHistory();
})();
