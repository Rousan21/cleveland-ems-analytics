"""FastAPI web interface and public aggregate JSON API."""
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from analytics import summarize
from geography import get_boundaries, get_area_summary
from db import init_database

HERE = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield

app = FastAPI(title="Cleveland EMS Analytics", version="2.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

@app.get("/", response_class=HTMLResponse)
def homepage(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})

@app.get("/api/summary")
def summary(window: str = "30d", priority: str = "all", start: str | None = None, end: str | None = None):
    try:
        return summarize(window=window, priority=priority, start_date=start, end_date=end)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/neighborhood-boundaries")
def neighborhood_boundaries():
    try:
        return get_boundaries()
    except Exception as exc:
        # Avoid leaking server internals to the browser.
        raise HTTPException(status_code=503, detail="Neighborhood boundary data is temporarily unavailable.") from exc


@app.get("/api/areas")
def areas(window: str = "30d", priority: str = "all", start: str | None = None, end: str | None = None):
    try:
        return get_area_summary(window=window, priority=priority, start_date=start, end_date=end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
