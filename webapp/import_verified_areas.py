"""Optional: import reviewed OBJECTID-to-neighborhood crosswalk.

Do NOT fabricate an area from block street names. Supply a researched source and
review its matching methodology before importing. Never publish the CSV itself.
"""
import argparse
import csv
from pathlib import Path
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from db import EMSArea, engine, init_database
from geography import get_boundaries


def import_areas(path, source_note):
    bounds = get_boundaries()
    names = {feature['properties']['name'].casefold(): feature['properties']['name'] for feature in bounds['features']}
    rows = []
    used = set()
    with Path(path).open(newline='', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        if not {'object_id','neighborhood'}.issubset(reader.fieldnames or []):
            raise ValueError('CSV must have columns: object_id, neighborhood')
        for entry in reader:
            object_id = int(entry['object_id'])
            n = entry['neighborhood'].strip().casefold()
            if object_id in used or n not in names:
                raise ValueError(f'Duplicate call ID or unrecognized neighborhood: {object_id} / {n}')
            used.add(object_id)
            rows.append({'object_id':object_id,'neighborhood':names[n], 'source_note':source_note})
    if not rows:
        raise ValueError('CSV had no assignments')
    init_database()
    with engine.begin() as conn:
        for i in range(0,len(rows),100):
            batch=rows[i:i+100]
            stmt = (pg_insert if conn.dialect.name == 'postgresql' else sqlite_insert)(EMSArea).values(batch)
            conn.execute(stmt.on_conflict_do_update(
                index_elements=['object_id'],
                set_={'neighborhood':stmt.excluded.neighborhood,'source_note':stmt.excluded.source_note}
            ))
    return len(rows)

if __name__ == '__main__':
    p=argparse.ArgumentParser(description='Import documented, verified geographic assignments')
    p.add_argument('csv_file')
    p.add_argument('--source',required=True,help='Document the provenance/matching method')
    args=p.parse_args()
    if len(args.source.strip()) < 15:
        p.error('Provide a meaningful source and matching-method description')
    print(f'Imported {import_areas(args.csv_file,args.source)} reviewed area assignments')
