"""Build the *Cleveland, Ohio* EMS analytics site from verified source fields.

Export only aggregate citywide/neighborhood summaries and official neighborhood
polygons. No record-level data, patient addresses, identifiers, or credentials.
"""
import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from cleveland_pipeline import SOURCE_ITEM_ID, area_summary, summarize
from geography import get_boundaries

HERE = Path(__file__).resolve().parent
WINDOWS = ("24h", "7d", "30d", "90d", "1y", "all")
PRIORITIES = ("all", "1", "2", "3", "4", "5", "6", "7")


def write_json(destination: Path, payload):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


def build_site(output: Path):
    """Generate all preset windows from one time anchor and validated geography."""
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
    (output / "_headers").write_text(
        "/*\n  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        "/api/*\n  Cache-Control: public, max-age=300, must-revalidate\n"
        "/static/*\n  Cache-Control: public, max-age=300, must-revalidate\n",
        encoding="utf-8",
    )

    now = datetime.now(timezone.utc)
    boundaries = get_boundaries()
    boundary_names = sorted({
        str(f.get("properties", {}).get("name", "")).strip()
        for f in boundaries.get("features", [])
        if f.get("properties", {}).get("name")
    })
    if len(boundary_names) < 20:
        raise RuntimeError("Cleveland boundary layer is missing or incomplete")

    first = summarize(window="30d", priority="all", now=now)
    if not first["records"] or not first["total_stored"]:
        raise RuntimeError(
            "No official Cleveland EMS records in the 30-day window. "
            "Run the Cleveland-only ingestion, or inspect source freshness; "
            "refusing to publish legacy Virginia Beach records."
        )
    if first["source_item_id"] != SOURCE_ITEM_ID:
        raise RuntimeError("Cleveland EMS source provenance mismatch")

    for window in WINDOWS:
        for priority in PRIORITIES:
            stats = first if (window, priority) == ("30d", "all") else summarize(
                window=window, priority=priority, now=now
            )
            stats["snapshot_generated_at"] = now.isoformat()
            write_json(output / "api" / "summary" / window / f"{priority}.json", stats)
            areas = area_summary(window=window, priority=priority, now=now,
                                 known_neighborhoods=boundary_names)
            if window == "30d" and priority == "all":
                coverage = areas.get("mapping_coverage_pct")
                print(
                    "Cleveland map QA: "
                    f"status={areas['status']}, "
                    f"mapped={areas['mapped_records']:,}/"
                    f"{areas['eligible_records']:,}, coverage={coverage}%, "
                    f"reportable_neighborhoods={len(areas['areas'])}, "
                    f"top={[(a['name'], a['count']) for a in areas['areas'][:5]]}",
                    flush=True,
                )
                if areas["status"] != "ready" or not areas["areas"]:
                    raise RuntimeError(
                        "No verified Cleveland neighborhoods can be mapped; "
                        "refusing to deploy an empty geographic explorer."
                    )
            write_json(output / "api" / "areas" / window / f"{priority}.json", areas)

    write_json(output / "api" / "neighborhood-boundaries.json", boundaries)
    write_json(output / "api" / "build-info.json", {
        "generated_at": now.isoformat(),
        "mode": "Cleveland-only verified public aggregates",
        "source_item_id": SOURCE_ITEM_ID,
        "priority_codes": list(PRIORITIES),
    })
    print(f"Built Cleveland-only site: {first['records']:,} records in 30d, "
          f"{first['total_stored']:,} Cleveland records stored, "
          f"{len(boundary_names)} official neighborhoods",flush=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export verified Cleveland EMS site")
    parser.add_argument("--output", default="../site_build", help="Empty build output folder")
    args = parser.parse_args()
    if not os.environ.get("EMS_DATABASE_URL"):
        parser.error("EMS_DATABASE_URL is required to read the separate Cleveland database table")
    print(f"Exported Cleveland EMS dashboard to {build_site(Path(args.output))}", flush=True)
