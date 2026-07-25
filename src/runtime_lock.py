import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def get_lock_age_hours(lock_file: Path) -> float:
    """根据锁文件修改时间计算存在小时数。"""
    modified_at = datetime.fromtimestamp(
        lock_file.stat().st_mtime,
        tz=timezone.utc,
    )
    return (datetime.now(timezone.utc) - modified_at).total_seconds() / 3600


def acquire_pipeline_lock(
    lock_file: Path,
    stale_hours: float,
    logger,
) -> str:
    """原子创建锁文件；陈旧锁超过阈值时清理后重试一次。"""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    token = str(uuid.uuid4())
    payload = {
        "token": token,
        "pid": os.getpid(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    for attempt in range(2):
        try:
            descriptor = os.open(
                lock_file,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as error:
            try:
                lock_age_hours = get_lock_age_hours(lock_file)
            except OSError:
                lock_age_hours = 0

            if lock_age_hours >= stale_hours and attempt == 0:
                try:
                    lock_file.unlink()
                    logger.warning(
                        "已清理陈旧管道锁：%s，存在 %.2f 小时。",
                        lock_file,
                        lock_age_hours,
                    )
                    continue
                except FileNotFoundError:
                    continue

            raise RuntimeError(
                "检测到另一个管道实例仍在运行。"
                f"锁文件：{lock_file.resolve()}，存在约 {lock_age_hours:.2f} 小时。"
            ) from error

        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        logger.info("已获得单实例运行锁：%s", lock_file.resolve())
        return token

    raise RuntimeError("无法获得管道运行锁。")


def release_pipeline_lock(
    lock_file: Path,
    token: str,
    logger,
) -> None:
    """只删除由当前进程创建的锁，避免误删其他实例的新锁。"""
    if not lock_file.exists():
        return

    try:
        payload = json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("无法读取锁文件，保留以避免误删：%s", lock_file)
        return

    if payload.get("token") != token:
        logger.warning("锁令牌已变化，当前进程不会删除该锁：%s", lock_file)
        return

    try:
        lock_file.unlink()
        logger.info("已释放单实例运行锁：%s", lock_file.resolve())
    except FileNotFoundError:
        pass
