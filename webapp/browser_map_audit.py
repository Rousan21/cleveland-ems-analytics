"""Read-only browser map layout diagnostic for Cloudflare preview.

Requires playwright and installed Chromium/Chrome. Prints aggregate geometry
and layout metrics, never raw incident data. Screenshots are saved only on CI.
"""
import argparse
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

JS = r"""() => {
  const map=document.querySelector('#map');
  const view=map?.getBoundingClientRect();
  const pane=map?.querySelector('.leaflet-map-pane');
  const paneStyle=pane ? getComputedStyle(pane) : null;
  const paths=[...(map?.querySelectorAll('.leaflet-overlay-pane path')||[])];
  const rects=paths.map(el=>el.getBoundingClientRect()).filter(r=>r.width>0 && r.height>0);
  const extent=rects.length ? {
    left:Math.min(...rects.map(r=>r.left)),right:Math.max(...rects.map(r=>r.right)),
    top:Math.min(...rects.map(r=>r.top)),bottom:Math.max(...rects.map(r=>r.bottom))
  }:null;
  const leafletLink=document.querySelector('link[href*="leaflet.css"]');
  const center=(typeof state!=='undefined' && state.map)?state.map.getCenter():null;
  return {
    viewport:{w:innerWidth,h:innerHeight},mapContainer:view?{w:view.width,h:view.height,left:view.left,right:view.right,top:view.top,bottom:view.bottom}:null,
    leafletCssLoaded:leafletLink?Boolean(leafletLink.sheet):null,
    leafletCssUrl:leafletLink?.href||null,
    leafletPanePosition:paneStyle?.position||null,
    hasMap:Boolean(typeof state!=='undefined' && state.map),
    zoom:(typeof state!=='undefined'&&state.map)?state.map.getZoom():null,
    center:center?{lat:center.lat,lon:center.lng}:null,
    bounds:(typeof state!=='undefined'&&state.map)?state.map.getBounds().toBBoxString():null,
    polygonPaths:paths.length,polygonExtent:extent,
    polygonWidthRatio:extent&&view?+( (extent.right-extent.left)/view.width).toFixed(3):null,
    polygonHeightRatio:extent&&view?+( (extent.bottom-extent.top)/view.height).toFixed(3):null,
    mapStatus:document.querySelector('#map-status')?.textContent,
    areaStatus:document.querySelector('#geo-data-status')?.textContent,
    attributionCount:map?.querySelectorAll('.leaflet-control-attribution').length,
    loadedTiles:map?.querySelectorAll('.leaflet-tile-loaded').length,
    rankListHeight:document.querySelector('#area-ranking')?.getBoundingClientRect().height,
    rankButtons:document.querySelectorAll('#area-ranking .geo-rank-button').length,
    firstRank:document.querySelector('#area-ranking .geo-rank-button')?.innerText,
  };
}"""


def diagnose(url, save_to):
    Path(save_to).mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome",headless=True,args=["--no-sandbox"])
        for label,width,height in [("desktop",1440,900),("mobile",390,844)]:
            page=browser.new_page(viewport={"width":width,"height":height},device_scale_factor=1)
            errors=[]
            page.on("pageerror",lambda error: errors.append(str(error)[:220]))
            page.goto(url,wait_until="domcontentloaded",timeout=45000)
            page.locator("#geography").scroll_into_view_if_needed()
            try:
                page.wait_for_function("window.L && typeof state !== 'undefined' && state.map && state.mapLayer && state.areaData",timeout=50000)
            except PlaywrightTimeout:
                print(label,"MAP DID NOT INITIALIZE",flush=True)
            page.wait_for_timeout(1000)
            result=page.evaluate(JS)
            print("MAP LAYOUT",label,json.dumps(result,sort_keys=True),flush=True)
            print("PAGE ERRORS",label,errors[:8],flush=True)
            # Regression guard: the unpkg stylesheet previously failed, leaving
            # the Leaflet panes static and the map 7,000–10,000px tall.
            if not result.get("leafletCssLoaded") or result.get("leafletPanePosition") != "absolute":
                raise AssertionError(f"{label}: Leaflet CSS was not loaded correctly: {result}")
            map_size=result.get("mapContainer") or {}
            expected_height=600 if label=="desktop" else 360
            if abs(map_size.get("h",0)-expected_height)>5:
                raise AssertionError(f"{label}: bad map height: {map_size}")
            if result.get("polygonPaths",0)<25 or (result.get("polygonWidthRatio") or 0)<0.3:
                raise AssertionError(f"{label}: Cleveland polygons missing or tiny: {result}")
            if result.get("loadedTiles",0)>0:
                raise AssertionError(f"{label}: third-party map tiles returned; avoid API-key watermarks")
            if page.locator('#geo-mapped-count').count()!=0:
                raise AssertionError(f"{label}: GIS match is still a prominent metric")
            if 'GIS name matching:' not in page.locator('#geo-match-note').inner_text():
                raise AssertionError(f"{label}: geographic source note did not render")
            if result.get("rankButtons",0)<5 or result.get("rankListHeight",0)<180:
                raise AssertionError(f"{label}: neighborhood rankings collapsed or missing: {result}")
            if errors:
                raise AssertionError(f"{label}: browser runtime errors: {errors[:4]}")

            # Verify the trend does not connect incomplete rolling-window
            # endpoints as if they were complete calendar dates.
            trend=page.evaluate("""() => {
              const d=state.currentData||{};
              const chart=state.charts['volume-chart'];
              return {
                source:d.source_item_id,
                rawFirst:d.daily?.[0]?.date,
                rawLast:d.daily?.at(-1)?.date,
                plottedFirst:chart?.data.labels?.[0],
                plottedLast:chart?.data.labels?.at(-1),
                plottedCount:chart?.data.labels?.length||0,
                excluded:d.daily_chart_excluded?.map(v=>v.date)||[],
                note:document.querySelector('#daily-chart-note')?.textContent||'',
              };
            }""")
            print("DAILY TREND",label,json.dumps(trend,sort_keys=True),flush=True)

            incidents=page.evaluate("""() => ({
              rows:document.querySelectorAll('#reason-rankings .reason-row').length,
              first:document.querySelector('#reason-rankings .reason-name')?.textContent||'',
              coverage:document.querySelector('#reason-coverage')?.textContent||'',
              scope:document.querySelector('#reason-filter-scope')?.textContent||'',
              transport:document.querySelector('#transport-share')?.textContent||'',
              removedWeakChart:!document.querySelector('#priority-chart')
            })""")
            print("INCIDENT TYPES",label,json.dumps(incidents,sort_keys=True),flush=True)
            if incidents["rows"]<5 or not incidents["coverage"].endswith("%") or not incidents["removedWeakChart"] or "Citywide" not in incidents["scope"]:
                raise AssertionError(f"{label}: incident type chart missing, unscoped or incorrectly laid out: {incidents}")

            selector=page.locator("#incident-type")
            options=selector.locator("option")
            available=options.count()
            print("FILTER OPTIONS",label,available,flush=True)
            if available<5:
                raise AssertionError(f"{label}: incident selector is missing source categories")
            if page.locator("#priority").count()!=0 or page.locator("#quality-types").count()!=0 or page.locator("#brief-title").count()!=0:
                raise AssertionError(f"{label}: removed priority/evidence/guidance clutter is still present")
            original_count=page.evaluate("Number(state.currentData?.records||0)")
            try:
                selector.select_option(label="BREATHING PROBLEMS")
            except Exception:
                raise AssertionError(f"{label}: Breathing Problems category unavailable")
            page.wait_for_function(
                "() => state.currentData?.selected_incident_type === 'BREATHING PROBLEMS' && state.areaData?.eligible_records === state.currentData?.records",
                timeout=30000
            )
            filtered=page.evaluate("""() => ({
               total:Number(state.currentData?.records||0),
               type:state.currentData?.selected_incident_type,
               mapTotal:state.areaData?.eligible_records,
               chartData:state.charts['volume-chart']?.data?.datasets?.[0]?.data?.reduce((a,b)=>a+b,0),
               chartHidden:document.querySelector('#call-types')?.hidden,
               mapRankings:document.querySelectorAll('#area-ranking .geo-rank-button').length,
            })""")
            print("FILTERED TYPE",label,json.dumps(filtered,sort_keys=True),flush=True)
            if (filtered["type"]!="BREATHING PROBLEMS" or filtered["total"]<=0 or
                    filtered["total"]>=original_count or filtered["mapTotal"]!=filtered["total"] or
                    not filtered["chartHidden"] or filtered["mapRankings"]<1):
                raise AssertionError(f"{label}: incident filter did not update the whole dashboard: {filtered}")
            selector.select_option("all")
            page.wait_for_function(
                "() => state.currentData?.incident_type === 'all' && state.areaData?.eligible_records === state.currentData?.records",
                timeout=30000
            )

            if trend["source"] != "d5d71757cc73400d843c98bcb46e46b6" or trend["plottedCount"] < 3:
                raise AssertionError(f"{label}: wrong source or no daily trend: {trend}")
            if (trend["plottedFirst"] in trend["excluded"] or
                    trend["plottedLast"] in trend["excluded"]):
                raise AssertionError(f"{label}: plotted a partial boundary date: {trend}")
            if len(trend["excluded"]) >= 2 and (
                    trend["plottedFirst"] == trend["rawFirst"] or
                    trend["plottedLast"] == trend["rawLast"]):
                raise AssertionError(f"{label}: first/latest incomplete date still appears: {trend}")
            if "complete Cleveland-local" not in trend["note"]:
                raise AssertionError(f"{label}: incomplete day explanation missing: {trend}")
            if label == "desktop":
                # README screenshots are captured from the verified, deployed
                # Cloudflare preview—not generated mockups or stale prototypes.
                page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                page.wait_for_timeout(300)
                page.screenshot(
                    path=str(Path(save_to)/"desktop-overview.png"),full_page=False
                )
                page.locator("#call-types").scroll_into_view_if_needed()
                page.wait_for_timeout(300)
                page.screenshot(
                    path=str(Path(save_to)/"desktop-incident-types.png"),full_page=False
                )
            page.locator('#trends').scroll_into_view_if_needed()
            page.screenshot(path=str(Path(save_to)/f"{label}-daily-trend.png"),full_page=False)
            page.locator('#geography').scroll_into_view_if_needed()
            page.screenshot(path=str(Path(save_to)/f"{label}.png"),full_page=False)
            if result.get("hasMap"):
                dropdown=page.locator("#neighborhood-select")
                if dropdown.is_enabled():
                    dropdown.select_option(label="Downtown")
                    page.wait_for_timeout(600)
                    local_type=page.locator('#area-type-value').inner_text()
                    print("NEIGHBORHOOD TYPE",label,local_type,flush=True)
                    if local_type in ("", "Choose a neighborhood", "Select a neighborhood"):
                        raise AssertionError(f"{label}: selected Downtown has no area-specific incident-type output")
                    print("MAP SELECT",label,json.dumps(page.evaluate(JS),sort_keys=True),flush=True)
                    page.screenshot(path=str(Path(save_to)/f"{label}-downtown.png"),full_page=False)
            page.close()
        browser.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",required=True)
    parser.add_argument("--output",default="map_browser_report")
    args=parser.parse_args()
    diagnose(args.url,args.output)
