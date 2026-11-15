/* Cleveland GIS explorer — verified city CAD neighborhood counts only.
   No incident points, private addresses, or fabricated station coverage maps. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const fmt = n => Number(n || 0).toLocaleString('en-US');
  let selected = "";
  let mapReady = false;

  function findLayer(name) {
    if (!state.mapLayer || !name) return null;
    let found = null;
    state.mapLayer.eachLayer(layer => {
      if (layer.feature?.properties?.name === name) found = layer;
    });
    return found;
  }

  function selectedAggregate(name) {
    return (state.areaData?.areas || []).find(v => v.name.toLowerCase() === name.toLowerCase()) || null;
  }

  function showSelectedDetails() {
    $('selected-neighborhood-name').textContent = selected || 'Explore a Cleveland neighborhood';
    const description = $('selected-neighborhood-copy');
    const areas = state.areaData?.areas || [];
    const matched = Number(state.areaData?.mapped_records || 0);
    const row = selectedAggregate(selected);
    if (!selected) {
      description.textContent = areas.length
        ? `Select a neighborhood on the map, use the dropdown, or click a ranked area. The map contains ${fmt(matched)} Cleveland EMS rows matched to official neighborhood boundaries for your filters.`
        : 'Loading neighborhood aggregates from official Cleveland CAD records.';
      $('geo-next-copy').textContent = areas.length
        ? 'Shading compares published EMS record counts, not population-adjusted medical risk. Lower counts may reflect different populations or incomplete records.'
        : 'Only source-provided and GIS-matched neighborhood labels are eligible for shading.';
      return;
    }
    if (row) {
      const rank = areas.findIndex(v => v.name === row.name) + 1;
      const share = matched > 0 ? (row.count / matched * 100).toFixed(1) : '0';
      description.textContent =
        `${fmt(row.count)} published Cleveland EMS rows in this neighborhood for the selected filters · #${rank} of ${areas.length} reportable areas · ${share}% of GIS-matched records.`;
      $('geo-next-copy').textContent =
        'This is raw published record volume, not a per-resident rate, distinct patients, disease prevalence, or evidence of required ambulance staffing.';
    } else {
      description.textContent = 'No reportable volume is shown for this area under the selected filters. It may have fewer than 11 rows, an unmatched source label, or no eligible records.';
      $('geo-next-copy').textContent =
        'Gray means unavailable or suppressed, not zero emergencies. Try a longer date range or All priorities.';
    }
  }

  function highlightSelected() {
    const layer = findLayer(selected);
    if (!layer) return;
    layer.setStyle({color:'#a4fff3',weight:3.1,opacity:1,fillOpacity:.98});
    layer.bringToFront();
  }

  function selectArea(name, zoom=false) {
    if (!mapReady) return;
    selected = name || '';
    $('neighborhood-select').value = selected;
    $('neighborhood-reset').disabled = !selected;
    updateMapColors();
    showSelectedDetails();
    const layer = findLayer(selected);
    if (zoom && layer) state.map.fitBounds(layer.getBounds(),{padding:[26,26],maxZoom:12});
  }

  function prepareMap() {
    if (!state.mapLayer || mapReady) return;
    mapReady = true;
    // Low-contrast basemap adds streets/river context without altering GIS data.
    // The interactive neighborhood polygons remain above the optional raster tiles.
    if (window.L) {
      try {
        L.tileLayer('https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{
          attribution:'© OpenStreetMap contributors · © CARTO',
          minZoom:8,maxZoom:17,opacity:.68,
        }).addTo(state.map).bringToBack();
        state.map.attributionControl?.addAttribution('Neighborhood boundaries: Cleveland GIS');
      } catch {
        // A failed third-party basemap must not block official polygon exploration.
      }
    }
    const names = [];
    state.mapLayer.eachLayer(layer => {
      const name = layer.feature?.properties?.name;
      if (typeof name === 'string' && name.trim()) names.push(name.trim());
    });
    const selector = $('neighborhood-select');
    selector.replaceChildren();
    const initial = document.createElement('option');
    initial.textContent = 'Choose a Cleveland neighborhood';
    initial.value = '';
    selector.append(initial);
    for (const name of [...new Set(names)].sort((a,b)=>a.localeCompare(b))) {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      selector.append(option);
    }
    selector.disabled = false;
    selector.addEventListener('change',()=>selectArea(selector.value,true));
    $('neighborhood-reset').addEventListener('click',()=>{
      selectArea('',false);
      state.map.fitBounds(state.mapLayer.getBounds(),{padding:[18,18]});
    });
    $('map-status').textContent =
      `${names.length} official Cleveland neighborhood shapes · click an area or ranked bar`;
    showSelectedDetails();
  }

  function rankingButton(area, max) {
    const li = document.createElement('li');
    li.className = 'geo-rank-item';
    const button = document.createElement('button');
    button.type='button';
    button.className = 'geo-rank-button';
    const head = document.createElement('span');
    head.className = 'geo-rank-head';
    const label = document.createElement('span');
    label.textContent = area.name;
    const count = document.createElement('strong');
    count.textContent = fmt(area.count);
    head.append(label,count);
    const progress = document.createElement('span');
    progress.className = 'geo-rank-progress';
    const bar = document.createElement('span');
    bar.style.width = `${Math.max(1,100 * area.count/max).toFixed(1)}%`;
    progress.append(bar);
    button.append(head,progress);
    button.addEventListener('click',()=>selectArea(area.name,true));
    li.append(button);
    return li;
  }

  function renderGeoStats(result) {
    const rows = result?.areas || [];
    const coverage = result?.mapping_coverage_pct;
    $('geo-mapped-count').textContent = typeof coverage === 'number' ? `${coverage.toFixed(1)}%` : '—';
    $('top-area-count').textContent = rows.length ? fmt(rows[0].count) : '—';
    $('area-ranking-title').textContent = 'Highest published EMS record counts';
    $('area-ranking-badge').textContent = rows.length ? 'CLEVELAND CAD' : 'NO REPORTABLE AREAS';
    $('geo-data-status').textContent = rows.length ? 'SOURCE-VERIFIED' : 'NO AREA COUNTS';

    const list = $('area-ranking');
    list.replaceChildren();
    if (!rows.length) {
      const li=document.createElement('li');
      li.className='area-empty';
      li.textContent = result?.status === 'suppressed'
        ? 'Neighborhood counts below the privacy threshold are withheld.'
        : 'No source-matched neighborhood counts available for this filter.';
      list.append(li);
      $('map-explainer').textContent = 'No reportable area totals. The outlines remain available as a reference map.';
    } else {
      const max = rows[0].count;
      for(const row of rows.slice(0,10)) list.append(rankingButton(row,max));
      $('map-explainer').textContent =
        `${rows.length} Cleveland neighborhoods have reportable counts (minimum 11). ${fmt(result.mapped_records)} of ${fmt(result.eligible_records)} published records match this official boundary set; the top 10 are shown.`;
    }
    showSelectedDetails();
    highlightSelected();
  }

  function renderInterpretation(summary) {
    const records=Number(summary.records||0);
    const best=(summary.hours||[]).filter(x=>Number(x.count)>0)
      .sort((a,b)=>b.count-a.count)[0];
    if (!records || !best) {
      $('brief-title').textContent='No published records for this filter';
      $('brief-detail').textContent='Try a longer date range or select All priorities to compare more records.';
      $('brief-caveat').textContent='Only City of Cleveland, Ohio source records appear.';
      return;
    }
    const hour=new Date(Date.UTC(2020,0,1,Number(best.hour)))
      .toLocaleTimeString('en-US',{hour:'numeric',timeZone:'UTC'});
    const share=(best.count/records*100).toFixed(1);
    $('brief-title').textContent=`Busiest recorded incident hour: ${hour}`;
    $('brief-detail').textContent=
      `Of ${fmt(records)} Cleveland CAD records in this selection, ${fmt(best.count)} (${share}%) fall in this hour of day. Compare across dates and neighborhoods before interpreting demand patterns.`;
    $('brief-caveat').textContent=
      'Counts use incident timestamps, not measured EMS response times. Source priority codes are not clinical diagnoses.';
  }

  document.addEventListener('ems:map-ready',prepareMap);
  document.addEventListener('ems:map-style',highlightSelected);
  document.addEventListener('ems:neighborhood-selected',evt=>selectArea(evt.detail.name,false));
  document.addEventListener('ems:areas',evt=>renderGeoStats(evt.detail));
  document.addEventListener('ems:summary',evt=>renderInterpretation(evt.detail));
  if(state.mapLayer)prepareMap();
  if(state.areaData)renderGeoStats(state.areaData);
  if(state.currentData)renderInterpretation(state.currentData);
})();
