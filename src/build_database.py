from pathlib import Path
import sqlite3

import pandas as pd


CSV_FILE = Path("data/ems_calls.csv")
DATABASE_FILE = Path("data/ems_analytics.db")


def main():

    if not CSV_FILE.exists():
        raise FileNotFoundError(
            "ems_calls.csv was not found. Run load_data.py first."
        )

    print("Reading EMS data...")

    df = pd.read_csv(CSV_FILE)

    print(f"Loaded {len(df)} records.")

    print("Creating SQLite database...")

    connection = sqlite3.connect(DATABASE_FILE)

    df.to_sql(
        "ems_calls",
        connection,
        if_exists="replace",
        index=False
    )

    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_priority
        ON ems_calls(Call_Priority)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dispatch_time
        ON ems_calls(Dispatch_Date_Time)
        """
    )

    connection.commit()
    connection.close()

    print(f"Database created: {DATABASE_FILE}")
    print(f"{len(df)} records added to ems_calls.")


if __name__ == "__main__":
    main()