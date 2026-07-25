-- 每日完整数据视图，供 Power BI 读取明细。
CREATE OR REPLACE VIEW vw_weather_daily AS
SELECT
    date,
    city,
    temperature_max_c,
    temperature_min_c,
    sunshine_duration_seconds,
    sunshine_duration_hours,
    shortwave_radiation_mj_m2,
    precipitation_mm,
    wind_speed_max_kmh,
    retrieved_at,
    created_at,
    updated_at
FROM weather_daily;

-- 城市月度太阳资源与天气汇总。
CREATE OR REPLACE VIEW vw_monthly_solar_summary AS
SELECT
    city,
    CAST(DATE_FORMAT(date, '%Y-%m-01') AS DATE) AS month,
    AVG(temperature_max_c) AS average_temperature_max_c,
    AVG(temperature_min_c) AS average_temperature_min_c,
    AVG(sunshine_duration_hours) AS average_sunshine_hours,
    SUM(shortwave_radiation_mj_m2) AS total_shortwave_radiation_mj_m2,
    SUM(precipitation_mm) AS total_precipitation_mm,
    AVG(wind_speed_max_kmh) AS average_wind_speed_max_kmh,
    COUNT(DISTINCT date) AS data_days
FROM weather_daily
GROUP BY city, CAST(DATE_FORMAT(date, '%Y-%m-01') AS DATE);

-- 最近 30 个日历日明细，供 Power BI 快速加载近期数据。
CREATE OR REPLACE VIEW vw_recent_30_days AS
SELECT
    date,
    city,
    temperature_max_c,
    temperature_min_c,
    sunshine_duration_seconds,
    sunshine_duration_hours,
    shortwave_radiation_mj_m2,
    precipitation_mm,
    wind_speed_max_kmh,
    retrieved_at,
    created_at,
    updated_at
FROM weather_daily
WHERE date >= CURRENT_DATE - INTERVAL 29 DAY;

-- 管道运行历史，增加耗时和成功标记，供 Power BI 监控趋势。
CREATE OR REPLACE VIEW vw_pipeline_run_history AS
SELECT
    run_id,
    started_at,
    finished_at,
    status,
    api_rows,
    historical_rows_before,
    inserted_rows,
    updated_rows,
    final_database_rows,
    failed_quality_checks,
    error_message,
    CASE
        WHEN finished_at IS NULL THEN NULL
        ELSE TIMESTAMPDIFF(MICROSECOND, started_at, finished_at) / 1000000.0
    END AS duration_seconds,
    CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END AS success_flag
FROM pipeline_runs;

-- 最近一次管道运行，供 Power BI 状态卡片直接使用。
CREATE OR REPLACE VIEW vw_latest_pipeline_run AS
SELECT *
FROM vw_pipeline_run_history
WHERE run_id = (SELECT MAX(run_id) FROM pipeline_runs);

-- 天气数据新鲜度和最近成功时间，不复制任何天气明细。
CREATE OR REPLACE VIEW vw_data_freshness AS
SELECT
    weather.latest_data_date,
    DATEDIFF(CURRENT_DATE, weather.latest_data_date) AS data_age_days,
    weather.total_weather_rows,
    duplicates.duplicate_key_count,
    runs.latest_success_time
FROM (
    SELECT
        MAX(date) AS latest_data_date,
        COUNT(*) AS total_weather_rows
    FROM weather_daily
) AS weather
CROSS JOIN (
    SELECT COUNT(*) AS duplicate_key_count
    FROM (
        SELECT city, date
        FROM weather_daily
        GROUP BY city, date
        HAVING COUNT(*) > 1
    ) AS duplicate_groups
) AS duplicates
CROSS JOIN (
    SELECT MAX(finished_at) AS latest_success_time
    FROM pipeline_runs
    WHERE status = 'SUCCESS'
) AS runs;
