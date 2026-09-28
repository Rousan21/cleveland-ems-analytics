from pathlib import Path
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st


DATABASE_FILE = Path("data/ems_analytics.db")


st.set_page_config(
    page_title="Cleveland EMS Analytics",
    page_icon="🚑",
    layout="wide"
)


# -------------------------------------------------
# LOAD DATA
# -------------------------------------------------

@st.cache_data
def load_data():
    if not DATABASE_FILE.exists():
        return pd.DataFrame()

    connection = sqlite3.connect(DATABASE_FILE)

    df = pd.read_sql_query(
        "SELECT * FROM ems_calls",
        connection
    )

    connection.close()

    date_columns = [
        "Call_Date_Time",
        "Dispatch_Date_Time",
        "On_Scene_Date_Time"
    ]

    for column in date_columns:
        df[column] = pd.to_datetime(
            df[column],
            utc=True,
            errors="coerce"
        ).dt.tz_convert("America/New_York")

    return df


df = load_data()


# -------------------------------------------------
# HEADER
# -------------------------------------------------

st.title("🚑 Cleveland EMS Analytics")

st.write(
    """
    Explore patterns in Cleveland EMS activity, including when calls occur,
    call priorities, and the time between key stages of an EMS call.
    """
)


if df.empty:
    st.error(
        "No EMS database was found. Run the data pipeline first."
    )
    st.stop()


# -------------------------------------------------
# SIDEBAR FILTERS
# -------------------------------------------------

st.sidebar.title("Explore the Data")

st.sidebar.write(
    "Use these filters to update the entire dashboard."
)


priorities = sorted(
    df["Call_Priority"]
    .dropna()
    .astype(str)
    .unique()
)


selected_priorities = st.sidebar.multiselect(
    "Call Priority",
    priorities,
    default=priorities,
    help="Priority codes are shown exactly as they appear in the source data."
)


filtered_df = df[
    df["Call_Priority"]
    .astype(str)
    .isin(selected_priorities)
].copy()


valid_dates = (
    filtered_df["Dispatch_Date_Time"]
    .dropna()
)


if not valid_dates.empty:
    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()

    selected_dates = st.sidebar.date_input(
        "Dispatch Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    if len(selected_dates) == 2:
        start_date = selected_dates[0]
        end_date = selected_dates[1]

        dispatch_dates = (
            filtered_df["Dispatch_Date_Time"]
            .dt.date
        )

        filtered_df = filtered_df[
            dispatch_dates.between(
                start_date,
                end_date
            )
        ]


# -------------------------------------------------
# DATA FOR TIMING METRICS
# -------------------------------------------------

dispatch_times = filtered_df[
    filtered_df["call_to_dispatch_minutes"] >= 0
]["call_to_dispatch_minutes"].dropna()


scene_times = filtered_df[
    filtered_df["call_to_scene_minutes"] >= 0
]["call_to_scene_minutes"].dropna()


# -------------------------------------------------
# DATE RANGE CAPTION
# -------------------------------------------------

filtered_dates = (
    filtered_df["Dispatch_Date_Time"]
    .dropna()
)


if not filtered_dates.empty:
    first_date = (
        filtered_dates.min()
        .strftime("%b %d, %Y")
    )

    last_date = (
        filtered_dates.max()
        .strftime("%b %d, %Y")
    )

    st.caption(
        f"Showing {len(filtered_df):,} records with dispatch timestamps "
        f"from {first_date} through {last_date}"
    )


# -------------------------------------------------
# AT A GLANCE
# -------------------------------------------------

st.header("At a Glance")


col1, col2, col3, col4 = st.columns(4)


col1.metric(
    "Records Shown",
    f"{len(filtered_df):,}",
    help="Number of EMS records currently included after filters are applied."
)


col2.metric(
    "Priority Levels",
    filtered_df["Call_Priority"].nunique(),
    help="Number of different priority codes represented."
)


if not dispatch_times.empty:
    col3.metric(
        "Median Call → Dispatch",
        f"{dispatch_times.median():.1f} min",
        help="Median interval between recorded call and dispatch times."
    )
else:
    col3.metric(
        "Median Call → Dispatch",
        "N/A"
    )


if not scene_times.empty:
    col4.metric(
        "Median Call → Scene",
        f"{scene_times.median():.1f} min",
        help="Median interval between recorded call and on-scene times."
    )
else:
    col4.metric(
        "Median Call → Scene",
        "N/A"
    )


# -------------------------------------------------
# KEY FINDINGS
# -------------------------------------------------

st.subheader("Key Findings")


hour_data = (
    filtered_df["Dispatch_Date_Time"]
    .dropna()
    .dt.hour
)


day_data = (
    filtered_df["Dispatch_Date_Time"]
    .dropna()
    .dt.day_name()
)


priority_data = (
    filtered_df["Call_Priority"]
    .dropna()
    .astype(str)
)


insight1, insight2, insight3, insight4 = st.columns(4)


if not hour_data.empty:
    hour_counts = hour_data.value_counts()

    busiest_hour = hour_counts.idxmax()
    busiest_hour_count = hour_counts.max()

    hour_label = pd.Timestamp(
        year=2000,
        month=1,
        day=1,
        hour=int(busiest_hour)
    ).strftime("%-I %p")

    insight1.metric(
        "Peak Dispatch Hour",
        hour_label,
        f"{busiest_hour_count:,} records"
    )


if not day_data.empty:
    day_counts_summary = day_data.value_counts()

    busiest_day = day_counts_summary.idxmax()
    busiest_day_count = day_counts_summary.max()

    insight2.metric(
        "Busiest Day",
        busiest_day,
        f"{busiest_day_count:,} records"
    )


if not priority_data.empty:
    priority_counts_summary = priority_data.value_counts()

    common_priority = priority_counts_summary.idxmax()
    common_priority_count = priority_counts_summary.max()

    insight3.metric(
        "Most Common Priority",
        f"Priority {common_priority}",
        f"{common_priority_count:,} records"
    )


if not scene_times.empty:
    insight4.metric(
        "Median Call → Scene",
        f"{scene_times.median():.1f} min"
    )


st.divider()


# -------------------------------------------------
# CALL VOLUME
# -------------------------------------------------

st.header("Call Volume")

st.write(
    """
    Daily EMS dispatch activity during the selected time period.
    """
)


daily_calls = (
    filtered_df
    .dropna(subset=["Dispatch_Date_Time"])
    .assign(
        Date=lambda x:
        x["Dispatch_Date_Time"].dt.date
    )
    .groupby("Date")
    .size()
    .reset_index(name="EMS Records")
)


if not daily_calls.empty:
    fig_daily = px.line(
        daily_calls,
        x="Date",
        y="EMS Records",
        markers=True
    )

    fig_daily.update_layout(
        xaxis_title="Dispatch Date",
        yaxis_title="Number of EMS Records",
        hovermode="x unified"
    )

    st.plotly_chart(
        fig_daily,
        use_container_width=True
    )


# -------------------------------------------------
# WHEN ACTIVITY HAPPENS
# -------------------------------------------------

st.header("When EMS Activity Happens")

st.write(
    """
    These charts show how dispatch activity changes by time of day
    and day of week.
    """
)


left, right = st.columns(2)


with left:
    st.subheader("Dispatches by Hour")

    hourly_calls = (
        filtered_df
        .dropna(subset=["Dispatch_Date_Time"])
        ["Dispatch_Date_Time"]
        .dt.hour
        .value_counts()
        .sort_index()
        .reindex(
            range(24),
            fill_value=0
        )
        .reset_index()
    )

    hourly_calls.columns = [
        "Hour",
        "EMS Records"
    ]

    hourly_calls["Time"] = hourly_calls["Hour"].apply(
        lambda hour:
        pd.Timestamp(
            year=2000,
            month=1,
            day=1,
            hour=hour
        ).strftime("%-I %p")
    )

    fig_hour = px.bar(
        hourly_calls,
        x="Time",
        y="EMS Records"
    )

    fig_hour.update_layout(
        xaxis_title="Hour of Day",
        yaxis_title="Number of EMS Records"
    )

    st.plotly_chart(
        fig_hour,
        use_container_width=True
    )


with right:
    st.subheader("Dispatches by Day")

    day_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday"
    ]

    day_counts = (
        filtered_df
        .dropna(subset=["Dispatch_Date_Time"])
        ["Dispatch_Date_Time"]
        .dt.day_name()
        .value_counts()
        .reindex(
            day_order,
            fill_value=0
        )
        .reset_index()
    )

    day_counts.columns = [
        "Day",
        "EMS Records"
    ]

    fig_day = px.bar(
        day_counts,
        x="Day",
        y="EMS Records",
        category_orders={
            "Day": day_order
        }
    )

    fig_day.update_layout(
        xaxis_title="Day of Week",
        yaxis_title="Number of EMS Records"
    )

    st.plotly_chart(
        fig_day,
        use_container_width=True
    )


# -------------------------------------------------
# PRIORITY DISTRIBUTION
# -------------------------------------------------

st.header("Call Priority Distribution")

st.write(
    """
    Distribution of the priority codes supplied by the Cleveland EMS dataset.
    """
)


priority_counts = (
    filtered_df["Call_Priority"]
    .dropna()
    .astype(str)
    .value_counts()
    .sort_index()
    .reset_index()
)


priority_counts.columns = [
    "Priority",
    "EMS Records"
]


if not priority_counts.empty:
    priority_counts["Percent"] = (
        priority_counts["EMS Records"]
        / priority_counts["EMS Records"].sum()
        * 100
    )

    priority_counts["Label"] = (
        priority_counts["Percent"]
        .round(1)
        .astype(str)
        + "%"
    )

    fig_priority = px.bar(
        priority_counts,
        x="Priority",
        y="EMS Records",
        text="Label",
        hover_data={
            "Percent": ":.1f"
        }
    )

    fig_priority.update_layout(
        xaxis_title="Priority Code",
        yaxis_title="Number of EMS Records"
    )

    fig_priority.update_traces(
        textposition="outside"
    )

    st.plotly_chart(
        fig_priority,
        use_container_width=True
    )


st.caption(
    "Priority codes are preserved exactly as they appear in the source dataset."
)


# -------------------------------------------------
# TIMING ANALYSIS
# -------------------------------------------------

st.header("Timing Between EMS Events")

st.write(
    """
    Distribution of recorded call-to-dispatch and call-to-scene intervals.
    Charts are limited to the 99th percentile for readability; original
    records are preserved.
    """
)


left, right = st.columns(2)


with left:
    st.subheader("Call → Dispatch")

    if not dispatch_times.empty:
        dispatch_limit = (
            dispatch_times.quantile(0.99)
        )

        dispatch_chart = dispatch_times[
            dispatch_times <= dispatch_limit
        ]

        fig_dispatch = px.histogram(
            x=dispatch_chart,
            nbins=35,
            labels={
                "x": "Minutes"
            }
        )

        fig_dispatch.update_layout(
            xaxis_title="Minutes",
            yaxis_title="Number of Records",
            showlegend=False
        )

        st.plotly_chart(
            fig_dispatch,
            use_container_width=True
        )

        st.caption(
            f"Median: {dispatch_times.median():.1f} minutes"
        )


with right:
    st.subheader("Call → Scene")

    if not scene_times.empty:
        scene_limit = (
            scene_times.quantile(0.99)
        )

        scene_chart = scene_times[
            scene_times <= scene_limit
        ]

        fig_scene = px.histogram(
            x=scene_chart,
            nbins=35,
            labels={
                "x": "Minutes"
            }
        )

        fig_scene.update_layout(
            xaxis_title="Minutes",
            yaxis_title="Number of Records",
            showlegend=False
        )

        st.plotly_chart(
            fig_scene,
            use_container_width=True
        )

        st.caption(
            f"Median: {scene_times.median():.1f} minutes"
        )


# -------------------------------------------------
# DATA COVERAGE
# -------------------------------------------------

st.header("About the Data")


st.info(
    """
    This dashboard uses public Cleveland EMS call records and focuses on
    aggregate operational patterns rather than individual incidents.

    Timing values are calculated from available timestamps and should be
    interpreted as call-to-event intervals rather than official EMS
    performance metrics.
    """
)


with st.expander("Data Coverage"):
    total_records = len(df)

    missing_dispatch = (
        df["Dispatch_Date_Time"]
        .isna()
        .sum()
    )

    missing_call = (
        df["Call_Date_Time"]
        .isna()
        .sum()
    )

    missing_scene = (
        df["On_Scene_Date_Time"]
        .isna()
        .sum()
    )

    coverage1, coverage2, coverage3 = st.columns(3)

    coverage1.metric(
        "Records Downloaded",
        f"{total_records:,}"
    )

    coverage2.metric(
        "Missing Dispatch Times",
        f"{missing_dispatch:,}"
    )

    coverage3.metric(
        "Records Currently Shown",
        f"{len(filtered_df):,}"
    )

    st.write(
        f"**Missing call timestamps:** {missing_call:,}"
    )

    st.write(
        f"**Missing on-scene timestamps:** {missing_scene:,}"
    )


# -------------------------------------------------
# DATA QUALITY
# -------------------------------------------------

with st.expander("Data Quality Details"):
    st.write(
        """
        Real-world operational data can contain missing timestamps
        and unusual values. Missing records are preserved rather than
        automatically deleted.
        """
    )

    missing_values = (
        filtered_df
        .isna()
        .sum()
        .reset_index()
    )

    missing_values.columns = [
        "Field",
        "Missing Records"
    ]

    st.dataframe(
        missing_values,
        use_container_width=True,
        hide_index=True
    )

    negative_dispatch = (
        filtered_df["call_to_dispatch_minutes"] < 0
    ).sum()

    negative_scene = (
        filtered_df["call_to_scene_minutes"] < 0
    ).sum()

    st.write(
        "**Negative call → dispatch intervals:**",
        int(negative_dispatch)
    )

    st.write(
        "**Negative call → scene intervals:**",
        int(negative_scene)
    )


# -------------------------------------------------
# SAMPLE RECORDS
# -------------------------------------------------

with st.expander("View Sample Records"):
    display_columns = [
        "Call_Priority",
        "Call_Date_Time",
        "Dispatch_Date_Time",
        "On_Scene_Date_Time",
        "call_to_dispatch_minutes",
        "call_to_scene_minutes"
    ]

    sample_df = (
        filtered_df[
            display_columns
        ]
        .head(100)
        .copy()
    )

    sample_df = sample_df.rename(
        columns={
            "Call_Priority":
                "Priority",

            "Call_Date_Time":
                "Call Time",

            "Dispatch_Date_Time":
                "Dispatch Time",

            "On_Scene_Date_Time":
                "On Scene Time",

            "call_to_dispatch_minutes":
                "Call → Dispatch (min)",

            "call_to_scene_minutes":
                "Call → Scene (min)"
        }
    )

    st.dataframe(
        sample_df,
        use_container_width=True,
        hide_index=True
    )


st.divider()


st.caption(
    "Built with Python • pandas • SQLite • Plotly • Streamlit"
)