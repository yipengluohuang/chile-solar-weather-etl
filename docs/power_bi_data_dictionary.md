# Power BI 数据字典

本数据字典面向数据库 `chile_solar_weather`。Power BI 建议优先连接视图，不直接修改基础表。

## 推荐视图

- `vw_weather_daily`：每日天气与太阳资源完整明细。
- `vw_monthly_solar_summary`：按城市和月份汇总的分析层。
- `vw_recent_30_days`：最近 30 个日历日明细，适合快速刷新页面。
- `vw_latest_pipeline_run`：最近一次管道运行，适合状态卡片。
- `vw_pipeline_run_history`：运行历史、耗时和成功标记。
- `vw_data_freshness`：最新数据日期、陈旧天数、行数、重复键和最近成功时间。

`vw_recent_30_days` 与 `vw_weather_daily` 使用相同字段，仅筛选最近 30 日。

## vw_weather_daily / vw_recent_30_days

| 字段名 | MySQL 数据类型 | 中文含义 | 数据来源 | 可为空 | 建议 Power BI 格式 |
| --- | --- | --- | --- | --- | --- |
| `date` | `DATE` | 天气观测或预测日期 | Open-Meteo `daily.time` | 否 | 日期 `yyyy-MM-dd` |
| `city` | `VARCHAR(100)` | 城市名称 | 配置值 `Antofagasta` | 否 | 文本 |
| `temperature_max_c` | `DECIMAL(6,2)` | 当日最高气温，摄氏度 | `temperature_2m_max` | 是 | 小数，2位；单位 °C |
| `temperature_min_c` | `DECIMAL(6,2)` | 当日最低气温，摄氏度 | `temperature_2m_min` | 是 | 小数，2位；单位 °C |
| `sunshine_duration_seconds` | `DECIMAL(12,2)` | 当日日照持续秒数 | `sunshine_duration` | 是 | 小数，2位；单位秒 |
| `sunshine_duration_hours` | `DECIMAL(8,4)` | 当日日照持续小时数 | 秒数除以3600 | 是 | 小数，2至4位；单位小时 |
| `shortwave_radiation_mj_m2` | `DECIMAL(10,2)` | 当日短波辐射总量 | `shortwave_radiation_sum` | 是 | 小数，2位；单位 MJ/m² |
| `precipitation_mm` | `DECIMAL(10,2)` | 当日降水总量 | `precipitation_sum` | 是 | 小数，2位；单位 mm |
| `wind_speed_max_kmh` | `DECIMAL(10,2)` | 当日10米最大风速 | `wind_speed_10m_max` | 是 | 小数，2位；单位 km/h |
| `retrieved_at` | `DATETIME(6)` | 本条数据最近一次抓取时间，按UTC存储 | ETL运行时间 | 否 | 日期/时间 `yyyy-MM-dd HH:mm:ss` |
| `created_at` | `TIMESTAMP(6)` | 数据库首次插入时间 | MySQL自动生成 | 否 | 日期/时间 |
| `updated_at` | `TIMESTAMP(6)` | 数据库最近一次UPSERT更新时间 | MySQL自动生成 | 否 | 日期/时间 |

## vw_monthly_solar_summary

| 字段名 | 建议数据类型 | 中文含义 | 数据来源 | 可为空 | 建议 Power BI 格式 |
| --- | --- | --- | --- | --- | --- |
| `city` | 文本 | 城市名称 | `weather_daily.city` | 否 | 文本 |
| `month` | 日期 | 月份第一天 | 从 `date` 截取月份 | 否 | `yyyy-MM` |
| `average_temperature_max_c` | 小数 | 月平均最高气温 | `AVG(temperature_max_c)` | 是 | 小数，2位；°C |
| `average_temperature_min_c` | 小数 | 月平均最低气温 | `AVG(temperature_min_c)` | 是 | 小数，2位；°C |
| `average_sunshine_hours` | 小数 | 月平均每日照小时数 | `AVG(sunshine_duration_hours)` | 是 | 小数，2位；小时 |
| `total_shortwave_radiation_mj_m2` | 小数 | 月短波辐射总量 | `SUM(shortwave_radiation_mj_m2)` | 是 | 小数，2位；MJ/m² |
| `total_precipitation_mm` | 小数 | 月降水总量 | `SUM(precipitation_mm)` | 是 | 小数，2位；mm |
| `average_wind_speed_max_kmh` | 小数 | 月平均每日最大风速 | `AVG(wind_speed_max_kmh)` | 是 | 小数，2位；km/h |
| `data_days` | 整数 | 当月拥有数据的不同日期数 | `COUNT(DISTINCT date)` | 否 | 整数 |

## pipeline_runs

| 字段名 | MySQL 数据类型 | 中文含义 |
| --- | --- | --- |
| `run_id` | `BIGINT UNSIGNED` | 每次管道运行的自增编号 |
| `started_at` | `DATETIME(6)` | 运行开始时间 |
| `finished_at` | `DATETIME(6)` | 运行结束时间 |
| `status` | `ENUM` | `RUNNING`、`SUCCESS` 或 `FAILED` |
| `api_rows` | `INT UNSIGNED` | 本次 API 返回行数 |
| `historical_rows_before` | `INT UNSIGNED` | 写入前数据库历史行数 |
| `inserted_rows` | `INT UNSIGNED` | 本次新增联合键数量 |
| `updated_rows` | `INT UNSIGNED` | 本次更新已有联合键数量 |
| `final_database_rows` | `INT UNSIGNED` | 运行结束时天气表总行数 |
| `failed_quality_checks` | `INT UNSIGNED` | 失败的数据质量检查数量 |
| `error_message` | `TEXT` | 失败原因；成功时为空 |

## vw_latest_pipeline_run / vw_pipeline_run_history

两个视图字段相同；`vw_latest_pipeline_run` 只返回最大 `run_id` 的一行，历史视图返回全部运行记录。

| 字段名 | MySQL 数据类型 | 中文含义 | 数据来源 | 可为空 | 建议 Power BI 格式 |
| --- | --- | --- | --- | --- | --- |
| `run_id` | `BIGINT UNSIGNED` | 管道运行编号 | `pipeline_runs` | 否 | 整数 |
| `started_at` | `DATETIME(6)` | 开始时间，UTC | `pipeline_runs` | 否 | 日期/时间 |
| `finished_at` | `DATETIME(6)` | 结束时间，UTC | `pipeline_runs` | 是 | 日期/时间 |
| `status` | `ENUM` | RUNNING、SUCCESS 或 FAILED | `pipeline_runs` | 否 | 文本 |
| `api_rows` | `INT UNSIGNED` | API 返回行数 | ETL 审计 | 否 | 整数 |
| `historical_rows_before` | `INT UNSIGNED` | 写入前天气总行数 | ETL 审计 | 否 | 整数 |
| `inserted_rows` | `INT UNSIGNED` | 新增联合键数量 | UPSERT 统计 | 否 | 整数 |
| `updated_rows` | `INT UNSIGNED` | 更新联合键数量 | UPSERT 统计 | 否 | 整数 |
| `final_database_rows` | `INT UNSIGNED` | 结束时天气总行数 | ETL 审计 | 否 | 整数 |
| `failed_quality_checks` | `INT UNSIGNED` | 质量检查 FAIL 数 | 质量报告 | 否 | 整数 |
| `error_message` | `TEXT` | 失败原因 | 异常处理 | 是 | 文本 |
| `duration_seconds` | `DECIMAL` | 本次运行耗时秒数 | 结束时间减开始时间 | 是 | 小数，2位；秒 |
| `success_flag` | `INTEGER` | 成功为1，其他状态为0 | 从 `status` 计算 | 否 | 整数/不汇总 |

## vw_data_freshness

| 字段名 | MySQL 数据类型 | 中文含义 | 数据来源 | 可为空 | 建议 Power BI 格式 |
| --- | --- | --- | --- | --- | --- |
| `latest_data_date` | `DATE` | weather_daily 最新日期 | `MAX(date)` | 是 | 日期 `yyyy-MM-dd` |
| `data_age_days` | `BIGINT` | 最新日期距 MySQL 当前日期的天数 | `DATEDIFF` | 是 | 整数；天 |
| `total_weather_rows` | `BIGINT` | 天气表总行数 | `COUNT(*)` | 否 | 整数 |
| `duplicate_key_count` | `BIGINT` | 重复 city + date 组合数 | 分组重复检查 | 否 | 整数 |
| `latest_success_time` | `DATETIME(6)` | 最近 SUCCESS 结束时间，UTC | `pipeline_runs` | 是 | 日期/时间 |

## Power BI 建模建议

- 将 `date` 关联到独立日期表，建立一对多关系。
- 温度和风速适合使用平均值；降水与短波辐射适合使用总和。
- 月度页面优先使用 `vw_monthly_solar_summary`，避免在 Power BI 重复实现 SQL 聚合。
- 近期监控页面优先使用 `vw_recent_30_days`，降低导入数据量。
- 管道健康页面使用三个 V4 监控视图，不在 Power BI 中复制运行状态 SQL。
