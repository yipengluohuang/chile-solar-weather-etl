USE chile_solar_weather;

-- 查询 1：当前数据库一共有多少条每日天气记录？
SELECT COUNT(*) AS total_weather_rows FROM weather_daily;

-- 查询 2：验证 city + date 是否存在重复，正常结果应为空。
SELECT city, date, COUNT(*) AS duplicate_count
FROM weather_daily
GROUP BY city, date
HAVING COUNT(*) > 1;

-- 查询 3：每个月的太阳辐射、日照、温度、降水和风速表现如何？
SELECT *
FROM vw_monthly_solar_summary
ORDER BY city, month;

-- 查询 4：最近 30 天中短波辐射最高的 10 天是哪几天？
SELECT city, date, shortwave_radiation_mj_m2,
       sunshine_duration_hours, temperature_max_c
FROM vw_recent_30_days
ORDER BY shortwave_radiation_mj_m2 DESC
LIMIT 10;

-- 查询 5：哪些日期出现了降水，这些日期的日照和辐射是多少？
SELECT city, date, precipitation_mm,
       sunshine_duration_hours, shortwave_radiation_mj_m2
FROM vw_weather_daily
WHERE precipitation_mm > 0
ORDER BY precipitation_mm DESC, date DESC;

-- 查询 6：最近的管道运行是否成功，各次运行插入和更新了多少行？
SELECT run_id, started_at, finished_at, status, api_rows,
       historical_rows_before, inserted_rows, updated_rows,
       final_database_rows, failed_quality_checks, error_message
FROM pipeline_runs
ORDER BY run_id DESC
LIMIT 20;

-- 查询 7：最近一次管道运行的状态、耗时和质量失败数是什么？
SELECT run_id, started_at, finished_at, status, duration_seconds,
       inserted_rows, updated_rows, failed_quality_checks, error_message
FROM vw_latest_pipeline_run;

-- 查询 8：最近 30 次运行的成功率是多少？
SELECT COUNT(*) AS run_count,
       SUM(status = 'SUCCESS') AS successful_runs,
       ROUND(100 * AVG(status = 'SUCCESS'), 2) AS success_rate_percent
FROM (
    SELECT status
    FROM vw_pipeline_run_history
    ORDER BY run_id DESC
    LIMIT 30
) AS recent_runs;

-- 查询 9：最新天气数据日期、数据陈旧天数和最近成功时间是什么？
SELECT latest_data_date, data_age_days, total_weather_rows,
       duplicate_key_count, latest_success_time
FROM vw_data_freshness;

-- 查询 10：每个月实际有多少数据天，约占该月日历天数的百分之多少？
SELECT city, month, data_days,
       DAY(LAST_DAY(month)) AS calendar_days,
       ROUND(100 * data_days / DAY(LAST_DAY(month)), 2) AS completeness_percent
FROM vw_monthly_solar_summary
ORDER BY city, month;

-- 查询 11：每个月的总辐射与平均每日照小时趋势如何？
SELECT city, month, total_shortwave_radiation_mj_m2,
       average_sunshine_hours, data_days
FROM vw_monthly_solar_summary
ORDER BY city, month;

-- 查询 12：weather_daily 的最早与最新日期是什么？
SELECT MIN(date) AS earliest_data_date,
       MAX(date) AS latest_data_date
FROM weather_daily;
