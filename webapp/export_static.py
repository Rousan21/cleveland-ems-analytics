"""Build a privacy-preserving, static Cloudflare Pages dashboard from aggregate API data.

Run inside a CI worker with EMS_DATABASE_URL pointing at Neon. Only summary JSON
and public neighborhood polygons are exported; incident rows never leave the DB.
"""
import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from analytics import summarize
from geography import get_area_summary, get_boundaries

HERE = Path(__file__).resolve().parent
WINDOWS = ("24h", "7d", "30d", "90d", "1y", "all")
PRIORITIES = ("all", "1", "2", "3")


def write_json(destination: Path, payload):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


def build_site(output: Path):
    """Export exact preset-window results using the same functions as FastAPI.

    Custom date ranges stay on FastAPI, because averaging daily medians would
    produce incorrect results. Generate each window against a fixed timestamp.
    """
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    html = (HERE / "templates" / "index.html").read_text(encoding="utf-8")
    if "<body>" not in html:
        raise RuntimeError("Dashboard template changed; static-mode marker not found")
    (output / "index.html").write_text(
        html.replace("<body>", '<body data-static-site="true">', 1), encoding="utf-8"
    )
    shutil.copytree(HERE / "static", output / "static", dirs_exist_ok=True)

    # Cloudflare can cache the shell briefly; JSON changes after a daily deploy.
    (output / "_headers").write_text(
        "/*\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        "/api/*\n"
        "  Cache-Control: public, max-age=300, must-revalidate\n"
        "/static/*\n"
        "  Cache-Control: public, max-age=300, must-revalidate\n",
        encoding="utf-8",
    )

    now = datetime.now(timezone.utc)
    for window in WINDOWS:
        for priority in PRIORITIES:
            stats = summarize(window=window, priority=priority, now=now)
            if window == "30d" and priority == "all" and not stats["total_stored"]:
                raise RuntimeError("Database is empty; refusing to deploy an empty dashboard")
            stats["snapshot_generated_at"] = now.isoformat()
            write_json(output / "api" / "summary" / window / f"{priority}.json", stats)

            areas = get_area_summary(window=window, priority=priority, now=now)
            write_json(output / "api" / "areas" / window / f"{priority}.json", areas)

    # Official neighborhood geometry only; no raw EMS locations or identifiers.
    write_json(output / "api" / "neighborhood-boundaries.json", get_boundaries())
    write_json(output / "api" / "build-info.json", {"generated_at": now.isoformat(), "mode": "precomputed"})
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Cloudflare Pages static dashboard")
    parser.add_argument("--output", default="../site_build", help="Empty build output folder")
    args = parser.parse_args()
    if not os.environ.get("EMS_DATABASE_URL"):
        parser.error("EMS_DATABASE_URL is required; export must read the existing Neon database")
    print(f"Exported static dashboard to {build_site(Path(args.output))}", flush=True)
