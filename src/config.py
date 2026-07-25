import os
from pathlib import Path

from dotenv import load_dotenv


# API 与城市配置
API_URL = "https://api.open-meteo.com/v1/forecast"
CITY = "Antofagasta"
LATITUDE = -23.65
LONGITUDE = -70.40
TIMEZONE = "America/Santiago"
REQUEST_TIMEOUT_SECONDS = 30
PAST_DAYS = 30
FORECAST_DAYS = 1
API_MAX_ATTEMPTS = 3
API_BACKOFF_FACTOR_SECONDS = 1.0
RAW_JSON_RETENTION_DAYS = 90

LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
LOCK_STALE_HOURS = 2

HEALTH_WARNING_HOURS = 30
HEALTH_CRITICAL_HOURS = 48
HEALTH_WARNING_DATA_AGE_DAYS = 1
HEALTH_CRITICAL_DATA_AGE_DAYS = 2

DAILY_FIELDS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "sunshine_duration",
    "shortwave_radiation_sum",
    "precipitation_sum",
    "wind_speed_10m_max",
]

# 所有路径都从当前项目根目录推导，因此不依赖启动程序时的工作目录。
PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
load_dotenv(ENV_FILE)

DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CLEAN_DIR = DATA_DIR / "clean"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
LOGS_DIR = PROJECT_DIR / "logs"
SQL_DIR = PROJECT_DIR / "sql"
DOCS_DIR = PROJECT_DIR / "docs"
RUNTIME_DIR = PROJECT_DIR / "runtime"

HISTORICAL_CSV_FILE = CLEAN_DIR / "antofagasta_weather.csv"
HISTORICAL_EXCEL_FILE = CLEAN_DIR / "antofagasta_weather.xlsx"
RAW_LATEST_FILE = RAW_DIR / "antofagasta_raw_latest.json"
QUALITY_REPORT_FILE = OUTPUTS_DIR / "data_quality_report.csv"
LOG_FILE = LOGS_DIR / "pipeline.log"
PIPELINE_LOCK_FILE = RUNTIME_DIR / "pipeline.lock"

# 数据库凭据只从环境变量或 .env 读取，不在源码中保存密码。
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "chile_solar_weather")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

SCHEMA_SQL_FILE = SQL_DIR / "schema.sql"
VIEWS_SQL_FILE = SQL_DIR / "views.sql"
