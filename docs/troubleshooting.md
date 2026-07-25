# 故障排查

## 数据库连接失败或密码错误

症状：终端提示 MySQL 连接失败，日志中可能出现 `Access denied`。

1. 检查 MySQL 服务是否正在运行。
2. 打开项目根目录 `.env`，核对 `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD`。
3. 不要把 `.env` 内容粘贴到公开 Issue、截图或 Git。
4. 使用 DataGrip 或 MySQL 客户端验证同一账号。
5. 再运行 `py src/health_check.py`。

## Open-Meteo 请求失败

- 确认电脑可以访问互联网。
- 连接错误、超时和部分 5xx 会自动有限重试。
- 4xx 通常代表参数或服务规则问题，应查看日志，不应无限重试。
- 无效 JSON 会立即失败并保留已成功写出的产物；不会写不完整天气数据。

## 检测到 pipeline.lock

- 先在任务管理器确认是否仍有本项目 Python 进程运行。
- 正在运行时不要手动删除锁。
- 程序正常或异常退出会在 `finally` 中释放锁。
- 超过配置阈值的陈旧锁会由下一次运行自动清理。

## 数据质量 FAIL

查看 `outputs/data_quality_report.csv` 和 `logs/pipeline.log`。关键 FAIL 会阻止 `weather_daily` 写入，并将运行记录标为 FAILED。不要为了通过检查而把缺失值随意填成0。

## CSV 或 Excel 被占用

如果文件正在 Excel 中打开，Windows 可能阻止覆盖。关闭工作簿后重新运行。数据库 UPSERT 已完成而文件导出失败时，本次运行会记录 FAILED；下次幂等运行会重新更新并导出。

## 计划任务没有运行

```powershell
Get-ScheduledTask -TaskName 'ChileSolarWeatherETL'
Get-ScheduledTaskInfo -TaskName 'ChileSolarWeatherETL'
Get-Content .\logs\scheduler.log -Tail 50
Get-Content .\logs\pipeline.log -Tail 100
```

安装脚本采用当前用户 `Interactive` 登录类型，默认要求该用户已登录。若要无人登录时运行，需要由用户根据公司安全策略配置专用 Windows 账号和“无论用户是否登录都运行”，不要把数据库密码放入任务参数。

## 健康检查退出码

- `0`：健康。
- `1`：数据或成功运行时间接近陈旧阈值，需要关注。
- `2`：数据库不可用、最近运行失败、重复键、质量 FAIL、产物缺失或严重陈旧。

## Power BI 没有显示新数据

MySQL 更新不会自动改变 Import 模式 `.pbix`。在 Desktop 点击刷新；完整自动化需要 Power BI Service、本地数据网关、数据源凭据和计划刷新。还要确认 Power BI 刷新发生在 ETL 成功之后。
