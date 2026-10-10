/* Tiny browser layer: Python handles queries/aggregation, Chart.js handles presentation. */
const state = { window: '30d', priority: 'all', charts: {}, areaData: null, mapLayer: null, map: null };
const $ = id => document.getElementById(id);
const number = n => Number(n ?? 0).toLocaleString('en-US');
const minutes = n => n == null ? 'N/A' : `${n.toFixed(1)} min`;
const dateString = iso => iso ? new Date(iso).toLocaleString('en-US', {dateStyle:'medium',timeStyle:'short',timeZone:'America/New_York'}) : 'Not available';

function draw(id, type, labels, values, color, extra = {}) {
  if (!window.Chart) return;
  if (state.charts[id]) state.charts[id].destroy();
  const opts = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: type === 'doughnut', position: 'bottom', labels: { boxWidth: 10, usePointStyle: true } } },
    scales: type === 'doughnut' ? {} : {
      x: { grid: { display: false }, ticks: { color: '#8b9aad', maxTicksLimit: 8 } },
      y: { beginAtZero: true, ticks: { precision: 0, color: '#8b9aad' }, grid: { color: '#edf2f6' } }
    },
    ...extra
  };
  state.charts[id] = new Chart($(id), {
    type,
    data: { labels, datasets: [{ label: 'Published EMS records', data: values, borderColor: color, backgroundColor: type === 'doughnut' ? ['#1978bc','#3cabc7','#89cbd6','#d9ebf4'] : (type === 'line' ? 'rgba(25,120,188,.09)' : color), fill: type === 'line', tension: .32, pointRadius: type === 'line' ? 2 : 0, borderWidth: type === 'line' ? 2.5 : 0, borderRadius: type === 'bar' ? 5 : undefined }] },
    options: opts
  });
}

async function refresh() {
  const params = new URLSearchParams({window: state.window, priority: state.priority});
  if (state.window === 'custom') {
    if (!$('start-date').value || !$('end-date').value) return;
    params.set('start', $('start-date').value);
    params.set('end', $('end-date').value);
  }
  $('error-message').hidden = true;
  $('sync-indicator').textContent = 'Loading records…';
  try {
    const response = await fetch(`/api/summary?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `Request failed: ${response.status}`);
    $('total-calls').textContent = number(data.records);
    $('total-stored').textContent = number(data.total_stored);
    $('median-dispatch').textContent = minutes(data.median_call_to_dispatch_min);
    $('median-scene').textContent = minutes(data.median_call_to_scene_min);
    $('sync-indicator').textContent = data.last_successful_sync ? `Last successful import: ${dateString(data.last_successful_sync)}${data.last_sync_failed ? ' · Latest sync failed' : ''}` : 'No import yet — run ingest.py';
    $('coverage').textContent = `Newest dispatch in database: ${dateString(data.latest_call)} · ${number(data.total_stored)} records imported`;
    draw('volume-chart','line',data.daily.map(v => v.date),data.daily.map(v => v.count),'#2488ca');
    draw('priority-chart','doughnut',data.priorities.map(v => `Priority ${v.priority}`),data.priorities.map(v => v.count),'#228acc', {cutout:'73%'});
    draw('hour-chart','bar',data.hours.map(v=>`${String(v.hour).padStart(2,'0')}:00`),data.hours.map(v=>v.count),'#1b83bf');
    await refreshAreas(params);
  } catch (error) {
    $('sync-indicator').textContent = 'Unable to load data';
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
  if (count === undefined) return '#e5ebf0'; // never misrepresent unknown as zero
  const max = Math.max(...rows.map(r => r.count), 1);
  const t = Math.max(0, Math.min(1, count / max));
  return t >= .8 ? '#104a78' : t >= .6 ? '#176998' : t >= .4 ? '#268db0' : t >= .2 ? '#73bad1' : '#bddfe9';
}

function updateMapColors() {
  if (!state.mapLayer) return;
  state.mapLayer.eachLayer(layer => {
    const name = layer.feature.properties.name;
    const entry = state.areaData?.areas?.find(r => r.name.toLowerCase() === name.toLowerCase());
    layer.setStyle({fillColor: mapFill(name), color:'#ffffff',weight:1.4, fillOpacity:1, opacity:1});
    // Safe: plain text, not user-supplied HTML or individual call addresses.
    layer.unbindTooltip();
    layer.bindTooltip(`${name} · ${entry ? number(entry.count) + ' recorded calls' : 'Not available'}`, {sticky:true});
  });
}

async function loadMap() {
  if (!window.L) {
    $('map-status').textContent = 'Map library could not load. Check your internet connection.';
    return;
  }
  const map = L.map('map', {scrollWheelZoom:false, attributionControl:false, zoomControl:false,
    dragging:false, doubleClickZoom:false, boxZoom:false, touchZoom:false, keyboard:false});
  state.map = map;
  try {
    const response = await fetch('/api/neighborhood-boundaries');
    if (!response.ok) throw new Error('Neighborhood boundary service unavailable');
    const geojson = await response.json();
    state.mapLayer = L.geoJSON(geojson, {
      style: f => ({color:'#fff', weight:1.4, fillOpacity:1, fillColor:mapFill(f.properties.name)}),
      onEachFeature: (feature, layer) => {
        layer.on('mouseover', () => layer.setStyle({weight:2.5,color:'#195e8c'}));
        layer.on('mouseout', () => updateMapColors());
      }
    }).addTo(map);
    map.fitBounds(state.mapLayer.getBounds(), {padding:[12,12]});
    requestAnimationFrame(() => map.invalidateSize());
    updateMapColors();
    $('map-status').textContent = 'Official Cleveland neighborhood boundaries';
  } catch (err) {
    $('map-status').textContent = 'Neighborhood outlines are temporarily unavailable. Try reloading.';
  }
}

async function refreshAreas(params) {
  try {
    const response = await fetch(`/api/areas?${params}`);
    if (!response.ok) throw new Error('Neighborhood summaries unavailable');
    const result = await response.json();
    state.areaData = result;
    updateMapColors();
    const list = $('area-ranking');
    list.replaceChildren();
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
        : 'Area call counts are not yet available: this EMS source needs a validated location-to-neighborhood match. Gray is not a zero-call result.';
      $('map-legend').hidden = true;
      const li = document.createElement('li');
      li.className='area-empty';
      li.textContent = 'Neighborhood ranking pending verified geographic data.';
      list.append(li);
    }
  } catch (err) {
    state.areaData = null;
    updateMapColors();
    $('map-explainer').textContent = 'Unable to retrieve geographic call totals right now.';
    $('map-legend').hidden = true;
  }
}

loadMap();
refresh();
// The import runs separately; update visible metrics automatically without reloading the page.
setInterval(() => { if (document.visibilityState === 'visible') refresh(); }, 120000);
