from pathlib import Path

import pandas as pd
import requests


API_URL = (
    "https://services2.arcgis.com/CyVvlIiUfRBmMQuu/"
    "arcgis/rest/services/EMS_Calls_for_Service2/FeatureServer/0/query"
)

OUTPUT_FILE = Path("data/ems_calls.csv")

PAGE_SIZE = 1000
MAX_RECORDS = 5000


def fetch_ems_data():
    records = []
    offset = 0

    print("Downloading Cleveland EMS records...")

    while len(records) < MAX_RECORDS:

        params = {
            "where": "1=1",
            "outFields": (
                "OBJECTID,"
                "Call_Priority,"
                "Call_Date_Time,"
                "Dispatch_Date_Time,"
                "On_Scene_Date_Time"
            ),
            "returnGeometry": "false",
            "resultRecordCount": PAGE_SIZE,
            "resultOffset": offset,
            "orderByFields": "OBJECTID DESC",
            "f": "json"
        }

        response = requests.get(
            API_URL,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        if "error" in data:
            raise RuntimeError(data["error"])

        features = data.get("features", [])

        if not features:
            break

        new_records = [
            feature["attributes"]
            for feature in features
        ]

        records.extend(new_records)

        print(
            f"Downloaded "
            f"{min(len(records), MAX_RECORDS):,} records"
        )

        if len(new_records) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return records[:MAX_RECORDS]


def clean_data(records):

    df = pd.DataFrame(records)

    date_columns = [
        "Call_Date_Time",
        "Dispatch_Date_Time",
        "On_Scene_Date_Time"
    ]

    for column in date_columns:

        df[column] = pd.to_datetime(
            df[column],
            unit="ms",
            utc=True,
            errors="coerce"
        ).dt.tz_convert(
            "America/New_York"
        )

    df["call_to_dispatch_minutes"] = (
        df["Dispatch_Date_Time"]
        - df["Call_Date_Time"]
    ).dt.total_seconds() / 60

    df["call_to_scene_minutes"] = (
        df["On_Scene_Date_Time"]
        - df["Call_Date_Time"]
    ).dt.total_seconds() / 60

    df["Dispatch_Date"] = (
        df["Dispatch_Date_Time"].dt.date
    )

    df["Dispatch_Hour"] = (
        df["Dispatch_Date_Time"].dt.hour
    )

    df["Dispatch_Day"] = (
        df["Dispatch_Date_Time"].dt.day_name()
    )

    return df


def save_data(df):

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        f"\nSaved cleaned data to "
        f"{OUTPUT_FILE}"
    )


def show_summary(df):

    print("\nDataset Summary")
    print("----------------")

    print(
        f"Records: {len(df):,}"
    )

    valid_dates = (
        df["Dispatch_Date_Time"]
        .dropna()
    )

    if not valid_dates.empty:

        print(
            "Dispatch date range:",
            valid_dates.min().date(),
            "to",
            valid_dates.max().date()
        )

    print("\nMissing values:")

    print(
        df[
            [
                "Call_Date_Time",
                "Dispatch_Date_Time",
                "On_Scene_Date_Time"
            ]
        ].isna().sum()
    )


def main():

    records = fetch_ems_data()

    df = clean_data(records)

    save_data(df)

    show_summary(df)


if __name__ == "__main__":
    main()