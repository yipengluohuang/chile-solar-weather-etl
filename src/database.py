import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import MetaData, Table, URL, create_engine, text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.engine import Engine

from config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    SCHEMA_SQL_FILE,
    VIEWS_SQL_FILE,
)


WEATHER_VALUE_COLUMNS = [
    "temperature_max_c",
    "temperature_min_c",
    "sunshine_duration_seconds",
    "sunshine_duration_hours",
    "shortwave_radiation_mj_m2",
    "precipitation_mm",
    "wind_speed_max_kmh",
    "retrieved_at",
]


def validate_database_config() -> None:
    """确认数据库连接配置完整，并限制数据库名称为安全标识符。"""
    missing_settings = []
    if not DB_USER:
        missing_settings.append("DB_USER")
    if DB_PASSWORD is None:
        missing_settings.append("DB_PASSWORD")

    if missing_settings:
        raise ValueError(
            "数据库配置缺失："
            f"{', '.join(missing_settings)}。请在项目根目录创建 .env。"
        )

    if not re.fullmatch(r"[A-Za-z0-9_]+", DB_NAME):
        raise ValueError("DB_NAME 只能包含英文字母、数字和下划线。")
    if DB_NAME != "chile_solar_weather":
        raise ValueError("V3 要求 DB_NAME 必须为 chile_solar_weather。")


def build_database_url(include_database: bool) -> URL:
    """使用 SQLAlchemy URL 安全处理用户名和密码中的特殊字符。"""
    return URL.create(
        drivername="mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME if include_database else None,
        query={"charset": "utf8mb4"},
    )


def connect_database(logger: logging.Logger) -> Engine:
    """先检查 MySQL 服务器连接，再创建项目数据库并返回业务连接。"""
    validate_database_config()
    server_engine = create_engine(
        build_database_url(include_database=False),
        pool_pre_ping=True,
    )

    try:
        with server_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("MySQL 服务器连接检查成功：%s:%s", DB_HOST, DB_PORT)

        # DB_NAME 已严格限制为安全标识符，因此可以用于数据库 DDL。
        create_database_sql = (
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        with server_engine.begin() as connection:
            connection.execute(text(create_database_sql))
        logger.info("数据库已确认存在：%s", DB_NAME)
    finally:
        server_engine.dispose()

    database_engine = create_engine(
        build_database_url(include_database=True),
        pool_pre_ping=True,
    )
    with database_engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    logger.info("业务数据库连接成功：%s", DB_NAME)
    return database_engine


def connect_existing_database(logger: logging.Logger) -> Engine:
    """只连接现有业务数据库，供健康检查执行只读查询。"""
    validate_database_config()
    database_engine = create_engine(
        build_database_url(include_database=True),
        pool_pre_ping=True,
    )
    try:
        with database_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_engine.dispose()
        raise
    logger.info("健康检查已连接业务数据库：%s", DB_NAME)
    return database_engine


def read_sql_statements(sql_file: Path) -> list[str]:
    """读取简单 SQL 文件，忽略整行注释并按分号拆分语句。"""
    sql_text = sql_file.read_text(encoding="utf-8")
    sql_lines = [
        line for line in sql_text.splitlines() if not line.strip().startswith("--")
    ]
    return [
        statement.strip()
        for statement in "\n".join(sql_lines).split(";")
        if statement.strip()
    ]


def execute_sql_file(
    engine: Engine,
    sql_file: Path,
    logger: logging.Logger,
) -> None:
    """在一个事务中执行 SQL 文件；任一语句失败时自动回滚。"""
    statements = read_sql_statements(sql_file)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    logger.info("SQL 文件执行成功：%s，共 %s 条语句。", sql_file, len(statements))


def initialize_schema(engine: Engine, logger: logging.Logger) -> None:
    """创建天气历史表和管道运行记录表。"""
    execute_sql_file(engine, SCHEMA_SQL_FILE, logger)


def initialize_views(engine: Engine, logger: logging.Logger) -> None:
    """创建或更新 Power BI 与分析使用的 SQL 视图。"""
    execute_sql_file(engine, VIEWS_SQL_FILE, logger)


def create_pipeline_run(engine: Engine, started_at: datetime) -> int:
    """创建 RUNNING 状态的管道运行记录并返回 run_id。"""
    statement = text(
        """
        INSERT INTO pipeline_runs (
            started_at, status, api_rows, historical_rows_before,
            inserted_rows, updated_rows, final_database_rows,
            failed_quality_checks
        )
        VALUES (:started_at, 'RUNNING', 0, 0, 0, 0, 0, 0)
        """
    )
    with engine.begin() as connection:
        result = connection.execute(statement, {"started_at": started_at})
        return int(result.lastrowid)


def finish_pipeline_run(
    engine: Engine,
    run_id: int,
    finished_at: datetime,
    status: str,
    api_rows: int,
    historical_rows_before: int,
    inserted_rows: int,
    updated_rows: int,
    final_database_rows: int,
    failed_quality_checks: int,
    error_message: str | None,
) -> None:
    """用参数化 SQL 完成 SUCCESS 或 FAILED 运行记录。"""
    if status not in {"SUCCESS", "FAILED"}:
        raise ValueError("pipeline_runs 的最终状态只能是 SUCCESS 或 FAILED。")

    statement = text(
        """
        UPDATE pipeline_runs
        SET finished_at = :finished_at,
            status = :status,
            api_rows = :api_rows,
            historical_rows_before = :historical_rows_before,
            inserted_rows = :inserted_rows,
            updated_rows = :updated_rows,
            final_database_rows = :final_database_rows,
            failed_quality_checks = :failed_quality_checks,
            error_message = :error_message
        WHERE run_id = :run_id
        """
    )
    parameters = {
        "finished_at": finished_at,
        "status": status,
        "api_rows": api_rows,
        "historical_rows_before": historical_rows_before,
        "inserted_rows": inserted_rows,
        "updated_rows": updated_rows,
        "final_database_rows": final_database_rows,
        "failed_quality_checks": failed_quality_checks,
        "error_message": error_message,
        "run_id": run_id,
    }
    with engine.begin() as connection:
        connection.execute(statement, parameters)


def get_weather_row_count(engine: Engine) -> int:
    """返回 weather_daily 当前总行数。"""
    with engine.connect() as connection:
        return int(
            connection.execute(text("SELECT COUNT(*) FROM weather_daily")).scalar_one()
        )


def normalize_datetime_for_mysql(value: object) -> datetime | None:
    """将带时区时间统一为 UTC 无时区 datetime，便于写入 MySQL DATETIME。"""
    if pd.isna(value):
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.to_pydatetime()


def dataframe_to_records(dataframe: pd.DataFrame) -> list[dict]:
    """将 pandas 数据转换为可供参数化 UPSERT 使用的 Python 记录。"""
    records = []
    for row in dataframe.to_dict(orient="records"):
        record = {
            "date": pd.Timestamp(row["date"]).date(),
            "city": row["city"],
            "retrieved_at": normalize_datetime_for_mysql(row["retrieved_at"]),
        }
        for column in WEATHER_VALUE_COLUMNS:
            if column == "retrieved_at":
                continue
            value = row[column]
            record[column] = None if pd.isna(value) else float(value)
        records.append(record)
    return records


def get_existing_weather_keys(engine: Engine) -> set[tuple[str, object]]:
    """读取现有联合键，用于报告本次插入与更新行数。"""
    with engine.connect() as connection:
        return {
            (row.city, row.date)
            for row in connection.execute(text("SELECT city, date FROM weather_daily"))
        }


def upsert_weather_data(
    engine: Engine,
    dataframe: pd.DataFrame,
    logger: logging.Logger,
) -> tuple[int, int]:
    """在单个事务中 UPSERT 天气数据，失败时由 SQLAlchemy 自动回滚。"""
    if dataframe.empty:
        logger.info("没有需要写入 weather_daily 的记录。")
        return 0, 0

    records = dataframe_to_records(dataframe)
    existing_keys = get_existing_weather_keys(engine)
    incoming_keys = {(record["city"], record["date"]) for record in records}
    inserted_rows = len(incoming_keys - existing_keys)
    updated_rows = len(incoming_keys & existing_keys)

    metadata = MetaData()
    weather_table = Table("weather_daily", metadata, autoload_with=engine)
    insert_statement = mysql_insert(weather_table)
    update_values = {
        column: getattr(insert_statement.inserted, column)
        for column in WEATHER_VALUE_COLUMNS
    }
    update_values["updated_at"] = text("CURRENT_TIMESTAMP(6)")
    upsert_statement = insert_statement.on_duplicate_key_update(**update_values)

    with engine.begin() as connection:
        connection.execute(upsert_statement, records)

    logger.info(
        "weather_daily UPSERT 成功：插入 %s 行，更新 %s 行。",
        inserted_rows,
        updated_rows,
    )
    return inserted_rows, updated_rows


def read_weather_history(engine: Engine) -> pd.DataFrame:
    """从 MySQL 读取完整天气历史，作为 CSV 和 Excel 的唯一输出来源。"""
    statement = text(
        """
        SELECT date, city, temperature_max_c, temperature_min_c,
               sunshine_duration_seconds, shortwave_radiation_mj_m2,
               precipitation_mm, wind_speed_max_kmh,
               sunshine_duration_hours, retrieved_at
        FROM weather_daily
        ORDER BY city, date
        """
    )
    with engine.connect() as connection:
        dataframe = pd.read_sql(statement, connection)
    dataframe["date"] = pd.to_datetime(dataframe["date"], errors="coerce")
    return dataframe


def get_database_validation_results(engine: Engine) -> dict:
    """返回计数、重复键、日期范围和月度汇总验证结果。"""
    queries = {
        "total_rows": "SELECT COUNT(*) FROM weather_daily",
        "duplicate_keys": """
            SELECT COUNT(*) FROM (
                SELECT city, date FROM weather_daily
                GROUP BY city, date HAVING COUNT(*) > 1
            ) AS duplicate_groups
        """,
        "earliest_date": "SELECT MIN(date) FROM weather_daily",
        "latest_date": "SELECT MAX(date) FROM weather_daily",
    }
    results = {}
    with engine.connect() as connection:
        for name, query in queries.items():
            results[name] = connection.execute(text(query)).scalar_one()
        results["monthly_summary"] = pd.read_sql(
            text(
                "SELECT * FROM vw_monthly_solar_summary ORDER BY city, month"
            ),
            connection,
        )
    return results
