import json
import logging
import re
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import perf_counter

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from sqlalchemy.engine import Engine
from urllib3.util.retry import Retry

from config import (
    API_BACKOFF_FACTOR_SECONDS,
    API_MAX_ATTEMPTS,
    API_URL,
    CITY,
    CLEAN_DIR,
    DAILY_FIELDS,
    DOCS_DIR,
    FORECAST_DAYS,
    HISTORICAL_CSV_FILE,
    HISTORICAL_EXCEL_FILE,
    LATITUDE,
    LOCK_STALE_HOURS,
    LOG_BACKUP_COUNT,
    LOG_FILE,
    LOG_MAX_BYTES,
    LOGS_DIR,
    LONGITUDE,
    OUTPUTS_DIR,
    PAST_DAYS,
    PIPELINE_LOCK_FILE,
    PROJECT_DIR,
    QUALITY_REPORT_FILE,
    RAW_DIR,
    RAW_JSON_RETENTION_DAYS,
    RAW_LATEST_FILE,
    REQUEST_TIMEOUT_SECONDS,
    RUNTIME_DIR,
    SQL_DIR,
    TIMEZONE,
)
from database import (
    connect_database,
    create_pipeline_run,
    finish_pipeline_run,
    get_database_validation_results,
    get_weather_row_count,
    initialize_schema,
    initialize_views,
    normalize_datetime_for_mysql,
    read_weather_history,
    upsert_weather_data,
)
from runtime_lock import acquire_pipeline_lock, release_pipeline_lock

COLUMN_NAMES = {
    "time": "date",
    "temperature_2m_max": "temperature_max_c",
    "temperature_2m_min": "temperature_min_c",
    "sunshine_duration": "sunshine_duration_seconds",
    "shortwave_radiation_sum": "shortwave_radiation_mj_m2",
    "precipitation_sum": "precipitation_mm",
    "wind_speed_10m_max": "wind_speed_max_kmh",
}

NUMERIC_COLUMNS = [
    "temperature_max_c",
    "temperature_min_c",
    "sunshine_duration_seconds",
    "shortwave_radiation_mj_m2",
    "precipitation_mm",
    "wind_speed_max_kmh",
    "sunshine_duration_hours",
]

OUTPUT_COLUMNS = [
    "date",
    "city",
    "temperature_max_c",
    "temperature_min_c",
    "sunshine_duration_seconds",
    "shortwave_radiation_mj_m2",
    "precipitation_mm",
    "wind_speed_max_kmh",
    "sunshine_duration_hours",
    "retrieved_at",
]

CRITICAL_CHECKS = {
    "city_not_null",
    "date_not_null",
    "unique_city_date",
    "date_is_datetime",
    "numeric_columns_are_numeric",
    "temperature_range_valid",
    "sunshine_hours_valid",
    "radiation_non_negative",
    "precipitation_non_negative",
    "wind_speed_non_negative",
}


def configure_console_encoding() -> None:
    """在 Windows 旧代码页终端中安全显示中文摘要和错误。"""
    for stream in [sys.stdout, sys.stderr]:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def ensure_directories() -> None:
    """创建 V4 运行所需的目录，但不删除任何已有文件。"""
    for directory in [
        RAW_DIR,
        CLEAN_DIR,
        OUTPUTS_DIR,
        LOGS_DIR,
        SQL_DIR,
        DOCS_DIR,
        RUNTIME_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def setup_logger(log_file: Path) -> logging.Logger:
    """配置 UTF-8 轮转日志，让终端仅显示简洁摘要。"""
    logger = logging.getLogger("chile_solar_weather")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)
    return logger


def fetch_weather_data(logger: logging.Logger) -> dict:
    """使用有限重试调用 Open-Meteo API，并返回完整 JSON。"""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "timezone": TIMEZONE,
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "daily": ",".join(DAILY_FIELDS),
    }

    retry_strategy = Retry(
        total=API_MAX_ATTEMPTS - 1,
        connect=API_MAX_ATTEMPTS - 1,
        read=API_MAX_ATTEMPTS - 1,
        status=API_MAX_ATTEMPTS - 1,
        allowed_methods=frozenset({"GET"}),
        status_forcelist=(500, 502, 503, 504),
        backoff_factor=API_BACKOFF_FACTOR_SECONDS,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    logger.info(
        "API 请求开始：%s，最多尝试 %s 次。",
        API_URL,
        API_MAX_ATTEMPTS,
    )
    try:
        response = session.get(
            API_URL,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        logger.error("API 请求失败：%s", error)
        raise RuntimeError(f"Open-Meteo API 请求失败：{error}") from error

    finally:
        session.close()

    try:
        api_data = response.json()
    except ValueError as error:
        logger.error("API 返回内容不是有效的 JSON，不进行重试：%s", error)
        raise ValueError("API 返回内容不是有效的 JSON。") from error

    logger.info("API 请求成功：HTTP %s", response.status_code)
    return api_data


def save_raw_data(
    api_data: dict,
    run_time: pd.Timestamp,
    logger: logging.Logger,
) -> Path:
    """保存带时间戳的原始响应，并更新 latest 快速查看文件。"""
    timestamp_text = run_time.strftime("%Y-%m-%d_%H%M%S")
    archive_file = RAW_DIR / f"antofagasta_raw_{timestamp_text}.json"

    # 极短时间内重复运行时增加序号，避免覆盖同秒生成的归档。
    sequence = 1
    while archive_file.exists():
        archive_file = RAW_DIR / (
            f"antofagasta_raw_{timestamp_text}_{sequence}.json"
        )
        sequence += 1

    json_text = json.dumps(api_data, ensure_ascii=False, indent=2)
    archive_file.write_text(json_text, encoding="utf-8")
    RAW_LATEST_FILE.write_text(json_text, encoding="utf-8")

    logger.info("原始 JSON 归档保存位置：%s", archive_file.resolve())
    logger.info("最新原始 JSON 保存位置：%s", RAW_LATEST_FILE.resolve())
    return archive_file


def cleanup_old_raw_archives(
    reference_time: pd.Timestamp,
    logger: logging.Logger,
) -> int:
    """仅删除超过保留天数的本项目时间戳 JSON，始终保留 latest。"""
    archive_pattern = re.compile(
        r"^antofagasta_raw_(\d{4}-\d{2}-\d{2}_\d{6})(?:_\d+)?\.json$"
    )
    deleted_count = 0

    for raw_file in RAW_DIR.iterdir():
        if not raw_file.is_file():
            continue
        match = archive_pattern.fullmatch(raw_file.name)
        if match is None:
            continue

        archive_time = pd.Timestamp(
            datetime.strptime(match.group(1), "%Y-%m-%d_%H%M%S")
        ).tz_localize(TIMEZONE)
        age_days = (reference_time - archive_time).total_seconds() / 86400
        if age_days <= RAW_JSON_RETENTION_DAYS:
            continue

        raw_file.unlink()
        deleted_count += 1
        logger.info(
            "已删除过期原始 JSON：%s，归档年龄 %.1f 天。",
            raw_file.resolve(),
            age_days,
        )

    logger.info(
        "原始 JSON 保留策略完成：保留最近 %s 天，本次删除 %s 个文件。",
        RAW_JSON_RETENTION_DAYS,
        deleted_count,
    )
    return deleted_count


def normalize_data_types(dataframe: pd.DataFrame) -> pd.DataFrame:
    """统一日期和数值列类型，不把缺失值自动填充为 0。"""
    normalized = dataframe.copy()
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")

    for column in NUMERIC_COLUMNS:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(
                normalized[column],
                errors="coerce",
            )

    return normalized


def create_clean_dataframe(
    api_data: dict,
    retrieved_at: pd.Timestamp,
) -> pd.DataFrame:
    """把本次 daily 数据转换为 DataFrame，并完成 V1 清洗。"""
    if "daily" not in api_data or not isinstance(api_data["daily"], dict):
        raise KeyError("API 响应中缺少 daily 对象。")

    daily_data = api_data["daily"]
    required_fields = ["time", *DAILY_FIELDS]
    missing_fields = [field for field in required_fields if field not in daily_data]
    if missing_fields:
        raise KeyError(f"daily 数据缺少字段：{missing_fields}")

    # 只选择本项目需要的 daily 字段，避免意外引入其他字段。
    dataframe = pd.DataFrame(
        {field: daily_data[field] for field in required_fields}
    ).rename(columns=COLUMN_NAMES)

    # 将天气指标转换为数值；无法转换的值变为 NaN，但不填充为 0。
    source_numeric_columns = [
        column
        for column in NUMERIC_COLUMNS
        if column != "sunshine_duration_hours"
    ]
    for column in source_numeric_columns:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    dataframe.insert(1, "city", CITY)
    dataframe["sunshine_duration_hours"] = (
        dataframe["sunshine_duration_seconds"] / 3600
    )

    # 使用 API 所在时区记录运行时间，并保存为带时区偏移的文本，便于 Excel 兼容。
    dataframe["retrieved_at"] = retrieved_at.isoformat()

    dataframe = normalize_data_types(dataframe)
    return dataframe[OUTPUT_COLUMNS].sort_values("date").reset_index(drop=True)


def load_historical_data(
    csv_file: Path,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, int]:
    """读取已有历史 CSV；文件不存在时返回一个空 DataFrame。"""
    if not csv_file.exists():
        logger.info("历史 CSV 不存在，将使用本次数据创建第一份历史文件。")
        return pd.DataFrame(columns=OUTPUT_COLUMNS), 0

    historical_data = pd.read_csv(csv_file, encoding="utf-8-sig")
    missing_columns = [
        column for column in OUTPUT_COLUMNS if column not in historical_data.columns
    ]
    if missing_columns:
        raise ValueError(f"历史 CSV 缺少字段：{missing_columns}")

    historical_data = normalize_data_types(historical_data[OUTPUT_COLUMNS])
    original_rows = len(historical_data)
    logger.info("历史 CSV 读取成功：%s 行，文件：%s", original_rows, csv_file.resolve())
    return historical_data, original_rows


def merge_historical_data(
    historical_data: pd.DataFrame,
    current_data: pd.DataFrame,
) -> tuple[pd.DataFrame, int, int]:
    """合并历史与本次数据，同一 city + date 保留本次最新记录。"""
    if historical_data.empty:
        combined_data = current_data.copy()
    else:
        # 本次数据放在后面，keep="last" 会优先保留本次抓取的同日记录。
        combined_data = pd.concat(
            [historical_data, current_data],
            ignore_index=True,
        )

    rows_before_deduplication = len(combined_data)
    merged_data = combined_data.drop_duplicates(
        subset=["city", "date"],
        keep="last",
    )
    removed_duplicate_rows = rows_before_deduplication - len(merged_data)

    merged_data = (
        merged_data.sort_values(["city", "date"], ascending=True)
        .reset_index(drop=True)
    )
    return merged_data[OUTPUT_COLUMNS], rows_before_deduplication, removed_duplicate_rows


def run_quality_checks(
    dataframe: pd.DataFrame,
    checked_at: pd.Timestamp,
) -> pd.DataFrame:
    """执行结构、类型、业务范围和逐列缺失值检查。"""
    results: list[dict] = []
    checked_at_text = checked_at.isoformat()

    def add_result(
        check_name: str,
        problem_count: int,
        description: str,
    ) -> None:
        results.append(
            {
                "check_name": check_name,
                "status": "PASS" if problem_count == 0 else "FAIL",
                "problem_count": int(problem_count),
                "description": description,
                "checked_at": checked_at_text,
            }
        )

    city_missing = (
        dataframe["city"].isna()
        | dataframe["city"].astype("string").str.strip().eq("").fillna(True)
    ).sum()
    add_result("city_not_null", city_missing, "city 不应为空。")

    date_missing = dataframe["date"].isna().sum()
    add_result("date_not_null", date_missing, "date 应成功解析且不为空。")

    duplicate_rows = dataframe.duplicated(
        subset=["city", "date"],
        keep=False,
    ).sum()
    add_result(
        "unique_city_date",
        duplicate_rows,
        "city + date 组合不应重复。",
    )

    date_type_problem = 0
    if not pd.api.types.is_datetime64_any_dtype(dataframe["date"]):
        date_type_problem = len(dataframe)
    add_result(
        "date_is_datetime",
        date_type_problem,
        "date 列应为 pandas 日期类型。",
    )

    non_numeric_columns = [
        column
        for column in NUMERIC_COLUMNS
        if not pd.api.types.is_numeric_dtype(dataframe[column])
    ]
    add_result(
        "numeric_columns_are_numeric",
        len(non_numeric_columns),
        "所有天气数值字段都应为数值类型；异常列："
        f"{non_numeric_columns or '无'}。",
    )

    invalid_temperature = (
        dataframe["temperature_max_c"] < dataframe["temperature_min_c"]
    ).sum()
    add_result(
        "temperature_range_valid",
        invalid_temperature,
        "temperature_max_c 不应小于 temperature_min_c。",
    )

    invalid_sunshine = (
        dataframe["sunshine_duration_hours"].notna()
        & ~dataframe["sunshine_duration_hours"].between(0, 24)
    ).sum()
    add_result(
        "sunshine_hours_valid",
        invalid_sunshine,
        "sunshine_duration_hours 应位于 0 到 24 之间。",
    )

    invalid_radiation = (dataframe["shortwave_radiation_mj_m2"] < 0).sum()
    add_result(
        "radiation_non_negative",
        invalid_radiation,
        "shortwave_radiation_mj_m2 不应小于 0。",
    )

    invalid_precipitation = (dataframe["precipitation_mm"] < 0).sum()
    add_result(
        "precipitation_non_negative",
        invalid_precipitation,
        "precipitation_mm 不应小于 0。",
    )

    invalid_wind_speed = (dataframe["wind_speed_max_kmh"] < 0).sum()
    add_result(
        "wind_speed_non_negative",
        invalid_wind_speed,
        "wind_speed_max_kmh 不应小于 0。",
    )

    for column in dataframe.columns:
        add_result(
            f"missing_values_{column}",
            dataframe[column].isna().sum(),
            f"{column} 列的缺失值数量。",
        )

    return pd.DataFrame(
        results,
        columns=[
            "check_name",
            "status",
            "problem_count",
            "description",
            "checked_at",
        ],
    )


def save_historical_data(
    dataframe: pd.DataFrame,
    logger: logging.Logger,
) -> None:
    """保存最终历史主文件到 CSV 和 Excel。"""
    csv_data = dataframe.copy()
    csv_data["date"] = pd.to_datetime(
        csv_data["date"],
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")
    csv_data.to_csv(
        HISTORICAL_CSV_FILE,
        index=False,
        encoding="utf-8-sig",
    )
    logger.info("历史 CSV 保存位置：%s", HISTORICAL_CSV_FILE.resolve())

    dataframe.to_excel(
        HISTORICAL_EXCEL_FILE,
        index=False,
        engine="openpyxl",
    )
    logger.info("历史 Excel 保存位置：%s", HISTORICAL_EXCEL_FILE.resolve())


def format_date_range(dataframe: pd.DataFrame) -> tuple[str, str]:
    """返回便于终端显示的最早和最晚有效日期。"""
    valid_dates = dataframe["date"].dropna()
    if valid_dates.empty:
        return "无有效日期", "无有效日期"
    return (
        valid_dates.min().strftime("%Y-%m-%d"),
        valid_dates.max().strftime("%Y-%m-%d"),
    )


def main() -> None:
    """运行 V4 API、质量检查、MySQL、文件输出和监控流程。"""
    started_counter = perf_counter()
    configure_console_encoding()
    ensure_directories()
    logger = setup_logger(LOG_FILE)
    run_time = pd.Timestamp.now(tz=TIMEZONE)
    database_time = normalize_datetime_for_mysql(run_time)

    engine: Engine | None = None
    run_id: int | None = None
    lock_token: str | None = None
    run_record_finished = False
    api_rows = 0
    historical_rows_before = 0
    inserted_rows = 0
    updated_rows = 0
    final_database_rows = 0
    failed_quality_checks = 0

    logger.info("程序开始：Chile Solar Weather ETL Pipeline V4")

    try:
        # 先检查数据库并创建表，确保后续失败也能写入 pipeline_runs。
        engine = connect_database(logger)
        initialize_schema(engine, logger)
        run_id = create_pipeline_run(engine, database_time)
        logger.info("pipeline_runs 已创建：run_id=%s", run_id)
        lock_token = acquire_pipeline_lock(
            PIPELINE_LOCK_FILE,
            LOCK_STALE_HOURS,
            logger,
        )
        initialize_views(engine, logger)
        historical_rows_before = get_weather_row_count(engine)

        api_data = fetch_weather_data(logger)
        archive_file = save_raw_data(api_data, run_time, logger)
        cleanup_old_raw_archives(run_time, logger)
        current_data = create_clean_dataframe(api_data, run_time)
        api_rows = len(current_data)
        logger.info("API 返回记录数：%s", api_rows)

        # 数据库首次为空时导入 V2 CSV；之后 MySQL 成为唯一历史主数据源。
        if historical_rows_before == 0:
            legacy_data, legacy_rows = load_historical_data(
                HISTORICAL_CSV_FILE,
                logger,
            )
            staged_data, combined_rows, removed_duplicate_rows = (
                merge_historical_data(legacy_data, current_data)
            )
            logger.info(
                "首次数据库导入：V2 历史 %s 行，本次 API %s 行，"
                "合并前 %s 行，删除重复 %s 行，待写入 %s 行。",
                legacy_rows,
                api_rows,
                combined_rows,
                removed_duplicate_rows,
                len(staged_data),
            )
        else:
            staged_data = current_data
            logger.info(
                "数据库已有 %s 行，本次仅 UPSERT API 返回的 %s 行。",
                historical_rows_before,
                api_rows,
            )

        quality_report = run_quality_checks(staged_data, run_time)
        quality_report.to_csv(
            QUALITY_REPORT_FILE,
            index=False,
            encoding="utf-8-sig",
        )
        failed_checks = quality_report[quality_report["status"] == "FAIL"]
        critical_failures = failed_checks[
            failed_checks["check_name"].isin(CRITICAL_CHECKS)
        ]
        failed_quality_checks = len(failed_checks)

        logger.info(
            "数据质量检查完成：PASS %s 项，FAIL %s 项，报告：%s",
            int((quality_report["status"] == "PASS").sum()),
            failed_quality_checks,
            QUALITY_REPORT_FILE.resolve(),
        )
        for _, failed_check in failed_checks.iterrows():
            logger.warning(
                "质量检查失败：%s，问题数：%s，说明：%s",
                failed_check["check_name"],
                failed_check["problem_count"],
                failed_check["description"],
            )

        if not critical_failures.empty:
            critical_names = ", ".join(critical_failures["check_name"])
            error_message = (
                "关键数据质量检查失败，未写入 weather_daily："
                f"{critical_names}"
            )
            logger.error(error_message)
            finish_pipeline_run(
                engine=engine,
                run_id=run_id,
                finished_at=normalize_datetime_for_mysql(
                    pd.Timestamp.now(tz=TIMEZONE)
                ),
                status="FAILED",
                api_rows=api_rows,
                historical_rows_before=historical_rows_before,
                inserted_rows=0,
                updated_rows=0,
                final_database_rows=get_weather_row_count(engine),
                failed_quality_checks=failed_quality_checks,
                error_message=error_message,
            )
            run_record_finished = True
            raise RuntimeError(error_message)

        inserted_rows, updated_rows = upsert_weather_data(
            engine,
            staged_data,
            logger,
        )
        final_database_rows = get_weather_row_count(engine)

        # MySQL 是 V4 主数据源；文件输出只使用数据库回读结果。
        final_data = read_weather_history(engine)
        save_historical_data(final_data, logger)
        validation = get_database_validation_results(engine)
        earliest_date, latest_date = format_date_range(final_data)

        finish_pipeline_run(
            engine=engine,
            run_id=run_id,
            finished_at=normalize_datetime_for_mysql(
                pd.Timestamp.now(tz=TIMEZONE)
            ),
            status="SUCCESS",
            api_rows=api_rows,
            historical_rows_before=historical_rows_before,
            inserted_rows=inserted_rows,
            updated_rows=updated_rows,
            final_database_rows=final_database_rows,
            failed_quality_checks=failed_quality_checks,
            error_message=None,
        )
        run_record_finished = True

        logger.info(
            "数据库验证：总行数 %s，重复键 %s，最早 %s，最晚 %s。",
            validation["total_rows"],
            validation["duplicate_keys"],
            validation["earliest_date"],
            validation["latest_date"],
        )

        print("\nChile Solar Weather ETL Pipeline V4 运行成功")
        print(f"pipeline run_id：{run_id}")
        print(f"本次 API 返回行数：{api_rows}")
        print(f"数据库原有行数：{historical_rows_before}")
        print(f"本次插入行数：{inserted_rows}")
        print(f"本次更新行数：{updated_rows}")
        print(f"最终数据库行数：{final_database_rows}")
        print(f"重复 city + date：{validation['duplicate_keys']}")
        print(f"数据日期范围：{earliest_date} 至 {latest_date}")
        print(
            "数据质量："
            f"PASS {int((quality_report['status'] == 'PASS').sum())} 项，"
            f"FAIL {failed_quality_checks} 项"
        )
        print("\n月度汇总视图：")
        print(validation["monthly_summary"].to_string(index=False))
        print("\nMySQL 回读数据前 5 行：")
        print(final_data.head().to_string(index=False))
        print("\n输出文件位置：")
        print(f"本次原始 JSON：{archive_file.resolve()}")
        print(f"最新原始 JSON：{RAW_LATEST_FILE.resolve()}")
        print(f"历史 CSV：{HISTORICAL_CSV_FILE.resolve()}")
        print(f"历史 Excel：{HISTORICAL_EXCEL_FILE.resolve()}")
        print(f"质量报告：{QUALITY_REPORT_FILE.resolve()}")
        print(f"运行日志：{LOG_FILE.resolve()}")
        print(f"项目目录：{PROJECT_DIR.resolve()}")
    except Exception as error:
        logger.exception("程序运行失败，完整错误信息如下。")
        if engine is not None and run_id is not None and not run_record_finished:
            try:
                final_database_rows = get_weather_row_count(engine)
                finish_pipeline_run(
                    engine=engine,
                    run_id=run_id,
                    finished_at=normalize_datetime_for_mysql(
                        pd.Timestamp.now(tz=TIMEZONE)
                    ),
                    status="FAILED",
                    api_rows=api_rows,
                    historical_rows_before=historical_rows_before,
                    inserted_rows=inserted_rows,
                    updated_rows=updated_rows,
                    final_database_rows=final_database_rows,
                    failed_quality_checks=failed_quality_checks,
                    error_message=str(error)[:60000],
                )
                logger.info("pipeline_runs 已更新为 FAILED：run_id=%s", run_id)
            except Exception:
                logger.exception("pipeline_runs FAILED 状态写入失败。")

        print(f"\n程序运行失败：{error}")
        raise SystemExit(1) from error
    finally:
        if lock_token is not None:
            release_pipeline_lock(PIPELINE_LOCK_FILE, lock_token, logger)
        if engine is not None:
            engine.dispose()
        elapsed_seconds = perf_counter() - started_counter
        logger.info("程序结束，总耗时：%.2f 秒。", elapsed_seconds)


if __name__ == "__main__":
    main()
