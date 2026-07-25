import logging
import sys
from logging.handlers import RotatingFileHandler

import pandas as pd
from sqlalchemy import text

from config import (
    HEALTH_CRITICAL_DATA_AGE_DAYS,
    HEALTH_CRITICAL_HOURS,
    HEALTH_WARNING_DATA_AGE_DAYS,
    HEALTH_WARNING_HOURS,
    HISTORICAL_CSV_FILE,
    HISTORICAL_EXCEL_FILE,
    LOG_BACKUP_COUNT,
    LOG_FILE,
    LOG_MAX_BYTES,
    LOGS_DIR,
    QUALITY_REPORT_FILE,
    RAW_LATEST_FILE,
    TIMEZONE,
)
from database import connect_existing_database


def configure_console_encoding() -> None:
    """让 Windows 终端稳定显示中文健康摘要。"""
    for stream in [sys.stdout, sys.stderr]:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def setup_health_logger() -> logging.Logger:
    """健康检查与主管道共用同一份轮转日志。"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("chile_solar_weather.health")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


def hours_since_utc(value: object) -> float | None:
    """计算 MySQL UTC 无时区时间距现在的小时数。"""
    if value is None or pd.isna(value):
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return (
        pd.Timestamp.now(tz="UTC") - timestamp
    ).total_seconds() / 3600


def read_quality_fail_count() -> int:
    """读取最近一份质量报告中的 FAIL 数量，不修改报告。"""
    report = pd.read_csv(QUALITY_REPORT_FILE, encoding="utf-8-sig")
    if "status" not in report.columns:
        raise ValueError("质量报告缺少 status 列。")
    return int(report["status"].astype("string").eq("FAIL").sum())


def main() -> int:
    """执行只读健康检查；0 健康、1 警告、2 严重失败。"""
    configure_console_encoding()
    logger = setup_health_logger()
    warnings: list[str] = []
    criticals: list[str] = []
    engine = None

    latest_run = None
    latest_success = None
    success_age_hours = None
    total_rows = 0
    duplicate_keys = 0
    earliest_date = None
    latest_date = None
    data_age_days = None
    quality_fail_count = None

    logger.info("健康检查开始。")
    try:
        engine = connect_existing_database(logger)
        with engine.connect() as connection:
            latest_run = connection.execute(
                text(
                    """
                    SELECT run_id, started_at, finished_at, status,
                           failed_quality_checks
                    FROM pipeline_runs
                    ORDER BY run_id DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()
            latest_success = connection.execute(
                text(
                    """
                    SELECT MAX(finished_at)
                    FROM pipeline_runs
                    WHERE status = 'SUCCESS'
                    """
                )
            ).scalar_one()
            weather_stats = connection.execute(
                text(
                    """
                    SELECT COUNT(*) AS total_rows,
                           MIN(date) AS earliest_date,
                           MAX(date) AS latest_date
                    FROM weather_daily
                    """
                )
            ).mappings().one()
            duplicate_keys = int(
                connection.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM (
                            SELECT city, date
                            FROM weather_daily
                            GROUP BY city, date
                            HAVING COUNT(*) > 1
                        ) AS duplicate_groups
                        """
                    )
                ).scalar_one()
            )

        total_rows = int(weather_stats["total_rows"])
        earliest_date = weather_stats["earliest_date"]
        latest_date = weather_stats["latest_date"]

        if latest_run is None:
            criticals.append("pipeline_runs 没有运行记录")
        elif latest_run["status"] != "SUCCESS":
            criticals.append(f"最近一次运行状态为 {latest_run['status']}")

        success_age_hours = hours_since_utc(latest_success)
        if success_age_hours is None:
            criticals.append("不存在成功运行记录")
        elif success_age_hours > HEALTH_CRITICAL_HOURS:
            criticals.append(
                f"最近成功运行已过去 {success_age_hours:.1f} 小时"
            )
        elif success_age_hours > HEALTH_WARNING_HOURS:
            warnings.append(
                f"最近成功运行已过去 {success_age_hours:.1f} 小时"
            )

        if total_rows == 0 or latest_date is None:
            criticals.append("weather_daily 没有可用数据")
        else:
            today = pd.Timestamp.now(tz=TIMEZONE).date()
            data_age_days = (today - latest_date).days
            if data_age_days > HEALTH_CRITICAL_DATA_AGE_DAYS:
                criticals.append(f"最新天气数据已陈旧 {data_age_days} 天")
            elif data_age_days > HEALTH_WARNING_DATA_AGE_DAYS:
                warnings.append(f"最新天气数据已陈旧 {data_age_days} 天")

        if duplicate_keys > 0:
            criticals.append(f"发现 {duplicate_keys} 组重复 city + date")
    except Exception as error:
        criticals.append(f"MySQL 只读检查失败：{error}")
        logger.exception("健康检查数据库查询失败。")
    finally:
        if engine is not None:
            engine.dispose()

    required_files = {
        "最新原始 JSON": RAW_LATEST_FILE,
        "历史 CSV": HISTORICAL_CSV_FILE,
        "历史 Excel": HISTORICAL_EXCEL_FILE,
        "质量报告": QUALITY_REPORT_FILE,
    }
    for label, file_path in required_files.items():
        if not file_path.is_file():
            criticals.append(f"{label}不存在：{file_path}")

    if QUALITY_REPORT_FILE.is_file():
        try:
            quality_fail_count = read_quality_fail_count()
            if quality_fail_count > 0:
                criticals.append(
                    f"最近质量报告包含 {quality_fail_count} 项 FAIL"
                )
        except Exception as error:
            criticals.append(f"质量报告无法读取：{error}")

    exit_code = 2 if criticals else 1 if warnings else 0
    status_text = {0: "健康", 1: "警告", 2: "严重失败"}[exit_code]

    print(f"\nChile Solar Weather V4 健康状态：{status_text}")
    print(f"MySQL：{'可连接' if not any('MySQL' in item for item in criticals) else '检查失败'}")
    print(
        "最近运行："
        f"{latest_run['status'] if latest_run else '无'}"
        f"（run_id={latest_run['run_id'] if latest_run else '无'}）"
    )
    print(
        "最近成功："
        f"{latest_success or '无'}"
        f"（距今 {success_age_hours:.1f} 小时）"
        if success_age_hours is not None
        else "最近成功：无"
    )
    print(f"weather_daily：{total_rows} 行，重复键 {duplicate_keys} 组")
    print(f"日期范围：{earliest_date or '无'} 至 {latest_date or '无'}")
    print(f"最新数据年龄：{data_age_days if data_age_days is not None else '无'} 天")
    print(f"最近质量报告 FAIL：{quality_fail_count if quality_fail_count is not None else '无法读取'}")

    for message in warnings:
        print(f"警告：{message}")
        logger.warning("健康检查警告：%s", message)
    for message in criticals:
        print(f"严重：{message}")
        logger.error("健康检查严重失败：%s", message)

    logger.info(
        "健康检查结束：状态=%s，退出码=%s，警告=%s，严重=%s。",
        status_text,
        exit_code,
        len(warnings),
        len(criticals),
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
