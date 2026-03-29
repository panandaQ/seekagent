from __future__ import annotations

import logging
import re
from pathlib import Path


def setup_logging(
    log_dir: Path,
    level: str = "INFO",
    console_output: bool = True,
    file_output: bool = True,
) -> None:
    """配置日志系统

    Args:
        log_dir: 日志目录
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console_output: 是否输出到控制台
        file_output: 是否输出到文件
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    # 将字符串级别转换为 logging 常量
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    log_level = level_map.get(level.upper(), logging.INFO)

    # 构建 handlers 列表
    handlers = []
    if file_output:
        log_path = log_dir / "expert_extraction.log"
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    if console_output:
        handlers.append(logging.StreamHandler())

    # 至少要有一个输出
    if not handlers:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
    )


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace("[at]", "@").replace("(at)", "@").replace("#", "@")
    normalized = normalized.replace(" ", "")
    return normalized if "@" in normalized else value
