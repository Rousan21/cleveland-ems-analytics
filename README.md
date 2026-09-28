# Cleveland EMS Analytics

An interactive data analytics project exploring Cleveland EMS call patterns using Python, SQL, and public EMS data.

## Project Overview

This project builds a small end-to-end data pipeline that:

1. Retrieves EMS records from a public API
2. Cleans and processes the data with pandas
3. Stores the processed data in SQLite
4. Uses SQL for analysis
5. Visualizes patterns through an interactive Streamlit dashboard

The dashboard explores:

- EMS call volume
- Call priority distribution
- Dispatch activity by hour
- Dispatch activity by day of week
- Call-to-dispatch intervals
- Call-to-scene intervals
- Missing and unusual data

## Technologies

- Python
- pandas
- requests
- SQL
- SQLite
- Streamlit
- Plotly

## Project Structure

```text
cleveland-ems-analytics/
├── app.py
├── requirements.txt
├── data/
├── sql/
│   └── analysis.sql
└── src/
    ├── load_data.py
    └── build_database.py