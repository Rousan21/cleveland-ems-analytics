/* Tiny browser layer: Python handles queries/aggregation, Chart.js handles presentation. */
const state = { window: '30d', priority: 'all', charts: {}, areaData: null, mapLayer: null, map: null, requestId: 0, cache: new Map(), currentData: null };
const $ = id => document.getElementById(id);
const staticSite = document.body.dataset.staticSite === 'true';
const fallbackApi = 'https://cleveland-ems-analytics.onrender.com';

// Cloudflare serves exact daily precomputed snapshots for preset date windows.
// Arbitrary custom ranges retain the original FastAPI API (and its cold-start).
function apiUrl(kind, params) {
  if (!staticSite) return `/api/${kind}?${params}`;
  if (state.window === 'custom') throw new Error('Custom ranges are unavailable during the Cleveland source migration.');
  return `/api/${kind}/${state.window}/${state.priority}.json`;
}
const number = n => Number(n ?? 0).toLocaleString('en-US');
const minutes = n => n == null ? 'N/A' : `${n.toFixed(1)} min`;
const dateString = iso => iso ? new Date(iso).toLocaleString('en-US', {dateStyle:'medium',timeStyle:'short',timeZone:'America/New_York'}) : 'Not available';

// Static JSON is already computed by Python and delivered by Cloudflare's CDN.
// A short in-memory cache makes repeated filter selections instant.
async function fetchAggregate(url) {
  const cached = state.cache.get(url);
  if (cached && Date.now() - cached.at < 300000) return cached.data;
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `Request failed: ${response.status}`);
  if (staticSite && url.startsWith('/api/')) state.cache.set(url, {data, at: Date.now()});
  return data;
}

function draw(id, type, labels, values, color, extra = {}) {
  if (!window.Chart) return;
  const opts = {
    responsive: true, maintainAspectRatio: false,
    animation: {duration: 230},
    interaction: {mode: 'index', intersect: false},
    plugins: {legend: {display: type === 'doughnut', position: 'bottom',
      labels: {boxWidth: 10, usePointStyle: true, color:'#a6c0ce'}}},
    scales: type === 'doughnut' ? {} : {
      x: {grid: {display: false}, ticks: {color: '#8aa9bd', maxTicksLimit: 9}},
      y: {beginAtZero: true, ticks: {precision: 0, color: '#8aa9bd'}, grid: {color: '#2c4352'}}
    },
    ...extra
  };
  const dataset = {
    label: 'Published EMS records', data: values, borderColor: color,
    backgroundColor: type === 'doughnut' ? ['#3ad9c0','#2f9db7','#6977cd','#41606d'] :
      type === 'line' ? 'rgba(54,222,192,.14)' : color,
    fill: type === 'line', tension: .28, pointRadius: type === 'line' ? 1.7 : 0,
    pointHoverRadius: 4, borderWidth: type === 'line' ? 2.5 : 0,
    borderRadius: type === 'bar' ? 5 : undefined
  };
  if (state.charts[id] && state.charts[id].config.type === type) {
    state.charts[id].data.labels = labels;
    state.charts[id].data.datasets[0] = dataset;
    state.charts[id].update('none');
    return;
  }
  if (state.charts[id]) state.charts[id].destroy();
  state.charts[id] = new Chart($(id), {type, data:{labels, datasets:[dataset]}, options:opts});
}

const percent = (part, total) => total > 0 ? `${(100 * part / total).toFixed(1)}%` : '—';
function hourLabel(hour) {
  if (!Number.isInteger(hour) || hour < 0 || hour > 23) return '—';
  return new Date(Date.UTC(2020, 0, 1, hour)).toLocaleTimeString('en-US',
    {hour:'numeric', hour12:true, timeZone:'UTC'});
}

// Interpretation is intentionally modest: these are published dispatch records,
// not distinct emergencies, forecasts or verified official response-time metrics.

function renderInsights(data) {
  const count = Number(data.records || 0);
  const peak = (data.hours || []).filter(v => Number(v.count) > 0)
    .sort((a,b) => b.count - a.count || a.hour - b.hour)[0];
  $('insight-hour').textContent = peak ? hourLabel(Number(peak.hour)) : 'No records';
  $('insight-hour-detail').textContent = peak
    ? `${number(peak.count)} published Cleveland EMS rows (${percent(peak.count,count)}) have an incident date during this hour.`
    : 'No Cleveland source records for this selection.';

  if (data.priority !== 'all') {
    $('insight-priority-title').textContent = 'Priority filter';
    $('insight-priority').textContent = `Priority ${data.priority}`;
    $('insight-priority-detail').textContent =
      'Showing only this Cleveland source priority code. Select All priorities to compare categories.';
  } else {
    $('insight-priority-title').textContent = 'Most common source priority';
    const top = (data.priorities || []).filter(v => Number(v.count) > 0)
      .sort((a,b) => b.count - a.count)[0];
    $('insight-priority').textContent = top
      ? (top.priority === 'Unknown' ? 'Uncoded' : `Priority ${top.priority}`) : 'No records';
    $('insight-priority-detail').textContent = top
      ? `${number(top.count)} rows (${percent(top.count,count)}) use this Cleveland CAD priority code; no clinical severity meaning is inferred.`
      : 'No priority distribution for this selection.';
  }

  const type = (data.incident_types || [])[0];
  $('insight-quality').textContent = type?.type || 'Not available';
  $('insight-quality-detail').textContent = type
    ? `${number(type.count)} rows (${percent(type.count,count)}) use this published incident type. This is a source classification, not a diagnosis.`
    : 'No source incident-type classification in this selection.';
}

function renderSummary(data) {
  if (data.source_item_id !== 'd5d71757cc73400d843c98bcb46e46b6') {
    throw new Error('Wrong EMS data source. Refusing to display non-Cleveland statistics.');
  }
  state.currentData = data;
  $('total-calls').textContent = number(data.records);
  const rate = (part, valid) => valid > 0 ? percent(part, valid) : 'N/A';
  $('dispatch-share').textContent = rate(data.dispatched_count, data.dispatch_flag_known);
  $('dispatch-meta').textContent = `${number(data.dispatched_count)} of ${number(data.dispatch_flag_known)} rows with a known dispatch flag`;
  $('transport-share').textContent = rate(data.transported_count, data.transport_flag_known);
  $('transport-meta').textContent = `${number(data.transported_count)} of ${number(data.transport_flag_known)} rows with a known transport flag`;
  $('areas-reported').textContent = number(data.neighborhoods_in_source);

  $('sync-indicator').textContent = data.last_successful_sync
    ? `Cleveland source import: ${dateString(data.last_successful_sync)}${data.last_sync_failed ? ' · Latest sync failed' : ''}`
    : 'Cleveland source imported; sync timestamp not available';
  $('snapshot-note').textContent = data.snapshot_generated_at
    ? `Published aggregate snapshot: ${dateString(data.snapshot_generated_at)}`
    : 'Using live Cleveland source aggregates';
  $('coverage').textContent =
    `Imported Cleveland records: ${number(data.total_stored)} · Dates: ${dateString(data.earliest_call)} – ${dateString(data.latest_call)}`;

  draw('volume-chart','line',data.daily.map(v=>v.date),data.daily.map(v=>v.count),'#3bd8bd');
  draw('priority-chart','doughnut',
    data.priorities.map(v=>v.priority==='Unknown'?'Uncoded':`Code ${v.priority}`),
    data.priorities.map(v=>v.count),'#3ad9c0',{cutout:'76%'});
  draw('hour-chart','bar',
    data.hours.map(v=>`${String(v.hour).padStart(2,'0')}:00`),
    data.hours.map(v=>v.count),'#48afc2');
  renderInsights(data);
  document.dispatchEvent(new CustomEvent('ems:summary',{detail:data}));
}

async function refresh() {
  const params = new URLSearchParams({window: state.window, priority: state.priority});
  if (state.window === 'custom') {
    if (!$('start-date').value || !$('end-date').value) {
      $('snapshot-note').textContent = 'Choose both dates, then apply your range';
      return;
    }
    params.set('start', $('start-date').value);
    params.set('end', $('end-date').value);
  }
  const requestId = ++state.requestId;
  $('error-message').hidden = true;
  $('sync-indicator').textContent = 'Loading records…';
  $('snapshot-note').textContent = 'Updating selected metrics';
  $('overview').setAttribute('aria-busy', 'true');
  // Start both network requests at once; don't let a failed geography request
  // hide valid statistics. Ignore outdated replies after fast filter changes.
  const areasPromise = fetchAggregate(apiUrl('areas', params)).catch(() => null);
  try {
    const data = await fetchAggregate(apiUrl('summary', params));
    if (requestId !== state.requestId) return;
    renderSummary(data);
    $('overview').setAttribute('aria-busy', 'false');
    const areas = await areasPromise;
    if (requestId !== state.requestId) return;
    renderAreas(areas);
  } catch (error) {
    if (requestId !== state.requestId) return;
    $('overview').setAttribute('aria-busy', 'false');
    $('sync-indicator').textContent = 'Unable to load data';
    $('snapshot-note').textContent = 'Previously displayed metrics may be outdated';
    $('error-message').textContent = error.message;
    $('error-message').hidden = false;
  }
}

for (const button of document.querySelectorAll('.range-button')) {
  button.addEventListener('click', () => {
    state.window = button.dataset.window;
    document.querySelectorAll('.range-button').forEach(b => {
      b.classList.toggle('selected', b === button);
      b.setAttribute('aria-pressed', String(b === button));
    });
    $('custom-range').hidden = state.window !== 'custom';
    if (state.window !== 'custom') refresh();
  });
}
$('priority').addEventListener('change', event => { state.priority = event.target.value; refresh(); });
$('apply-custom').addEventListener('click', refresh);

// No raster tiles. The official neighborhood polygons draw as a simple vector map.
// Only reviewed neighborhood assignments can produce colored call counts.
function mapFill(name) {
  const rows = state.areaData?.areas || [];
  const count = rows.find(r => r.name.toLowerCase() === name.toLowerCase())?.count;
  if (count === undefined) return '#1d394b'; // not verified (NOT zero calls)
  const max = Math.max(...rows.map(r => r.count), 1);
  const t = Math.max(0, Math.min(1, count / max));
  return t >= .8 ? '#1cdebf' : t >= .6 ? '#20afa8' : t >= .4 ? '#277e91' : t >= .2 ? '#2c617b' : '#28556a';
}

function updateMapColors() {
  if (!state.mapLayer) return;
  state.mapLayer.eachLayer(layer => {
    const name = layer.feature.properties.name;
    const entry = state.areaData?.areas?.find(r => r.name.toLowerCase() === name.toLowerCase());
    layer.setStyle({fillColor: mapFill(name), color:'#4d7284',weight:1.3, fillOpacity:.93, opacity:1});
    // Safe: plain text, not user-supplied HTML or individual call addresses.
    layer.unbindTooltip();
    const tooltip = document.createElement('span');
    tooltip.textContent = `${name} · ${entry ? number(entry.count) + ' verified published rows' : 'Call volume not verified'}`;
    layer.bindTooltip(tooltip, {sticky:true});
  });
  document.dispatchEvent(new Event('ems:map-style'));
}

async function loadMap() {
  if (!window.L) {
    $('map-status').textContent = 'Map library could not load. Check your internet connection.';
    return;
  }
  const map = L.map('map', {scrollWheelZoom:false, attributionControl:false, zoomControl:true,
    dragging:true, doubleClickZoom:true, boxZoom:false, touchZoom:true, keyboard:true});
  state.map = map;
  try {
    const response = await fetch(staticSite ? '/api/neighborhood-boundaries.json' : '/api/neighborhood-boundaries');
    if (!response.ok) throw new Error('Neighborhood boundary service unavailable');
    const geojson = await response.json();
    state.mapLayer = L.geoJSON(geojson, {
      style: f => ({color:'#4d7284', weight:1.3, fillOpacity:.93, fillColor:mapFill(f.properties.name)}),
      onEachFeature: (feature, layer) => {
        layer.on('mouseover', () => layer.setStyle({weight:2.5,color:'#73dfd5'}));
        layer.on('mouseout', () => updateMapColors());
        layer.on('click', () => document.dispatchEvent(
          new CustomEvent('ems:neighborhood-selected', {detail:{name:feature.properties.name}})
        ));
      }
    }).addTo(map);
    map.fitBounds(state.mapLayer.getBounds(), {padding:[12,12]});
    requestAnimationFrame(() => map.invalidateSize());
    updateMapColors();
    $('map-status').textContent = 'Official Cleveland boundaries · click an area or station';
    document.dispatchEvent(new Event('ems:map-ready'));
  } catch (err) {
    $('map-status').textContent = 'Neighborhood outlines are temporarily unavailable. Try reloading.';
  }
}

function renderAreas(result) {
  state.areaData = result;
  updateMapColors();
  document.dispatchEvent(new CustomEvent('ems:areas', {detail: result}));
  const list = $('area-ranking');
  list.replaceChildren();
  if (!result) {
    $('map-explainer').textContent = 'Unable to retrieve geographic call totals right now.';
    $('map-legend').hidden = true;
    return;
  }
  if (result.status === 'ready') {
    $('map-explainer').textContent = 'Shading reflects verified, aggregated EMS counts in your selected time range. Gray areas have unavailable or suppressed data.';
    $('map-legend').hidden = false;
    for (const area of result.areas.slice(0, 10)) {
      const li = document.createElement('li');
      const label = document.createElement('span');
      const value = document.createElement('strong');
      label.textContent = area.name;
      value.textContent = number(area.count);
      li.append(label, value);
      list.append(li);
    }
  } else {
    $('map-explainer').textContent = result.status === 'suppressed'
      ? 'Counts for this time period are below the privacy reporting threshold (11).'
      : 'Verified neighborhood call volume is not yet available. Official boundaries are shown for reference; gray does not mean zero calls.';
    $('map-legend').hidden = true;
    const li = document.createElement('li');
    li.className='area-empty';
    li.textContent = result.status === 'suppressed'
      ? 'Counts below the reporting threshold are hidden.'
      : 'Call-volume ranking pending verified geographic assignments.';
    list.append(li);
  }
}

// Download aggregated daily counts only; no incident rows or locations.
function downloadDailyCsv() {
  const data = state.currentData;
  if (!data || !Array.isArray(data.daily)) return;
  const rows = ['date,published_cleveland_ems_records',
    ...data.daily.map(row => `${row.date},${Math.trunc(Number(row.count))}`)];
  const blob = new Blob([rows.join('\n') + '\n'], {type:'text/csv;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `cleveland-ems-records-${data.window}-priority-${data.priority}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
$('download-daily').addEventListener('click', downloadDailyCsv);

// Defer GeoJSON parsing and map initialization until the visitor approaches it.
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) {
      observer.disconnect();
      loadMap();
    }
  }, {rootMargin:'250px'});
  observer.observe($('geography'));
} else {
  loadMap();
}
refresh();
// Static snapshots change on deployment, not every two minutes: don't poll
// Cloudflare unnecessarily. The live FastAPI version retains its refresh.
if (!staticSite) setInterval(() => {
  if (document.visibilityState === 'visible') refresh();
}, 120000);
