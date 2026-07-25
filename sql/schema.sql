-- 天气历史主表：city + date 是业务联合唯一键。
CREATE TABLE IF NOT EXISTS weather_daily (
    date DATE NOT NULL,
    city VARCHAR(100) NOT NULL,
    temperature_max_c DECIMAL(6, 2) NULL,
    temperature_min_c DECIMAL(6, 2) NULL,
    sunshine_duration_seconds DECIMAL(12, 2) NULL,
    sunshine_duration_hours DECIMAL(8, 4) NULL,
    shortwave_radiation_mj_m2 DECIMAL(10, 2) NULL,
    precipitation_mm DECIMAL(10, 2) NULL,
    wind_speed_max_kmh DECIMAL(10, 2) NULL,
    retrieved_at DATETIME(6) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT uq_weather_daily_city_date UNIQUE (city, date),
    INDEX idx_weather_daily_date (date),
    INDEX idx_weather_daily_city (city)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

-- 每次管道运行一条记录，最终状态为 SUCCESS 或 FAILED。
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    started_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    status ENUM('RUNNING', 'SUCCESS', 'FAILED') NOT NULL,
    api_rows INT UNSIGNED NOT NULL DEFAULT 0,
    historical_rows_before INT UNSIGNED NOT NULL DEFAULT 0,
    inserted_rows INT UNSIGNED NOT NULL DEFAULT 0,
    updated_rows INT UNSIGNED NOT NULL DEFAULT 0,
    final_database_rows INT UNSIGNED NOT NULL DEFAULT 0,
    failed_quality_checks INT UNSIGNED NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    PRIMARY KEY (run_id),
    INDEX idx_pipeline_runs_started_at (started_at),
    INDEX idx_pipeline_runs_status (status)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;
