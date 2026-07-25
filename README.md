# Chile Solar Weather ETL Pipeline V4

一个从 Open-Meteo 获取智利 Antofagasta 每日天气与太阳辐射数据，并通过 pandas、数据质量检查、MySQL、SQL 视图、CSV/Excel 和 Power BI 分析层完成交付的端到端 ETL 作品集项目。

V4 在已验证的 V3 数据核心上增加 Windows 每日运行、运行健康检查、可靠性控制、自动测试以及 GitHub/简历展示材料。项目保持函数式、单城市和易于初级数据分析师理解的结构，不包含预测模型。

## 业务背景

Antofagasta 位于智利北部。本项目持续收集最高/最低气温、日照时长、短波辐射、降水和最大风速，为 SQL 分析与 Power BI 天气/太阳资源展示建立可追溯历史。它是数据工程与分析作品，不估算或预测光伏发电量。

## 版本演进

- V1：Open-Meteo API、原始 JSON、pandas 清洗、CSV 和 Excel。
- V2：时间戳归档、历史文件合并去重、质量报告、日志和配置。
- V3：MySQL、city + date 联合唯一键、事务 UPSERT、`pipeline_runs`、三个 SQL 视图、数据库回读输出。
- V4：有限重试、单实例锁、轮转日志、90天 JSON 保留、Windows 任务脚本、健康检查、单元测试、三个监控视图、Power BI 最终规格和作品集文档。

## 最终架构

```text
Windows Task Scheduler
        │
        ▼
PowerShell入口 ──> 单实例锁 ──> Open-Meteo API（有限重试）
                                      │
                          JSON归档 + latest JSON
                                      │
                                      ▼
                                  pandas清洗
                                      │
                                      ▼
                               20项数据质量检查
                          ┌───────────┴───────────┐
                       关键失败                  通过
                          │                       │
                pipeline_runs=FAILED             ▼
                   非0退出码               MySQL事务UPSERT
                                                  │
                            ┌─────────────────────┼──────────────────┐
                            ▼                     ▼                  ▼
                       SQL视图             MySQL全量回读       pipeline_runs
                                                  │
                                              CSV / Excel
                                                  │
                                           Power BI Import
```

更详细的职责和失败边界见 `docs/architecture.md`。

## 目录

```text
chile_solar_weather/
├─ data/
│  ├─ raw/
│  └─ clean/
├─ docs/
│  ├─ architecture.md
│  ├─ interview_questions.md
│  ├─ power_bi_automation_guide.md
│  ├─ power_bi_build_guide.md
│  ├─ power_bi_data_dictionary.md
│  ├─ resume_project_entry.md
│  └─ troubleshooting.md
├─ logs/
├─ outputs/
├─ powerbi/
│  ├─ dashboard_specification.md
│  └─ measures.dax
├─ runtime/
├─ scripts/
│  ├─ check_pipeline_health.ps1
│  ├─ install_scheduled_task.ps1
│  ├─ remove_scheduled_task.ps1
│  └─ run_pipeline.ps1
├─ sql/
│  ├─ analysis_queries.sql
│  ├─ schema.sql
│  └─ views.sql
├─ src/
│  ├─ config.py
│  ├─ database.py
│  ├─ health_check.py
│  ├─ main.py
│  └─ runtime_lock.py
├─ tests/
│  └─ test_pipeline.py
├─ .env.example
├─ .gitignore
├─ CHANGELOG.md
├─ README.md
└─ requirements.txt
```

## 环境与依赖

项目使用本机全局 Python，不创建或激活 `.venv`：

```powershell
py -c "import sys; print(sys.executable)"
py --version
py -m pip list
```

仅在确认缺少依赖并由用户决定后安装：

```powershell
py -m pip install -r requirements.txt
```

`requirements.txt` 只记录 requests、pandas、openpyxl、SQLAlchemy、python-dotenv 和 PyMySQL；项目不同时使用第二个 MySQL 驱动。

## 安全配置

复制示例并在本机填写 MySQL 账号：

```powershell
Copy-Item .env.example .env
```

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=chile_solar_weather
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
```

`.env` 已被 Git 忽略。不要把密码写入 Python、PowerShell、SQL、README、截图、任务参数或 Git。建议作品集使用权限受限的专用 MySQL 账号，不使用管理员账号。

## 手动运行

从项目根目录执行：

```powershell
py src/main.py
```

程序使用 `src/config.py` 推导项目绝对路径，所以从其他工作目录启动仍能找到 `.env`、SQL 和输出目录。退出码0表示成功；关键失败返回非0。

## 可靠性设计

- `PAST_DAYS=30`、`FORECAST_DAYS=1` 位于配置文件。
- API 对连接错误、读取超时和 500/502/503/504 最多尝试3次并指数退避；4xx与无效 JSON不无限重试。
- `runtime/pipeline.lock` 原子阻止两个实例同时写 MySQL；`finally` 清锁，并处理超过阈值的陈旧锁。
- `pipeline.log` 使用 UTF-8 `RotatingFileHandler`，每份最大5MB，保留5份历史。
- 时间戳原始 JSON 默认保留90天；`antofagasta_raw_latest.json`、CSV、Excel和质量报告永不被该清理逻辑删除。
- 关键质量失败发生在正式 UPSERT 前，保留 JSON/报告，写 FAILED，返回非0。

## 数据库与幂等性

`weather_daily` 的 `(city, date)` 联合唯一键从数据库层禁止重复。SQLAlchemy MySQL UPSERT 对新键 INSERT，对已有键 UPDATE，不清空整表。天气写入使用事务，异常时自动回滚。

因此同一天重复运行不会重复增加数据。已经验证的 V3 结果为：首次数据库结果33行；第二次插入0行、更新31行；重复 city + date 为0。

`pipeline_runs` 每次在数据库可连接后登记一行，最终保存 SUCCESS/FAILED、API行数、插入/更新数量、质量失败数和错误。若 MySQL 本身完全不可连接，数据库无法记录失败，但完整异常仍写入日志并返回非0。

## 数据质量

`outputs/data_quality_report.csv` 至少检查：city/date 非空、联合键重复、日期类型、数值类型、最高温不低于最低温、日照0至24小时、辐射/降水/风速非负，以及每列缺失值数量。项目不自动把缺失值填成0。

## SQL 分析层

- `vw_weather_daily`：每日完整数据。
- `vw_monthly_solar_summary`：月度温度、日照、辐射、降水、风速和数据天数。
- `vw_recent_30_days`：最近30个日历日。
- `vw_latest_pipeline_run`：最近一次运行。
- `vw_pipeline_run_history`：运行历史、耗时和成功标记。
- `vw_data_freshness`：数据最新日期、年龄、总行数、重复键和最近成功时间。

`sql/analysis_queries.sql` 可直接在 DataGrip 中运行，包括最近状态、最近30次成功率、数据陈旧、月度完整度和太阳资源趋势。

## Windows 每日自动运行

入口脚本已经绑定当前全局 Python 的绝对路径，也允许通过参数覆盖。手动验证入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_pipeline.ps1
```

只有确定每日时间后才注册任务，例如：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_scheduled_task.ps1 -RunTime "08:00"
```

默认任务名为 `ChileSolarWeatherETL`，每日执行，失败后每15分钟重试、最多3次，禁止并发，允许唤醒，超过30分钟停止。安装脚本使用当前用户的 Interactive 登录类型，默认要求用户已登录。

查看和手动触发：

```powershell
Get-ScheduledTask -TaskName 'ChileSolarWeatherETL'
Start-ScheduledTask -TaskName 'ChileSolarWeatherETL'
Get-ScheduledTaskInfo -TaskName 'ChileSolarWeatherETL'
```

安全删除任务而不删除数据：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\remove_scheduled_task.ps1
```

## 健康检查

```powershell
py src/health_check.py
# 或
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_pipeline_health.ps1
```

健康检查只读取数据库和文件，不修改天气数据。它检查 MySQL、最近运行、最近成功时间、天气行数、重复键、日期范围、数据年龄、JSON/CSV/Excel/质量报告及最近质量 FAIL。

- 退出码0：健康。
- 退出码1：警告。
- 退出码2：严重失败。

## 自动测试

测试使用 Python 标准库 `unittest`，不依赖 pytest，不访问真实 API，也不写真实 MySQL：

```powershell
py -m unittest discover -s tests -v
```

覆盖正常/缺字段 JSON、日期与日照换算、关键质量规则、`pd.concat()`、`drop_duplicates()` 幂等合并，以及 pandas 值到 MySQL 参数记录的转换。

## Power BI

Power BI Desktop 连接：

- 服务器：`127.0.0.1:3306`
- 数据库：`chile_solar_weather`
- 模式：Import
- 推荐加载：全部6个视图

Import 模式需要在 Desktop 手动点击刷新；MySQL 更新不会自动修改打开或关闭的 `.pbix` 模型。完整自动化需要发布到 Power BI Service、安装本地数据网关标准模式、保持 MySQL和网关服务运行、在 Service 配置 MySQL凭据和语义模型计划刷新，并把 Power BI 刷新安排在 ETL成功之后。

详细步骤见 `docs/power_bi_build_guide.md`、`docs/power_bi_automation_guide.md`、`powerbi/measures.dax` 和 `powerbi/dashboard_specification.md`。项目不伪造或自动生成不可验证的 `.pbix`。

## 输出

- `data/raw/antofagasta_raw_YYYY-MM-DD_HHMMSS.json`
- `data/raw/antofagasta_raw_latest.json`
- `data/clean/antofagasta_weather.csv`
- `data/clean/antofagasta_weather.xlsx`
- `outputs/data_quality_report.csv`
- `logs/pipeline.log` 与轮转备份
- `logs/scheduler.log`

CSV和Excel只由 MySQL 全量回读结果生成，因此数据库是 V4历史主数据源。

## 故障排查

常见问题包括 `.env` 凭据、MySQL服务、API网络、陈旧锁、Excel占用输出文件、计划任务用户登录状态以及 Power BI未刷新。逐项操作见 `docs/troubleshooting.md`。

## 当前限制

- 只处理 Antofagasta，不支持多城市参数化。
- 使用 Open-Meteo Forecast API 的滚动窗口，不是完整历史回填服务。
- 依赖本机 Windows、MySQL、互联网与有效凭据。
- 计划任务默认 InteractiveToken，用户未登录时不运行。
- 没有在本项目中生成或验证真实 `.pbix`，Power BI Service和网关需用户手动配置。
- 无 Docker、异步框架、预测模型或云端 CI。

## 作品集截图占位

发布到 GitHub 前可在 `docs/images/` 手动加入已脱敏截图，并在此处引用：

- 管道连续两次成功运行摘要。
- DataGrip 的月度视图和重复键检查。
- Power BI Executive Overview、Daily Analysis、Pipeline Health 三个页面。
- Windows任务计划程序状态。

截图不得包含 `.env`、数据库密码、私人路径中的敏感信息或账号凭据。

## 作品集与面试材料

- `docs/interview_questions.md`：15个项目问答。
- `docs/resume_project_entry.md`：中文、西班牙语和英文简历描述。
- `CHANGELOG.md`：版本变更记录。
