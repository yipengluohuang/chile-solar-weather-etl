# Changelog

## V4 - Portfolio and Operations Readiness

### Added

- Windows Task Scheduler 运行、安装、删除和健康检查 PowerShell 脚本。
- API 连接/超时/可重试 5xx 的最多3次有限重试和指数退避。
- `runtime/pipeline.lock` 单实例保护与陈旧锁处理。
- 5MB、5份备份的 UTF-8 轮转日志。
- 最近90天原始 JSON 保留策略。
- 只读 `src/health_check.py` 和 0/1/2 健康退出码。
- 基于 `unittest` 的离线单元测试。
- 3个管道监控 SQL 视图、Power BI DAX、页面规格和刷新指南。
- 架构、故障排查、面试问答和中西英三语简历材料。

### Changed

- `PAST_DAYS` 与 `FORECAST_DAYS` 移入配置文件。
- Power BI 数据字典和业务分析查询扩展到 V4 监控层。
- `.gitignore` 增加锁、缓存、临时文件和生成产物规则。

### Preserved

- V3 Open-Meteo JSON 归档、pandas 清洗、20项质量检查、MySQL事务 UPSERT、运行审计、CSV/Excel 回读输出及三个原有视图。
