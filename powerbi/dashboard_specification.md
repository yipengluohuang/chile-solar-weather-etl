# Power BI 仪表板规格

本文件是可验证的构建规格，不是假造的 `.pbix`。所有指标必须来自 MySQL 视图，刷新后再核对 SQL 结果。

## 页面 1：Executive Overview

目标：快速说明 Antofagasta 数据覆盖范围和太阳资源概况。

- 卡片：Latest Data Date、Total Data Days、Average Sunshine Hours、Total Radiation、Average Maximum Temperature、Total Precipitation。
- 折线图：轴为 `vw_monthly_solar_summary[month]`，值为 `total_shortwave_radiation_mj_m2`。
- 折线图：轴为月份，值为 `average_sunshine_hours`。
- 页面筛选：城市；当前 V4 只有 Antofagasta。
- 格式：辐射 `0.00 MJ/m²`，日照 `0.00 h`，温度 `0.00 °C`，降水 `0.00 mm`。

## 页面 2：Daily Weather and Solar Resource

目标：探索每日天气与太阳资源之间的共同变化。

- 日期筛选器：`vw_weather_daily[date]`，类型为“介于”。
- 温度折线图：最高温和最低温两条线。
- 日照与短波辐射组合图：日期为轴，日照小时和辐射分别为值。
- 降水柱形图：日期与 `precipitation_mm`。
- 风速折线图：日期与 `wind_speed_max_kmh`。
- 明细表：日期、所有天气指标和 `retrieved_at`。

## 页面 3：Pipeline Health

目标：判断 ETL 是否成功、是否及时以及数据是否可用。

- 卡片：Last Pipeline Status、Last Successful Run、Data Age Days、Pipeline Success Rate。
- 卡片：`vw_latest_pipeline_run[inserted_rows]`、`updated_rows`、`failed_quality_checks`。
- 折线图：`started_at` 与 `duration_seconds`，展示运行耗时趋势。
- 堆积柱形图：按 `status` 统计最近 30 次运行。
- 表格：最近运行的 run_id、时间、状态、API 行数、插入、更新、质量失败和错误信息。
- 条件格式：SUCCESS 绿色、RUNNING 黄色、FAILED 红色；数据年龄大于健康阈值时显示警告。

## 验收规则

- Power BI 最新日期应与 `SELECT latest_data_date FROM vw_data_freshness` 一致。
- 总行数应与 `SELECT COUNT(*) FROM weather_daily` 一致。
- 最近运行状态应与 `vw_latest_pipeline_run` 一致。
- 页面不得保存或展示数据库密码。
