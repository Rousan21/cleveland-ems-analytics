"""Read-only, aggregate audit of Cleveland's public EMS ArcGIS table.

This script never prints EMS call numbers, unit identifiers, or incident locations.
It does not connect to or modify the project's Neon database.

Usage: python audit_source.py --days 30
"""
import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from ingest import API_URL, PAGE_SIZE, parse_epoch_ms

LOCAL = ZoneInfo('America/New_York')
AUDIT_FIELDS = 'OBJECTID,EMS_Call_Number,Unit_Callsign,Dispatch_Date_Time'


def fetch_audit_pages(*, days=30, session=None, now=None):
    """Retrieve all rows in the selected dispatch-date window, by OBJECTID."""
    if days <= 0 or days > 365:
        raise ValueError('days must be between 1 and 365')
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    last_id = -1
    client = session or requests.Session()
    while True:
        params = {
            'where': (f"OBJECTID > {last_id} AND Dispatch_Date_Time >= "
                      f"TIMESTAMP '{cutoff:%Y-%m-%d %H:%M:%S}'"),
            'outFields': AUDIT_FIELDS,
            'returnGeometry': 'false',
            'orderByFields': 'OBJECTID ASC',
            'resultRecordCount': PAGE_SIZE,
            'f': 'json',
        }
        response = client.get(API_URL, params=params, timeout=45)
        response.raise_for_status()
        payload = response.json()
        if payload.get('error'):
            raise RuntimeError('ArcGIS audit query was rejected')
        rows = [item['attributes'] for item in payload.get('features', [])]
        if not rows:
            return
        ids = [int(r['OBJECTID']) for r in rows]
        if ids[0] <= last_id or any(ids[i] >= ids[i + 1] for i in range(len(ids)-1)):
            raise RuntimeError('ArcGIS returned unordered or repeated OBJECTIDs; audit stopped')
        yield rows
        last_id = ids[-1]
        if len(rows) < PAGE_SIZE and not payload.get('exceededTransferLimit', False):
            return


def aggregate_audit(pages, *, days=30):
    """Summarize source rows without retaining or emitting individual incident details."""
    counts_by_number = Counter()
    units_by_number = defaultdict(set)
    day_counts = Counter()
    dates_by_number = defaultdict(set)
    numbers_by_date = defaultdict(set)
    same_number_unit_day = Counter()
    rows = missing_number = missing_dispatch = 0
    newest_dispatch = None
    for page in pages:
        for row in page:
            rows += 1
            call_number = str(row.get('EMS_Call_Number') or '').strip()
            if call_number:
                counts_by_number[call_number] += 1
                unit = str(row.get('Unit_Callsign') or '').strip()
                if unit:
                    units_by_number[call_number].add(unit)
            else:
                missing_number += 1
            timestamp = parse_epoch_ms(row.get('Dispatch_Date_Time'))
            if timestamp is None:
                missing_dispatch += 1
            else:
                day = timestamp.astimezone(LOCAL).date().isoformat()
                day_counts[day] += 1
                if call_number:
                    dates_by_number[call_number].add(day)
                    numbers_by_date[day].add(call_number)
                    same_number_unit_day[(call_number, unit, day)] += 1
                if newest_dispatch is None or timestamp > newest_dispatch:
                    newest_dispatch = timestamp

    repeated = [key for key, count in counts_by_number.items() if count > 1]
    additional_rows = sum(counts_by_number[key] - 1 for key in repeated)
    multi_unit_numbers = sum(len(units_by_number[key]) > 1 for key in repeated)
    cross_date_numbers = sum(len(days) >= 2 for days in dates_by_number.values())
    long_span_numbers = sum(
        (date.fromisoformat(max(days)) - date.fromisoformat(min(days))).days >= 7
        for days in dates_by_number.values() if days
    )
    repeated_number_unit_day_groups = sum(count > 1 for count in same_number_unit_day.values())
    return {
        'days_requested': days,
        'source_rows': rows,
        'rows_with_missing_call_number': missing_number,
        'rows_with_missing_dispatch_time': missing_dispatch,
        'distinct_nonempty_call_numbers': len(counts_by_number),
        'call_numbers_seen_more_than_once': len(repeated),
        'additional_rows_sharing_a_call_number': additional_rows,
        'repeated_call_numbers_with_multiple_unit_callsigns': multi_unit_numbers,
        'call_numbers_on_two_or_more_dispatch_dates': cross_date_numbers,
        'call_numbers_spanning_at_least_seven_days': long_span_numbers,
        'call_number_unit_date_groups_with_multiple_rows': repeated_number_unit_day_groups,
        'newest_source_dispatch_utc': newest_dispatch.isoformat() if newest_dispatch else None,
        'daily_counts_local': [
            {'date': d, 'source_rows': day_counts[d],
             'distinct_nonempty_call_numbers_that_day': len(numbers_by_date[d])}
            for d in sorted(day_counts)
        ],
        'interpretation': ('Counts are source table rows, NOT unique incidents. Call numbers seen '
                           'on dates at least seven days apart indicate identifier reuse or '
                           'unexpected source behavior, not an ongoing single incident. '
                           'Same-day distinct call numbers are a diagnostic only, not independently '
                           'validated incident counts. Recently published dates may be incomplete '
                           'or backfilled; compare repeated audit snapshots to test that.'),
    }


def main():
    parser = argparse.ArgumentParser(description='Aggregate audit of EMS source row identity and reporting lag')
    parser.add_argument('--days', type=int, default=30, help='Audit the most recent N days (1-365)')
    parser.add_argument('--output', default='source_audit_summary.json', help='Aggregated JSON output path')
    args = parser.parse_args()
    result = aggregate_audit(fetch_audit_pages(days=args.days), days=args.days)
    from pathlib import Path
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Source rows:', result['source_rows'])
    print('Nonempty distinct call numbers:', result['distinct_nonempty_call_numbers'])
    print('Call numbers seen more than once:', result['call_numbers_seen_more_than_once'])
    print('Additional rows sharing a call number:', result['additional_rows_sharing_a_call_number'])
    print('Repeated numbers across multiple unit callsigns:', result['repeated_call_numbers_with_multiple_unit_callsigns'])
    print('Call numbers seen on 2+ different dispatch dates:', result['call_numbers_on_two_or_more_dispatch_dates'])
    print('Call numbers spanning 7+ calendar days:', result['call_numbers_spanning_at_least_seven_days'])
    print('Call-number + unit + day groups with 2+ rows:', result['call_number_unit_date_groups_with_multiple_rows'])
    print('Rows missing call number:', result['rows_with_missing_call_number'])
    print('Latest source dispatch (UTC):', result['newest_source_dispatch_utc'])
    print('Recent daily published-row counts (Cleveland local dates):')
    for row in result['daily_counts_local'][-14:]:
        print(f"  {row['date']}: {row['source_rows']:,} rows; "
              f"{row['distinct_nonempty_call_numbers_that_day']:,} distinct call numbers on that day")
    print('An aggregate-only report was written to:', args.output)
    print(result['interpretation'])


if __name__ == '__main__':
    main()
