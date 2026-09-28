-- Total number of EMS records
SELECT COUNT(*) AS total_calls
FROM ems_calls;


-- Calls by priority
SELECT
    Call_Priority,
    COUNT(*) AS total_calls
FROM ems_calls
GROUP BY Call_Priority
ORDER BY total_calls DESC;


-- Calls by dispatch hour
SELECT
    Dispatch_Hour,
    COUNT(*) AS total_calls
FROM ems_calls
WHERE Dispatch_Hour IS NOT NULL
GROUP BY Dispatch_Hour
ORDER BY Dispatch_Hour;


-- Calls by day of week
SELECT
    Dispatch_Day,
    COUNT(*) AS total_calls
FROM ems_calls
WHERE Dispatch_Day IS NOT NULL
GROUP BY Dispatch_Day
ORDER BY total_calls DESC;


-- Average call-to-dispatch interval
SELECT
    AVG(call_to_dispatch_minutes)
        AS average_call_to_dispatch_minutes
FROM ems_calls
WHERE call_to_dispatch_minutes >= 0;


-- Average call-to-scene interval
SELECT
    AVG(call_to_scene_minutes)
        AS average_call_to_scene_minutes
FROM ems_calls
WHERE call_to_scene_minutes >= 0;


-- Missing timestamp counts
SELECT
    SUM(
        CASE
            WHEN Call_Date_Time IS NULL THEN 1
            ELSE 0
        END
    ) AS missing_call_times,

    SUM(
        CASE
            WHEN Dispatch_Date_Time IS NULL THEN 1
            ELSE 0
        END
    ) AS missing_dispatch_times,

    SUM(
        CASE
            WHEN On_Scene_Date_Time IS NULL THEN 1
            ELSE 0
        END
    ) AS missing_scene_times

FROM ems_calls;