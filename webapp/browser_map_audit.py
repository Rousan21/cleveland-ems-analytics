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
            page.screenshot(path=str(Path(save_to)/f"{label}.png"),full_page=False)
            if result.get("hasMap"):
                dropdown=page.locator("#neighborhood-select")
                if dropdown.is_enabled():
                    dropdown.select_option(label="Downtown")
                    page.wait_for_timeout(600)
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
