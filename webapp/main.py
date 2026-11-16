"""FastAPI application for actual City of Cleveland, Ohio EMS CAD records."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cleveland_pipeline import SOURCE_ITEM_ID, area_summary, summarize, common_incident_types
from db import init_database
from geography import get_boundaries

HERE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield


app = FastAPI(title="Cleveland EMS Analytics — Verified Cleveland CAD", version="6.0.0",
              lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https://(?:[a-z0-9-]+\.){1,3}pages\.dev$",
    allow_methods=["GET"], allow_headers=[], allow_credentials=False,
)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


@app.get("/", response_class=HTMLResponse)
def homepage(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/summary")
def summary(window: str = "30d", priority: str = "all",
            incident_type: str = "all", start: str | None = None, end: str | None = None):
    try:
        return summarize(window=window, priority=priority, incident_type=incident_type, start_date=start, end_date=end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/areas")
def areas(window: str = "30d", priority: str = "all",
          incident_type: str = "all", start: str | None = None, end: str | None = None):
    try:
        boundaries = get_boundaries()
        names = [
            feature.get("properties", {}).get("name", "")
            for feature in boundaries.get("features", [])
        ]
        return area_summary(window=window, priority=priority, incident_type=incident_type, start_date=start,
                            end_date=end, known_neighborhoods=names)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Cleveland neighborhood data unavailable") from exc


@app.get("/api/neighborhood-boundaries")
def neighborhood_boundaries():
    try:
        return get_boundaries()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Cleveland GIS boundaries unavailable") from exc


@app.get("/api/incident-types")
def incident_types():
    return {"types": common_incident_types(),
            "scope": "Ten most frequent Cleveland CAD incident classifications across imported dates"}


@app.get("/api/source")
def source():
    return {"name": "City of Cleveland, Ohio — CAD_EMS_Public",
            "arcgis_item_id": SOURCE_ITEM_ID,
            "note": "No Virginia Beach statistics are included in this API."}
