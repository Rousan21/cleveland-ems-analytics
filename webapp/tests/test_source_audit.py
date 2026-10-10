from datetime import datetime, timezone

import pytest
from audit_source import aggregate_audit, fetch_audit_pages


def ms(iso):
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def test_aggregate_duplicate_call_number_and_hide_identifiers():
    rows = [[
        {'OBJECTID': 1, 'EMS_Call_Number': 'INC-SENSITIVE-123', 'Unit_Callsign': 'UNIT-A',
         'Dispatch_Date_Time': ms('2026-10-08T23:30:00+00:00')},
        {'OBJECTID': 2, 'EMS_Call_Number': 'INC-SENSITIVE-123', 'Unit_Callsign': 'UNIT-B',
         'Dispatch_Date_Time': ms('2026-10-09T01:30:00+00:00')},
        {'OBJECTID': 3, 'EMS_Call_Number': 'INC-SENSITIVE-456', 'Unit_Callsign': 'UNIT-B',
         'Dispatch_Date_Time': ms('2026-10-09T22:30:00+00:00')},
        {'OBJECTID': 4, 'EMS_Call_Number': None, 'Unit_Callsign': None,
         'Dispatch_Date_Time': None},
    ]]
    result = aggregate_audit(rows, days=30)
    assert result['source_rows'] == 4
    assert result['distinct_nonempty_call_numbers'] == 2
    assert result['call_numbers_seen_more_than_once'] == 1
    assert result['additional_rows_sharing_a_call_number'] == 1
    assert result['repeated_call_numbers_with_multiple_unit_callsigns'] == 1
    assert result['rows_with_missing_call_number'] == 1
    assert result['rows_with_missing_dispatch_time'] == 1
    assert result['daily_counts_local'] == [
        {'date': '2026-10-08', 'source_rows': 2, 'distinct_nonempty_call_numbers_that_day': 1, 'distinct_call_unit_exact_dispatch_keys_that_day': 2},
        {'date': '2026-10-09', 'source_rows': 1, 'distinct_nonempty_call_numbers_that_day': 1, 'distinct_call_unit_exact_dispatch_keys_that_day': 1}]
    assert result['call_numbers_on_two_or_more_dispatch_dates'] == 0
    assert result['call_numbers_spanning_at_least_seven_days'] == 0
    assert result['call_number_unit_date_groups_with_multiple_rows'] == 0
    assert 'INC-SENSITIVE' not in str(result)
    assert 'UNIT-A' not in str(result)


class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class FakeSource:
    def __init__(self): self.calls = []
    def get(self, url, params, timeout):
        self.calls.append(params)
        assert 'EMS_Call_Number' in params['outFields']
        assert 'Block_Location' not in params['outFields']
        assert params['returnGeometry'] == 'false'
        if len(self.calls) == 1:
            return FakeResponse({'features': [{'attributes': {'OBJECTID': 10}},
                                               {'attributes': {'OBJECTID': 11}}]})
        return FakeResponse({'features': [{'attributes': {'OBJECTID': 12}}]})


def test_audit_source_paginates_safely(monkeypatch):
    import audit_source
    monkeypatch.setattr(audit_source, 'PAGE_SIZE', 2)
    fake = FakeSource()
    pages = list(fetch_audit_pages(days=30, session=fake,
                                   now=datetime(2026, 10, 10, tzinfo=timezone.utc)))
    assert [p[0]['OBJECTID'] for p in pages] == [10, 12]
    assert len(fake.calls) == 2
    assert 'OBJECTID > 11' in fake.calls[1]['where']
    assert "2026-09-10" in fake.calls[0]['where']


def test_audit_rejects_bad_limits_and_duplicate_rows():
    with pytest.raises(ValueError):
        list(fetch_audit_pages(days=0))
    class BadSource:
        def get(self, url, params, timeout):
            return FakeResponse({'features': [{'attributes': {'OBJECTID': 2}},
                                               {'attributes': {'OBJECTID': 2}}]})
    with pytest.raises(RuntimeError, match='unordered or repeated'):
        list(fetch_audit_pages(days=30, session=BadSource()))


def test_public_dashboard_labels_are_record_based():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / 'templates' / 'index.html').read_text()
    assert 'EMS dispatch records' in html
    assert 'not verified unique incidents' in html


def test_audit_identifiers_reused_far_apart_and_same_day_unit_repeats():
    rows = [[
        {'EMS_Call_Number': 'REUSE-1', 'Unit_Callsign': 'CAR-A',
         'Dispatch_Date_Time': ms('2026-09-29T17:00:00+00:00')},
        {'EMS_Call_Number': 'REUSE-1', 'Unit_Callsign': 'CAR-A',
         'Dispatch_Date_Time': ms('2026-09-29T18:00:00+00:00')},
        {'EMS_Call_Number': 'REUSE-1', 'Unit_Callsign': 'CAR-A',
         'Dispatch_Date_Time': ms('2026-10-08T17:00:00+00:00')},
        {'EMS_Call_Number': 'OTHER-2', 'Unit_Callsign': 'CAR-A',
         'Dispatch_Date_Time': ms('2026-10-08T17:00:00+00:00')},
    ]]
    result = aggregate_audit(rows)
    assert result['call_numbers_on_two_or_more_dispatch_dates'] == 1
    assert result['call_numbers_spanning_at_least_seven_days'] == 1
    assert result['call_number_unit_date_groups_with_multiple_rows'] == 1
    assert result['daily_counts_local'] == [
        {'date': '2026-09-29', 'source_rows': 2, 'distinct_nonempty_call_numbers_that_day': 1, 'distinct_call_unit_exact_dispatch_keys_that_day': 2},
        {'date': '2026-10-08', 'source_rows': 2, 'distinct_nonempty_call_numbers_that_day': 2, 'distinct_call_unit_exact_dispatch_keys_that_day': 2}]
    assert 'REUSE-1' not in str(result)
    assert 'CAR-A' not in str(result)


def test_multiple_rows_same_call_unit_dispatch_are_counted_without_exposing_identifiers():
    stamp = ms('2026-10-02T12:34:00+00:00')
    rows = [[
        {'EMS_Call_Number': 'SECRET-A', 'Unit_Callsign': 'EMS7', 'Dispatch_Date_Time': stamp},
        {'EMS_Call_Number': 'SECRET-A', 'Unit_Callsign': 'EMS7', 'Dispatch_Date_Time': stamp},
        {'EMS_Call_Number': 'SECRET-A', 'Unit_Callsign': 'EMS7', 'Dispatch_Date_Time': stamp},
        {'EMS_Call_Number': 'SECRET-A', 'Unit_Callsign': 'EMS8', 'Dispatch_Date_Time': stamp},
        {'EMS_Call_Number': 'SECRET-B', 'Unit_Callsign': 'EMS7', 'Dispatch_Date_Time': stamp},
    ]]
    result = aggregate_audit(rows)
    assert result['source_rows'] == 5
    assert result['call_number_unit_exact_dispatch_groups_with_multiple_rows'] == 1
    assert result['extra_rows_with_same_call_unit_exact_dispatch'] == 2
    assert result['largest_call_unit_exact_dispatch_group'] == 3
    assert result['call_unit_exact_dispatch_group_multiplicity'] == [
        {'rows_per_key': '1', 'groups': 2},
        {'rows_per_key': '3', 'groups': 1}]
    assert result['daily_counts_local'] == [{
        'date': '2026-10-02', 'source_rows': 5,
        'distinct_nonempty_call_numbers_that_day': 2,
        'distinct_call_unit_exact_dispatch_keys_that_day': 3,
    }]
    assert 'SECRET-A' not in str(result)
    assert 'EMS7' not in str(result)
